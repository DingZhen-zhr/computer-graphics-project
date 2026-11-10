"""读 SCA 官方 skill 文档（第二版计划 1 Task 9）。"""

import re
from pathlib import Path

import pytest

from cad_agent import references
from cad_agent.agent.state import PROMPT_DIR
from cad_agent.references import HEAD_CHARS, REFERENCES, SECTION_CHARS, RefError, read_reference
from cad_agent.staged import messages as msg

TAIL = "\n…（后面的内容省略）"
DOC_V2 = Path(__file__).resolve().parent.parent / "docs" / "superpowers" / "plans" / "2026-11-10-caliper-1-kernel-prompts.md"


def test_whitelist_matches_the_index():
    index = (PROMPT_DIR / "references_index.md").read_text(encoding="utf-8")
    names = re.findall(r"^- ([a-z-]+)：", index, flags=re.M)
    assert sorted(names) == sorted(REFERENCES) and len(REFERENCES) == 10
    sec = DOC_V2.read_text(encoding="utf-8").split("## 2. 文档目录")[1].split("## 3. 快照格式")[0]
    block = re.findall(r"```text\n(.*?)\n```", sec, flags=re.S)
    assert len(block) == 1 and index.rstrip("\n") == block[0]


def test_every_reference_file_exists():
    root = references.reference_root()
    assert root is not None
    for name, rel in REFERENCES.items():
        assert (root / rel).is_file(), name
    assert REFERENCES["feature-ordering"] == "discipline/feature-ordering.md"
    assert REFERENCES["ql-playbook"] == "ql-playbook.md"


def test_head_lists_sections():
    r = read_reference("part-modeling")
    assert r["name"] == "part-modeling" and "Boolean discipline" in r["sections"]
    assert len(r["text"]) <= HEAD_CHARS == 3000
    assert r["text"].startswith("# ")
    long = read_reference("ql-playbook")
    assert len(long["text"]) <= HEAD_CHARS and long["truncated"] is True


def test_section_text():
    r = read_reference("part-modeling", "Boolean discipline")
    assert r["text"].startswith("## Boolean discipline")
    assert "## Validation gates" not in r["text"] and "## API groups" not in r["text"]
    assert r["truncated"] is False
    assert read_reference("part-modeling", "  Boolean discipline ")["text"] == r["text"]   # 首尾空白不计


def longest_section(name: str) -> str:
    sections = read_reference(name)["sections"]
    return max(sections, key=lambda s: len(read_reference(name, s)["text"]))


def test_long_section_truncated(monkeypatch):
    # 提示词文档设想 ql-playbook 里最长的一节超过 6000 字符，实测最长只有约 3200 字符（偏离 D11），
    # 所以先确认真实上限下不截断，再把上限调小，验证截断的写法。
    title = longest_section("ql-playbook")
    full = read_reference("ql-playbook", title)
    assert SECTION_CHARS == 6000 and full["truncated"] is False and len(full["text"]) <= SECTION_CHARS
    monkeypatch.setattr(references, "SECTION_CHARS", 1000)
    cut = read_reference("ql-playbook", title)
    assert cut["truncated"] is True
    assert len(cut["text"]) <= 1000 + len(TAIL) and cut["text"].endswith(TAIL)
    assert cut["text"].startswith(full["text"][:1000])


def test_unknown_name_and_section():
    names = list(REFERENCES)
    for bad in ("nope", "../SKILL", "SKILL", "docs/api/make_box_rsolid"):
        with pytest.raises(RefError) as e:
            read_reference(bad)
        assert str(e.value) == msg.ref_unknown(bad, names)
    with pytest.raises(RefError) as e:
        read_reference("part-modeling", "No such part")
    assert str(e.value) == msg.ref_no_section("part-modeling", "No such part", read_reference("part-modeling")["sections"])
