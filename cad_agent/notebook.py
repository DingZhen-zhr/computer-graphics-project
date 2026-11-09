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

    def remove(self, slug: str) -> None:
        for i, old in enumerate(self._items):
            if old.slug == slug:
                del self._items[i]
                return
        raise NotebookError(f"没有特征 {slug}，无法删除")

    def to_list(self) -> list[dict]:
        return [{"slug": f.slug, "role": f.role, "code": f.code} for f in self._items]

    @classmethod
    def from_list(cls, raw: list[dict]) -> "FeatureList":
        return cls([Feature(d["slug"], d["role"], d["code"]) for d in raw])


@dataclass
class RenderedNotebook:
    text: str
    cell_lines: dict[str, tuple[int, int]]


class _Names(ast.NodeVisitor):
    """收集一段代码读取了哪些名字、在最外层给哪些名字赋了值。

    函数、lambda、推导式、类里面的局部名字不算最外层的赋值；它们读取的名字照常算读取。
    """

    def __init__(self) -> None:
        self.reads: set[str] = set()
        self.writes: set[str] = set()
        self._depth = 0

    def visit_Name(self, node: ast.Name) -> None:
        if isinstance(node.ctx, ast.Load):
            self.reads.add(node.id)
        elif isinstance(node.ctx, ast.Store) and self._depth == 0:
            self.writes.add(node.id)

    def visit_AugAssign(self, node: ast.AugAssign) -> None:
        if isinstance(node.target, ast.Name):
            self.reads.add(node.target.id)
        self.generic_visit(node)

    def _enter(self, children: list[ast.AST]) -> None:
        self._depth += 1
        for child in children:
            self.visit(child)
        self._depth -= 1

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        if self._depth == 0:
            self.writes.add(node.name)
        for outer in [*node.decorator_list, *node.args.defaults, *[d for d in node.args.kw_defaults if d]]:
            self.visit(outer)
        self._enter(list(node.body))

    visit_AsyncFunctionDef = visit_FunctionDef  # type: ignore[assignment]

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        if self._depth == 0:
            self.writes.add(node.name)
        for outer in [*node.decorator_list, *node.bases]:
            self.visit(outer)
        self._enter(list(node.body))

    def visit_Lambda(self, node: ast.Lambda) -> None:
        for outer in [*node.args.defaults, *[d for d in node.args.kw_defaults if d]]:
            self.visit(outer)
        self._enter([node.body])

    def _comprehension(self, node: ast.AST) -> None:
        self._enter(list(ast.iter_child_nodes(node)))

    visit_ListComp = visit_SetComp = visit_DictComp = visit_GeneratorExp = _comprehension  # type: ignore[assignment]

    def visit_Import(self, node: ast.Import) -> None:
        if self._depth == 0:
            self.writes.update((a.asname or a.name.split(".")[0]) for a in node.names)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if self._depth == 0:
            self.writes.update((a.asname or a.name) for a in node.names)

    def visit_ExceptHandler(self, node: ast.ExceptHandler) -> None:
        if node.name and self._depth == 0:
            self.writes.add(node.name)
        self.generic_visit(node)


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


def render_notebook(params: list[Param], features: list[Feature]) -> RenderedNotebook:
    if not features:
        raise NotebookError("还没有任何特征，无法生成模型。请先用 upsert_feature 写至少一个特征")
    param_names = [p.name for p in params]
    for f in features:
        _check_slug_role(f)
    slugs = [f.slug for f in features]
    if len(set(slugs)) != len(slugs):
        raise NotebookError("特征名有重复")
    analysed = {f.slug: _analyse(f) for f in features}

    lines = HEADER.splitlines()
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

    last = features[-1].var
    add_cell([last], [f'model = scad.Part(part_id="model", body={last})', "return (model,)"])
    text = "\n".join(lines) + "\n" + FOOTER
    return RenderedNotebook(text=text, cell_lines=cell_lines)
