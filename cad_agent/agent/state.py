"""给模型的系统提示词和每轮开头生成一次的快照。"""

from __future__ import annotations

import json
from pathlib import Path

from cad_agent.tools import Workspace

PROMPT_DIR = Path(__file__).parent / "prompts"
SNAPSHOT_TITLE = "【当前状态（程序生成，不是用户说的话）】"


V2_PARTS = ("system_v2.md", "system_multipart.md", "system_voice.md", "references_index.md", "sca_cheatsheet.md", "sca_cheatsheet_more.md")


def load_system_prompt(staged: bool = False) -> str:
    """系统提示词全文。旧流程：system.md 接速查表（和 1.2 版逐字相同）；分阶段：V2_PARTS 四段，各段之间空一行。"""
    if staged:
        return "\n\n".join((PROMPT_DIR / n).read_text(encoding="utf-8").rstrip("\n") for n in V2_PARTS) + "\n"
    system = (PROMPT_DIR / "system.md").read_text(encoding="utf-8").rstrip("\n")
    sheet = (PROMPT_DIR / "sca_cheatsheet.md").read_text(encoding="utf-8").rstrip("\n")
    return system + "\n\n" + sheet + "\n"


def _plan_lines(ws: Workspace) -> str:
    if ws.plan is None:
        return "无"
    cur = ws.plan.current()
    def status(s) -> str:  # noqa: ANN001 - Stage
        return "已通过" if s.passed else ("当前" if cur is not None and s.id == cur.id else "未开始")
    return "\n".join(f"{s.id} {s.title}：{s.done_when} —— {status(s)}" for s in ws.plan.stages)


def _part_lines(ws: Workspace) -> list[str]:
    """多零件时，计划前面列各零件的进度；全部做完后再列装配的状态。单零件时是空表。"""
    if not ws.brief.is_multipart() or not ws.parts:
        return []
    from cad_agent.product.materials import MATERIALS  # 避免循环导入

    out = ["零件："]
    for p in ws.brief.parts:
        st = ws.parts.get(p.id)
        status = "已做完" if st is not None and st.done else ("当前" if p.id == ws.active else "未开始")
        out.append(f"{p.id} {p.name}（{MATERIALS[p.material].name}）—— {status}")
    if all(st.done for st in ws.parts.values()):
        state = "已通过" if ws.assembly_passed else ("没通过" if ws.last_assembly is not None else "未开始")
        out.append(f"装配：{state}")
    return out


def _render_staged(ws: Workspace) -> str:
    """分阶段流程的快照，格式见第二版提示词文档第 3 节。"""
    from cad_agent.staged.summary import feature_block  # 避免循环导入

    ok, _ = ws.brief.can_build()
    if not ok:
        phase = "澄清中（需求单未确认）"
    elif ws.plan is None:
        phase = "规划中（还没有计划，先调用 set_plan）"
    elif ws.plan.current() is not None:
        phase = f"建模中（当前阶段 {ws.plan.current().id}）"
    else:
        phase = "全部阶段已通过"
    lines = [SNAPSHOT_TITLE, f"阶段：{phase}", "需求单：", json.dumps(ws.brief.to_dict(), ensure_ascii=False, indent=1)]
    if ok:
        checks = json.dumps(ws.checks_raw, ensure_ascii=False, indent=1) if ws.checks_raw else "无"
        last_build = "未运行" if ws.last_build_content is None else ws.last_build_content
        lines += _part_lines(ws)
        lines += ["计划：", _plan_lines(ws), "特征（按顺序）：", feature_block(ws.features.items),
                  "检查项：", checks, "上次 build：", last_build]
    return "\n".join(lines)


def render_snapshot(ws: Workspace, staged: bool = False) -> str:
    """快照，格式见 1.1 版提示词文档第 2 节（staged 为真时见第二版第 3 节）。每轮开始时生成一次，这一轮中间不再改。"""
    if staged:
        return _render_staged(ws)
    ok, _ = ws.brief.can_build()
    lines = [
        SNAPSHOT_TITLE,
        f"阶段：{'可以建模（需求单已确认）' if ok else '澄清中（需求单未确认）'}",
        "需求单：",
        json.dumps(ws.brief.to_dict(), ensure_ascii=False, indent=1),
    ]
    if ok:
        features = "\n\n".join(f"--- {f.slug}（{f.role}）---\n{f.code}" for f in ws.features.items) or "无"
        checks = json.dumps(ws.checks_raw, ensure_ascii=False, indent=1) if ws.checks_raw else "无"
        last_build = "未运行" if ws.last_build_content is None else ws.last_build_content
        lines += ["特征（按顺序）：", features, "检查项：", checks, "上次 build：", last_build]
    return "\n".join(lines)
