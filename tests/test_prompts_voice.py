"""3.0 计划 4 Task 3：说人话的提示词。"""

from __future__ import annotations

import re
from pathlib import Path

from cad_agent.agent.state import PROMPT_DIR, load_system_prompt

PLAN = Path(__file__).resolve().parents[1] / "docs/superpowers/plans/2026-11-20-datum-4-quality.md"


def test_system_voice_verbatim():
    section = PLAN.read_text(encoding="utf-8").split("### Task 3", 1)[1].split("### Task 4", 1)[0]
    [block] = re.findall(r"```text\n(.*?)\n```", section, flags=re.S)
    assert (PROMPT_DIR / "system_voice.md").read_text(encoding="utf-8").rstrip("\n") == block


def test_voice_comes_after_multipart():
    full = load_system_prompt(True)
    voice = full.index("## 和用户说话的口气")
    first_ref_line = (PROMPT_DIR / "references_index.md").read_text(encoding="utf-8").strip().splitlines()[0]
    assert full.index("## 零件要做得好看、好用") < voice < full.index(first_ref_line)
    assert "## 和用户说话的口气" not in load_system_prompt(False)
