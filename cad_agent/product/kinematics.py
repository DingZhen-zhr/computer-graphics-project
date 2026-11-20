"""摆放、关节姿态、取样、炸开方向。纯 Python，不依赖 SCA（设计文档第 5.4、5.5 节）。

约定：三维变换都是 4×4 矩阵，按行展开成 16 个数（Mat）；装好后的坐标是 ground 零件的坐标。
连接点的坐标系 Frame 用零件自己的坐标：origin 原点，z 方向，x 垂直于 z（y = z × x）。
配合把 moving 端的坐标系对到 fixed 端的坐标系上：先沿 fixed 的 z 移 gap，再绕它转 angle，
align 为 opposite 时再绕 x 转 180 度（让两个 z 相反）。关节的值为 0 时就是装好时的位置。
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from ..checks.expr import eval_expr
from .model import Assembly
from .spec import mate_tree, part_of

Mat = list[float]
Vec = tuple[float, float, float]
IDENTITY: Mat = [1.0, 0, 0, 0, 0, 1.0, 0, 0, 0, 0, 1.0, 0, 0, 0, 0, 1.0]


@dataclass(frozen=True)
class Frame:
    origin: Vec
    z: Vec
    x: Vec


def _norm(v) -> Vec:
    n = math.sqrt(sum(c * c for c in v))
    return (v[0] / n, v[1] / n, v[2] / n)


def _dot(a, b) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _cross(a, b) -> Vec:
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def matmul(a: Mat, b: Mat) -> Mat:
    return [sum(a[r * 4 + k] * b[k * 4 + c] for k in range(4)) for r in range(4) for c in range(4)]


def inverse(m: Mat) -> Mat:
    """刚体变换的逆：旋转转置，平移取 -Rᵀt。"""
    rt = [m[c * 4 + r] for r in range(3) for c in range(3)]
    t = (m[3], m[7], m[11])
    tt = [-sum(rt[r * 3 + k] * t[k] for k in range(3)) for r in range(3)]
    return [rt[0], rt[1], rt[2], tt[0], rt[3], rt[4], rt[5], tt[1], rt[6], rt[7], rt[8], tt[2], 0, 0, 0, 1.0]


def apply_point(m: Mat, p) -> Vec:
    return tuple(m[r * 4] * p[0] + m[r * 4 + 1] * p[1] + m[r * 4 + 2] * p[2] + m[r * 4 + 3] for r in range(3))  # type: ignore[return-value]


def apply_vector(m: Mat, v) -> Vec:
    return tuple(m[r * 4] * v[0] + m[r * 4 + 1] * v[1] + m[r * 4 + 2] * v[2] for r in range(3))  # type: ignore[return-value]


def translation(v) -> Mat:
    return [1.0, 0, 0, v[0], 0, 1.0, 0, v[1], 0, 0, 1.0, v[2], 0, 0, 0, 1.0]


def rotation(axis, deg: float, point=(0.0, 0.0, 0.0)) -> Mat:
    """绕过 point、方向为 axis 的直线转 deg 度（右手定则）。"""
    x, y, z = _norm(axis)
    c, s = math.cos(math.radians(deg)), math.sin(math.radians(deg))
    k = 1 - c
    r = [c + x * x * k, x * y * k - z * s, x * z * k + y * s,
         y * x * k + z * s, c + y * y * k, y * z * k - x * s,
         z * x * k - y * s, z * y * k + x * s, c + z * z * k]
    px, py, pz = point
    t = [px - (r[0] * px + r[1] * py + r[2] * pz), py - (r[3] * px + r[4] * py + r[5] * pz), pz - (r[6] * px + r[7] * py + r[8] * pz)]
    return [r[0], r[1], r[2], t[0], r[3], r[4], r[5], t[1], r[6], r[7], r[8], t[2], 0, 0, 0, 1.0]


def frame_matrix(f: Frame) -> Mat:
    y = _cross(f.z, f.x)
    o = f.origin
    return [f.x[0], y[0], f.z[0], o[0], f.x[1], y[1], f.z[1], o[1], f.x[2], y[2], f.z[2], o[2], 0, 0, 0, 1.0]


def frame_from_geometry(kind: str, center, direction, offset: float, flip: bool) -> Frame:
    """连接点的坐标系。kind 是几何类型（圆柱面、平面、圆形的边），只用于说明，三种算法相同。"""
    z = _norm(direction)
    if flip:
        z = (-z[0], -z[1], -z[2])
    origin = (center[0] + z[0] * offset, center[1] + z[1] * offset, center[2] + z[2] * offset)
    ref = (1.0, 0.0, 0.0) if abs(z[0]) < 0.99 else (0.0, 1.0, 0.0)
    d = _dot(ref, z)
    x = _norm((ref[0] - d * z[0], ref[1] - d * z[1], ref[2] - d * z[2]))
    return Frame(tuple(float(v) for v in origin), z, x)  # type: ignore[arg-type]


FLIP: Mat = [1.0, 0, 0, 0, 0, -1.0, 0, 0, 0, 0, -1.0, 0, 0, 0, 0, 1.0]


def _num(v, values: dict[str, float]) -> float:
    return float(v) if isinstance(v, (int, float)) else eval_expr(v, values)


def _local(asm: Assembly, frames: dict[str, Frame], mate_id: str, values: dict[str, float]) -> Mat:
    """配合两边的相对位置：父零件坐标里，子零件放在哪。"""
    m = asm.mate(mate_id)
    target = matmul(matmul(frame_matrix(frames[m.fixed]), translation((0, 0, _num(m.gap, values)))),
                    rotation((0, 0, 1), _num(m.angle, values)))
    if m.align == "opposite":
        target = matmul(target, FLIP)
    return matmul(target, inverse(frame_matrix(frames[m.moving])))


def _order(asm: Assembly) -> list[tuple[str, str, str]]:
    """从 ground 往下的 (子零件, 父零件, 配合 id)，父零件总在子零件前面。"""
    tree = mate_tree(asm)
    out, placed = [], {asm.ground}
    while len(out) < len(tree):
        for child, (par, mid) in tree.items():
            if child not in placed and par in placed:
                out.append((child, par, mid))
                placed.add(child)
    return out


def rest_placements(asm: Assembly, frames: dict[str, Frame], values: dict[str, float]) -> dict[str, Mat]:
    rest = {asm.ground: list(IDENTITY)}
    for child, par, mid in _order(asm):
        rest[child] = matmul(rest[par], _local(asm, frames, mid, values))
    return rest


def joint_value_samples(lo: float, hi: float, n: int) -> list[float]:
    """均匀取 n 个位置，含两端；范围写反时按从小到大。"""
    lo, hi = min(lo, hi), max(lo, hi)
    n = max(2, int(n))
    return [lo + (hi - lo) * i / (n - 1) for i in range(n)]


def joint_values(asm: Assembly, given: dict[str, float], values: dict[str, float]) -> dict[str, float]:
    """全部关节的值：联动带动的按 ratio × 带动的关节；没给的取 0（0 不在范围里时取 lo）。"""
    out: dict[str, float] = {}
    driven = {c.driven: c for c in asm.couplings}

    def value(jid: str) -> float:
        if jid in out:
            return out[jid]
        if jid in driven:
            c = driven[jid]
            v = _num(c.ratio, values) * value(c.driver)
        elif jid in given:
            v = float(given[jid])
        else:
            j = asm.joint(jid)
            lo, hi = sorted((_num(j.lo, values), _num(j.hi, values)))
            v = 0.0 if lo <= 0 <= hi else lo
        out[jid] = v
        return v

    for j in asm.joints:
        value(j.id)
    return out


def poses_at(asm: Assembly, frames: dict[str, Frame], rest: dict[str, Mat], joint_values_: dict[str, float],
             values: dict[str, float]) -> dict[str, Mat]:
    """各关节放到给定的值时，每个零件在装好的坐标里的矩阵。"""
    jv = joint_values(asm, joint_values_, values)
    by_mate = {j.mate: j for j in asm.joints}
    poses = {asm.ground: list(rest[asm.ground])}
    for child, par, mid in _order(asm):
        local = matmul(inverse(rest[par]), rest[child])
        j = by_mate.get(mid)
        if j is not None:
            f = frames[asm.mate(mid).fixed]
            if j.type == "revolute":
                motion = rotation(f.z, jv[j.id], f.origin)
            else:   # 滑动方向是装好时的世界方向，换到父零件的坐标里
                d = apply_vector(inverse(rest[par]), j.direction)
                motion = translation((d[0] * jv[j.id], d[1] * jv[j.id], d[2] * jv[j.id]))
            local = matmul(motion, local)
        poses[child] = matmul(poses[par], local)
    return poses


def explode_directions(asm: Assembly, frames: dict[str, Frame], rest: dict[str, Mat]) -> dict[str, Vec]:
    """炸开时各零件往哪个方向移：沿它的配合 fixed 端的方向；和"从 ground 指向它"相反时取反。"""
    out: dict[str, Vec] = {asm.ground: (0.0, 0.0, 0.0)}
    g = (rest[asm.ground][3], rest[asm.ground][7], rest[asm.ground][11])
    for child, par, mid in _order(asm):
        d = _norm(apply_vector(rest[par], frames[asm.mate(mid).fixed].z))
        away = (rest[child][3] - g[0], rest[child][7] - g[1], rest[child][11] - g[2])
        if _dot(d, away) < 0:
            d = (-d[0], -d[1], -d[2])
        out[child] = tuple(0.0 if abs(c) < 1e-12 else c for c in d)  # type: ignore[assignment]
    return out


__all__ = ["Frame", "Mat", "apply_point", "explode_directions", "frame_from_geometry", "joint_value_samples",
           "joint_values", "part_of", "poses_at", "rest_placements"]
