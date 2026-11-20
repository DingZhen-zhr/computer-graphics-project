"""特征列表 → marimo notebook 文件。

写法依据 docs/sca-api-notes.md 第 3 节：参数 cell 用 scad.var（单位 mm / deg），
"1" 单位的参数写成普通整数常量；每个特征一个 cell，第一行是 `# ---- feature: <slug> (<role>) ----`。
"""

from __future__ import annotations

import ast
import keyword
import re
from dataclasses import dataclass

from cad_agent.brief import Param
from cad_agent.code_names import _Names
from cad_agent.product.materials import Material, rgb01

ROLES = {"build", "add", "subtract", "intersect", "modify", "pattern"}
SLUG_RE = re.compile(r"^[a-z][a-z0-9-]*$")
# 这些名字在 notebook 里已有别的用途
RESERVED_VARS = frozenset({"scad", "ql", "math", "model", "marimo", "app"})

HEADER = '''# /// script
# requires-python = ">=3.10"
# dependencies = ["simplecadapi"]
#
# [tool.simplecadapi]
# id = "model"
# ///
import marimo

app = marimo.App()

with app.setup:
    import simplecadapi as scad
    from simplecadapi import ql
    import math
'''
FOOTER = '''

if __name__ == "__main__":
    app.run()
'''


class NotebookError(ValueError):
    """特征列表不能拼成 notebook；`feature` 是相关特征的 slug，不确定时为 None。"""

    def __init__(self, message: str, feature: str | None = None) -> None:
        super().__init__(message)
        self.feature = feature


@dataclass
class Feature:
    slug: str
    role: str
    code: str
    stage: str = ""   # 分阶段时归属的阶段编号；旧流程是空文字

    @property
    def var(self) -> str:
        return self.slug.replace("-", "_")


def _check_slug_role(f: Feature) -> None:
    if not isinstance(f.slug, str) or not SLUG_RE.match(f.slug):
        raise NotebookError(f"特征名 {f.slug!r} 不合法：必须是小写字母开头，只含小写字母、数字和短横线", f.slug if isinstance(f.slug, str) else None)
    if f.role not in ROLES:
        raise NotebookError(f"特征 {f.slug} 的 role {f.role!r} 不合法，只能是：{'、'.join(sorted(ROLES))}", f.slug)
    if f.var in RESERVED_VARS or keyword.iskeyword(f.var):
        raise NotebookError(f"特征名 {f.slug} 对应的变量名 {f.var} 是保留名或 Python 关键字，请换一个", f.slug)


class FeatureList:
    """有序的特征列表。"""

    def __init__(self, items: list[Feature] | None = None) -> None:
        self._items: list[Feature] = list(items or [])

    @property
    def items(self) -> list[Feature]:
        return list(self._items)

    def upsert(self, f: Feature, before: str | None = None) -> None:
        _check_slug_role(f)
        for i, old in enumerate(self._items):
            if old.slug == f.slug:
                self._items[i] = f  # 同名：原位替换，忽略 before
                return
        if before is None:
            self._items.append(f)
            return
        for i, old in enumerate(self._items):
            if old.slug == before:
                self._items.insert(i, f)
                return
        raise NotebookError(f"找不到特征 {before}，无法把 {f.slug} 插到它前面")

    def insert(self, f: Feature, index: int) -> None:
        """把新特征插到第 index 个位置（分阶段时用）；已有同名 slug 时抛 NotebookError。"""
        _check_slug_role(f)
        if any(old.slug == f.slug for old in self._items):
            raise NotebookError(f"已经有特征 {f.slug}，不能再插入一个同名的", f.slug)
        self._items.insert(index, f)

    def in_stage(self, stage_id: str) -> list[Feature]:
        return [f for f in self._items if f.stage == stage_id]

    def remove(self, slug: str) -> None:
        for i, old in enumerate(self._items):
            if old.slug == slug:
                del self._items[i]
                return
        raise NotebookError(f"没有特征 {slug}，无法删除")

    def to_list(self) -> list[dict]:
        return [{"slug": f.slug, "role": f.role, "code": f.code, **({"stage": f.stage} if f.stage else {})} for f in self._items]

    @classmethod
    def from_list(cls, raw: list[dict]) -> "FeatureList":
        return cls([Feature(d["slug"], d["role"], d["code"], d.get("stage", "")) for d in raw])


@dataclass
class RenderedNotebook:
    text: str
    cell_lines: dict[str, tuple[int, int]]


def _analyse(f: Feature) -> _Names:
    try:
        tree = ast.parse(f.code.replace("\r\n", "\n"))
    except SyntaxError as e:
        raise NotebookError(f"特征 {f.slug} 的代码有语法错误：第 {e.lineno} 行，{e.msg}", f.slug) from e
    names = _Names()
    names.visit(tree)
    return names


def _ret(names: list[str]) -> str:
    return f"return ({names[0]},)" if len(names) == 1 else "return " + ", ".join(names)


def _literal(v: float) -> str:
    return str(int(v)) if float(v).is_integer() else repr(float(v))


PLACEHOLDER = "placeholder_body"  # 没有特征时 probe 用的占位实体（笔记第 17 节）
PLACEHOLDER_CODE = f"{PLACEHOLDER} = scad.make_box_rsolid(width=1, height=1, depth=1, bottom_face_center=(0, 0, 0))"


def _probe_cell(code: str, available: set[str], last: str | None) -> tuple[list[str], list[str]]:
    """probe 单元的输入和内容（笔记第 17 节）。probe 代码已经先过 check_code；这段包装是程序写的。"""
    try:
        tree = ast.parse(code.replace("\r\n", "\n"))
    except SyntaxError as e:
        raise NotebookError(f"probe 代码有语法错误：第 {e.lineno} 行，{e.msg}") from e
    names = _Names()
    names.visit(tree)
    inputs = {n for n in names.reads if n in available}
    if last is not None:
        inputs.add(last)
    lines = code.replace("\r\n", "\n").strip("\n").splitlines() or ["pass"]
    body = [
        "# ---- probe ----", "import contextlib as _ctx", "import io as _io", "def _probe(model):",
        *(("    " + ln) if ln.strip() else "" for ln in lines),
        "_buf = _io.StringIO()", "try:", "    with _ctx.redirect_stdout(_buf):", f"        _probe({last or 'None'})", "finally:",
        '    with open("probe_out.txt", "w", encoding="utf-8") as _f:', "        _f.write(_buf.getvalue())", "return ()",
    ]
    return sorted(inputs), body


def render_notebook(params: list[Param], features: list[Feature], probe: str | None = None, *,
                    notebook_id: str = "model", material: "Material | None" = None,
                    color: str | None = None) -> RenderedNotebook:
    """拼出 notebook。probe 不是 None 时，在最后一个特征之后加一个 probe 单元（没有特征时先加一个占位实体）。

    notebook_id、material 是多零件用的（3.0）：编号写进文件头和零件的 part_id，给了材料时产品带上材料和颜色（笔记第 25 节）。
    默认值时输出和以前逐字相同。"""
    if not features and probe is None:
        raise NotebookError("还没有任何特征，无法生成模型。请先用 upsert_feature 写至少一个特征")
    param_names = [p.name for p in params]
    for f in features:
        _check_slug_role(f)
    slugs = [f.slug for f in features]
    if len(set(slugs)) != len(slugs):
        raise NotebookError("特征名有重复")
    analysed = {f.slug: _analyse(f) for f in features}

    lines = HEADER.replace('id = "model"', f'id = "{notebook_id}"').splitlines()
    cell_lines: dict[str, tuple[int, int]] = {}

    def add_cell(sig: list[str], body: list[str]) -> tuple[int, int]:
        lines.extend(["", ""])
        start = len(lines) + 1
        lines.append("@app.cell")
        lines.append(f"def _({', '.join(sig)}):")
        lines.extend(("    " + ln) if ln.strip() else "" for ln in body)
        return start, len(lines)

    if params:
        body = ["# ---- params ----"]
        for p in params:
            if p.unit == "1":
                body.append(f"{p.name} = {_literal(p.value)}")
            else:
                body.append(f'{p.name} = scad.var("{p.name}", {_literal(p.value)}, unit="{p.unit}")')
        body.append(_ret(param_names))
        add_cell([], body)

    available = set(param_names)
    for i, f in enumerate(features):
        names = analysed[f.slug]
        if f.var in available:
            raise NotebookError(f"特征 {f.slug} 的变量名 {f.var} 与参数或前面的特征重名", f.slug)
        if f.var not in names.writes:
            raise NotebookError(f"特征 {f.slug} 的代码最后必须把结果赋给与 slug 同名的变量 {f.var}（短横线换成下划线）", f.slug)
        extra = sorted(n for n in names.writes if n != f.var and not n.startswith("_"))
        if extra:
            raise NotebookError(
                f"特征 {f.slug} 的代码里除了 {f.var} 之外，还给 {'、'.join(extra)} 赋了值；临时变量必须以下划线开头，如 _{extra[0]}", f.slug
            )
        later = {g.var: g.slug for g in features[i + 1 :]}
        bad = sorted(n for n in names.reads if n in later and n not in names.writes)
        if bad:
            raise NotebookError(f"特征 {f.slug} 用到了排在它后面的特征 {later[bad[0]]} 的变量 {bad[0]}，请调整顺序，或先写 {later[bad[0]]}", f.slug)
        inputs = sorted(n for n in names.reads if n in available and n not in names.writes)
        code = f.code.replace("\r\n", "\n").strip("\n").splitlines()
        body = [f"# ---- feature: {f.slug} ({f.role}) ----", *code, _ret([f.var])]
        cell_lines[f.slug] = add_cell(inputs, body)
        available.add(f.var)

    last = features[-1].var if features else None
    if probe is not None:
        if last is None:
            add_cell([], [PLACEHOLDER_CODE, f"return ({PLACEHOLDER},)"])
        sig, body = _probe_cell(probe, available, last)
        add_cell(sig, body)
    body_var = last or PLACEHOLDER
    if material is None:
        product = f'model = scad.Part(part_id="{notebook_id}", body={body_var})'
    else:
        rgb = ", ".join(f"{v:g}" for v in rgb01(color or material.color))
        product = (f'model = scad.assign_material_rpart(scad.make_part_rpart("{notebook_id}", {body_var}), '
                   f'scad.make_material_rmaterial("{material.key}", name="{material.key}", color=({rgb})))')
    add_cell([body_var], [product, "return (model,)"])
    text = "\n".join(lines) + "\n" + FOOTER
    return RenderedNotebook(text=text, cell_lines=cell_lines)
