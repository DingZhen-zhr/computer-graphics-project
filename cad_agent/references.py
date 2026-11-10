"""读 SCA 官方 skill 里的建模文档（read_reference 工具用，设计文档第 3.4 节）。

文档只在运行时从用户本机的 SCA 安装包里读，不复制进仓库。只能读白名单里的 10 篇；
定位办法和 api_docs._api_dir 相同（只定位，不导入 SCA）。
"""

from __future__ import annotations

import importlib.util
from functools import lru_cache
from pathlib import Path

from cad_agent.staged import messages as msg

REFERENCES: dict[str, str] = {
    "mechanical-modeling": "discipline/mechanical-modeling.md",
    "datums-and-coordinate-systems": "discipline/datums-and-coordinate-systems.md",
    "feature-ordering": "discipline/feature-ordering.md",
    "sketch-and-features": "domains/sketch-and-features.md",
    "standard-parts": "domains/standard-parts.md",
    "part-modeling": "domains/part-modeling.md",
    "ql-playbook": "ql-playbook.md",
    "geometric-validation": "discipline/geometric-validation.md",
    "failure-and-repair": "discipline/failure-and-repair.md",
    "manufacturing-boundaries": "discipline/manufacturing-boundaries.md",
}
HEAD_CHARS = 3000      # 不给 section 时返回开头这么多字符
SECTION_CHARS = 6000   # 一节最多返回这么多字符
TAIL = "\n…（后面的内容省略）"


class RefError(ValueError):
    """名字或小节不对；信息是提示词文档 7.3 的原文，直接返回给模型。"""


@lru_cache(maxsize=1)
def reference_root() -> Path | None:
    spec = importlib.util.find_spec("simplecadapi")
    if spec is None or not spec.submodule_search_locations:
        return None
    d = Path(list(spec.submodule_search_locations)[0]) / "skill" / "resources" / "docs" / "skill" / "references"
    return d if d.is_dir() else None


def _sections(text: str) -> list[tuple[str, int]]:
    """二级标题（去掉 `## `）和它所在的字符位置。"""
    out, pos = [], 0
    for line in text.splitlines(keepends=True):
        if line.startswith("## "):
            out.append((line[3:].strip(), pos))
        pos += len(line)
    return out


def read_reference(name: str, section: str | None = None) -> dict:
    """返回 {"name", "sections", "text", "truncated"}。不给 section 时 text 是开头一段，给了就是那一节。"""
    root = reference_root()
    if name not in REFERENCES or root is None or not (root / REFERENCES[name]).is_file():
        raise RefError(msg.ref_unknown(name, list(REFERENCES)))
    text = (root / REFERENCES[name]).read_text(encoding="utf-8")
    heads = _sections(text)
    titles = [t for t, _ in heads]
    if section is None:
        return {"name": name, "sections": titles, "text": text[:HEAD_CHARS], "truncated": len(text) > HEAD_CHARS}
    want = section.strip()
    for i, (title, start) in enumerate(heads):
        if title == want:
            end = heads[i + 1][1] if i + 1 < len(heads) else len(text)
            body = text[start:end].rstrip("\n")
            if len(body) > SECTION_CHARS:
                return {"name": name, "sections": titles, "text": body[:SECTION_CHARS] + TAIL, "truncated": True}
            return {"name": name, "sections": titles, "text": body, "truncated": False}
    raise RefError(msg.ref_no_section(name, want, titles))
