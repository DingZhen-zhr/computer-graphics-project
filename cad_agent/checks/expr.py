"""检查项里表达式的解析与求值：只认白名单里的写法。纯 Python，不依赖 SCA。

从 checks/spec.py 拆出来；公开的名字仍然可以从 cad_agent.checks.spec 导入。
"""

from __future__ import annotations

import ast
import math
from typing import Any, Mapping

MAX_EXPR_LEN = 200


class CheckSpecError(ValueError):
    """检查项写得不对；信息是中文，直接返回给模型。"""


_FUNCS: dict[str, Any] = {
    "sin": math.sin, "cos": math.cos, "tan": math.tan, "asin": math.asin, "acos": math.acos, "atan": math.atan,
    "radians": math.radians, "degrees": math.degrees, "sqrt": math.sqrt, "abs": abs, "min": min, "max": max,
}
_CONSTS = {"pi": math.pi}
_BINOPS = (ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Pow)


def _parse_expr(expr: str | float) -> ast.Expression:
    if isinstance(expr, bool) or not isinstance(expr, (int, float, str)):
        raise CheckSpecError(f"表达式必须是数字或文字，收到 {expr!r}")
    text = repr(float(expr)) if not isinstance(expr, str) else expr.strip()
    if not text or len(text) > MAX_EXPR_LEN:
        raise CheckSpecError(f"表达式不能为空，也不能超过 {MAX_EXPR_LEN} 个字符")
    try:
        tree = ast.parse(text, mode="eval")
    except SyntaxError as e:
        raise CheckSpecError(f"表达式 {text!r} 写法不对：{e.msg}") from e
    _validate(tree.body, text)
    return tree


def _validate(node: ast.AST, text: str) -> None:
    ok_hint = "表达式里只能用：数字、参数名、+ - * / **、括号、sin cos tan asin acos atan radians degrees sqrt abs min max、pi"
    if isinstance(node, ast.Constant):
        if isinstance(node.value, bool) or not isinstance(node.value, (int, float)):
            raise CheckSpecError(f"表达式 {text!r} 里有不能用的常量 {node.value!r}。{ok_hint}")
    elif isinstance(node, ast.Name):
        pass
    elif isinstance(node, ast.BinOp) and isinstance(node.op, _BINOPS):
        _validate(node.left, text)
        _validate(node.right, text)
    elif isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
        _validate(node.operand, text)
    elif isinstance(node, ast.Call):
        if not isinstance(node.func, ast.Name) or node.func.id not in _FUNCS or node.keywords:
            raise CheckSpecError(f"表达式 {text!r} 里调用了不能用的函数。{ok_hint}")
        for arg in node.args:
            _validate(arg, text)
    else:
        raise CheckSpecError(f"表达式 {text!r} 里有不能用的写法（{type(node).__name__}）。{ok_hint}")


def expr_names(expr: str | float) -> set[str]:
    """表达式里用到的参数名（不含函数名和 pi）。写法不合法时抛 CheckSpecError。"""
    tree = _parse_expr(expr)
    funcs = {n.func.id for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
    return {n.id for n in ast.walk(tree) if isinstance(n, ast.Name) and n.id not in funcs and n.id not in _CONSTS}


def _eval(node: ast.AST, values: Mapping[str, float], text: str) -> float:
    if isinstance(node, ast.Constant):
        return float(node.value)
    if isinstance(node, ast.Name):
        if node.id in _CONSTS:
            return _CONSTS[node.id]
        if node.id not in values:
            raise CheckSpecError(f"表达式 {text!r} 里用到了不存在的参数 {node.id}")
        return float(values[node.id])
    if isinstance(node, ast.UnaryOp):
        v = _eval(node.operand, values, text)
        return -v if isinstance(node.op, ast.USub) else v
    if isinstance(node, ast.BinOp):
        a, b = _eval(node.left, values, text), _eval(node.right, values, text)
        if isinstance(node.op, ast.Add):
            return a + b
        if isinstance(node.op, ast.Sub):
            return a - b
        if isinstance(node.op, ast.Mult):
            return a * b
        if isinstance(node.op, ast.Div):
            if b == 0:
                raise CheckSpecError(f"表达式 {text!r} 里除以了 0")
            return a / b
        if abs(b) > 100:
            raise CheckSpecError(f"表达式 {text!r} 里的乘方次数太大")
        return a**b
    if isinstance(node, ast.Call):
        args = [_eval(a, values, text) for a in node.args]
        try:
            return float(_FUNCS[node.func.id](*args))  # type: ignore[union-attr]
        except (TypeError, ValueError, OverflowError) as e:
            raise CheckSpecError(f"表达式 {text!r} 里 {node.func.id} 的参数不对：{e}") from e  # type: ignore[union-attr]
    raise CheckSpecError(f"表达式 {text!r} 无法计算")


def eval_expr(expr: str | float, values: Mapping[str, float]) -> float:
    """用白名单求值：数字、参数名、四则乘方、括号、若干数学函数、pi。其余一律报错。"""
    tree = _parse_expr(expr)
    text = expr.strip() if isinstance(expr, str) else repr(float(expr))
    try:
        result = _eval(tree.body, values, text)
    except OverflowError as e:
        raise CheckSpecError(f"表达式 {text!r} 的结果太大") from e
    if not math.isfinite(result):
        raise CheckSpecError(f"表达式 {text!r} 的结果不是有限的数")
    return result
