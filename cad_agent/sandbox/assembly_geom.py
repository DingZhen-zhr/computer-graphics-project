"""子进程里装配要用的几何：连接点取几何、按矩阵摆放、重叠体积、最短距离（笔记第 24、25、27 节）。

摆好的零件只用 OCP 形状量（SCA 的 Solid 不能从 OCP 形状构造）；截图要 Solid，用 SCA 的转动、平移摆。
"""

from __future__ import annotations

import math
from typing import Any

from OCP.Bnd import Bnd_Box
from OCP.BRepAdaptor import BRepAdaptor_Curve, BRepAdaptor_Surface
from OCP.BRepAlgoAPI import BRepAlgoAPI_Common
from OCP.BRepBndLib import BRepBndLib
from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform
from OCP.BRepExtrema import BRepExtrema_DistShapeShape
from OCP.BRepGProp import BRepGProp
from OCP.GProp import GProp_GProps
from OCP.gp import gp_Trsf

TYPE_CN = {"PLANE": "平面", "CYLINDER": "圆柱面", "CIRCLE": "圆形的边", "LINE": "直线边", "CONE": "圆锥面",
           "SPHERE": "球面", "TORUS": "圆环面", "BSPLINESURFACE": "自由曲面", "BSPLINECURVE": "自由曲线"}
ANCHOR_TYPES = {"faces": ("PLANE", "CYLINDER"), "edges": ("CIRCLE",)}


def _xyz(p: Any) -> tuple[float, float, float]:
    return (float(p.X()), float(p.Y()), float(p.Z()))


def geom_type(entity: Any, kind: str) -> str:
    if kind == "faces":
        return BRepAdaptor_Surface(entity.wrapped).GetType().name.removeprefix("GeomAbs_").upper()
    return BRepAdaptor_Curve(entity.wrapped).GetType().name.removeprefix("GeomAbs_").upper()


def anchor_geometry(entity: Any, kind: str) -> tuple[str, tuple, tuple]:
    """连接点挂的几何：(类型, 中心, 方向)。圆柱面取轴线（原点是面中心投到轴上的点），平面取中心和朝外的法向，圆形的边取圆心和法向。"""
    t = geom_type(entity, kind)
    if t == "CYLINDER":
        ax = BRepAdaptor_Surface(entity.wrapped).Cylinder().Axis()
        p, d = _xyz(ax.Location()), _xyz(ax.Direction())
        c = entity.get_center()
        k = (c.x - p[0]) * d[0] + (c.y - p[1]) * d[1] + (c.z - p[2]) * d[2]
        return t, (p[0] + k * d[0], p[1] + k * d[1], p[2] + k * d[2]), d
    if t == "PLANE":
        c, n = entity.get_center(), entity.get_normal_at()
        return t, (c.x, c.y, c.z), (n.x, n.y, n.z)
    if t == "CIRCLE":
        ax = BRepAdaptor_Curve(entity.wrapped).Circle().Axis()
        return t, _xyz(ax.Location()), _xyz(ax.Direction())
    raise ValueError(t)


def placed(shape: Any, m: list[float]) -> Any:
    """OCP 形状按 4×4 矩阵（16 个数，按行）摆好，返回新的 OCP 形状。"""
    tr = gp_Trsf()
    tr.SetValues(*m[:12])
    return BRepBuilderAPI_Transform(shape, tr, True).Shape()


def placed_solid(solid: Any, m: list[float]) -> Any:
    """SCA 的 Solid 按矩阵摆好（截图用）：拆成绕 x、y、z 三次转动再平移。"""
    import simplecadapi as scad

    r20 = max(-1.0, min(1.0, m[8]))
    b = -math.asin(r20)
    if abs(math.cos(b)) > 1e-9:
        a, c = math.atan2(m[4], m[0]), math.atan2(m[9], m[10])
    else:
        a, c = math.atan2(-m[1], m[5]), 0.0
    out = solid
    for ang, axis in ((c, (1, 0, 0)), (b, (0, 1, 0)), (a, (0, 0, 1))):
        if abs(ang) > 1e-12:
            out = scad.rotate_shape(shape=out, angle=math.degrees(ang), axis=axis, origin=(0, 0, 0))
    return scad.translate_shape(shape=out, vector=(m[3], m[7], m[11]))


def bbox(shape: Any) -> Bnd_Box:
    box = Bnd_Box()
    BRepBndLib.Add_s(shape, box)
    return box


def overlap_volume(a: Any, b: Any, box_a: Bnd_Box | None = None, box_b: Bnd_Box | None = None) -> float:
    """两个摆好的形状重叠的体积；包围盒不相交时直接是 0。算不出来时抛 RuntimeError。"""
    if (box_a or bbox(a)).IsOut(box_b or bbox(b)):
        return 0.0
    op = BRepAlgoAPI_Common(a, b)
    op.Build()
    if not op.IsDone():
        raise RuntimeError("求重叠体积的布尔运算没有算成")
    props = GProp_GProps()
    BRepGProp.VolumeProperties_s(op.Shape(), props)
    return max(0.0, float(props.Mass()))


def min_distance(a: Any, b: Any) -> float:
    d = BRepExtrema_DistShapeShape(a, b)
    d.Perform()
    if not d.IsDone():
        raise RuntimeError("求最短距离没有算成")
    return float(d.Value())


def line_distance_angle(p1, d1, p2, d2) -> tuple[float, float]:
    """两条轴线的距离和夹角（度，0～90，不分方向）。平行时距离是点到线的距离。"""
    def dot(u, v): return u[0] * v[0] + u[1] * v[1] + u[2] * v[2]
    def sub(u, v): return (u[0] - v[0], u[1] - v[1], u[2] - v[2])
    def cross(u, v): return (u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0])
    def norm(u): return math.sqrt(dot(u, u))
    ang = math.degrees(math.acos(min(1.0, abs(dot(d1, d2)) / (norm(d1) * norm(d2)))))
    w = sub(p2, p1)
    n = cross(d1, d2)
    if norm(n) < 1e-9:
        return norm(cross(w, d1)) / norm(d1), ang
    return abs(dot(w, n)) / norm(n), ang


def plane_distance_angle(c1, n1, c2, n2) -> tuple[float, float]:
    """两个平面的距离（第二个面的中心到第一个面）和法向夹角（度，0～90，不分朝向）。"""
    nn = math.sqrt(n1[0] ** 2 + n1[1] ** 2 + n1[2] ** 2)
    dist = abs((c2[0] - c1[0]) * n1[0] + (c2[1] - c1[1]) * n1[1] + (c2[2] - c1[2]) * n1[2]) / nn
    cos = abs(n1[0] * n2[0] + n1[1] * n2[1] + n1[2] * n2[2]) / (nn * math.sqrt(n2[0] ** 2 + n2[1] ** 2 + n2[2] ** 2))
    return dist, math.degrees(math.acos(min(1.0, cos)))
