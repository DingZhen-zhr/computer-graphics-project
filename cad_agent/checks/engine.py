"""测量引擎：在运行模型的子进程里用 SCA 和 OCP 做测量。

写法依据 docs/sca-api-notes.md 第 4、5、6、14 节。
"""

from __future__ import annotations

import math
from typing import Any, Mapping

from OCP.BRep import BRep_Builder
from OCP.BRepAdaptor import BRepAdaptor_Curve, BRepAdaptor_Surface
from OCP.BRepClass3d import BRepClass3d_SolidClassifier
from OCP.BRepExtrema import BRepExtrema_DistShapeShape
from OCP.gp import gp_Pnt
from OCP.TopAbs import TopAbs_IN, TopAbs_ON, TopAbs_OUT
from OCP.TopoDS import TopoDS_Compound
from simplecadapi import ql
from simplecadapi.inspect import brep

from cad_agent.checks.spec import Check, CheckResult, eval_expr, parse_where

CARD_LIMIT = 8  # 选中几何的说明里最多列几个
EPS = 1e-9
KIND_CN = {"faces": "面", "edges": "边"}
AXIS_INDEX = {"x": 0, "y": 1, "z": 2}
POINT_TOL = 1e-6


# ---------------------------------------------------------------- 选择与描述


def _r(v: float, n: int = 4) -> float:
    return round(float(v), n) + 0.0  # + 0.0 把 -0.0 变成 0.0


def _surface_type(face: Any) -> str:
    return BRepAdaptor_Surface(face.wrapped).GetType().name.removeprefix("GeomAbs_").upper()


def _curve_type(edge: Any) -> str:
    return BRepAdaptor_Curve(edge.wrapped).GetType().name.removeprefix("GeomAbs_").upper()


def _select(solid: Any, kind: str, where: list[list], values: Mapping[str, float]) -> list[Any]:
    """按 where 条件选面或边，返回实体列表。条件里的表达式用 values 求值。"""
    where = parse_where(where, set(values))
    preds = []
    for path, op, value in where:
        preds.append(ql.prop(path, op, value if path == "geom.type" else eval_expr(value, values)))
    base = ql.faces() if kind == "faces" else ql.edges()
    if preds:
        base = base.where(preds[0] if len(preds) == 1 else ql.and_(*preds))
    return list(base.resolve(solid))


def _describe(entity: Any, kind: str) -> dict:
    c = entity.get_center()
    item: dict = {"center": [_r(c.x), _r(c.y), _r(c.z)]}
    if kind == "faces":
        t = _surface_type(entity)
        item = {"type": t, "center": item["center"], "area": _r(entity.get_area())}
        if t == "PLANE":
            n = entity.get_normal_at()
            item["normal"] = [_r(n.x), _r(n.y), _r(n.z)]
    else:
        item = {"type": _curve_type(entity), "center": item["center"], "length": _r(entity.get_length())}
    return item


def _card_line(i: int, item: dict) -> str:
    c = item["center"]
    size = f"面积 {item['area']:g}" if "area" in item else f"长度 {item['length']:g}"
    normal = f" 法向({item['normal'][0]:g}, {item['normal'][1]:g}, {item['normal'][2]:g})" if "normal" in item else ""
    return f"[{i}] {item['type']} 中心({c[0]:g}, {c[1]:g}, {c[2]:g}) {size}{normal}"


def _card(entities: list[Any], kind: str) -> str:
    """被选中几何的说明：个数，以及最多 CARD_LIMIT 个的类型、中心和尺寸。"""
    n = len(entities)
    if n == 0:
        return "选中 0 个"
    shown = [_card_line(i, _describe(e, kind)) for i, e in enumerate(entities[:CARD_LIMIT], 1)]
    head = f"选中 {n} 个" if n <= CARD_LIMIT else f"选中 {n} 个，只列前 {CARD_LIMIT} 个（共 {n} 个）"
    return head + "：" + "；".join(shown)


def query(solid: Any, kind: str, where: list, values: Mapping[str, float]) -> list[dict]:
    """列出满足条件的面或边：类型、中心、面积或长度，平面还有法向。"""
    return [_describe(e, kind) for e in _select(solid, kind, where, values)]


def body_facts(solid: Any) -> dict:
    """整体事实：包围盒、三向尺寸、体积、面数、边数。"""
    i = brep.inspect_shape_rbrepinspection(solid.wrapped)
    bb = [float(v) for v in i.bounding_box]
    return {
        "bbox": bb,
        "size": [bb[3] - bb[0], bb[4] - bb[1], bb[5] - bb[2]],
        "volume": float(i.volume),
        "n_faces": int(i.counts["unique_faces"]),
        "n_edges": int(i.counts["unique_edges"]),
    }


# ---------------------------------------------------------------- 各类检查


def _within(measured: float, expected: float, tol: float) -> bool:
    return abs(measured - expected) <= tol + EPS


def _compare(measured: float, expected: float, op: str, tol: float = 0.0) -> bool:
    if op == "==":
        return abs(measured - expected) <= tol + EPS
    if op == ">=":
        return measured >= expected - tol - EPS
    return measured <= expected + tol + EPS


def _check_bbox(solid: Any, c: Check, values: Mapping[str, float]) -> CheckResult:
    axis = c.args["axis"]
    expected = eval_expr(c.expected, values)  # type: ignore[arg-type]
    size = body_facts(solid)["size"][AXIS_INDEX[axis]]
    ok = _within(size, expected, c.tol or 0.0)
    return CheckResult(c.id, c.type, ok, size, expected, c.tol, f"{axis} 向尺寸 {size:.4f}，期望 {expected:.4f}，容差 ±{c.tol:g}")


def _check_count(solid: Any, c: Check, values: Mapping[str, float]) -> CheckResult:
    kind = c.args["kind"]
    expected = eval_expr(c.expected, values)  # type: ignore[arg-type]
    found = _select(solid, kind, c.args["where"], values)
    ok = _compare(len(found), expected, c.op)
    return CheckResult(c.id, c.type, ok, float(len(found)), expected, None,
                       f"满足条件的{KIND_CN[kind]}有 {len(found)} 个，期望 {c.op} {expected:g}。{_card(found, kind)}")


def _biggest_plane(solid: Any, where: list, name: str, values: Mapping[str, float]) -> tuple[Any | None, str]:
    faces = _select(solid, "faces", where, values)
    planes = [f for f in faces if _surface_type(f) == "PLANE"]
    if not planes:
        extra = f"（条件选中了 {len(faces)} 个面，但都不是平面）" if faces else ""
        return None, f"{name} 选中 0 个平面{extra}，没有可测的面。请检查 {name} 的 where 条件"
    face = max(planes, key=lambda f: f.get_area())
    return face, f"{name}：{_card_line(1, _describe(face, 'faces'))}（共选中 {len(planes)} 个平面，取面积最大的）"


def _check_angle(solid: Any, c: Check, values: Mapping[str, float]) -> CheckResult:
    expected = eval_expr(c.expected, values)  # type: ignore[arg-type]
    fa, msg_a = _biggest_plane(solid, c.args["a"], "a", values)
    fb, msg_b = _biggest_plane(solid, c.args["b"], "b", values)
    if fa is None or fb is None:
        return CheckResult(c.id, c.type, False, None, expected, c.tol, "；".join(m for f, m in ((fa, msg_a), (fb, msg_b)) if f is None))
    na, nb = fa.get_normal_at(), fb.get_normal_at()
    dot = na.x * nb.x + na.y * nb.y + na.z * nb.z
    angle = math.degrees(math.acos(max(-1.0, min(1.0, dot))))
    ok = _within(angle, expected, c.tol or 0.0)
    return CheckResult(c.id, c.type, ok, angle, expected, c.tol,
                       f"两个平面法向夹角 {angle:.4f}°，期望 {expected:.4f}°，容差 ±{c.tol:g}°。{msg_a}；{msg_b}")


def _check_point(solid: Any, c: Check, values: Mapping[str, float]) -> CheckResult:
    x, y, z = (eval_expr(v, values) for v in c.args["point"])
    state = BRepClass3d_SolidClassifier(solid.wrapped, gp_Pnt(x, y, z), POINT_TOL).State()
    where_is = {TopAbs_IN: "材料里", TopAbs_OUT: "材料外", TopAbs_ON: "材料表面上"}[state]
    ok = state in (TopAbs_IN, TopAbs_ON) if c.type == "point_inside" else state == TopAbs_OUT
    want = "在材料里（含表面）" if c.type == "point_inside" else "在材料外"
    return CheckResult(c.id, c.type, ok, None, None, None, f"点 ({x:g}, {y:g}, {z:g}) 实际在{where_is}，要求{want}")


def _compound(entities: list[Any]) -> TopoDS_Compound:
    builder, comp = BRep_Builder(), TopoDS_Compound()
    builder.MakeCompound(comp)
    for e in entities:
        builder.Add(comp, e.wrapped)
    return comp


def _check_distance(solid: Any, c: Check, values: Mapping[str, float]) -> CheckResult:
    expected = eval_expr(c.expected, values)  # type: ignore[arg-type]
    sides = {}
    for name in ("a", "b"):
        spec = c.args[name]
        sides[name] = (_select(solid, spec["kind"], spec["where"], values), spec["kind"])
    empty = [n for n, (ents, _) in sides.items() if not ents]
    if empty:
        return CheckResult(c.id, c.type, False, None, expected, c.tol, "；".join(f"{n} 选中 0 个，没有可测的几何。请检查 {n} 的 where 条件" for n in empty))
    d = BRepExtrema_DistShapeShape(_compound(sides["a"][0]), _compound(sides["b"][0]))
    d.Perform()
    if not d.IsDone():
        return CheckResult(c.id, c.type, False, None, expected, c.tol, "OCC 没能算出这两组几何的最小距离")
    dist = float(d.Value())
    ok = _compare(dist, expected, c.op, c.tol or 0.0)
    return CheckResult(c.id, c.type, ok, dist, expected, c.tol,
                       f"最小距离 {dist:.4f}，期望 {c.op} {expected:.4f}，容差 ±{c.tol:g}。a {_card(*sides['a'])}；b {_card(*sides['b'])}")


def _check_volume(solid: Any, c: Check, values: Mapping[str, float]) -> CheckResult:
    expected = eval_expr(c.expected, values)  # type: ignore[arg-type]
    volume = body_facts(solid)["volume"]
    ok = abs(volume - expected) <= (c.tol or 0.0) * abs(expected) + EPS
    return CheckResult(c.id, c.type, ok, volume, expected, c.tol, f"体积 {volume:.3f}，期望 {expected:.3f}，相对容差 {(c.tol or 0) * 100:g}%")


def _mandatory(solid: Any, c: Check) -> CheckResult:
    i = brep.inspect_shape_rbrepinspection(solid.wrapped)
    if c.id == "valid":
        return CheckResult(c.id, c.type, bool(i.valid), None, None, None, "几何体有效" if i.valid else "几何体无效（OCC 判定拓扑或几何有问题）")
    if c.id == "single_solid":
        n = int(i.counts["solid"])
        return CheckResult(c.id, c.type, n == 1, float(n), 1.0, None, f"模型里有 {n} 个实体，应当只有 1 个")
    v = float(i.volume)
    return CheckResult(c.id, c.type, v > 0, v, None, None, f"体积 {v:.3f}，应当大于 0")


_DISPATCH = {
    "bbox": _check_bbox, "count": _check_count, "angle": _check_angle, "point_inside": _check_point,
    "point_outside": _check_point, "distance": _check_distance, "volume": _check_volume,
}


def run_checks(solid: Any, checks: list[Check], values: Mapping[str, float]) -> list[CheckResult]:
    """逐条运行检查。每条各自捕获异常：出错的检查算不通过，原因写进 detail。"""
    results: list[CheckResult] = []
    for c in checks:
        try:
            if c.type in _DISPATCH:
                results.append(_DISPATCH[c.type](solid, c, values))
            else:
                results.append(_mandatory(solid, c))
        except Exception as e:  # noqa: BLE001 - 单条检查出错不能拖垮整次检查，原因会写进结果
            expected = None
            if c.expected is not None:
                try:
                    expected = eval_expr(c.expected, values)
                except Exception:  # noqa: BLE001 - 期望值本身算不出来时，只是不填
                    expected = None
            results.append(CheckResult(c.id, c.type, False, None, expected, c.tol, f"检查执行出错（{type(e).__name__}）：{e}"))
    return results
