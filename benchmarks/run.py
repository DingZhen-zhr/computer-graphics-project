"""跑评测：python -m benchmarks.run [--set dev|holdout|all] [--repeat N] [--tasks 任务名 ...] [--config config.toml]

每个任务：模拟用户（一个手里拿着“隐藏需求”的大模型）和智能体对话，从一句话需求走到交付，再走完各条修改请求；
每次交付后，用任务文件里人工写的验收检查，对交付版本的 model.py 重新测量。
"""

from __future__ import annotations

import argparse
import json
import time
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from typing import Callable

import yaml

from benchmarks.compare import COST_FMT, SECONDS_FMT, CALLS_FMT, TOKEN_FMT, fmt, success_text, task_means, total_row
from benchmarks.sim_user import SimUser
from cad_agent.checks.spec import MANDATORY_IDS, CheckSpecError, parse_checks
from cad_agent.cli import build_agent
from cad_agent.config import ConfigError, load_config
from cad_agent.llm.factory import make_llm
from cad_agent.notebook import RenderedNotebook
from cad_agent.sandbox import execute

TASKS_DIR = Path(__file__).parent / "tasks"
ALL_TASKS = ["phone_stand", "flange", "l_bracket"]
HOLDOUT_TASKS: list[str] = ["enclosure", "stepped_shaft"]  # 留出任务：只用来测，不许为它们调提示词
TASK_SETS: dict[str, list[str]] = {"dev": ALL_TASKS, "holdout": HOLDOUT_TASKS, "all": ALL_TASKS + HOLDOUT_TASKS}
DEFAULT_MAX_USER_TURNS = 12
LENGTH_TYPES = ("bbox", "distance")  # “尺寸偏差”只统计以 mm 为单位的长度类检查
TABLE_HEADER = "任务 | 成功 | 修复次数 | 耗时(s) | 模型调用 | token | 最大尺寸偏差"
SUMMARY_HEADER = "| 任务 | 成功 | 平均费用(元) | 平均耗时(s) | 平均模型调用 | 平均输入 | 其中命中缓存 | 平均输出 | 其中思考 |"


# ---------------------------------------------------------------- 任务文件


def stage_names(task: dict) -> list[str]:
    return ["after_initial"] + [f"after_mod_{i}" for i in range(1, len(task.get("modifications", [])) + 1)]


def load_task(name_or_path: str | Path) -> dict:
    """读入并校验一个任务文件。参数是任务名（benchmarks/tasks 下的 <名字>.yaml）或文件路径。"""
    path = Path(name_or_path)
    if not path.suffix:
        path = TASKS_DIR / f"{name_or_path}.yaml"
    if not path.is_file():
        raise ValueError(f"没有这个任务：{name_or_path}（可用：{'、'.join(ALL_TASKS)}）")
    task = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(task, dict):
        raise ValueError(f"任务文件 {path.name} 的格式不对")
    for key in ("id", "initial", "hidden_spec", "acceptance"):
        if not task.get(key):
            raise ValueError(f"任务文件 {path.name} 缺少 {key}")
    if task["id"] != path.stem:
        raise ValueError(f"任务文件 {path.name} 里的 id（{task['id']}）要和文件名（{path.stem}）一致")
    task.setdefault("modifications", [])
    task.setdefault("max_user_turns", DEFAULT_MAX_USER_TURNS)
    expected_stages = stage_names(task)
    if list(task["acceptance"]) != expected_stages:
        raise ValueError(f"任务 {task['id']} 的 acceptance 必须恰好有这几组（按顺序）：{'、'.join(expected_stages)}，现在是 {list(task['acceptance'])}")
    for stage, raw in task["acceptance"].items():
        try:
            parse_checks(raw, set())
        except CheckSpecError as e:
            raise ValueError(f"任务 {task['id']} 的 {stage} 验收检查写得不对：{e}") from e
    return task


# ---------------------------------------------------------------- 跑一个任务


def _converse(agent, sim_user: SimUser, first_message: str, max_turns: int, totals: dict, costs: list):
    """用 first_message 开头，和模拟用户来回对话直到交付；超过 max_turns 仍未交付返回 None。"""
    message = first_message
    for i in range(max_turns):
        turn = agent.handle_user(message)
        totals["user_turns"] += 1
        totals["repairs"] += turn.repairs
        totals["llm_calls"] += turn.llm_calls
        totals["tokens"] += turn.tokens
        for key in ("prompt_tokens", "completion_tokens", "cached_tokens", "reasoning_tokens"):
            totals[key] += getattr(turn, key)
        if turn.llm_calls:  # 没有成功调用的轮没有费用可言
            costs.append(turn.cost)
        if turn.kind == "delivered":
            return turn
        if i < max_turns - 1:
            message = sim_user.reply(turn.text, turn.kind)
    return None


def _evaluate(stage: str, turn, checks_raw: list[dict], run_job: Callable, timeout_s: float) -> dict:
    """对交付版本的 model.py 单独跑一遍验收检查（参数集合为空，期望值都是数字）。"""
    text = (turn.version_dir / "model.py").read_text(encoding="utf-8")
    result = run_job(RenderedNotebook(text=text, cell_lines={}), checks_raw, set(), timeout_s=timeout_s)
    by_id = {c.id: c for c in result.checks}
    entries = []
    for raw in checks_raw:
        r = by_id.get(raw["id"])
        measured = r.measured if r else None
        expected = r.expected if r else None
        entries.append({
            "id": raw["id"], "type": raw["type"], "expected": expected, "measured": measured,
            "deviation": measured - expected if measured is not None and expected is not None else None,
            "passed": bool(r and r.passed), "detail": r.detail if r else "",
        })
    mandatory_ok = all(by_id[i].passed for i in MANDATORY_IDS if i in by_id)
    return {"stage": stage, "delivered": True, "version": turn.version_dir.name, "acceptance": entries,
            "mandatory_ok": mandatory_ok, "error": result.error}


def run_task(task: dict, make_agent: Callable[[Path], object], sim_user: SimUser, out_dir: Path, *,
             run_job: Callable = execute.run_job, acceptance_timeout_s: float = 60) -> dict:
    """跑一个任务：初始需求 + 各条修改请求，每次交付后做验收。

    某个阶段对话超过 max_user_turns 仍未交付时，该阶段记为失败，后面的阶段跳过。
    """
    started = time.monotonic()
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    agent = make_agent(out_dir)
    totals = {"repairs": 0, "llm_calls": 0, "tokens": 0, "user_turns": 0, "prompt_tokens": 0, "completion_tokens": 0,
              "cached_tokens": 0, "reasoning_tokens": 0}
    costs: list[float | None] = []
    max_turns = int(task.get("max_user_turns", DEFAULT_MAX_USER_TURNS))
    names = stage_names(task)
    messages = [task["initial"], *task.get("modifications", [])]
    stages: list[dict] = []
    for index, (stage, message) in enumerate(zip(names, messages)):
        if index > 0:  # 修改阶段：先让模拟用户知道这条修改，再发出修改请求
            sim_user.add_change(message)
        turn =_converse(agent, sim_user, message, max_turns, totals, costs)
        if turn is None:
            reason = f"对话 {max_turns} 轮仍未交付"
            stages.append({"stage": stage, "delivered": False, "acceptance": [], "reason": reason})
            stages += [{"stage": later, "delivered": False, "acceptance": [], "skipped": True} for later in names[index + 1 :]]
            break
        stages.append(_evaluate(stage, turn, task["acceptance"][stage], run_job, acceptance_timeout_s))
    success = len(stages) == len(names) and all(
        s["delivered"] and s["mandatory_ok"] and not s["error"] and all(a["passed"] for a in s["acceptance"]) for s in stages
    )
    return {
        "task": task["id"], "success": success, "stages": stages, **totals,
        "cost": sum(costs) if costs and all(c is not None for c in costs) else None,
        "duration_s": round(time.monotonic() - started, 2),
        "sim_llm_calls": getattr(sim_user, "calls", 0), "sim_tokens": getattr(sim_user, "tokens", 0),
        "sim_cost": getattr(sim_user, "cost", None),
    }


# ---------------------------------------------------------------- 汇总


def max_dimension_deviation(result: dict) -> float | None:
    """所有长度类验收（bbox、distance）里偏差绝对值的最大值，单位 mm；没有就是 None。"""
    devs = [abs(a["deviation"]) for s in result["stages"] for a in s["acceptance"]
            if a.get("type") in LENGTH_TYPES and a["deviation"] is not None]
    return max(devs) if devs else None


def _num(v: float | None) -> str:
    return "-" if v is None else f"{v:.4f}".rstrip("0").rstrip(".")


def render_summary_md(results: list[dict]) -> str:
    """按任务汇总的表：成功次数 / 遍数，以及各项平均值；最后一行"合计"是各任务平均值相加。缺字段的格显示 -。"""
    means = task_means(results)
    lines = [SUMMARY_HEADER, "|---|---|---|---|---|---|---|---|---|"]
    for label, m in [*means.items(), ("合计", total_row(means))]:
        cells = [success_text(m), fmt(m["cost"], COST_FMT), fmt(m["duration_s"], SECONDS_FMT), fmt(m["llm_calls"], CALLS_FMT)]
        cells += [fmt(m[key], TOKEN_FMT) for key in ("prompt_tokens", "cached_tokens", "completion_tokens", "reasoning_tokens")]
        lines.append(f"| {label} | " + " | ".join(cells) + " |")
    return "\n".join(lines) + "\n"


def _label(result: dict) -> str:
    return f"{result['task']}#{result['run']}" if "run" in result else result["task"]


def render_results_md(results: list[dict]) -> str:
    lines = ["# 评测结果", "", f"| {TABLE_HEADER} |", "|---|---|---|---|---|---|---|"]
    for r in results:
        dev = max_dimension_deviation(r)
        lines.append(f"| {_label(r)} | {'是' if r['success'] else '否'} | {r['repairs']} | {r['duration_s']:.1f} | "
                     f"{r['llm_calls']} | {r['tokens']} | {'-' if dev is None else f'{dev:.3g} mm'} |")
    for r in results:
        lines += ["", f"## {_label(r)}", ""]
        if r.get("error"):
            lines += [f"运行中断：{r['error']}", ""]
        for s in r["stages"]:
            state = f"已交付 {s.get('version', '')}" if s["delivered"] else ("跳过" if s.get("skipped") else f"未交付（{s.get('reason', '')}）")
            lines += [f"### {s['stage']}（{state}）", ""]
            if s.get("error"):
                lines += [f"验收运行出错：{s['error'].get('message', '')}", ""]
            if s["acceptance"]:
                lines += ["| 验收项 | 期望 | 实测 | 偏差 | 结果 |", "|---|---|---|---|---|"]
                lines += [f"| {a['id']} | {_num(a['expected'])} | {_num(a['measured'])} | {_num(a['deviation'])} | {'通过' if a['passed'] else '没通过'} |"
                          for a in s["acceptance"]]
                lines.append("")
    return "\n".join(lines) + "\n"


def run_benchmarks(names: list[str], make_agent: Callable[[Path], object], make_sim_user: Callable[[str], SimUser],
                   results_dir: Path, *, run_job: Callable = execute.run_job, print_fn: Callable[..., None] = print,
                   repeat: int = 1) -> list[dict]:
    """依次跑各个任务，每个任务跑 repeat 遍；某一遍意外崩溃只记一条失败，不影响其余的。每跑完一遍就写一次结果文件。

    repeat == 1：目录是 results_dir/<任务名>，结果里没有 "run"（和第一版一样）。
    repeat > 1：目录是 results_dir/<任务名>-<r>，结果里有 "run": r（r 从 1 开始）。
    results.md = 汇总表 + 各遍的明细。
    """
    results_dir = Path(results_dir)
    results_dir.mkdir(parents=True, exist_ok=True)
    results: list[dict] = []
    for name in names:
        task = load_task(name)
        for r in range(1, repeat + 1):
            label = name if repeat == 1 else f"{name}#{r}"
            print_fn(f"== 开始任务 {label} ==")
            out_dir = results_dir / (name if repeat == 1 else f"{name}-{r}")
            try:
                result = run_task(task, make_agent, make_sim_user(task["hidden_spec"]), out_dir, run_job=run_job)
            except Exception as e:  # noqa: BLE001 - 单个任务崩溃不能让整个评测白跑，原因记进结果里
                result = {"task": name, "success": False, "stages": [], "repairs": 0, "duration_s": 0.0, "llm_calls": 0, "tokens": 0,
                          "user_turns": 0, "error": f"{type(e).__name__}: {e}"}
            if repeat > 1:
                result["run"] = r
            results.append(result)
            print_fn(f"== 任务 {label}：{'成功' if result['success'] else '没有成功'} ==")
            (results_dir / "results.json").write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")
            (results_dir / "results.md").write_text(render_summary_md(results) + "\n" + render_results_md(results), encoding="utf-8")
    return results


def main(argv: list[str] | None = None, print_fn: Callable[..., None] = print) -> int:
    parser = argparse.ArgumentParser(prog="python -m benchmarks.run", description="跑 CAD 建模智能体的评测")
    parser.add_argument("--set", dest="task_set", choices=list(TASK_SETS), default="dev",
                        help="跑哪一组任务：dev（开发任务，默认）、holdout（留出任务）、all（两组都跑）")
    parser.add_argument("--repeat", type=int, default=1, help="每个任务跑几遍，默认 1")
    parser.add_argument("--tasks", nargs="+", default=[], help="直接指定要跑的任务；给了就以它为准，不看 --set")
    parser.add_argument("--config", default="config.toml", help="配置文件路径，默认 config.toml")
    parser.add_argument("--out", default=str(Path(__file__).parent / "results"), help="结果目录，默认 benchmarks/results")
    args = parser.parse_args(argv)

    if args.repeat < 1:
        print_fn("repeat 至少是 1")
        return 1
    names: list[str] = args.tasks or TASK_SETS[args.task_set]
    if not names:
        print_fn("这一组还没有任务")
        return 1
    try:
        for name in names:
            load_task(name)
        config = load_config(Path(args.config))
        key = config.api_key()
    except (ValueError, ConfigError) as e:
        print_fn(str(e))
        return 1

    def make_agent(root: Path):
        return build_agent(replace(config, sessions_dir=root / "sessions"))[0]

    def make_sim_user(hidden_spec: str) -> SimUser:
        return SimUser(make_llm(config, "base", key), hidden_spec)

    results_dir = Path(args.out) / datetime.now().strftime("%Y%m%d-%H%M%S")
    results = run_benchmarks(names, make_agent, make_sim_user, results_dir, print_fn=print_fn, repeat=args.repeat)
    print_fn("\n" + render_summary_md(results) + "\n" + render_results_md(results))
    print_fn(f"结果已保存到 {results_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
