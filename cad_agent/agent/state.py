"""给模型的系统提示词和每轮开头生成一次的快照。"""

from __future__ import annotations

import json
from pathlib import Path

from cad_agent.tools import Workspace

PROMPT_DIR = Path(__file__).parent / "prompts"
SNAPSHOT_TITLE = "【当前状态（程序生成，不是用户说的话）】"


def load_system_prompt() -> str:
    """系统提示词全文，末尾接上 SCA 常用写法速查表。"""
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
