"""按账本跑评测（3.0 计划 4 Task 1）：开跑前检查账本、两段价格、是不是空闲时段；每次调用后记账，到上限当前任务立刻停。

python -m benchmarks.run --config config.toml --set v3all --label round1 --cap 20
"""

from __future__ import annotations

import os
from dataclasses import replace
from datetime import datetime
from pathlib import Path
from typing import Callable

from benchmarks.ledger import LEDGER, BudgetExceeded, Ledger, LedgerError, TaskCapExceeded, metered
from benchmarks.report import render_results_md, render_summary_md
from benchmarks.report_v3 import render_v3_md
from benchmarks.run import _write_results, load_task, run_task
from benchmarks.sim_user import SimUser
from cad_agent.config import OFFPEAK_MISSING, Config, ConfigError

BLANK = {"success": False, "stages": [], "repairs": 0, "duration_s": 0.0, "llm_calls": 0, "tokens": 0, "user_turns": 0}
NO_KEY = "没有找到 DeepSeek 的 API key：请在 Datum 的设置里填好（存进系统钥匙串），或者设置环境变量 DEEPSEEK_API_KEY。"


def find_key(config: Config) -> str | None:
    """先环境变量，后 Datum 设置里存进钥匙串的 key。不打印、不写进任何文件。"""
    from cad_agent.keystore import get_key

    return os.environ.get(config.api_key_env, "").strip() or get_key("deepseek", config.api_key_env)


def check_ready(config: Config, ledger_path: Path, cap: float, allow_peak: bool, now: datetime) -> tuple[Ledger | None, str | None]:
    """开跑前的三道检查。返回 (账本, 拒绝的原因)。"""
    try:
        ledger = Ledger.load(ledger_path, cap)
    except LedgerError as e:
        return None, str(e)
    try:
        config.price_at(now)
    except ConfigError:
        return None, OFFPEAK_MISSING
    if not allow_peak and not config.is_offpeak(now):
        o = config.offpeak
        return None, f"现在不在空闲时段（{o.start}–{o.end}），先不跑。要在高峰时段跑，加 --allow-peak。"
    if ledger.remaining() <= 0:
        return None, f"账本里已经花了 ¥{ledger.spent:.2f}，到了上限 ¥{cap:.2f}，不能再跑。"
    return ledger, None


def run_metered(names: list[str], *, config: Config, label: str, cap: float, allow_peak: bool, results_dir: Path,
                make_agent: Callable, make_sim_user: Callable, run_task_fn: Callable = run_task,
                print_fn: Callable[..., None] = print, now: Callable[[], datetime] = datetime.now,
                ledger_path: Path = LEDGER, task_cap: float | None = None) -> list[dict] | None:
    """task_cap（元）：一个任务（智能体加模拟用户）花到这个数就停下这个任务，接着跑下一个；None 表示不设。

    make_agent(root, wrap) / make_sim_user(hidden_spec, wrap)：wrap(llm, who) 返回记账的模型。拒绝开跑时返回 None。"""
    ledger, why = check_ready(config, ledger_path, cap, allow_peak, now())
    if why:
        print_fn(why)
        return None
    results_dir = Path(results_dir)
    results_dir.mkdir(parents=True, exist_ok=True)
    results: list[dict] = []
    stop = False
    for name in names:
        if stop:
            results.append({"task": name, "skipped_for_cap": True})
            continue
        if not allow_peak and not config.is_offpeak(now()):
            results.append({"task": name, "skipped_for_offpeak": True})
            print_fn(f"== 任务 {name}：空闲时段已经结束，不再开始 ==")
            continue
        task = load_task(name)
        wrap = lambda llm, who, _t=name: metered(llm, ledger, config, label, _t, who, now, task_cap)   # noqa: E731
        print_fn(f"== 开始任务 {name} ==")
        try:
            result = run_task_fn(task, lambda root: make_agent(root, wrap), make_sim_user(task["hidden_spec"], wrap), results_dir / name)
        except TaskCapExceeded:
            result = {"task": name, **BLANK, "stopped_for_task_cap": True}
        except BudgetExceeded:
            result = {"task": name, **BLANK, "stopped_for_cap": True}
        except Exception as e:  # noqa: BLE001 - 一个任务出错（包括模拟用户调用出错）不影响其余任务，原因记下来
            result = {"task": name, **BLANK, "error": f"{type(e).__name__}: {e}"}
        results.append(result)
        stop = bool(result.get("stopped_for_cap")) or ledger.remaining() <= 0
        print_fn(f"== 任务 {name}：{'成功' if result.get('success') else '没有成功'} ==")
        _write_results(results_dir, results)
    _write_results(results_dir, results)
    (results_dir / "results-v3.md").write_text(render_v3_md(results), encoding="utf-8")
    print_fn(f"已花费 ¥{ledger.spent:.2f}，上限 ¥{ledger.cap:.2f}，剩 ¥{ledger.remaining():.2f}")
    return results


def main_metered(args, config: Config, names: list[str], print_fn: Callable[..., None]) -> int:   # noqa: ANN001 - argparse 的结果
    from cad_agent.cli import build_agent
    from cad_agent.llm.factory import make_llm

    key = find_key(config)
    if not key:
        print_fn(NO_KEY)
        return 2
    os.environ.setdefault(config.api_key_env, key)   # 只在这个进程里；沙盒子进程会去掉它（secret_env_names）
    if args.cases == "off":
        config = replace(config, gates=replace(config.gates, cases=False))

    def make_agent(root: Path, wrap: Callable):
        agent = build_agent(replace(config, sessions_dir=root / "sessions"))[0]
        agent.llm = wrap(agent.llm, "agent")
        if agent.modeling_llm is not None:
            agent.modeling_llm = wrap(agent.modeling_llm, "agent")
        if agent.review_llm is not None:
            agent.review_llm = wrap(agent.review_llm, "agent")
        return agent

    def make_sim_user(hidden_spec: str, wrap: Callable) -> SimUser:
        return SimUser(wrap(make_llm(config, "base", key), "sim_user"), hidden_spec)

    results_dir = Path(args.out) / f"{datetime.now().strftime('%Y%m%d-%H%M%S')}-{args.label}"
    results = run_metered(names, config=config, label=args.label, cap=args.cap, allow_peak=args.allow_peak, results_dir=results_dir,
                          make_agent=make_agent, make_sim_user=make_sim_user, print_fn=print_fn, task_cap=args.task_cap)
    if results is None:
        return 2
    print_fn("\n" + render_summary_md(results) + "\n" + render_results_md(results))
    print_fn(f"结果已保存到 {results_dir}")
    return 0
