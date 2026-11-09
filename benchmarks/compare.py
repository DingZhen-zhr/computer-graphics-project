"""前后对比：python -m benchmarks.compare 旧/results.json 新/results.json [--out compare.md]

按任务算每项指标的平均值，输出旧 → 新的对比表（Markdown）和总费用之比。
结果里缺字段（比如第一版的 results.json 没有 prompt_tokens 和 cost）的格子显示 "-"，不报错。
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Callable

# 取平均值的指标
MEAN_KEYS = ("cost", "duration_s", "llm_calls", "prompt_tokens", "cached_tokens", "completion_tokens", "reasoning_tokens")
# 表里每一列：(指标, 数字格式)；费用 4 位小数，耗时、调用次数 1 位小数，token 取整
COST_FMT, SECONDS_FMT, CALLS_FMT, TOKEN_FMT = ".4f", ".1f", ".1f", ".0f"
COMPARE_HEADER = "| 任务 | 成功（旧→新） | 费用（旧→新） | 耗时（旧→新） | 调用（旧→新） | 输入（旧→新） | 输出（旧→新） |"
COMPARE_COLUMNS = (("cost", COST_FMT), ("duration_s", SECONDS_FMT), ("llm_calls", CALLS_FMT),
                   ("prompt_tokens", TOKEN_FMT), ("completion_tokens", TOKEN_FMT))


def fmt(value: float | None, spec: str) -> str:
    return "-" if value is None else format(value, spec)


def _mean(values: list) -> float | None:
    """有一遍缺这一项（或是 None），平均值就是 None。"""
    if not values or any(v is None for v in values):
        return None
    return sum(values) / len(values)


def task_means(results: list[dict]) -> dict[str, dict]:
    """按任务（首次出现的顺序）汇总：遍数、成功次数，以及各项指标的平均值。"""
    grouped: dict[str, list[dict]] = {}
    for r in results:
        grouped.setdefault(r["task"], []).append(r)
    return {
        task: {"runs": len(runs), "successes": sum(1 for r in runs if r.get("success")),
               **{key: _mean([r.get(key) for r in runs]) for key in MEAN_KEYS}}
        for task, runs in grouped.items()
    }


def total_row(means: dict[str, dict]) -> dict:
    """各任务平均值相加；有一个任务缺这一项，合计就是 None。没有任务时全是 None。"""
    row: dict = {"runs": sum(m["runs"] for m in means.values()), "successes": sum(m["successes"] for m in means.values())}
    for key in MEAN_KEYS:
        values = [m[key] for m in means.values()]
        row[key] = None if not values or any(v is None for v in values) else sum(values)
    return row


def success_text(m: dict | None) -> str:
    return "-" if m is None or not m["runs"] else f"{m['successes']}/{m['runs']}"


def render_compare_md(old: list[dict], new: list[dict]) -> str:
    old_means, new_means = task_means(old), task_means(new)
    lines = [COMPARE_HEADER, "|---|---|---|---|---|---|---|"]

    def row(label: str, o: dict | None, n: dict | None) -> str:
        cells = [f"{success_text(o)} → {success_text(n)}"]
        for key, spec in COMPARE_COLUMNS:
            cells.append(f"{fmt(o and o[key], spec)} → {fmt(n and n[key], spec)}")
        return f"| {label} | " + " | ".join(cells) + " |"

    for task in [*old_means, *(t for t in new_means if t not in old_means)]:
        lines.append(row(task, old_means.get(task), new_means.get(task)))
    old_total, new_total = total_row(old_means), total_row(new_means)
    lines.append(row("合计", old_total, new_total))
    o_cost, n_cost = old_total["cost"], new_total["cost"]
    ratio = "-" if o_cost is None or n_cost is None or o_cost == 0 else f"{n_cost / o_cost:.2f}"
    return "\n".join(lines) + f"\n\n费用比（新/旧）：{ratio}\n"


def _load(path: str) -> list[dict]:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        raise ValueError(f"读不了结果文件 {path}：{e}") from e
    if not isinstance(data, list):
        raise ValueError(f"结果文件 {path} 的格式不对（应该是 results.json）")
    return data


def main(argv: list[str] | None = None, print_fn: Callable[..., None] = print) -> int:
    parser = argparse.ArgumentParser(prog="python -m benchmarks.compare", description="对比两次评测的结果")
    parser.add_argument("old", help="旧结果的 results.json")
    parser.add_argument("new", help="新结果的 results.json")
    parser.add_argument("--out", help="把对比表另存到这个文件（UTF-8）")
    args = parser.parse_args(argv)
    try:
        md = render_compare_md(_load(args.old), _load(args.new))
    except ValueError as e:
        print_fn(str(e))
        return 1
    print_fn(md)
    if args.out:
        Path(args.out).write_text(md, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
