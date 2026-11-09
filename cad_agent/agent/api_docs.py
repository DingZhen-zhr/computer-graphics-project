"""查 SCA 内置的 API 文档（api_help 工具用）。

文档位置见 docs/sca-api-notes.md 第 10 节：包内 skill/resources/docs/skill/references/docs/api/<函数名>.md。
"""

from __future__ import annotations

import importlib.util
import re
from functools import lru_cache
from pathlib import Path

MAX_DOC_CHARS = 4000
NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
PREFIXES = ("simplecadapi.", "scad.", "ql.")


@lru_cache(maxsize=1)
def _api_dir() -> Path | None:
    spec = importlib.util.find_spec("simplecadapi")  # 只定位，不导入（导入很慢）
    if spec is None or not spec.submodule_search_locations:
        return None
    d = Path(list(spec.submodule_search_locations)[0]) / "skill" / "resources" / "docs" / "skill" / "references" / "docs" / "api"
    return d if d.is_dir() else None


def normalize_api_name(name: str) -> str:
    """去掉 scad.、ql. 之类的前缀和括号：`scad.make_box_rsolid()` → `make_box_rsolid`。"""
    n = name.strip().removesuffix("()")
    for p in PREFIXES:
        n = n.removeprefix(p)
    return n


def api_names() -> list[str]:
    d = _api_dir()
    return sorted(p.stem for p in d.glob("*.md")) if d else []


def lookup_api(name: str) -> str | None:
    """返回该函数的文档文字（过长会截断）；没有这个函数时返回 None。"""
    d = _api_dir()
    n = normalize_api_name(name)
    if d is None or not NAME_RE.match(n):  # 名字只能是标识符，不能带路径
        return None
    path = d / f"{n}.md"
    if not path.is_file():
        return None
    text = path.read_text(encoding="utf-8").strip()
    if len(text) > MAX_DOC_CHARS:
        text = text[:MAX_DOC_CHARS].rsplit("\n", 1)[0] + "\n…（后面的内容省略）"
    return text
