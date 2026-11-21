"""跑评测：python -m benchmarks.run [--set 组] [--tasks 任务名 ...] [--config config.toml] [--label 标签 --cap 元] [--cases on|off]
每个任务：模拟用户（拿着"隐藏需求"的大模型）和智能体对话，从一句话需求走到交付，再走完各条修改请求；每次交付后用任务文件里的验收重新测量。
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

from benchmarks.report import (LENGTH_TYPES, SKIPPED_TEXT, SUMMARY_HEADER, TABLE_HEADER, is_skipped,  # noqa: F401 - 测试从这里导入
                               max_dimension_deviation, render_results_md, render_summary_md)
from benchmarks.sim_user import SimUser
from benchmarks.assembly_accept import AcceptSpecError, validate_entries
from benchmarks.ledger import BudgetExceeded
from benchmarks.assembly_accept import evaluate as assembly_evaluate
from cad_agent.checks.spec import MANDATORY_IDS, CheckSpecError, parse_checks
from cad_agent.cli import build_agent
from cad_agent.config import ConfigError, load_config
from cad_agent.llm.factory import make_llm
from cad_agent.notebook import RenderedNotebook
from cad_agent.sandbox import execute

from benchmarks.task_sets import (ALL_TASKS, HARD_TASKS, HOLDOUT_TASKS, MEDIUM_TASKS, MULTI_TASKS, TASK_SETS,  # noqa: F401
                                  V3_DEV, V3_HOLDOUT)

TASKS_DIR = Path(__file__).parent / "tasks"
MULTI_TYPES = ("joint", "at_pose")
DEFAULT_MAX_USER_TURNS = 12


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
            parse_checks([c for c in raw if c.get("type") not in MULTI_TYPES], set())
            validate_entries(raw)
            for c in raw:
                if c.get("type") == "at_pose":
                    parse_checks(c["checks"], set())
        except (CheckSpecError, AcceptSpecError) as e:
            raise ValueError(f"任务 {task['id']} 的 {stage} 验收检查写得不对：{e}") from e
    return task


# ---------------------------------------------------------------- 跑一个任务


def _converse(agent, sim_user: SimUser, first_message: str, max_turns: int, totals: dict, costs: list):
    """用 first_message 开头，和模拟用户来回对话直到交付；超过 max_turns 仍未交付返回 None。"""
    message = first_message
    for i in range(max_turns):
        turn = agent.handle_user(message)
        totals["user_turns"] += 1
        totals["questions"] += turn.kind == "question"
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
    """对交付版本的 model.py 单独跑一遍验收检查（参数集合为空，期望值都是数字）。多零件的版本交给 assembly_accept。"""
    if (turn.version_dir / "assembly.json").is_file():
        return _evaluate_multi(stage, turn, checks_raw)
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


def _evaluate_multi(stage: str, turn, checks_raw: list[dict]) -> dict:
    res = assembly_evaluate(turn.version_dir, checks_raw)
    entries = [{"id": e["id"], "type": e["type"], "expected": e.get("expected"), "measured": e.get("measured"),
                "deviation": e["measured"] - e["expected"] if e.get("measured") is not None and e.get("expected") is not None else None,
                "passed": bool(e["passed"]), "detail": e.get("detail", "")} for e in res["entries"]]
    if res["error"] is not None:   # 验收本身没跑成：每一条都算不通过
        entries = [{"id": c["id"], "type": c["type"], "expected": None, "measured": None, "deviation": None, "passed": False,
                    "detail": res["error"]["message"]} for c in checks_raw]
    return {"stage": stage, "delivered": True, "version": turn.version_dir.name, "acceptance": entries,
            "mandatory_ok": res["mandatory_ok"], "error": res["error"]}


def run_task(task: dict, make_agent: Callable[[Path], object], sim_user: SimUser, out_dir: Path, *,
             run_job: Callable = execute.run_job, acceptance_timeout_s: float = 60) -> dict:
    """跑一个任务：初始需求 + 各条修改请求，每次交付后做验收。

    某个阶段对话超过 max_user_turns 仍未交付时，该阶段记为失败，后面的阶段跳过。
    """
    started = time.monotonic()
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    agent = make_agent(out_dir)
    totals = {"repairs": 0, "llm_calls": 0, "tokens": 0, "user_turns": 0, "questions": 0, "prompt_tokens": 0, "completion_tokens": 0,
              "cached_tokens": 0, "reasoning_tokens": 0}
    costs: list[float | None] = []
    max_turns = int(task.get("max_user_turns", DEFAULT_MAX_USER_TURNS))
    names = stage_names(task)
    messages = [task["initial"], *task.get("modifications", [])]
    stages: list[dict] = []
    stopped = False
    for index, (stage, message) in enumerate(zip(names, messages)):
        if index > 0:  # 修改阶段：先让模拟用户知道这条修改，再发出修改请求
            sim_user.add_change(message)
        try:
            turn = _converse(agent, sim_user, message, max_turns, totals, costs)
        except BudgetExceeded:   # 到了花费上限：立刻停，已有的阶段结果照常留下（3.0 计划 4）
            stopped = True
            stages.append({"stage": stage, "delivered": False, "acceptance": [], "reason": "到了花费上限"})
            break
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
        "sim_cost": getattr(sim_user, "cost", None), **({"stopped_for_cap": True} if stopped else {}),
    }


def run_benchmarks(names: list[str], make_agent: Callable[[Path], object], make_sim_user: Callable[[str], SimUser],
                   results_dir: Path, *, run_job: Callable = execute.run_job, print_fn: Callable[..., None] = print,
                   repeat: int = 1, budget: float | None = None) -> list[dict]:
    """依次跑各个任务，每个任务跑 repeat 遍；某一遍意外崩溃只记一条失败，不影响其余的。每跑完一遍就写一次结果文件。

    repeat == 1：目录是 results_dir/<任务名>，结果里没有 "run"（和第一版一样）。
    repeat > 1：目录是 results_dir/<任务名>-<r>，结果里有 "run": r（r 从 1 开始）。
    results.md = 汇总表 + 各遍的明细。
    budget（元）：每跑完一遍，把这一遍的费用（智能体的加上模拟用户的）累加；累计达到上限后不再开始新的一遍，
    没跑的记成 {"task", "skipped_for_budget": true}，结果文件照常写出，最后打印一行已花费和上限。
    """
    results_dir = Path(results_dir)
    results_dir.mkdir(parents=True, exist_ok=True)
    results: list[dict] = []
    spent = 0.0
    for name in names:
        task = load_task(name)
        for r in range(1, repeat + 1):
            label = name if repeat == 1 else f"{name}#{r}"
            if budget is not None and spent >= budget:
                results.append({"task": name, "skipped_for_budget": True, **({"run": r} if repeat > 1 else {})})
                print_fn(f"== 任务 {label}：{SKIPPED_TEXT} ==")
                _write_results(results_dir, results)
                continue
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
            if budget is not None:
                spent += _run_cost(result, label, print_fn)
            _write_results(results_dir, results)
    if budget is not None:
        print_fn(f"已花费 ¥{spent:.2f}，上限 ¥{budget:.2f}")
    return results


def _run_cost(result: dict, label: str, print_fn: Callable[..., None]) -> float:
    """这一遍的费用：智能体的加上模拟用户的。算不出来（某次调用没有用量）的部分按 0 计，并提示一句。"""
    parts = [result.get("cost"), result.get("sim_cost")]
    if any(p is None for p in parts):
        print_fn(f"注意：任务 {label} 有一部分调用没有算出费用，按 0 计入花费上限")
    return sum(p for p in parts if p is not None)


def _write_results(results_dir: Path, results: list[dict]) -> None:
    (results_dir / "results.json").write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")
    (results_dir / "results.md").write_text(render_summary_md(results) + "\n" + render_results_md(results), encoding="utf-8")


def main(argv: list[str] | None = None, print_fn: Callable[..., None] = print) -> int:
    parser = argparse.ArgumentParser(prog="python -m benchmarks.run", description="跑 CAD 建模智能体的评测")
    parser.add_argument("--set", dest="task_set", choices=list(TASK_SETS), default="dev", help="跑哪一组任务，默认 dev")
    parser.add_argument("--label", help="3.0：这一遍的标签（如 round1）；给了就按账本计价、到上限立刻停")
    parser.add_argument("--cap", type=float, default=20, help="3.0：账本的花费上限（元），所有标签共用，默认 20")
    parser.add_argument("--allow-peak", action="store_true", help="3.0：允许在高峰时段跑（默认只在空闲时段跑）")
    parser.add_argument("--repeat", type=int, default=1, help="每个任务跑几遍，默认 1")
    parser.add_argument("--tasks", nargs="+", default=[], help="直接指定要跑的任务；给了就以它为准，不看 --set")
    parser.add_argument("--config", default="config.toml", help="配置文件路径，默认 config.toml")
    parser.add_argument("--out", default=str(Path(__file__).parent / "results"), help="结果目录，默认 benchmarks/results")
    parser.add_argument("--budget", type=float, default=None, metavar="元",
                        help="花费上限（元）：累计到这个数就不再开始新任务；必须先在配置里填价目表")
    parser.add_argument("--cases", choices=("on", "off"), default="on", help="规划时用不用案例库，默认 on；off 用来做对照")
    args = parser.parse_args(argv)

    if args.repeat < 1:
        print_fn("repeat 至少是 1")
        return 1
    if args.label and args.repeat > 1:
        print_fn("用 --label 记账时每个任务只跑一遍，不能同时给 --repeat；要多跑几遍就换个标签再跑")
        return 1
    names: list[str] = args.tasks or TASK_SETS[args.task_set]
    if not names:
        print_fn("这一组还没有任务")
        return 1
    try:
        for name in names:
            load_task(name)
        config = load_config(Path(args.config))
        if args.label:
            from benchmarks.metered_run import main_metered
            return main_metered(args, config, names, print_fn)
        key = config.api_key()
    except (ValueError, ConfigError) as e:
        print_fn(str(e))
        return 1
    if args.budget is not None:
        if config.pricing is None:
            print_fn("用 --budget 之前，请先在配置文件的 [llm.pricing] 里照模型服务的价目页填好价目表，否则算不出花了多少钱")
            return 2
        if args.budget <= 0:
            print_fn(f"--budget 要大于 0，收到 {args.budget:g}")
            return 2
    if args.cases == "off":
        config = replace(config, gates=replace(config.gates, cases=False))

    def make_agent(root: Path):
        return build_agent(replace(config, sessions_dir=root / "sessions"))[0]

    def make_sim_user(hidden_spec: str) -> SimUser:
        return SimUser(make_llm(config, "base", key), hidden_spec)

    results_dir = Path(args.out) / datetime.now().strftime("%Y%m%d-%H%M%S")
    results = run_benchmarks(names, make_agent, make_sim_user, results_dir, print_fn=print_fn, repeat=args.repeat, budget=args.budget)
    print_fn("\n" + render_summary_md(results) + "\n" + render_results_md(results))
    print_fn(f"结果已保存到 {results_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
