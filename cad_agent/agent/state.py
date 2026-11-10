"""给模型的系统提示词和每轮开头生成一次的快照。"""

from __future__ import annotations

import json
from pathlib import Path

from cad_agent.tools import Workspace

PROMPT_DIR = Path(__file__).parent / "prompts"
SNAPSHOT_TITLE = "【当前状态（程序生成，不是用户说的话）】"


V2_PARTS = ("system_v2.md", "references_index.md", "sca_cheatsheet.md", "sca_cheatsheet_more.md")


def load_system_prompt(staged: bool = False) -> str:
    """系统提示词全文。旧流程：system.md 接速查表（和 1.2 版逐字相同）；分阶段：V2_PARTS 四段，各段之间空一行。"""
    if staged:
        return "\n\n".join((PROMPT_DIR / n).read_text(encoding="utf-8").rstrip("\n") for n in V2_PARTS) + "\n"
    system = (PROMPT_DIR / "system.md").read_text(encoding="utf-8").rstrip("\n")
    sheet = (PROMPT_DIR / "sca_cheatsheet.md").read_text(encoding="utf-8").rstrip("\n")
    return system + "\n\n" + sheet + "\n"


def render_snapshot(ws: Workspace) -> str:
    """快照，格式见 1.1 版提示词文档第 2 节。每轮开始时生成一次，这一轮中间不再改。"""
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
