"""3.0 计划 5 Task 2：提示词与工具定义文档要和代码一致。"""

from __future__ import annotations

import re
import sys
from pathlib import Path

from cad_agent.staged.specs import TOOL_NAMES_V2

ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "docs" / "prompts-and-tools.md"
sys.path.insert(0, str(ROOT / "scripts"))


def test_prompts_doc_up_to_date():
    from export_prompts import build

    assert DOC.read_text(encoding="utf-8") == build(), "代码里的提示词或工具改了：重新运行 scripts/export_prompts.py"


def test_doc_has_all_tools():
    text = DOC.read_text(encoding="utf-8")
    for title in ("# 提示词与工具定义", "## 系统提示词", "## 工具定义", "## 程序生成给模型的消息", "## 模拟用户的提示词"):
        assert title in text, title
    assert len(TOOL_NAMES_V2) == 17
    for name in TOOL_NAMES_V2:
        assert f"### {name}\n" in text, name


def test_doc_has_no_key():
    text = DOC.read_text(encoding="utf-8")
    assert not re.search(r"sk-[A-Za-z0-9]{16,}", text)
    assert ":\\Users" not in text and "/Users/" not in text
