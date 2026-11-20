"""评测结果的两张表：按任务的汇总表、每一遍的明细（从 run.py 拆出来，名字仍可从 benchmarks.run 导入）。

因为花费上限没有跑的任务（{"task", "skipped_for_budget": true}）不算进平均值，"成功"一列写"因预算跳过"。
"""

from __future__ import annotations

from benchmarks.compare import CALLS_FMT, COST_FMT, SECONDS_FMT, TOKEN_FMT, fmt, success_text, task_means, total_row

LENGTH_TYPES = ("bbox", "distance")  # “尺寸偏差”只统计以 mm 为单位的长度类检查
TABLE_HEADER = "任务 | 成功 | 修复次数 | 耗时(s) | 模型调用 | token | 最大尺寸偏差"
SUMMARY_HEADER = "| 任务 | 成功 | 平均费用(元) | 平均耗时(s) | 平均模型调用 | 平均输入 | 其中命中缓存 | 平均输出 | 其中思考 |"
SKIPPED_TEXT = "因预算跳过"


def is_skipped(result: dict) -> bool:
    """没跑的任务：到了花费上限（第二版的 --budget 或 3.0 的账本），或者空闲时段已经结束。"""
    return bool(result.get("skipped_for_budget") or result.get("skipped_for_cap") or result.get("skipped_for_offpeak"))


def max_dimension_deviation(result: dict) -> float | None:
    """所有长度类验收（bbox、distance）里偏差绝对值的最大值，单位 mm；没有就是 None。"""
    devs = [abs(a["deviation"]) for s in result["stages"] for a in s["acceptance"]
            if a.get("type") in LENGTH_TYPES and a["deviation"] is not None]
    return max(devs) if devs else None


def _num(v: float | None) -> str:
    return "-" if v is None else f"{v:.4f}".rstrip("0").rstrip(".")


def render_summary_md(results: list[dict]) -> str:
    """按任务汇总的表：成功次数 / 遍数，以及各项平均值；最后一行"合计"是各任务平均值相加。缺字段的格显示 -。"""
    means = task_means([r for r in results if not is_skipped(r)])
    skipped: dict[str, int] = {}
    for r in results:
        if is_skipped(r):
            skipped[r["task"]] = skipped.get(r["task"], 0) + 1
    lines = [SUMMARY_HEADER, "|---|---|---|---|---|---|---|---|---|"]
    order = list(dict.fromkeys(r["task"] for r in results))
    for task in order:
        if task not in means:   # 这个任务一遍都没跑
            lines.append(f"| {task} | {SKIPPED_TEXT} |" + " - |" * 7)
            continue
        m = means[task]
        ok = success_text(m) + (f"（另有 {skipped[task]} 遍{SKIPPED_TEXT}）" if task in skipped else "")
        cells = [ok, fmt(m["cost"], COST_FMT), fmt(m["duration_s"], SECONDS_FMT), fmt(m["llm_calls"], CALLS_FMT)]
        cells += [fmt(m[key], TOKEN_FMT) for key in ("prompt_tokens", "cached_tokens", "completion_tokens", "reasoning_tokens")]
        lines.append(f"| {task} | " + " | ".join(cells) + " |")
    for label, m in [("合计", total_row(means))]:
        cells = [success_text(m), fmt(m["cost"], COST_FMT), fmt(m["duration_s"], SECONDS_FMT), fmt(m["llm_calls"], CALLS_FMT)]
        cells += [fmt(m[key], TOKEN_FMT) for key in ("prompt_tokens", "cached_tokens", "completion_tokens", "reasoning_tokens")]
        lines.append(f"| {label} | " + " | ".join(cells) + " |")
    return "\n".join(lines) + "\n"


def _label(result: dict) -> str:
    return f"{result['task']}#{result['run']}" if "run" in result else result["task"]


def render_results_md(results: list[dict]) -> str:
    lines = ["# 评测结果", "", f"| {TABLE_HEADER} |", "|---|---|---|---|---|---|---|"]
    for r in results:
        if is_skipped(r):
            lines.append(f"| {_label(r)} | {SKIPPED_TEXT} | - | - | - | - | - |")
            continue
        dev = max_dimension_deviation(r)
        lines.append(f"| {_label(r)} | {'是' if r['success'] else '否'} | {r['repairs']} | {r['duration_s']:.1f} | "
                     f"{r['llm_calls']} | {r['tokens']} | {'-' if dev is None else f'{dev:.3g} mm'} |")
    for r in results:
        if is_skipped(r):
            continue
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


