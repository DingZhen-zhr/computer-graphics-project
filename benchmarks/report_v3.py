"""3.0 的评测结果表（计划 4 Task 2）：开发 / 留出 × 单零件 / 多零件四张表，再加一张作业要求的覆盖情况表。

覆盖情况：这一遍里有没有经过需求澄清（模型至少问过一次）、多轮修改（有修改阶段并且交付了）、错误反馈修正（修复次数 ≥ 1）。
"""

from __future__ import annotations

from benchmarks.report import is_skipped, max_dimension_deviation
from benchmarks.task_sets import MULTI_TASKS, V3_DEV, V3_HOLDOUT

HEADER = "| 任务 | 成功 | 最大尺寸偏差(mm) | 耗时(s) | 修复次数 | 模型调用 | 花费(元) |"
COVER_HEADER = "| 任务 | 需求澄清 | 多轮修改 | 错误反馈修正 |"


def _n(v: float | None, digits: int = 2) -> str:
    if v is None:
        return "-"
    text = f"{v:.{digits}f}"
    return text.rstrip("0").rstrip(".") if "." in text else text


def _cost(r: dict) -> float | None:
    parts = [r.get("cost"), r.get("sim_cost")]
    return None if all(p is None for p in parts) else sum(p for p in parts if p is not None)


def _row(r: dict) -> str:
    if is_skipped(r):
        why = "到了花费上限，没跑" if r.get("skipped_for_cap") or r.get("skipped_for_budget") else "空闲时段结束，没跑"
        return f"| {r['task']} | {why} | - | - | - | - | - |"
    ok = "成功" if r.get("success") else ("到上限停了" if r.get("stopped_for_cap") else "没成功")
    return (f"| {r['task']} | {ok} | {_n(max_dimension_deviation(r) if r.get('stages') else None, 3)} | {_n(r.get('duration_s'), 0)} | "
            f"{r.get('repairs', 0)} | {r.get('llm_calls', 0)} | {_n(_cost(r))} |")


def coverage(r: dict) -> dict[str, bool]:
    stages = r.get("stages") or []
    return {
        "clarify": (r.get("questions") or 0) >= 1,
        "modify": any(s.get("stage", "").startswith("after_mod") and s.get("delivered") for s in stages),
        "repair": (r.get("repairs") or 0) >= 1,
    }


def render_v3_md(results: list[dict]) -> str:
    groups = [("开发 · 单零件", V3_DEV, False), ("开发 · 多零件", V3_DEV, True), ("留出 · 单零件", V3_HOLDOUT, False), ("留出 · 多零件", V3_HOLDOUT, True)]
    out = []
    for title, names, multi in groups:
        rows = [r for r in results if r["task"] in names and (r["task"] in MULTI_TASKS) == multi]
        if not rows:
            continue
        ok = sum(1 for r in rows if r.get("success"))
        out += [f"### {title}（{ok}/{len(rows)} 成功）", "", HEADER, "|---|---|---|---|---|---|---|", *map(_row, rows), ""]
    ran = [r for r in results if not is_skipped(r)]
    marks = {r["task"]: coverage(r) for r in ran}
    yes = lambda b: "✓" if b else "—"   # noqa: E731
    all3 = [t for t, c in marks.items() if all(c.values())]
    out += ["### 覆盖情况（作业要求：至少 3 组，覆盖需求澄清、多轮修改、错误反馈修正）", "", COVER_HEADER, "|---|---|---|---|",
            *[f"| {t} | {yes(c['clarify'])} | {yes(c['modify'])} | {yes(c['repair'])} |" for t, c in marks.items()], "",
            f"三项都覆盖到的任务：{len(all3)} 个" + (f"（{'、'.join(all3)}）" if all3 else "") + "。", ""]
    return "\n".join(out)
