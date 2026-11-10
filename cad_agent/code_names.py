"""代码里读了哪些名字、在最外层给哪些名字赋了值（拼 notebook 时推断每个 cell 的输入用）。"""

from __future__ import annotations

import ast


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
