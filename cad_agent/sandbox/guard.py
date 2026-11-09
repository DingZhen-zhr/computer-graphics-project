"""特征代码的静态检查，以及子进程环境变量的清理。"""

from __future__ import annotations

import ast
from typing import Iterable, Mapping

FORBIDDEN_NAMES = frozenset({
    "open", "exec", "eval", "compile", "__import__", "input", "globals", "locals", "vars",
    "getattr", "setattr", "delattr", "breakpoint",
})
SECRET_MARKERS = ("KEY", "TOKEN", "SECRET", "PASSWORD")


class _Guard(ast.NodeVisitor):
    def __init__(self) -> None:
        self.problems: list[tuple[int, str]] = []
        self._in_function = 0

    def _add(self, node: ast.AST, msg: str) -> None:
        self.problems.append((getattr(node, "lineno", 0), msg))

    def visit_Import(self, node: ast.Import) -> None:
        self._add(node, "特征代码里不能写 import；scad（SimpleCADAPI）、ql（选择器）、math 已经可以直接用")

    visit_ImportFrom = visit_Import  # type: ignore[assignment]

    def visit_Name(self, node: ast.Name) -> None:
        if node.id in FORBIDDEN_NAMES:
            self._add(node, f"不能使用 {node.id}（与建模无关的文件、执行或反射类功能一律禁止）")
        elif node.id.startswith("__"):
            self._add(node, f"不能使用以双下划线开头的名字 {node.id}")

    def visit_Attribute(self, node: ast.Attribute) -> None:
        if node.attr.startswith("__"):
            self._add(node, f"不能访问以双下划线开头的属性 {node.attr}")
        self.generic_visit(node)

    def _function(self, node: ast.AST) -> None:
        self._in_function += 1
        self.generic_visit(node)
        self._in_function -= 1

    visit_FunctionDef = visit_AsyncFunctionDef = visit_Lambda = _function  # type: ignore[assignment]

    def visit_Return(self, node: ast.Return) -> None:
        if not self._in_function:
            self._add(node, "特征代码的最外层不能写 return；直接把结果赋给与 slug 同名的变量即可")
        self.generic_visit(node)

    def _yield(self, node: ast.AST) -> None:
        if not self._in_function:
            self._add(node, "特征代码的最外层不能写 yield")
        self.generic_visit(node)

    visit_Yield = visit_YieldFrom = visit_Await = _yield  # type: ignore[assignment]


def check_code(code: str) -> list[str]:
    """检查一段特征代码；返回中文问题列表，空列表表示通过。"""
    try:
        tree = ast.parse(code.replace("\r\n", "\n"))
    except SyntaxError as e:
        return [f"第 {e.lineno} 行有语法错误：{e.msg}"]
    guard = _Guard()
    guard.visit(tree)
    return [f"第 {line} 行：{msg}" for line, msg in sorted(guard.problems, key=lambda p: p[0])]


def clean_env(env: Mapping[str, str], secret_names: Iterable[str]) -> dict[str, str]:
    """去掉 secret_names 里的变量，以及名字里含 KEY、TOKEN、SECRET、PASSWORD 的变量（不区分大小写）。"""
    secrets = {n.upper() for n in secret_names}
    return {
        k: v for k, v in env.items()
        if k.upper() not in secrets and not any(m in k.upper() for m in SECRET_MARKERS)
    }
