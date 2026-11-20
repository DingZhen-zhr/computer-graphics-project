"""3.0 计划 2 Task 1：装配相关的 SCA 探测。

只给开发时探测用，输出追加进 docs/sca-probe-output.txt，结论写进 docs/sca-api-notes.md 第 23–27 节。
每个实验单独 try/except，出错记下异常类型和前 300 个字符后继续。
"""

from __future__ import annotations

import math
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from probe_common import facts, new_tmp, say  # noqa: E402

PART = '''# /// script
# requires-python = ">=3.10"
# dependencies = ["simplecadapi"]
#
# [tool.simplecadapi]
# id = "{pid}"
# ///
import marimo

app = marimo.App()

with app.setup:
    import simplecadapi as scad
    from simplecadapi import ql
    import math


@app.cell
def _():
    # ---- params ----
    h = scad.var("h", {h}, unit="mm")
    w = scad.var("w", 40, unit="mm")
    return h, w


@app.cell
def _(h, w):
    # ---- feature: base (build) ----
    base = scad.make_box_rsolid(width=w, height=w, depth=h, bottom_face_center=(0, 0, 0))
    return (base,)


@app.cell
def _(base):
    {pid} = scad.Part(part_id="{pid}", body=base)
    return ({pid},)
'''

ASM = '''# /// script
# requires-python = ">=3.10"
# dependencies = ["simplecadapi"]
#
# [tool.simplecadapi]
# id = "product"
# ///
import marimo

app = marimo.App()

with app.setup:
    import simplecadapi as scad
    from simplecadapi import ql
    import math


@app.cell
def _():
    # ---- params ----
    h = scad.var("h", 12, unit="mm")
    w = scad.var("w", 40, unit="mm")
    return h, w


@app.cell
def _(h, w):
    body = scad.use("body.py", h=h, w=w)
    lid = scad.use("lid.py", h=h, w=w)
    return body, lid


@app.cell
def _(body, h, lid):
    _a = scad.make_assembly_rassembly("product")
    _a = scad.add_component_rassembly(_a, body, "body", scad.make_placement_rplacement((0, 0, 0)))
    _a = scad.add_component_rassembly(_a, lid, "lid", scad.make_placement_rplacement((0, 0, h)))
    product = _a
    return (product,)
'''


def attempt(tag: str, fn):
    try:
        return fn()
    except Exception as e:  # noqa: BLE001 - 探测脚本要记录任何异常后继续
        say(tag, f"异常 {type(e).__name__}: {str(e).replace(chr(10), ' | ')[:300]}")
        return None


def mat_rot(axis, deg):
    x, y, z = axis
    n = math.sqrt(x * x + y * y + z * z)
    x, y, z = x / n, y / n, z / n
    c, s = math.cos(math.radians(deg)), math.sin(math.radians(deg))
    C = 1 - c
    return [[c + x * x * C, x * y * C - z * s, x * z * C + y * s],
            [y * x * C + z * s, c + y * y * C, y * z * C - x * s],
            [z * x * C - y * s, z * y * C + x * s, c + z * z * C]]


def exp1() -> None:
    from simplecadapi.runtime import run_notebook

    d = new_tmp("cad-asm1-")
    (d / "body.py").write_text(PART.format(pid="body", h=10), encoding="utf-8")
    (d / "lid.py").write_text(PART.format(pid="lid", h=4), encoding="utf-8")
    (d / "product.py").write_text(ASM, encoding="utf-8")
    t = time.time()
    run = run_notebook(d / "product.py", cache=False, timeout=120)
    say("1 组装", f"成功，{time.time() - t:.2f}s，产品类型 {type(run.product).__name__}，definition {type(run.definition).__name__}")
    comps = attempt("1 组件", lambda: [c.component_id for c in run.product.components])
    say("1 组件", comps)
    # 只传一部分覆盖值
    (d / "product2.py").write_text(ASM.replace('scad.use("body.py", h=h, w=w)', 'scad.use("body.py", h=h)'), encoding="utf-8")
    attempt("1 部分覆盖", lambda: say("1 部分覆盖", type(run_notebook(d / "product2.py", cache=False, timeout=120).product).__name__))
    # 编号都写成 model
    (d / "body.py").write_text(PART.format(pid="body", h=10).replace('id = "body"', 'id = "model"'), encoding="utf-8")
    attempt("1 编号写死 model", lambda: say("1 编号写死 model", type(run_notebook(d / "product.py", cache=False, timeout=120).product).__name__))
    # 用 id= 改编号
    (d / "product3.py").write_text(ASM.replace('scad.use("body.py", h=h, w=w)', 'scad.use("body.py", id="body", h=h, w=w)'), encoding="utf-8")
    attempt("1 id 覆盖", lambda: say("1 id 覆盖", type(run_notebook(d / "product3.py", cache=False, timeout=120).product).__name__))


def place(solid, m):
    """4×4 矩阵（3×3 旋转 + 平移）用 rotate_shape、translate_shape 摆放。"""
    import simplecadapi as scad

    R = m["R"]
    tr = R[0][0] + R[1][1] + R[2][2]
    ang = math.degrees(math.acos(max(-1.0, min(1.0, (tr - 1) / 2))))
    if ang > 1e-9:
        ax = (R[2][1] - R[1][2], R[0][2] - R[2][0], R[1][0] - R[0][1])
        solid = scad.rotate_shape(shape=solid, angle=ang, axis=ax, origin=(0, 0, 0))
    return scad.translate_shape(shape=solid, vector=tuple(m["t"]))


def exp2():
    import simplecadapi as scad

    box = scad.make_box_rsolid(width=20, height=10, depth=4, bottom_face_center=(0, 0, 0))
    say("2 原始", facts(box)["bbox"])
    m = {"R": mat_rot((1, 1, 0), 90), "t": (100, 0, 50)}
    t = time.time()
    moved = place(box, m)
    say("2 摆放后", f"{facts(moved)['bbox']}，{(time.time() - t) * 1000:.1f}ms")
    # 手算：8 个角点变换后的包围盒
    pts = [(x, y, z) for x in (-10, 10) for y in (-5, 5) for z in (0, 4)]
    R = m["R"]
    tp = [[sum(R[i][j] * p[j] for j in range(3)) + m["t"][i] for i in range(3)] for p in pts]
    say("2 手算", [round(min(p[i] for p in tp), 4) for i in range(3)] + [round(max(p[i] for p in tp), 4) for i in range(3)])
    return moved


def overlap(a, b):
    import simplecadapi as scad

    t = time.time()
    try:
        v = scad.intersect_rsolid(a, b).get_volume()
    except Exception as e:  # noqa: BLE001
        v = f"{type(e).__name__}: {str(e)[:160]}"
    return v, (time.time() - t) * 1000


def exp3():
    import simplecadapi as scad

    a = scad.make_box_rsolid(width=20, height=20, depth=10, bottom_face_center=(0, 0, 0))
    for gap, tag in ((5, "不重叠"), (0, "贴面"), (-1, "重叠 1mm")):
        b = scad.make_box_rsolid(width=20, height=20, depth=10, bottom_face_center=(0, 0, 10 + gap))
        v, ms = overlap(a, b)
        say(f"3 {tag}", f"体积 {v}，{ms:.1f}ms")
    # 包围盒判断要多久
    from simplecadapi.inspect import brep

    b = scad.make_box_rsolid(width=20, height=20, depth=10, bottom_face_center=(0, 0, 100))
    t = time.time()
    for _ in range(10):
        brep.inspect_shape_rbrepinspection(a.wrapped).bounding_box
        brep.inspect_shape_rbrepinspection(b.wrapped).bounding_box
    say("3 包围盒", f"两个包围盒 {(time.time() - t) * 100:.2f}ms/次")
    from OCP.Bnd import Bnd_Box
    from OCP.BRepBndLib import BRepBndLib

    t = time.time()
    for _ in range(10):
        ba, bb = Bnd_Box(), Bnd_Box()
        BRepBndLib.Add_s(a.wrapped, ba)
        BRepBndLib.Add_s(b.wrapped, bb)
        ba.IsOut(bb)
    say("3 OCP 包围盒", f"{(time.time() - t) * 100:.2f}ms/次，不相交={ba.IsOut(bb)}")
    # 圆柱插进孔里（间隙 0.2）
    plate = scad.cut_rsolid(a, scad.make_cylinder_rsolid(radius=4.2, height=12, bottom_face_center=(0, 0, -1)))
    pin = scad.make_cylinder_rsolid(radius=4, height=20, bottom_face_center=(0, 0, -5))
    say("3 轴在孔里(间隙0.2)", "体积 %s，%.1fms" % overlap(plate, pin))
    pin2 = scad.make_cylinder_rsolid(radius=4.2, height=20, bottom_face_center=(0, 0, -5))
    say("3 轴在孔里(零间隙)", "体积 %s，%.1fms" % overlap(plate, pin2))


def exp4():
    import simplecadapi as scad
    from simplecadapi import exporter

    d = new_tmp("cad-asm4-")
    parts = []
    for i, (pid, col) in enumerate((("a", "#3A3F47"), ("b", "#C9CDD3"), ("c", "#4767E8"))):
        body = scad.make_box_rsolid(width=20, height=20, depth=10, bottom_face_center=(0, 0, 0))
        p = scad.Part(part_id=pid, body=body)
        mat = attempt("4 材料", lambda: scad.make_material_rmaterial(f"m_{pid}", name=pid, color=col))
        if mat is not None:
            p2 = attempt("4 赋材料", lambda: scad.assign_material_rpart(p, mat))
            if p2 is not None:
                p = p2
        parts.append(p)
        say("4 零件", f"{pid} {type(p).__name__} material={getattr(p, 'material', None)}")
    asm = scad.make_assembly_rassembly("product")
    for i, p in enumerate(parts):
        pl = scad.make_placement_rplacement((i * 30, 0, 0), x_axis=(0, 1, 0), y_axis=(-1, 0, 0))
        asm = scad.add_component_rassembly(asm, p, p.part_id, pl)
    say("4 装配", type(asm).__name__)
    cap = attempt("4 capture 装配", lambda: scad.capture(asm, d / "product.scadpkg"))
    if cap is None:
        b = attempt("4 assemble", lambda: scad.assemble)
        say("4 assemble", b)
    else:
        rep = attempt("4 STEP", lambda: exporter.export_product_package_to_step(cap.package, d / "product.step"))
        if rep is not None:
            txt = (d / "product.step").read_text(encoding="utf-8", errors="replace")
            say("4 STEP", f"{(d / 'product.step').stat().st_size} 字节，occurrence={getattr(rep, 'occurrence_count', None)}，含颜色={'COLOUR_RGB' in txt}")
        rep = attempt("4 STL 产品", lambda: exporter.export_product_package_to_stl(cap.package, d / "product.stl"))
        say("4 STL 产品", getattr(rep, "triangle_count", None))
    return parts


def exp5():
    import simplecadapi as scad
    from simplecadapi import ql

    base = scad.make_box_rsolid(width=40, height=40, depth=10, bottom_face_center=(0, 0, 0))
    arm = scad.make_box_rsolid(width=40, height=10, depth=4, bottom_face_center=(20, 0, 0))
    top = ql.faces().where(ql.and_(ql.prop("geom.type", "==", "PLANE"), ql.prop("geom.normal.z", ">=", 0.99)))
    bot = ql.faces().where(ql.and_(ql.prop("geom.type", "==", "PLANE"), ql.prop("geom.normal.z", "<=", -0.99)))
    pb = scad.Part(part_id="base", body=base)
    pa = scad.Part(part_id="arm", body=arm)
    fb = top.resolve(base)[0]
    fa = bot.resolve(arm)[0]
    pb = scad.add_connector_rpart(pb, scad.make_face_connector_rconnector("top", fb))
    pa = scad.add_connector_rpart(pa, scad.make_face_connector_rconnector("bottom", fa, flip=True))
    for drive in (30, 60, 90):
        asm = scad.make_assembly_rassembly("p")
        asm = scad.add_component_rassembly(asm, pb, "base", scad.make_placement_rplacement((0, 0, 0)))
        asm = scad.add_component_rassembly(asm, pa, "arm", scad.make_placement_rplacement((0, 0, 0)))
        asm = scad.ground_component_rassembly(asm, "base")
        asm = scad.add_revolute_constraint_rassembly(asm, "hinge", scad.make_connector_ref_rconnectorref("base", "top"),
                                                     scad.make_connector_ref_rconnectorref("arm", "bottom"),
                                                     drive_angle_degrees=drive)
        t = time.time()
        solved = scad.solve_assembly_constraints_rassembly(asm)
        ms = (time.time() - t) * 1000
        comp = [c for c in solved.components if c.component_id == "arm"][0]
        say("5 转动", f"{drive}° {ms:.0f}ms placement={comp.placement}")
    rep = attempt("5 报告", lambda: scad.inspect_assembly_constraints_rconstraintreport(solved))
    say("5 报告", rep)


def exp7():
    import simplecadapi as scad

    t = time.time()
    g1 = scad.std.gear.make_spur_gear_rsolid(n_teeth=20, module=2, gear_height=10)
    g2 = scad.std.gear.make_spur_gear_rsolid(n_teeth=40, module=2, gear_height=10)
    say("7 生成", f"{time.time() - t:.2f}s")
    # 大齿轮 +x 正对一个齿，放到 x=60 时要转半个齿（4.5°）让齿槽对着小齿轮的齿
    for rot, tag in ((180 / 40, "对上齿槽"), (0, "齿顶对齿顶")):
        g2p = scad.translate_shape(shape=scad.rotate_shape(shape=g2, angle=rot, axis=(0, 0, 1)), vector=(60, 0, 0))
        say(f"7 {tag}", "重叠 %s，%.0fms" % overlap(g1, g2p))
    # 小齿轮转 9°（半个齿），大齿轮反向转 4.5°
    g1r = scad.rotate_shape(shape=g1, angle=9, axis=(0, 0, 1))
    g2p = scad.translate_shape(shape=scad.rotate_shape(shape=g2, angle=180 / 40 - 4.5, axis=(0, 0, 1)), vector=(60, 0, 0))
    say("7 一起转半齿", "重叠 %s，%.0fms" % overlap(g1r, g2p))


def exp8():
    import simplecadapi as scad
    from simplecadapi import ql
    from OCP.BRepAdaptor import BRepAdaptor_Curve, BRepAdaptor_Surface

    blk = scad.make_box_rsolid(width=40, height=30, depth=10, bottom_face_center=(0, 0, 0))
    body = scad.cut_rsolid(blk, scad.make_cylinder_rsolid(radius=3, height=12, bottom_face_center=(5, 0, -1)))
    cyl = ql.faces().where(ql.prop("geom.type", "==", "CYLINDER")).resolve(body)[0]
    s = BRepAdaptor_Surface(cyl.wrapped)
    ax = s.Cylinder().Axis()
    loc, dr = ax.Location(), ax.Direction()
    say("8 圆柱面", f"center={cyl.get_center().to_tuple()} 轴点=({loc.X():.3f},{loc.Y():.3f},{loc.Z():.3f}) 轴向=({dr.X():.3f},{dr.Y():.3f},{dr.Z():.3f}) 半径={s.Cylinder().Radius():.3f}")
    top = ql.faces().where(ql.and_(ql.prop("geom.type", "==", "PLANE"), ql.prop("geom.normal.z", ">=", 0.99))).resolve(body)[0]
    say("8 平面", f"center={top.get_center().to_tuple()} normal={top.get_normal_at().to_tuple()}")
    side = ql.faces().where(ql.and_(ql.prop("geom.type", "==", "PLANE"), ql.prop("geom.normal.x", "<=", -0.99))).resolve(body)[0]
    say("8 平面 -x", f"center={side.get_center().to_tuple()} normal={side.get_normal_at().to_tuple()}")
    ce = ql.edges().where(ql.and_(ql.prop("geom.type", "==", "CIRCLE"), ql.prop("geom.center.z", ">=", 9.9))).resolve(body)[0]
    c = BRepAdaptor_Curve(ce.wrapped).Circle()
    a = c.Axis()
    say("8 圆边", f"center={ce.get_center().to_tuple()} 圆心=({a.Location().X():.3f},{a.Location().Y():.3f},{a.Location().Z():.3f}) 法向=({a.Direction().X():.3f},{a.Direction().Y():.3f},{a.Direction().Z():.3f}) r={c.Radius():.3f}")
    cyl_t = attempt("8 面类型", lambda: cyl.get_type() if hasattr(cyl, "get_type") else None)
    say("8 面类型", cyl_t)
    con = attempt("8 圆柱连接点", lambda: scad.make_face_connector_rconnector("hole", cyl))
    say("8 圆柱连接点", getattr(con, "frame", con))


def ocp_common(a, b):
    """OCP 的布尔交：不重叠时得到空形状，体积 0，不抛异常。"""
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Common
    from OCP.BRepGProp import BRepGProp
    from OCP.GProp import GProp_GProps

    t = time.time()
    op = BRepAlgoAPI_Common(a.wrapped, b.wrapped)
    op.Build()
    props = GProp_GProps()
    BRepGProp.VolumeProperties_s(op.Shape(), props)
    return props.Mass(), (time.time() - t) * 1000, not op.IsDone()


def exp3b():
    import simplecadapi as scad

    a = scad.make_box_rsolid(width=20, height=20, depth=10, bottom_face_center=(0, 0, 0))
    for gap, tag in ((5, "不重叠"), (0, "贴面"), (-1, "重叠 1mm")):
        b = scad.make_box_rsolid(width=20, height=20, depth=10, bottom_face_center=(0, 0, 10 + gap))
        say(f"3b OCP {tag}", "体积 %.4f，%.1fms，出错=%s" % ocp_common(a, b))
    plate = scad.cut_rsolid(a, scad.make_cylinder_rsolid(radius=4.2, height=12, bottom_face_center=(0, 0, -1)))
    pin = scad.make_cylinder_rsolid(radius=4, height=20, bottom_face_center=(0, 0, -5))
    say("3b OCP 轴在孔里(间隙0.2)", "体积 %.4f，%.1fms，出错=%s" % ocp_common(plate, pin))
    pin2 = scad.make_cylinder_rsolid(radius=4.2, height=20, bottom_face_center=(0, 0, -5))
    say("3b OCP 轴在孔里(零间隙)", "体积 %.4f，%.1fms，出错=%s" % ocp_common(plate, pin2))
    g1 = scad.std.gear.make_spur_gear_rsolid(n_teeth=20, module=2, gear_height=10)
    g2 = scad.std.gear.make_spur_gear_rsolid(n_teeth=40, module=2, gear_height=10)
    for r1, r2, tag in ((0, 4.5, "对上齿槽"), (0, 0, "齿顶对齿顶"), (9, 0, "一起转半齿"), (4, 4.5 - 2, "转 4 度")):
        g1r = scad.rotate_shape(shape=g1, angle=r1, axis=(0, 0, 1)) if r1 else g1
        g2p = scad.translate_shape(shape=scad.rotate_shape(shape=g2, angle=r2, axis=(0, 0, 1)), vector=(60, 0, 0))
        say(f"3b OCP 齿轮 {tag}", "体积 %.4f，%.1fms，出错=%s" % ocp_common(g1r, g2p))


PART_MAT = PART.replace(
    '    {pid} = scad.Part(part_id="{pid}", body=base)\n',
    '    {pid} = scad.assign_material_rpart(scad.make_part_rpart("{pid}", base), '
    'scad.make_material_rmaterial("abs", name="ABS", color=(0.227, 0.247, 0.278)))\n')


def exp4b():
    from simplecadapi import exporter
    import simplecadapi as scad
    from simplecadapi.runtime import run_notebook

    d = new_tmp("cad-asm4b-")
    (d / "body.py").write_text(PART_MAT.format(pid="body", h=10), encoding="utf-8")
    (d / "lid.py").write_text(PART.format(pid="lid", h=4), encoding="utf-8")
    # lid 绕 x 轴转 90 度：x 轴不变，y 轴变成 (0, 0, 1)
    asm = ASM.replace("scad.make_placement_rplacement((0, 0, h))",
                      "scad.make_placement_rplacement((0, 0, h), x_axis=(1, 0, 0), y_axis=(0, 0, 1))")
    (d / "product.py").write_text(asm, encoding="utf-8")
    run = run_notebook(d / "product.py", cache=False, timeout=120)
    cap = scad.capture(run.definition, d / "product.scadpkg")
    rep = exporter.export_product_package_to_step(cap.package, d / "product.step")
    txt = (d / "product.step").read_text(encoding="utf-8", errors="replace")
    say("4b 产品 STEP", f"{(d / 'product.step').stat().st_size} 字节 occurrence={rep.occurrence_count} 含颜色={'COLOUR_RGB' in txt}")
    rep = exporter.export_product_package_to_stl(cap.package, d / "product.stl")
    say("4b 产品 STL", f"三角形 {rep.triangle_count} 实体 {rep.solid_count}")
    import struct
    raw = (d / "product.stl").read_bytes()
    n = struct.unpack("<I", raw[80:84])[0]
    zs = [struct.unpack("<3f", raw[84 + i * 50 + 12 + k * 12:84 + i * 50 + 24 + k * 12])[2] for i in range(n) for k in range(3)]
    ys = [struct.unpack("<3f", raw[84 + i * 50 + 12 + k * 12:84 + i * 50 + 24 + k * 12])[1] for i in range(n) for k in range(3)]
    say("4b 产品 STL 范围", f"y {min(ys):.2f}~{max(ys):.2f} z {min(zs):.2f}~{max(zs):.2f}（lid 转 90 度后 z 应到 12+20=32）")
    body = run.product.components[0]
    say("4b 组件", f"{[c.component_id for c in run.product.components]} {type(body).__name__} 属性 {[a for a in dir(body) if not a.startswith('_')][:30]}")
    # 单个零件 notebook 带材料时导出
    r2 = run_notebook(d / "body.py", cache=False, timeout=60)
    cap2 = scad.capture(r2.definition, d / "body.scadpkg")
    exporter.export_product_package_to_step(cap2.package, d / "body.step")
    say("4b 零件 STEP 颜色", "COLOUR_RGB" in (d / "body.step").read_text(encoding="utf-8", errors="replace"))
    say("4b 零件材料", getattr(r2.product, "material", None))


def main() -> None:
    os.chdir(new_tmp("cad-asm-cwd-"))
    say("开始", "3.0 计划 2 Task 1 装配探测")
    for tag, fn in (("1", exp1), ("2", exp2), ("3", exp3), ("4", exp4), ("5", exp5), ("7", exp7), ("8", exp8), ("3b", exp3b), ("4b", exp4b), ("2b", exp2b)):
        t = time.time()
        attempt(f"实验 {tag}", fn)
        say(f"实验 {tag} 用时", f"{time.time() - t:.1f}s")



def exp2b():
    """4×4 矩阵直接用 OCP 的 gp_Trsf 摆放（含转 180 度的情况）。"""
    import simplecadapi as scad
    from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform
    from OCP.gp import gp_Trsf

    box = scad.make_box_rsolid(width=20, height=10, depth=4, bottom_face_center=(0, 0, 0))
    for axis, deg, t in (((1, 1, 0), 90, (100, 0, 50)), ((1, 0, 0), 180, (0, 0, 10))):
        R = mat_rot(axis, deg)
        tr = gp_Trsf()
        tr.SetValues(R[0][0], R[0][1], R[0][2], t[0], R[1][0], R[1][1], R[1][2], t[1], R[2][0], R[2][1], R[2][2], t[2])
        shape = BRepBuilderAPI_Transform(box.wrapped, tr, True).Shape()
        from simplecadapi.inspect import brep  # SCA 的 Solid 不能从 OCP 形状构造，量 OCP 形状本身

        i = brep.inspect_shape_rbrepinspection(shape)
        say("2b gp_Trsf", f"{axis} {deg}° → {[round(v, 4) for v in i.bounding_box]} 体积 {i.volume:.4f}")


if __name__ == "__main__":
    main()
