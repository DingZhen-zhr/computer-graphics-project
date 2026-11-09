"""摸底第 14、15 项：速查表每个条目跑通，以及 4 种常见报错的原文。

参数全部用 scad.var（和真实 notebook 一样），这样能测出 Var 参与运算、传入函数时的坑。
"""

from __future__ import annotations

from probe_common import Cell, build_nb, facts, run_nb, say

PARAMS = [
    ("base_w", 60, "mm"), ("base_d", 40, "mm"), ("base_t", 8, "mm"), ("hole_d", 10, "mm"),
    ("tilt_deg", 65, "deg"), ("n_holes", 6, None), ("rib_h", 30, "mm"), ("rib_t", 5, "mm"),
    ("pcd", 40, "mm"), ("flange_od", 100, "mm"), ("bore_d", 30, "mm"), ("boss_d", 55, "mm"),
    ("flange_t", 10, "mm"), ("total_h", 30, "mm"),
]
BASE = Cell("base", "build", ["base_w", "base_d", "base_t"],
            "base = scad.make_box_rsolid(width=base_w, height=base_d, depth=base_t, bottom_face_center=(0, 0, 0))",
            ["base"])


def case(tag: str, cells: list[Cell], expect: tuple[float, ...] | None = None, product: str | None = None,
         check_faces: dict[str, int] | None = None):
    """跑一个条目：打印包围盒、体积、面类型；有期望包围盒就对照。"""
    try:
        run = run_nb(build_nb(PARAMS, cells, product))
    except Exception as e:  # noqa: BLE001
        say(tag, f"异常 {type(e).__name__}: {str(e)[:500]!r}")
        return None
    body = run.product.body
    f = facts(body)
    ok = ""
    if expect is not None:
        ok = " 与期望一致" if all(abs(a - b) < 1e-3 for a, b in zip(f["bbox"], expect)) else f" ！与期望 {expect} 不一致"
    say(tag, f"bbox={f['bbox']}{ok} 体积={f['volume']} 面型={f['surface_types']} valid={f['valid']} 实体数={f['solids']}")
    return run


def basics() -> None:
    case("14 基本体/长方体(底面中心在原点)", [BASE], (-30, -20, 0, 30, 20, 8))
    case("14 基本体/长方体(角点在原点)", [Cell(
        "base", "build", ["base_w", "base_d", "base_t"],
        "base = scad.make_box_rsolid(width=base_w, height=base_d, depth=base_t, bottom_face_center=(base_w / 2, base_d / 2, 0))",
        ["base"])], (0, 0, 0, 60, 40, 8))
    case("14 基本体/圆柱(竖直)", [Cell(
        "post", "build", ["base_t", "hole_d"],
        "post = scad.make_cylinder_rsolid(radius=hole_d / 2, height=base_t, bottom_face_center=(0, 0, 0))", ["post"])],
        (-5, -5, 0, 5, 5, 8))
    case("14 基本体/圆柱(沿x横放)", [Cell(
        "pin", "build", ["hole_d"],
        "pin = scad.make_cylinder_rsolid(radius=hole_d / 2, height=20, bottom_face_center=(0, 0, 5), axis=(1, 0, 0))", ["pin"])],
        (0, -5, 0, 20, 5, 10))


def sketches() -> None:
    case("14 草图轮廓与拉伸/矩形", [Cell(
        "plate", "build", ["base_w", "base_d", "base_t"],
        "_profile = scad.make_rectangle_rface(width=base_w, height=base_d, center=(0, 0, 0), normal=(0, 0, 1))\n"
        "plate = scad.extrude_rsolid(profile=_profile, direction=(0, 0, 1), distance=base_t)", ["plate"])],
        (-30, -20, 0, 30, 20, 8))
    case("14 草图轮廓与拉伸/圆形", [Cell(
        "disc", "build", ["base_t", "hole_d"],
        "_profile = scad.make_circle_rface(center=(0, 0, 0), radius=hole_d / 2, normal=(0, 0, 1))\n"
        "disc = scad.extrude_rsolid(profile=_profile, direction=(0, 0, 1), distance=base_t)", ["disc"])],
        (-5, -5, 0, 5, 5, 8))
    case("14 多边形截面拉伸/XZ平面三角形,沿+y", [Cell(
        "rib", "build", ["base_d", "rib_h", "rib_t"],
        "_wire = scad.make_polyline_rwire(points=[(0, 0, 0), (base_d, 0, 0), (0, 0, rib_h)], closed=True)\n"
        "_profile = scad.make_face_from_wire_rface(wire=_wire, normal=(0, -1, 0))\n"
        "rib = scad.extrude_rsolid(profile=_profile, direction=(0, 1, 0), distance=rib_t)", ["rib"])],
        (0, 0, 0, 40, 5, 30))
    case("14 多边形截面拉伸/故意写成 normal=(0,1,0)(会有告警)", [Cell(
        "rib", "build", ["base_d", "rib_h", "rib_t"],
        "_wire = scad.make_polyline_rwire(points=[(0, 0, 0), (base_d, 0, 0), (0, 0, rib_h)], closed=True)\n"
        "_profile = scad.make_face_from_wire_rface(wire=_wire, normal=(0, 1, 0))\n"
        "rib = scad.extrude_rsolid(profile=_profile, direction=(0, 1, 0), distance=rib_t)", ["rib"])],
        (0, 0, 0, 40, 5, 30))
    case("14 多边形截面拉伸/用角度算顶点(math.tan)", [Cell(
        "ramp", "build", ["base_d", "rib_t", "tilt_deg"],
        "_rise = base_d * math.tan(math.radians(tilt_deg))\n"
        "_wire = scad.make_polyline_rwire(points=[(0, 0, 0), (base_d, 0, 0), (base_d, 0, _rise)], closed=True)\n"
        "_profile = scad.make_face_from_wire_rface(wire=_wire, normal=(0, -1, 0))\n"
        "ramp = scad.extrude_rsolid(profile=_profile, direction=(0, 1, 0), distance=rib_t)", ["ramp"])],
        None)
    case("14 多边形截面拉伸/用float()包住Var再算", [Cell(
        "ramp", "build", ["base_d", "rib_t", "tilt_deg"],
        "_rise = float(base_d) * math.tan(math.radians(float(tilt_deg)))\n"
        "_wire = scad.make_polyline_rwire(points=[(0, 0, 0), (float(base_d), 0, 0), (float(base_d), 0, _rise)], closed=True)\n"
        "_profile = scad.make_face_from_wire_rface(wire=_wire, normal=(0, -1, 0))\n"
        "ramp = scad.extrude_rsolid(profile=_profile, direction=(0, 1, 0), distance=rib_t)", ["ramp"])],
        None)


def revolve() -> None:
    case("14 旋转体/截面在XZ平面绕z轴", [Cell(
        "body", "build", ["bore_d", "boss_d", "flange_od", "flange_t", "total_h"],
        "_pts = [(bore_d / 2, 0, 0), (flange_od / 2, 0, 0), (flange_od / 2, 0, flange_t),\n"
        "        (boss_d / 2, 0, flange_t), (boss_d / 2, 0, total_h), (bore_d / 2, 0, total_h)]\n"
        "_wire = scad.make_polyline_rwire(points=_pts, closed=True)\n"
        "_profile = scad.make_face_from_wire_rface(wire=_wire, normal=(0, -1, 0))\n"
        "body = scad.revolve_rsolid(profile=_profile, axis=(0, 0, 1), angle=360, origin=(0, 0, 0))", ["body"])],
        (-50, -50, 0, 50, 50, 30))


def booleans_and_transforms() -> None:
    post = Cell("post", "add", ["base_t", "hole_d"],
                "post = scad.make_cylinder_rsolid(radius=hole_d / 2, height=20, bottom_face_center=(0, 0, base_t))", ["post"])
    case("14 布尔/union_rsolid", [BASE, post, Cell("joined", "add", ["base", "post"],
                                                    "joined = scad.union_rsolid(base, post)", ["joined"])],
         (-30, -20, 0, 30, 20, 28))
    holes = Cell("holes", "subtract", ["base", "base_t", "hole_d"],
                 "_h1 = scad.make_cylinder_rsolid(radius=hole_d / 2, height=base_t + 2, bottom_face_center=(-15, 0, -1))\n"
                 "_h2 = scad.make_cylinder_rsolid(radius=hole_d / 2, height=base_t + 2, bottom_face_center=(15, 0, -1))\n"
                 "holes = scad.cut_rsolid(base, _h1, _h2)", ["holes"])
    r = case("14 布尔/cut_rsolid 一次减两个工具体", [BASE, holes], (-30, -20, 0, 30, 20, 8))
    if r is not None:
        n = len(__import__("simplecadapi").ql.faces().where(__import__("simplecadapi").ql.prop("geom.type", "==", "CYLINDER")).resolve(r.product.body))
        say("14 布尔/cut_rsolid 一次减两个工具体", f"圆柱面个数={n}（期望 2）")
    case("14 布尔/intersect_rsolid", [BASE, Cell(
        "cap", "intersect", ["base", "base_t"],
        "_box = scad.make_box_rsolid(width=20, height=100, depth=100, bottom_face_center=(0, 0, -10))\n"
        "cap = scad.intersect_rsolid(base, _box)", ["cap"])], (-10, -20, 0, 10, 20, 8))
    case("14 移动/translate_shape", [BASE, Cell(
        "moved", "modify", ["base"], "moved = scad.translate_shape(shape=base, vector=(10, 0, 5))", ["moved"])],
        (-20, -20, 5, 40, 20, 13))
    case("14 旋转/rotate_shape(angle 用普通数)", [BASE, Cell(
        "turned", "modify", ["base"],
        "turned = scad.rotate_shape(shape=base, angle=90, axis=(0, 0, 1), origin=(0, 0, 0))", ["turned"])],
        (-20, -30, 0, 20, 30, 8))
    case("14 旋转/rotate_shape(angle 直接传 Var)", [BASE, Cell(
        "turned", "modify", ["base", "tilt_deg"],
        "turned = scad.rotate_shape(shape=base, angle=tilt_deg, axis=(0, 0, 1), origin=(0, 0, 0))", ["turned"])],
        None)


def patterns() -> None:
    from simplecadapi import ql

    r = case("14 阵列/radial_pattern_rsolidlist 后一次 cut", [BASE, Cell(
        "bolt-holes", "pattern", ["base", "base_t", "hole_d", "n_holes", "pcd"],
        "_hole = scad.make_cylinder_rsolid(radius=hole_d / 2, height=base_t + 2, bottom_face_center=(pcd / 2, 0, -1))\n"
        "_holes = scad.radial_pattern_rsolidlist(shape=_hole, center=(0, 0, 0), axis=(0, 0, 1), count=n_holes, total_rotation_angle=360)\n"
        "bolt_holes = scad.cut_rsolid(base, _holes)", ["bolt_holes"])], (-30, -20, 0, 30, 20, 8), product="bolt_holes")
    if r is not None:
        n = len(ql.faces().where(ql.prop("geom.type", "==", "CYLINDER")).resolve(r.product.body))
        say("14 阵列/radial", f"圆柱面个数={n}（期望 n_holes=6，说明阵列包含原件、总共 6 个）")
    r = case("14 阵列/linear_pattern_rsolidlist", [BASE, Cell(
        "row-holes", "pattern", ["base", "base_t", "hole_d"],
        "_hole = scad.make_cylinder_rsolid(radius=hole_d / 2, height=base_t + 2, bottom_face_center=(-15, 0, -1))\n"
        "_holes = scad.linear_pattern_rsolidlist(shape=_hole, direction=(1, 0, 0), count=3, spacing=15)\n"
        "row_holes = scad.cut_rsolid(base, _holes)", ["row_holes"])], (-30, -20, 0, 30, 20, 8), product="row_holes")
    if r is not None:
        cyl = ql.faces().where(ql.prop("geom.type", "==", "CYLINDER")).resolve(r.product.body)
        say("14 阵列/linear", f"圆柱面个数={len(cyl)} 中心 x={sorted(round(c.get_center().x, 3) for c in cyl)}（期望 -15, 0, 15）")
    r = case("14 阵列/用循环生成工具体后一次 cut(range 用整数参数)", [BASE, Cell(
        "row-holes", "pattern", ["base", "base_t", "hole_d", "n_holes"],
        "_tools = [scad.make_cylinder_rsolid(radius=hole_d / 2.5, height=base_t + 2, bottom_face_center=(-25 + i * 10, 0, -1))\n"
        "          for i in range(n_holes)]\n"
        "row_holes = scad.cut_rsolid(base, _tools)", ["row_holes"])], (-30, -20, 0, 30, 20, 8), product="row_holes")
    if r is not None:
        say("14 阵列/循环", f"圆柱面个数={len(ql.faces().where(ql.prop('geom.type', '==', 'CYLINDER')).resolve(r.product.body))}（期望 6）")


def fillet_chamfer_and_ql() -> None:
    from simplecadapi import ql

    top_edges = ('ql.edges().where(ql.and_(ql.prop("geom.type", "==", "LINE"), '
                 'ql.prop("geom.center.z", ">=", 7.9), ql.prop("geom.center.z", "<=", 8.1))).exactly(4)')
    r = case("14 圆角/fillet_rsolid(选顶面4条边)", [BASE, Cell(
        "rounded", "modify", ["base"],
        f"_edges = {top_edges}\nrounded = scad.fillet_rsolid(solid=base, edges=_edges, radius=2)", ["rounded"])])
    if r is not None:
        say("14 圆角", f"圆角后圆柱面个数={len(ql.faces().where(ql.prop('geom.type', '==', 'CYLINDER')).resolve(r.product.body))}（期望 0，圆角在平顶面四边上是柱面？见面型）")
    case("14 圆角/ql.prop 里的值直接用 Var 表达式 base_t - 0.1", [BASE, Cell(
        "rounded", "modify", ["base", "base_t"],
        '_edges = ql.edges().where(ql.and_(ql.prop("geom.type", "==", "LINE"), ql.prop("geom.center.z", ">=", base_t - 0.1))).exactly(4)\n'
        "rounded = scad.fillet_rsolid(solid=base, edges=_edges, radius=2)", ["rounded"])])
    case("14 圆角/ql.prop 里的值用 float(base_t) - 0.1", [BASE, Cell(
        "rounded", "modify", ["base", "base_t"],
        '_edges = ql.edges().where(ql.and_(ql.prop("geom.type", "==", "LINE"), ql.prop("geom.center.z", ">=", float(base_t) - 0.1))).exactly(4)\n'
        "rounded = scad.fillet_rsolid(solid=base, edges=_edges, radius=2)", ["rounded"])])
    case("14 圆角/先 resolve 成列表再传入", [BASE, Cell(
        "rounded", "modify", ["base"],
        f"_sel = {top_edges}\n_edges = _sel.resolve(base)\nrounded = scad.fillet_rsolid(solid=base, edges=_edges, radius=2)", ["rounded"])])
    case("14 倒角/chamfer_rsolid(选顶面4条边)", [BASE, Cell(
        "chamfered", "modify", ["base"],
        f"_edges = {top_edges}\nchamfered = scad.chamfer_rsolid(solid=base, edges=_edges, distance=1)", ["chamfered"])])
    # 竖直棱
    case("14 圆角/竖直4条棱(LINE 且 center.z 在 4 附近)", [BASE, Cell(
        "rounded", "modify", ["base"],
        '_edges = ql.edges().where(ql.and_(ql.prop("geom.type", "==", "LINE"), ql.prop("geom.center.z", ">=", 3.9), '
        'ql.prop("geom.center.z", "<=", 4.1))).exactly(4)\nrounded = scad.fillet_rsolid(solid=base, edges=_edges, radius=3)', ["rounded"])])

    # QL 各函数的例子
    run = run_nb(build_nb(PARAMS, [BASE]))
    b = run.product.body
    n_f, n_e = len(ql.faces().resolve(b)), len(ql.edges().resolve(b))
    say("14 QL/faces()/edges()/resolve", f"长方体: ql.faces().resolve(b) -> {n_f} 个, ql.edges().resolve(b) -> {n_e} 条（resolve 返回 Python 列表）")
    sel = ql.faces().where(ql.and_(ql.prop("geom.type", "==", "PLANE"), ql.prop("geom.normal.z", ">=", 0.99)))
    say("14 QL/where/and_/prop", f"顶面选择器 resolve -> {len(sel.resolve(b))} 个；.exactly(1).resolve -> {len(sel.exactly(1).resolve(b))} 个")
    try:
        ql.faces().where(ql.prop("geom.center.z", ">=", 999)).exactly(1).resolve(b)
    except Exception as e:  # noqa: BLE001
        say("14 QL/exactly 不满足时", f"{type(e).__name__}: {str(e)[:300]!r}")
    big = ql.faces().where(ql.prop("geom.type", "==", "PLANE")).order_by(ql.value("geom.area"), desc=True).take(1).resolve(b)
    say("14 QL/order_by+take", f"面积最大的平面: area={big[0].get_area()}")
    either = ql.faces().where(ql.or_(ql.prop("geom.normal.z", ">=", 0.99), ql.prop("geom.normal.z", "<=", -0.99))).resolve(b)
    say("14 QL/or_", f"顶面或底面 {len(either)} 个")
    notz = ql.faces().where(ql.not_(ql.prop("geom.normal.z", ">=", 0.99))).resolve(b)
    say("14 QL/not_", f"非顶面 {len(notz)} 个")


def errors() -> None:
    """第 15 项：故意制造 4 种常见错误（另加 2 种），记录异常原文。"""
    def go(tag: str, cells: list[Cell], product: str | None = None):
        try:
            run = run_nb(build_nb(PARAMS, cells, product))
            body = run.product.body
            say(tag, f"没有报错, 结果 bbox={facts(body)['bbox']} 体积={facts(body)['volume']} 实体数={facts(body)['solids']}")
        except Exception as e:  # noqa: BLE001
            say(tag, f"异常类型={type(e).__module__}.{type(e).__name__} 信息原文={str(e)[:1500]!r}")

    go("15 报错/选中0条边", [BASE, Cell(
        "rounded", "modify", ["base"],
        '_edges = ql.edges().where(ql.prop("geom.center.z", ">=", 999)).exactly(4)\n'
        "rounded = scad.fillet_rsolid(solid=base, edges=_edges, radius=2)", ["rounded"])])
    go("15 报错/圆角半径过大(半径50 比板厚8大)", [BASE, Cell(
        "rounded", "modify", ["base"],
        '_edges = ql.edges().where(ql.and_(ql.prop("geom.type", "==", "LINE"), ql.prop("geom.center.z", ">=", 7.9))).exactly(4)\n'
        "rounded = scad.fillet_rsolid(solid=base, edges=_edges, radius=50)", ["rounded"])])
    far = ("_tool = scad.make_cylinder_rsolid(radius=3, height=5, bottom_face_center=(500, 500, 0))\n")
    go("15 报错/cut 的工具体离主体很远(默认参数)", [BASE, Cell(
        "holes", "subtract", ["base"], far + "holes = scad.cut_rsolid(base, _tool)", ["holes"])])
    go("15 报错/cut 的工具体离主体很远(skip_non_intersecting=False)", [BASE, Cell(
        "holes", "subtract", ["base"], far + "holes = scad.cut_rsolid(base, _tool, skip_non_intersecting=False)", ["holes"])])
    go("15 报错/union 两个不相连的实体", [BASE, Cell(
        "joined", "add", ["base"], far + "joined = scad.union_rsolid(base, _tool)", ["joined"])])
    # 参数名写错：特征代码里用了 base_wd，Task 3 的输入推断不会把它当输入，运行时才暴露
    go("15 报错/参数名写错(base_wd)", [Cell(
        "base", "build", ["base_d", "base_t"],
        "base = scad.make_box_rsolid(width=base_wd, height=base_d, depth=base_t, bottom_face_center=(0, 0, 0))", ["base"])])
    go("15 报错/关键字参数名写错(w= 而不是 width=)", [Cell(
        "base", "build", ["base_d", "base_t", "base_w"],
        "base = scad.make_box_rsolid(w=base_w, height=base_d, depth=base_t)", ["base"])])
    go("15 报错/函数名写错", [Cell(
        "base", "build", ["base_d", "base_t", "base_w"],
        "base = scad.make_box(width=base_w, height=base_d, depth=base_t)", ["base"])])


def main() -> None:
    for fn in (basics, sketches, revolve, booleans_and_transforms, patterns, fillet_chamfer_and_ql, errors):
        print(f"\n==== {fn.__name__} ====", flush=True)
        try:
            fn()
        except Exception as e:  # noqa: BLE001
            say("脚本", f"{fn.__name__} 中途异常 {type(e).__name__}: {str(e)[:300]}")


if __name__ == "__main__":
    main()
