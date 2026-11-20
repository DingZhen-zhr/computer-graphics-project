"""第二版提示词文件和提示词文档的逐字比对（计划 1）。"""

import re
from pathlib import Path

from cad_agent.agent.api_docs import _api_dir, api_names
from cad_agent.agent.state import PROMPT_DIR
from cad_agent.sandbox.guard import check_code

PROMPTS_DOC_V2 = Path(__file__).resolve().parent.parent / "docs" / "superpowers" / "plans" / "2026-11-10-caliper-1-kernel-prompts.md"


def doc_section(title: str) -> str:
    """第二版提示词文档里以 `## <title>` 开头的一节（到下一个 `## 数字.` 标题之前）。"""
    doc = PROMPTS_DOC_V2.read_text(encoding="utf-8")
    start = doc.index(f"\n## {title}\n")
    rest = doc[start + 1:]
    m = re.search(r"\n## \d+\. ", rest[3:])
    return rest if m is None else rest[: m.start() + 3]


def text_blocks(section: str) -> list[str]:
    return re.findall(r"```text\n(.*?)\n```", section, flags=re.S)


def read(name: str) -> str:
    return (PROMPT_DIR / name).read_text(encoding="utf-8")


def stdlib_names() -> set[str]:
    """标准件函数（scad.std.<模块>.<函数>）的文档在 api 目录旁边的 stdlib 目录里（笔记第 21 节）。"""
    d = _api_dir()
    return {p.stem for p in (d.parent / "stdlib").glob("*.md")} if d else set()


def test_cheatsheet_more_sections():
    block = text_blocks(doc_section("8. 速查表补充"))[0].splitlines()
    text = read("sca_cheatsheet_more.md")
    assert text.splitlines()[0] == block[0]
    # 3.0 计划 2 Task 11（偏离 D31，用户同意）：末尾多一节"装配的写法"
    assert ["## " + h for h in re.findall(r"^## (.+)$", text, flags=re.M)] == block[1:] + ["## 装配的写法"]


def test_cheatsheet_more_staged_rules_verbatim():
    rules = text_blocks(doc_section("8. 速查表补充"))[1].splitlines()
    assert len(rules) == 3
    text = read("sca_cheatsheet_more.md")
    for line in rules:
        assert line in text.splitlines(), line


def test_cheatsheet_more_examples_pass_the_guard():
    names, std = set(api_names()), stdlib_names()
    text = read("sca_cheatsheet_more.md")
    examples = re.findall(r"例：`([^`]+)`", text)
    assert len(examples) >= 8
    for code in examples:
        assert check_code(code) == [], code  # 示例必须是合法的单行 Python，并且能通过静态检查
        for fn in re.findall(r"\bscad\.std\.[a-z_]+\.([A-Za-z_]\w*)", code):
            assert fn in std, (fn, code)
        plain = re.sub(r"\bscad\.std\.[a-z_]+\.", "", code)
        for fn in re.findall(r"\bscad\.([A-Za-z_]\w*)", plain):
            assert fn in names, (fn, code)
        for fn in re.findall(r"\bql\.([A-Za-z_]\w*)", code):
            assert fn in {"faces", "edges", "vertices", "prop", "and_", "or_", "not_", "value"}, (fn, code)


def test_cheatsheet_more_sections_have_entries():
    parts = re.split(r"^## (.+)$", read("sca_cheatsheet_more.md"), flags=re.M)
    sections = {parts[i]: parts[i + 1] for i in range(1, len(parts), 2)}
    for title in ("草图约束与轮廓", "抽壳", "扫掠", "标准件：齿轮与齿条"):
        entries = re.findall(r"^- ", sections[title], flags=re.M)
        assert len(entries) >= 2, title
        assert "例：`" in sections[title], title
