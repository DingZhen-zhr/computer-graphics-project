"""跑评测：python -m benchmarks.run [--tasks phone_stand flange l_bracket] [--config config.toml]

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

from benchmarks.sim_user import SimUser
from cad_agent.checks.spec import MANDATORY_IDS, CheckSpecError, parse_checks
from cad_agent.cli import build_agent
from cad_agent.config import ConfigError, load_config
from cad_agent.llm.factory import make_llm
from cad_agent.notebook import RenderedNotebook
from cad_agent.sandbox import execute

TASKS_DIR = Path(__file__).parent / "tasks"
ALL_TASKS = ["phone_stand", "flange", "l_bracket"]
DEFAULT_MAX_USER_TURNS = 12
LENGTH_TYPES = ("bbox", "distance")  # “尺寸偏差”只统计以 mm 为单位的长度类检查
TABLE_HEADER = "任务 | 成功 | 修复次数 | 耗时(s) | 模型调用 | token | 最大尺寸偏差"


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


def _converse(agent, sim_user: SimUser, first_message: str, max_turns: int, totals: dict):
    """用 first_message 开头，和模拟用户来回对话直到交付；超过 max_turns 仍未交付返回 None。"""
    message = first_message
    for i in range(max_turns):
        turn = agent.handle_user(message)
        totals["user_turns"] += 1
        totals["repairs"] += turn.repairs
        totals["llm_calls"] += turn.llm_calls
        totals["tokens"] += turn.tokens
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
    totals = {"repairs": 0, "llm_calls": 0, "tokens": 0, "user_turns": 0}
    max_turns = int(task.get("max_user_turns", DEFAULT_MAX_USER_TURNS))
    names = stage_names(task)
    messages = [task["initial"], *task.get("modifications", [])]
    stages: list[dict] = []
    for index, (stage, message) in enumerate(zip(names, messages)):
        turn = _converse(agent, sim_user, message, max_turns, totals)
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
        "duration_s": round(time.monotonic() - started, 2),
        "sim_llm_calls": getattr(sim_user, "calls", 0), "sim_tokens": getattr(sim_user, "tokens", 0),
    }


# ---------------------------------------------------------------- 汇总


def max_dimension_deviation(result: dict) -> float | None:
    """所有长度类验收（bbox、distance）里偏差绝对值的最大值，单位 mm；没有就是 None。"""
    devs = [abs(a["deviation"]) for s in result["stages"] for a in s["acceptance"]
            if a.get("type") in LENGTH_TYPES and a["deviation"] is not None]
    return max(devs) if devs else None


def _num(v: float | None) -> str:
    return "-" if v is None else f"{v:.4f}".rstrip("0").rstrip(".")


def render_results_md(results: list[dict]) -> str:
    lines = ["# 评测结果", "", f"| {TABLE_HEADER} |", "|---|---|---|---|---|---|---|"]
    for r in results:
        dev = max_dimension_deviation(r)
        lines.append(f"| {r['task']} | {'是' if r['success'] else '否'} | {r['repairs']} | {r['duration_s']:.1f} | "
                     f"{r['llm_calls']} | {r['tokens']} | {'-' if dev is None else f'{dev:.3g} mm'} |")
    for r in results:
        lines += ["", f"## {r['task']}", ""]
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
                   results_dir: Path, *, run_job: Callable = execute.run_job, print_fn: Callable[..., None] = print) -> list[dict]:
    """依次跑各个任务；某个任务意外崩溃只记一条失败，不影响其余任务。每跑完一个就写一次结果文件。"""
    results_dir = Path(results_dir)
    results_dir.mkdir(parents=True, exist_ok=True)
    results: list[dict] = []
    for name in names:
        task = load_task(name)
        print_fn(f"== 开始任务 {name} ==")
        try:
            result = run_task(task, make_agent, make_sim_user(task["hidden_spec"]), results_dir / name, run_job=run_job)
        except Exception as e:  # noqa: BLE001 - 单个任务崩溃不能让整个评测白跑，原因记进结果里
            result = {"task": name, "success": False, "stages": [], "repairs": 0, "duration_s": 0.0, "llm_calls": 0, "tokens": 0,
                      "user_turns": 0, "error": f"{type(e).__name__}: {e}"}
        results.append(result)
        print_fn(f"== 任务 {name}：{'成功' if result['success'] else '没有成功'} ==")
        (results_dir / "results.json").write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")
        (results_dir / "results.md").write_text(render_results_md(results), encoding="utf-8")
    return results


def main(argv: list[str] | None = None, print_fn: Callable[..., None] = print) -> int:
    parser = argparse.ArgumentParser(prog="python -m benchmarks.run", description="跑 CAD 建模智能体的评测")
    parser.add_argument("--tasks", nargs="+", default=ALL_TASKS, help=f"要跑的任务，默认全部：{' '.join(ALL_TASKS)}")
    parser.add_argument("--config", default="config.toml", help="配置文件路径，默认 config.toml")
    parser.add_argument("--out", default=str(Path(__file__).parent / "results"), help="结果目录，默认 benchmarks/results")
    args = parser.parse_args(argv)

    try:
        for name in args.tasks:
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
    results = run_benchmarks(args.tasks, make_agent, make_sim_user, results_dir, print_fn=print_fn)
    print_fn("\n" + render_results_md(results))
    print_fn(f"结果已保存到 {results_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
