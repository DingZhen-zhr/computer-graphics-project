"""多零件评测任务的验收（3.0 计划 2 Task 14）。

和内核分开写，不读内核写的 motion.json，也不用内核里算姿态的那个模块（product 下的 kinematics）：
- 装好的位置：运行版本目录里的 assembly.py，取每个组件的 placement；
- 关节：读 assembly.json 里声明的关节，关节轴用 SCA 的选择和 OCP 的几何在零件上重新取；
- 把关节放到某个位置：这里独立写的转动、平移变换（笔记第 26 节说 SCA 的转动约束能驱动，但它要用 SCA 自己的
  连接点对象，和交付的声明对不上，所以没用它；偏离 D33 一并记录）。
验收条目：单零件的 bbox、point_inside、point_outside 作用在装好的整个产品上（世界坐标）；另外两类：
- {id, type: joint, kind, axis, through, pos_tol, lo, hi}：找一个同类、方向和 axis 平行（±2 度）、
  （转动时）轴线到 through 的距离 ≤ pos_tol 的关节，它的范围要覆盖 [lo, hi]；
- {id, type: at_pose, joint, value, checks: [...]}：把上一条找到的关节放到 value，再跑里面的点检查。
用法（由 run.py 在子进程里调用）：python -m benchmarks.assembly_accept <版本目录> <检查.json> <结果.json>
"""

from __future__ import annotations

import json
import math
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
POINT_TYPES = ("bbox", "point_inside", "point_outside")
ANGLE_TOL_DEG = 2.0


class AcceptSpecError(ValueError):
    pass


def validate_entries(raw: list[dict]) -> None:
    """检查多零件验收条目的格式（单零件条目由 parse_checks 校验）。"""
    ids = set()
    for e in raw:
        t = e.get("type")
        if t == "joint":
            for key in ("kind", "axis", "lo", "hi"):
                if key not in e:
                    raise AcceptSpecError(f"验收条目 {e.get('id')} 缺少 {key}")
            if e["kind"] not in ("revolute", "prismatic"):
                raise AcceptSpecError(f"验收条目 {e['id']} 的 kind 只能是 revolute 或 prismatic")
            if e["kind"] == "revolute" and ("through" not in e or "pos_tol" not in e):
                raise AcceptSpecError(f"验收条目 {e['id']} 是转动关节，要写 through 和 pos_tol")
        elif t == "at_pose":
            if e.get("joint") not in ids:
                raise AcceptSpecError(f"验收条目 {e.get('id')} 的 joint 要指向前面已有的 joint 条目")
            if not all(c.get("type") in POINT_TYPES for c in e.get("checks") or []) or not e.get("checks"):
                raise AcceptSpecError(f"验收条目 {e['id']} 的 checks 要写点检查或包围盒检查")
        ids.add(e.get("id"))


# ---------------------------------------------------------------- 矩阵（独立写的）


def _mat_from_placement(pl: Any) -> list[list[float]]:
    x, y, z, o = pl.x_axis, pl.y_axis, pl.z_axis, pl.origin
    return [[x[0], y[0], z[0], o[0]], [x[1], y[1], z[1], o[1]], [x[2], y[2], z[2], o[2]], [0, 0, 0, 1]]


def _mul(a, b):
    return [[sum(a[i][k] * b[k][j] for k in range(4)) for j in range(4)] for i in range(4)]


def _rot(axis, deg, point):
    n = math.sqrt(sum(c * c for c in axis))
    x, y, z = (c / n for c in axis)
    c, s = math.cos(math.radians(deg)), math.sin(math.radians(deg))
    k = 1 - c
    r = [[c + x * x * k, x * y * k - z * s, x * z * k + y * s], [y * x * k + z * s, c + y * y * k, y * z * k - x * s],
         [z * x * k - y * s, z * y * k + x * s, c + z * z * k]]
    t = [point[i] - sum(r[i][j] * point[j] for j in range(3)) for i in range(3)]
    return [[*r[0], t[0]], [*r[1], t[1]], [*r[2], t[2]], [0, 0, 0, 1]]


def _move(d, v):
    return [[1, 0, 0, d[0] * v], [0, 1, 0, d[1] * v], [0, 0, 1, d[2] * v], [0, 0, 0, 1]]


def _apply(m, p):
    return [sum(m[i][j] * p[j] for j in range(3)) + m[i][3] for i in range(3)]


def _applyv(m, v):
    return [sum(m[i][j] * v[j] for j in range(3)) for i in range(3)]


# ---------------------------------------------------------------- 子进程里做的事


def _eval(v: Any, values: dict[str, float]) -> float:
    if isinstance(v, (int, float)):
        return float(v)
    return float(eval(str(v), {"__builtins__": {}}, {**values, **{k: getattr(math, k) for k in ("pi", "sin", "cos", "tan", "sqrt", "radians", "degrees")}}))  # noqa: S307 - 验收自己的表达式，只有参数名


def _select(solid: Any, kind: str, where: list, values: dict[str, float]) -> list:
    from simplecadapi import ql

    preds = [ql.prop(path, op, val if path == "geom.type" else _eval(val, values)) for path, op, val in where]
    base = ql.faces() if kind == "faces" else ql.edges()
    if preds:
        base = base.where(preds[0] if len(preds) == 1 else ql.and_(*preds))
    return list(base.resolve(solid))


def _axis(entity: Any, kind: str) -> tuple[list[float], list[float]]:
    from OCP.BRepAdaptor import BRepAdaptor_Curve, BRepAdaptor_Surface

    if kind == "faces":
        s = BRepAdaptor_Surface(entity.wrapped)
        name = s.GetType().name
        if name.endswith("Cylinder"):
            ax = s.Cylinder().Axis()
            return [ax.Location().X(), ax.Location().Y(), ax.Location().Z()], [ax.Direction().X(), ax.Direction().Y(), ax.Direction().Z()]
        c, n = entity.get_center(), entity.get_normal_at()
        return [c.x, c.y, c.z], [n.x, n.y, n.z]
    ax = BRepAdaptor_Curve(entity.wrapped).Circle().Axis()
    return [ax.Location().X(), ax.Location().Y(), ax.Location().Z()], [ax.Direction().X(), ax.Direction().Y(), ax.Direction().Z()]


def _place(shape: Any, m) -> Any:
    from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform
    from OCP.gp import gp_Trsf

    tr = gp_Trsf()
    tr.SetValues(*[m[i][j] for i in range(3) for j in range(4)])
    return BRepBuilderAPI_Transform(shape, tr, True).Shape()


def _point_state(shapes: list, p) -> bool:
    """点在不在任意一个零件的材料里（含表面）。"""
    from OCP.BRepClass3d import BRepClass3d_SolidClassifier
    from OCP.gp import gp_Pnt
    from OCP.TopAbs import TopAbs_IN, TopAbs_ON

    for s in shapes:
        c = BRepClass3d_SolidClassifier(s, gp_Pnt(*p), 1e-6)
        if c.State() in (TopAbs_IN, TopAbs_ON):
            return True
    return False


def _bbox(shapes: list) -> list[float]:
    from OCP.BRep import BRep_Builder
    from OCP.TopoDS import TopoDS_Compound
    from simplecadapi.inspect import brep

    comp = TopoDS_Compound()
    b = BRep_Builder()
    b.MakeCompound(comp)
    for s in shapes:
        b.Add(comp, s)
    return list(brep.inspect_shape_rbrepinspection(comp).bounding_box)


def _check(c: dict, shapes: list) -> dict:
    t = c["type"]
    if t == "bbox":
        bb = _bbox(shapes)
        i = "xyz".index(c["axis"])
        m = bb[i + 3] - bb[i]
        ok = abs(m - float(c["expected"])) <= float(c.get("tol", 0.1))
        return {"passed": ok, "measured": m, "expected": float(c["expected"]), "detail": f"{c['axis']} 向尺寸 {m:.4f}"}
    inside = _point_state(shapes, c["point"])
    ok = inside if t == "point_inside" else not inside
    return {"passed": ok, "measured": None, "expected": None, "detail": f"点 {c['point']} {'在' if inside else '不在'}材料里"}


def _children(asm: dict) -> dict[str, str]:
    return {m["moving"].split(".")[0]: m["fixed"].split(".")[0] for m in asm["mates"]}


def _subtree(asm: dict, root: str) -> set[str]:
    par, out = _children(asm), {root}
    changed = True
    while changed:
        changed = False
        for child, p in par.items():
            if p in out and child not in out:
                out.add(child)
                changed = True
    return out


def work(vdir: Path, checks: list[dict]) -> list[dict]:
    from OCP.BRepCheck import BRepCheck_Analyzer
    from simplecadapi.runtime import run_notebook

    asm = json.loads((vdir / "assembly.json").read_text(encoding="utf-8"))
    brief = json.loads((vdir / "brief.json").read_text(encoding="utf-8"))
    values = {p["name"]: float(p["value"]) for p in brief["params"]}
    run = run_notebook(vdir / "assembly.py", cache=False, timeout=180)
    placements = {c.component_id: _mat_from_placement(c.placement) for c in run.product.components}
    solids = {pid: run_notebook(vdir / "parts" / pid / "model.py", cache=False, timeout=180).product.body for pid in placements}
    rest = {pid: _place(s.wrapped, placements[pid]) for pid, s in solids.items()}
    valid = all(BRepCheck_Analyzer(s).IsValid() for s in rest.values())
    # 每个声明的关节在世界坐标里的轴（取 fixed 那一边的连接点几何）
    found_axes = {}
    for j in asm["joints"]:
        mate = next(m for m in asm["mates"] if m["id"] == j["mate"])
        pid, cname = mate["fixed"].split(".")
        con = next(c for c in json.loads((vdir / "parts" / pid / "connectors.json").read_text(encoding="utf-8")) if c["name"] == cname)
        hits = _select(solids[pid], con["kind"], con["where"], values)
        if len(hits) != 1:
            continue
        p, d = _axis(hits[0], con["kind"])
        if con.get("flip"):   # 声明里写了方向反过来（关节的正方向跟着它）
            d = [-v for v in d]
        found_axes[j["id"]] = (_apply(placements[pid], p), _applyv(placements[pid], d), j, mate["moving"].split(".")[0])
    out, matched, signs = [], {}, {}
    for c in checks:
        t = c["type"]
        if t in POINT_TYPES:
            r = _check(c, list(rest.values()))
        elif t == "joint":
            r = _joint(c, found_axes, values)
            if r.get("joint_id"):
                matched[c["id"]] = r.pop("joint_id")
                signs[matched[c["id"]]] = r.pop("sign")
        else:
            r = _at_pose(c, matched, found_axes, asm, rest, values, signs)
        out.append({"id": c["id"], "type": t, **r})
    return [{"mandatory_ok": valid}] + out


def _joint(c: dict, axes: dict, values: dict) -> dict:
    want = c["axis"]
    for jid, (p, d, j, _) in axes.items():
        if j["type"] != c["kind"]:
            continue
        direction = j.get("direction") if j["type"] == "prismatic" else d
        cos = abs(sum(a * b for a, b in zip(direction, want))) / (math.sqrt(sum(a * a for a in direction)) * math.sqrt(sum(a * a for a in want)))
        if math.degrees(math.acos(min(1.0, cos))) > ANGLE_TOL_DEG:
            continue
        if j["type"] == "revolute":
            w = [c["through"][i] - p[i] for i in range(3)]
            n = math.sqrt(sum(a * a for a in d))
            cr = [w[1] * d[2] - w[2] * d[1], w[2] * d[0] - w[0] * d[2], w[0] * d[1] - w[1] * d[0]]
            if math.sqrt(sum(a * a for a in cr)) / n > float(c["pos_tol"]):
                continue
        lo, hi = sorted((_eval(j["range"][0], values), _eval(j["range"][1], values)))
        # 方向不分正负，所以"轴反过来、角度也反过来"是同一个运动：原样盖不住要求的范围时，换成反过来的写法再比
        # （3.0 修改清单第 2 条）。真的转错方向，后面的 at_pose 照样不通过。
        sign = 1
        if not _covers(lo, hi, c) and _covers(-hi, -lo, c):
            sign, lo, hi = -1, -hi, -lo
        ok = _covers(lo, hi, c)
        return {"passed": ok, "measured": hi, "expected": float(c["hi"]), "joint_id": jid, "sign": sign,
                "detail": f"找到关节 {j['label']}，范围 {lo:g} 到 {hi:g}" + ("（按反过来的方向算）" if sign < 0 else "")}
    return {"passed": False, "measured": None, "expected": None, "detail": "没有找到方向和位置都对的关节"}


def _covers(lo: float, hi: float, c: dict) -> bool:
    return lo <= float(c["lo"]) + 1e-6 and hi >= float(c["hi"]) - 1e-6


def _at_pose(c: dict, matched: dict, axes: dict, asm: dict, rest: dict, values: dict, signs: dict | None = None) -> dict:
    jid = matched.get(c["joint"])
    if jid is None:
        return {"passed": False, "measured": None, "expected": None, "detail": "前面没有找到这个关节"}
    moves = {jid: (signs or {}).get(jid, 1) * float(c["value"])}
    for cp in asm.get("couplings", []):   # 被它带动的关节一起动
        if cp["driver"] in moves:
            moves[cp["driven"]] = _eval(cp["ratio"], values) * moves[cp["driver"]]
    shapes = dict(rest)
    for mid, v in moves.items():
        if mid not in axes:
            continue
        p, d, j, root = axes[mid]
        m = _rot(d, v, p) if j["type"] == "revolute" else _move(j["direction"], v)
        for pid in _subtree(asm, root):
            shapes[pid] = _place(shapes[pid], m)
    results = [_check(x, list(shapes.values())) for x in c["checks"]]
    bad = [x["id"] for x, r in zip(c["checks"], results) if not r["passed"]]
    return {"passed": not bad, "measured": None, "expected": None,
            "detail": f"放到 {c['value']} 时" + ("全部符合" if not bad else f"这些不符合：{'、'.join(bad)}")}


# ---------------------------------------------------------------- 父进程这边


def evaluate(vdir: Path, checks: list[dict], timeout_s: float = 300) -> dict:
    """在子进程里验收一个多零件版本。返回 {"entries": [...], "mandatory_ok": bool, "error": dict | None}。"""
    with tempfile.TemporaryDirectory(prefix="cad-accept-") as tmp:
        cj, rj = Path(tmp) / "checks.json", Path(tmp) / "result.json"
        cj.write_text(json.dumps(checks, ensure_ascii=False), encoding="utf-8")
        env = {**os.environ, "PYTHONUTF8": "1", "PYTHONPATH": str(ROOT)}
        try:
            r = subprocess.run([sys.executable, "-X", "utf8", "-m", "benchmarks.assembly_accept", str(vdir), str(cj), str(rj)],
                               cwd=tmp, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout_s)
        except subprocess.TimeoutExpired:
            return {"entries": [], "mandatory_ok": False, "error": {"type": "TimeoutError", "message": f"验收超过 {timeout_s:g} 秒"}}
        if not rj.is_file():
            return {"entries": [], "mandatory_ok": False, "error": {"type": "AcceptCrash", "message": (r.stderr or "")[-800:]}}
        data = json.loads(rj.read_text(encoding="utf-8"))
    return {"entries": data[1:], "mandatory_ok": data[0]["mandatory_ok"], "error": None}


def main(argv: list[str]) -> int:
    vdir, cj, rj = Path(argv[1]), Path(argv[2]), Path(argv[3])
    result = work(vdir, json.loads(cj.read_text(encoding="utf-8")))
    rj.write_text(json.dumps(result, ensure_ascii=False, default=float), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
