"""检查项的格式、表达式求值、覆盖规则。纯 Python，不依赖 SCA。

检查项由模型通过 set_checks 写入；测量由 checks/engine.py 在子进程里完成。
"""

from __future__ import annotations

import ast
import math
import re
from dataclasses import dataclass, field
from typing import Any, Mapping

CHECK_TYPES = {"bbox", "count", "angle", "point_inside", "point_outside", "distance", "volume"}
MANDATORY_IDS = ("valid", "single_solid", "positive_volume")
ID_RE = re.compile(r"^[a-z][a-z0-9_-]*$")
KNOWN_KEYS = {"id", "type", "axis", "kind", "where", "a", "b", "point", "expected", "op", "tol", "rel_tol"}
COUNT_OPS = ("==", ">=", "<=")
WHERE_OPS = ("==", "!=", ">=", "<=", ">", "<")
GEOM_PATHS = (
    "geom.type", "geom.center.x", "geom.center.y", "geom.center.z",
    "geom.normal.x", "geom.normal.y", "geom.normal.z", "geom.area", "geom.length",
)
DEFAULT_TOL = {"bbox": 0.1, "angle": 0.5, "distance": 0.1, "volume": 0.01}
MAX_EXPR_LEN = 200


class CheckSpecError(ValueError):
    """检查项写得不对；信息是中文，直接返回给模型。"""


# ---------------------------------------------------------------- 表达式

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


# ---------------------------------------------------------------- 数据结构


@dataclass
class Check:
    id: str
    type: str
    args: dict
    expected: str | float | None
    tol: float | None
    op: str
    refs: set[str] = field(default_factory=set)


@dataclass
class CheckResult:
    id: str
    type: str
    passed: bool
    measured: float | None
    expected: float | None
    tol: float | None
    detail: str

    def to_dict(self) -> dict:
        return {
            "id": self.id, "type": self.type, "passed": self.passed, "measured": self.measured,
            "expected": self.expected, "tol": self.tol, "detail": self.detail,
        }

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> "CheckResult":
        return cls(d["id"], d["type"], bool(d["passed"]), d.get("measured"), d.get("expected"), d.get("tol"), d.get("detail", ""))


# ---------------------------------------------------------------- 解析


class _Ctx:
    """解析一条检查时的上下文：标签（用于报错）、可用参数名、收集到的引用。"""

    def __init__(self, label: str, params: set[str]) -> None:
        self.label, self.params, self.refs = label, params, set()

    def expr(self, value: Any, what: str) -> str | float:
        try:
            names = expr_names(value)
        except CheckSpecError as e:
            raise CheckSpecError(f"{self.label}的 {what}：{e}") from e
        unknown = sorted(names - self.params)
        if unknown:
            avail = "、".join(sorted(self.params)) or "（没有参数）"
            raise CheckSpecError(f"{self.label}的 {what} 用到了不存在的参数 {'、'.join(unknown)}；可用参数：{avail}")
        self.refs |= names
        return value.strip() if isinstance(value, str) else float(value)

    def where(self, raw: Any, what: str) -> list[list]:
        if not isinstance(raw, list):
            raise CheckSpecError(f"{self.label}的 {what} 必须是条件数组，每条写成 [属性, 比较符, 值]")
        out: list[list] = []
        for cond in raw:
            if not isinstance(cond, (list, tuple)) or len(cond) != 3:
                raise CheckSpecError(f"{self.label}的 {what} 里每个条件必须是三项 [属性, 比较符, 值]，收到 {cond!r}")
            path, op, value = cond
            if not isinstance(path, str) or not path.startswith("geom."):
                raise CheckSpecError(f"{self.label}的 {what}：属性路径必须以 geom. 开头，收到 {path!r}")
            if path not in GEOM_PATHS:
                raise CheckSpecError(f"{self.label}的 {what}：没有属性 {path}（选不到任何东西）。可用属性：{'、'.join(GEOM_PATHS)}")
            if op not in WHERE_OPS:
                raise CheckSpecError(f"{self.label}的 {what}：比较符 {op!r} 不对，只能是 {' '.join(WHERE_OPS)}")
            if path == "geom.type":
                if op not in ("==", "!="):
                    raise CheckSpecError(f"{self.label}的 {what}：geom.type 只能用 == 或 !=")
                if not isinstance(value, str) or not re.fullmatch(r"[A-Z_]+", value):
                    raise CheckSpecError(f"{self.label}的 {what}：geom.type 的值要写大写字样，如 PLANE、CYLINDER，收到 {value!r}")
                out.append([path, op, value])
            else:
                out.append([path, op, self.expr(value, f"{what} 里 {path} 的值")])
        return out

    def target(self, raw: Any, what: str) -> dict:
        if not isinstance(raw, dict):
            raise CheckSpecError(f"{self.label}的 {what} 必须写成 {{\"kind\": \"faces\", \"where\": [...]}}")
        kind = raw.get("kind")
        if kind not in ("faces", "edges"):
            raise CheckSpecError(f"{self.label}的 {what} 缺少 kind，或写错了：只能是 faces 或 edges")
        if "where" not in raw:
            raise CheckSpecError(f"{self.label}的 {what} 缺少 where")
        return {"kind": kind, "where": self.where(raw["where"], f"{what}.where")}


def _tol(item: dict, ctx: _Ctx, key: str, default: float | None) -> float | None:
    if key not in item:
        return default
    v = item[key]
    if isinstance(v, bool) or not isinstance(v, (int, float)) or v < 0 or not math.isfinite(v):
        raise CheckSpecError(f"{ctx.label}的 {key} 必须是不小于 0 的数，收到 {v!r}")
    return float(v)


def _need(item: dict, key: str, ctx: _Ctx) -> Any:
    if key not in item:
        raise CheckSpecError(f"{ctx.label}缺少 {key}")
    return item[key]


def _op(item: dict, ctx: _Ctx, allowed: tuple[str, ...] | None) -> str:
    op = item.get("op", "==")
    if allowed is None:
        if op != "==":
            raise CheckSpecError(f"{ctx.label}的类型不支持 op={op!r}；只有 count 和 distance 可以写 op，其余类型按容差判断")
        return "=="
    if op not in allowed:
        raise CheckSpecError(f"{ctx.label}的 op 只能是 {'、'.join(allowed)}，收到 {op!r}")
    return op


def _parse_one(item: Any, idx: int, params: set[str]) -> Check:
    if not isinstance(item, dict):
        raise CheckSpecError(f"第 {idx} 条检查必须是对象，收到 {item!r}")
    cid = item.get("id")
    if not isinstance(cid, str) or not ID_RE.match(cid):
        raise CheckSpecError(f"第 {idx} 条检查的 id 不合法：要用小写字母开头，只含小写字母、数字、下划线、短横线，收到 {cid!r}")
    ctx = _Ctx(f"检查 {cid}", params)
    unknown = sorted(set(item) - KNOWN_KEYS)
    if unknown:
        raise CheckSpecError(f"{ctx.label}里有不认识的字段 {'、'.join(unknown)}；可用字段：{'、'.join(sorted(KNOWN_KEYS))}")
    ctype = item.get("type")
    if ctype not in CHECK_TYPES:
        raise CheckSpecError(f"{ctx.label}的 type {ctype!r} 不对（缺少 type 或写错了），只能是：{'、'.join(sorted(CHECK_TYPES))}")

    args: dict = {}
    expected: str | float | None = None
    tol: float | None = None
    op = "=="
    if ctype == "bbox":
        axis = _need(item, "axis", ctx)
        if axis not in ("x", "y", "z"):
            raise CheckSpecError(f"{ctx.label}的 axis 只能是 x、y、z，收到 {axis!r}")
        args = {"axis": axis}
        expected = ctx.expr(_need(item, "expected", ctx), "expected")
        tol, op = _tol(item, ctx, "tol", DEFAULT_TOL["bbox"]), _op(item, ctx, None)
    elif ctype == "count":
        kind = _need(item, "kind", ctx)
        if kind not in ("faces", "edges"):
            raise CheckSpecError(f"{ctx.label}的 kind 只能是 faces 或 edges，收到 {kind!r}")
        args = {"kind": kind, "where": ctx.where(_need(item, "where", ctx), "where")}
        expected = ctx.expr(_need(item, "expected", ctx), "expected")
        op = _op(item, ctx, COUNT_OPS)
    elif ctype == "angle":
        args = {"a": ctx.where(_need(item, "a", ctx), "a"), "b": ctx.where(_need(item, "b", ctx), "b")}
        expected = ctx.expr(_need(item, "expected", ctx), "expected")
        tol, op = _tol(item, ctx, "tol", DEFAULT_TOL["angle"]), _op(item, ctx, None)
    elif ctype in ("point_inside", "point_outside"):
        point = _need(item, "point", ctx)
        if not isinstance(point, list) or len(point) != 3:
            raise CheckSpecError(f"{ctx.label}的 point 必须是三个数或表达式 [x, y, z]")
        args = {"point": [ctx.expr(v, "point") for v in point]}
    elif ctype == "distance":
        args = {"a": ctx.target(_need(item, "a", ctx), "a"), "b": ctx.target(_need(item, "b", ctx), "b")}
        expected = ctx.expr(_need(item, "expected", ctx), "expected")
        tol, op = _tol(item, ctx, "tol", DEFAULT_TOL["distance"]), _op(item, ctx, COUNT_OPS)
    else:  # volume
        expected = ctx.expr(_need(item, "expected", ctx), "expected")
        tol, op = _tol(item, ctx, "rel_tol", DEFAULT_TOL["volume"]), _op(item, ctx, None)
    return Check(cid, ctype, args, expected, tol, op, ctx.refs)


def parse_where(raw: Any, param_names: set[str]) -> list[list]:
    """单独校验一组 where 条件（inspect 工具和测量引擎用）。"""
    return _Ctx("查询", set(param_names)).where(raw, "where")


def parse_checks(raw: list[dict], param_names: set[str]) -> list[Check]:
    """解析模型写的检查项；结果总是以三条必做检查开头。"""
    if not isinstance(raw, list):
        raise CheckSpecError("checks 必须是数组")
    out = [Check(i, i, {}, None, None, "==", set()) for i in MANDATORY_IDS]
    seen = set(MANDATORY_IDS)
    for idx, item in enumerate(raw, 1):
        c = _parse_one(item, idx, set(param_names))
        if c.id in MANDATORY_IDS:
            raise CheckSpecError(f"id {c.id} 是程序自动加的必做检查，不用写，也不能占用这个名字")
        if c.id in seen:
            raise CheckSpecError(f"检查 id {c.id} 重复了")
        seen.add(c.id)
        out.append(c)
    return out


def missing_coverage(checks: list[Check], user_params: set[str]) -> set[str]:
    """哪些用户给的参数没有被任何检查引用。"""
    covered: set[str] = set()
    for c in checks:
        covered |= c.refs
    return set(user_params) - covered
