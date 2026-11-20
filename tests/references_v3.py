"""三个多零件评测任务的标准答案（3.0 计划 2 Task 14）：按模型会写的样子写好零件、步骤、特征、检查、连接点和装配。

每个函数接收参数的覆盖值（修改请求用），返回一个已确认的多零件工作区。速查表"装配的写法"里的 4 个例子都出自这里。
写法只用 docs/sca-api-notes.md 里实测过的（盒子、圆柱、转动平移、布尔运算、标准件齿轮）。
"""

from __future__ import annotations

from cad_agent.brief import Brief
from cad_agent.notebook import Feature, FeatureList
from cad_agent.plan import revise
from cad_agent.product.checks import parse_assembly_checks
from cad_agent.product.spec import parse_assembly, parse_connectors
from cad_agent.product.workspace import ensure_parts, select_part
from cad_agent.tools import Workspace

PLANE, CYL, CIRCLE = ["geom.type", "==", "PLANE"], ["geom.type", "==", "CYLINDER"], ["geom.type", "==", "CIRCLE"]
X_CYL = "scad.rotate_shape(shape=scad.make_cylinder_rsolid(radius={r}, height={h}, bottom_face_center=(0, 0, 0)), angle=90, axis=(0, 1, 0))"


def bbox(cid, axis, expected, stage, **kw):
    return {"id": cid, "type": "bbox", "axis": axis, "expected": expected, "stage": stage, **kw}


def inside(cid, point, stage):
    return {"id": cid, "type": "point_inside", "point": point, "stage": stage}


def outside(cid, point, stage):
    return {"id": cid, "type": "point_outside", "point": point, "stage": stage}


def build_ws(name: str, params: list[tuple], parts: list[dict], defs: dict, assembly: dict, assembly_checks: list[dict],
             over: dict[str, float]) -> Workspace:
    b = Brief()
    b.apply_patch({"part": {"name": name, "purpose": "评测任务的标准答案"},
                   "parts": [{k: p[k] for k in ("id", "name", "material", "features")} for p in parts],
                   "set_params": [{"name": n, "value": over.get(n, v), "unit": u, "source": "user", "note": n} for n, v, u in params]})
    b.confirmed = True
    ws = Workspace(b, FeatureList(), [])
    ensure_parts(ws)
    names = {n for n, _, _ in params}
    for p in parts:
        d = defs[p["id"]]
        select_part(ws, p["id"])
        ws.features = FeatureList([Feature(slug, role, code.strip("\n"), stage) for slug, role, stage, code in d["features"]])
        ws.checks_raw = list(d["checks"])
        ws.plan = revise(None, [{"title": t, "done_when": f"有{t}"} for t in d["stages"]], {})
        ws.parts[p["id"]].connectors = parse_connectors(p["id"], d["connectors"], names)
    select_part(ws, parts[0]["id"])
    ws.assembly = parse_assembly(assembly, [p["id"] for p in parts], {k: v.connectors for k, v in ws.parts.items()}, names)
    ws.assembly_checks_raw = parse_assembly_checks(assembly_checks, ws.assembly, [p["id"] for p in parts], names)
    return ws


def _handle(span: str) -> tuple:
    code = f"""
_base = scad.make_box_rsolid(width={span}, height=14, depth=3, bottom_face_center=(0, 0, 0))
_p1 = scad.make_box_rsolid(width=8, height=10, depth=8, bottom_face_center=(-({span} / 2 - 4), 0, 3))
_p2 = scad.make_box_rsolid(width=8, height=10, depth=8, bottom_face_center=({span} / 2 - 4, 0, 3))
_g = scad.translate_shape(shape={X_CYL.format(r=4, h=span)}, vector=(-{span} / 2, 0, 13))
grip = scad.union_rsolid(scad.union_rsolid(scad.union_rsolid(_base, _p1), _p2), _g)
"""
    return {"stages": ["提手"], "features": [("grip", "build", "s1", code)],
            "checks": [bbox("hx", "x", span, "s1"), bbox("hz", "z", 17, "s1"), inside("grip_in", [0, 0, 13], "s1"),
                       outside("under_grip", [0, 0, 7], "s1")],
            "connectors": [{"name": "base", "kind": "faces", "where": [PLANE, ["geom.normal.z", "<=", -0.99]]}]}


# ---------------------------------------------------------------- 工具盒

TOOLBOX_PARAMS = [("box_l", 160, "mm"), ("box_w", 100, "mm"), ("box_h", 60, "mm"), ("wall", 3, "mm"), ("floor_t", 3, "mm"),
                  ("lid_t", 6, "mm"), ("hinge_off", 5, "mm"), ("pin_d", 3, "mm"), ("handle_span", 70, "mm"), ("lid_max", 110, "deg")]
HY = "box_w / 2 + hinge_off"


def toolbox(**over: float) -> Workspace:
    hole = f"_hole = scad.translate_shape(shape={X_CYL.format(r='pin_d / 2 + 0.2', h=130)}, vector=(-65, _hy, _hz))"
    body = {
        "stages": ["盒体", "铰链耳"],
        "features": [
            ("shell", "build", "s1", """
_outer = scad.make_box_rsolid(width=box_l, height=box_w, depth=box_h, bottom_face_center=(0, 0, 0))
_cav = scad.make_box_rsolid(width=box_l - 2 * wall, height=box_w - 2 * wall, depth=box_h, bottom_face_center=(0, 0, floor_t))
shell = scad.cut_rsolid(_outer, _cav, skip_non_intersecting=False)
"""),
            ("knuckles", "add", "s2", f"""
_hy = box_w / 2 + hinge_off
_hz = box_h + lid_t / 2
_k = shell
for _x0 in (-60, -10, 40):
    _blk = scad.make_box_rsolid(width=20, height=hinge_off + 2, depth=8, bottom_face_center=(_x0 + 10, box_w / 2 - 2 + (hinge_off + 2) / 2, box_h - 8))
    _cyl = scad.translate_shape(shape={X_CYL.format(r=4, h=20)}, vector=(_x0, _hy, _hz))
    _k = scad.union_rsolid(scad.union_rsolid(_k, _blk), _cyl)
{hole}
knuckles = scad.cut_rsolid(_k, _hole, skip_non_intersecting=False)
"""),
        ],
        "checks": [
            bbox("bx", "x", "box_l", "s1"), bbox("by", "y", "box_w", "s1", holds="here_only"), bbox("bz", "z", "box_h", "s1", holds="here_only"),
            inside("wall_in", ["box_l / 2 - wall + 0.3", 0, "box_h / 2"], "s1"), outside("wall_out", ["box_l / 2 - wall - 0.3", 0, "box_h / 2"], "s1"),
            inside("floor_in", [0, 0, "floor_t - 0.3"], "s1"), outside("floor_out", [0, 0, "floor_t + 0.3"], "s1"),
            bbox("by2", "y", "box_w + hinge_off + 4", "s2"), bbox("bz2", "z", "box_h + lid_t / 2 + 4", "s2"),
            inside("hole_in", [0, HY, "box_h + lid_t / 2 + pin_d / 2 + 0.4"], "s2"),
            outside("hole_out", [0, HY, "box_h + lid_t / 2 + pin_d / 2"], "s2"),
        ],
        "connectors": [{"name": "hinge_axis", "kind": "faces", "flip": True,
                        "where": [CYL, ["geom.center.x", ">=", -1], ["geom.center.x", "<=", 1], ["geom.area", "<=", 300]]}],
    }
    lid = {
        "stages": ["盖板", "铰链耳"],
        "features": [
            ("plate", "build", "s1", "plate = scad.make_box_rsolid(width=box_l, height=box_w, depth=lid_t, bottom_face_center=(0, 0, 0))"),
            ("lid-knuckles", "add", "s2", f"""
_hy = box_w / 2 + hinge_off
_hz = lid_t / 2
_k = plate
for _x0 in (-39.5, 10.5):
    _tab = scad.make_box_rsolid(width=29, height=hinge_off + 1, depth=lid_t, bottom_face_center=(_x0 + 14.5, box_w / 2 - 1 + (hinge_off + 1) / 2, 0))
    _cyl = scad.translate_shape(shape={X_CYL.format(r=4, h=29)}, vector=(_x0, _hy, _hz))
    _k = scad.union_rsolid(scad.union_rsolid(_k, _tab), _cyl)
{hole}
lid_knuckles = scad.cut_rsolid(_k, _hole, skip_non_intersecting=False)
"""),
        ],
        "checks": [
            bbox("lx", "x", "box_l", "s1"), bbox("ly", "y", "box_w", "s1", holds="here_only"),
            inside("top_in", [0, 0, "lid_t - 0.3"], "s1"), outside("top_out", [0, 0, "lid_t + 0.3"], "s1"),
            bbox("ly2", "y", "box_w + hinge_off + 4", "s2"),
            inside("hole_in", [25, HY, "lid_t / 2 + pin_d / 2 + 0.4"], "s2"), outside("hole_out", [25, HY, "lid_t / 2 + pin_d / 2"], "s2"),
        ],
        "connectors": [
            {"name": "hinge_axis", "kind": "faces", "flip": True, "offset": 25,
             "where": [CYL, ["geom.center.x", ">=", 20], ["geom.center.x", "<=", 30], ["geom.area", "<=", 400]]},
            {"name": "top", "kind": "faces", "where": [PLANE, ["geom.normal.z", ">=", 0.99], ["geom.center.y", ">=", -5], ["geom.center.y", "<=", 5]]},
        ],
    }
    pin = {"stages": ["轴"],
           "features": [("rod", "build", "s1", f"rod = scad.translate_shape(shape={X_CYL.format(r='pin_d / 2', h=120)}, vector=(-60, 0, 0))")],
           "checks": [bbox("px", "x", 120, "s1"), bbox("py", "y", "pin_d", "s1")],
           "connectors": [{"name": "axis", "kind": "faces", "flip": True, "where": [CYL]}]}
    parts = [{"id": "body", "name": "盒体", "material": "abs", "features": ["盒体", "铰链耳"]},
             {"id": "lid", "name": "盖子", "material": "anodized", "features": ["盖板", "铰链耳"]},
             {"id": "pin", "name": "铰链轴", "material": "steel", "features": ["轴"]},
             {"id": "handle", "name": "提手", "material": "rubber", "features": ["提手"]}]
    assembly = {"ground": "body",
                "mates": [{"id": "lid_hinge", "fixed": "body.hinge_axis", "moving": "lid.hinge_axis", "align": "same"},
                          {"id": "pin_in", "fixed": "body.hinge_axis", "moving": "pin.axis", "align": "same"},
                          {"id": "handle_on", "fixed": "lid.top", "moving": "handle.base", "align": "opposite"}],
                "joints": [{"id": "lid_open", "mate": "lid_hinge", "type": "revolute", "range": [0, "lid_max"], "label": "盖子翻开"}]}
    return build_ws("工具盒", TOOLBOX_PARAMS, parts, {"body": body, "lid": lid, "pin": pin, "handle": _handle("handle_span")},
                    assembly, [], over)


# ---------------------------------------------------------------- 抽屉柜

DRAWER_PARAMS = [("cab_w", 200, "mm"), ("cab_d", 150, "mm"), ("cab_h", 120, "mm"), ("cab_wall", 4, "mm"), ("gap_s", 1, "mm"),
                 ("drw_depth", 140, "mm"), ("drw_wall", 3, "mm"), ("panel_t", 4, "mm"), ("handle_w", 60, "mm"), ("pull_max", 100, "mm")]
BW = "(cab_w - 2 * cab_wall - 2 * gap_s)"
BH = "(cab_h - 2 * cab_wall - 2 * gap_s)"
CY = "drw_depth / 2"   # 抽屉自己的坐标：前面板背面在 y=0，抽屉盒往 +y 伸


def drawer_cabinet(**over: float) -> Workspace:
    cabinet = {
        "stages": ["柜体"],
        "features": [("carcass", "build", "s1", """
_outer = scad.make_box_rsolid(width=cab_w, height=cab_d, depth=cab_h, bottom_face_center=(0, 0, 0))
_cav = scad.make_box_rsolid(width=cab_w - 2 * cab_wall, height=cab_d - cab_wall + 1, depth=cab_h - 2 * cab_wall, bottom_face_center=(0, -(cab_wall + 1) / 2, cab_wall))
carcass = scad.cut_rsolid(_outer, _cav, skip_non_intersecting=False)
""")],
        "checks": [bbox("cx", "x", "cab_w", "s1"), bbox("cy", "y", "cab_d", "s1"), bbox("cz", "z", "cab_h", "s1"),
                   inside("side_in", ["cab_w / 2 - cab_wall + 0.4", 0, "cab_h / 2"], "s1"),
                   outside("side_out", ["cab_w / 2 - cab_wall - 0.4", 0, "cab_h / 2"], "s1")],
        "connectors": [{"name": "front", "kind": "faces", "where": [PLANE, ["geom.normal.y", "<=", -0.99], ["geom.center.y", "<=", "-cab_d / 2 + 0.1"]]}],
    }
    drawer = {
        "stages": ["抽屉盒", "前面板"],
        "features": [
            ("tray", "build", "s1", f"""
_bw = {BW}
_bh = {BH}
_cy = {CY}
_box = scad.make_box_rsolid(width=_bw, height=drw_depth, depth=_bh, bottom_face_center=(0, _cy, 0))
_in = scad.make_box_rsolid(width=_bw - 2 * drw_wall, height=drw_depth - 2 * drw_wall, depth=_bh, bottom_face_center=(0, _cy, drw_wall))
tray = scad.cut_rsolid(_box, _in, skip_non_intersecting=False)
"""),
            ("front", "add", "s2", """
_panel = scad.make_box_rsolid(width=cab_w, height=panel_t, depth=cab_h, bottom_face_center=(0, -panel_t / 2, -(cab_wall + gap_s)))
front = scad.union_rsolid(tray, _panel)
"""),
        ],
        "checks": [
            inside("side_in", [f"{BW} / 2 - 0.1", CY, f"{BH} / 2"], "s1"), outside("side_out", [f"{BW} / 2 + 0.1", CY, f"{BH} / 2"], "s1"),
            inside("inner_in", [f"{BW} / 2 - drw_wall + 0.3", CY, f"{BH} / 2"], "s1"),
            outside("inner_out", [f"{BW} / 2 - drw_wall - 0.3", CY, f"{BH} / 2"], "s1"),
            inside("floor_in", [0, CY, "drw_wall - 0.3"], "s1"), outside("floor_out", [0, CY, "drw_wall + 0.3"], "s1"),
            bbox("dy", "y", "drw_depth", "s1", holds="here_only"), bbox("dz", "z", BH, "s1", holds="here_only"),
            bbox("fx", "x", "cab_w", "s2"), bbox("fy", "y", "drw_depth + panel_t", "s2"), bbox("fz", "z", "cab_h", "s2"),
        ],
        "connectors": [
            {"name": "panel_back", "kind": "faces",
             "where": [PLANE, ["geom.normal.y", ">=", 0.99], ["geom.center.y", ">=", -0.1], ["geom.center.y", "<=", 0.1]]},
            {"name": "front", "kind": "faces", "where": [PLANE, ["geom.normal.y", "<=", -0.99], ["geom.center.y", "<=", "-panel_t + 0.1"]]},
        ],
    }
    parts = [{"id": "cabinet", "name": "柜体", "material": "wood", "features": ["柜体"]},
             {"id": "drawer", "name": "抽屉", "material": "abs", "features": ["抽屉盒", "前面板"]},
             {"id": "handle", "name": "拉手", "material": "brass", "features": ["拉手"]}]
    assembly = {"ground": "cabinet",
                "mates": [{"id": "drawer_in", "fixed": "cabinet.front", "moving": "drawer.panel_back", "align": "opposite"},
                          {"id": "handle_on", "fixed": "drawer.front", "moving": "handle.base", "align": "opposite"}],
                "joints": [{"id": "drawer_pull", "mate": "drawer_in", "type": "prismatic", "range": [0, "pull_max"],
                            "direction": [0, -1, 0], "label": "拉出抽屉"}]}
    return build_ws("抽屉柜", DRAWER_PARAMS, parts, {"cabinet": cabinet, "drawer": drawer, "handle": _handle("handle_w")},
                    assembly, [], over)


# ---------------------------------------------------------------- 齿轮对

GEAR_PARAMS = [("plate_l", 140, "mm"), ("plate_w", 80, "mm"), ("plate_t", 8, "mm"), ("shaft_d", 8, "mm"), ("shaft_h", 30, "mm"),
               ("gear_m", 2, "mm"), ("pinion_z", 20, "1"), ("gear_z", 40, "1"), ("face_w", 10, "mm"), ("lift", 5, "mm"), ("clear", 0.2, "mm")]
HALF_C = "gear_m * (pinion_z + gear_z) / 4"


def _gear(teeth: str) -> dict:
    return {
        "stages": ["齿轮", "轴孔"],
        "features": [
            ("teeth", "build", "s1", f"teeth = scad.std.gear.make_spur_gear_rsolid(n_teeth={teeth}, module=gear_m, gear_height=face_w)"),
            ("bore", "subtract", "s2", """
_t = scad.make_cylinder_rsolid(radius=shaft_d / 2 + clear, height=face_w + 2, bottom_face_center=(0, 0, -1))
bore = scad.cut_rsolid(teeth, _t, skip_non_intersecting=False)
"""),
        ],
        "checks": [bbox("gx", "x", f"gear_m * ({teeth} + 2)", "s1"), bbox("gz", "z", "face_w", "s1"),
                   inside("bore_in", ["shaft_d / 2 + clear + 0.01", 0, "face_w / 2"], "s2"),
                   outside("bore_out", ["shaft_d / 2 + clear - 0.01", 0, "face_w / 2"], "s2")],
        "connectors": [{"name": "bore", "kind": "edges", "where": [CIRCLE, ["geom.center.z", "<=", 0.1], ["geom.center.x", ">=", -0.5],
                                                                  ["geom.center.x", "<=", 0.5], ["geom.center.y", ">=", -0.5], ["geom.center.y", "<=", 0.5]]}],
    }


def gear_pair(**over: float) -> Workspace:
    def shaft_edge(name: str, sign: str) -> dict:
        x = f"{sign}{HALF_C}"
        return {"name": name, "kind": "edges", "where": [CIRCLE, ["geom.center.x", ">=", f"{x} - 0.5"], ["geom.center.x", "<=", f"{x} + 0.5"],
                                                         ["geom.center.z", ">=", "plate_t - 0.1"], ["geom.center.z", "<=", "plate_t + 0.1"]]}

    plate = {
        "stages": ["底板", "两根轴"],
        "features": [
            ("slab", "build", "s1", "slab = scad.make_box_rsolid(width=plate_l, height=plate_w, depth=plate_t, bottom_face_center=(0, 0, 0))"),
            ("shafts", "add", "s2", """
_c = gear_m * (pinion_z + gear_z) / 2
_a = scad.make_cylinder_rsolid(radius=shaft_d / 2, height=shaft_h, bottom_face_center=(-_c / 2, 0, plate_t))
_b = scad.make_cylinder_rsolid(radius=shaft_d / 2, height=shaft_h, bottom_face_center=(_c / 2, 0, plate_t))
shafts = scad.union_rsolid(scad.union_rsolid(slab, _a), _b)
"""),
        ],
        "checks": [
            bbox("sx", "x", "plate_l", "s1"), bbox("sy", "y", "plate_w", "s1"), bbox("sz", "z", "plate_t", "s1", holds="here_only"),
            bbox("sz2", "z", "plate_t + shaft_h", "s2"),
            inside("a_in", [f"-{HALF_C} + shaft_d / 2 - 0.2", 0, "plate_t + shaft_h / 2"], "s2"),
            outside("a_out", [f"-{HALF_C} + shaft_d / 2 + 0.2", 0, "plate_t + shaft_h / 2"], "s2"),
            inside("b_in", [f"{HALF_C} - shaft_d / 2 + 0.2", 0, "plate_t + shaft_h / 2"], "s2"),
            outside("b_out", [f"{HALF_C} - shaft_d / 2 - 0.2", 0, "plate_t + shaft_h / 2"], "s2"),
        ],
        "connectors": [shaft_edge("shaft_a", "-"), shaft_edge("shaft_b", "")],
    }
    parts = [{"id": "plate", "name": "底板和轴", "material": "aluminum", "features": ["底板", "两根轴"]},
             {"id": "pinion", "name": "小齿轮", "material": "brass", "features": ["齿轮", "轴孔"]},
             {"id": "gear", "name": "大齿轮", "material": "brass", "features": ["齿轮", "轴孔"]}]
    assembly = {"ground": "plate",
                "mates": [{"id": "pinion_on", "fixed": "plate.shaft_a", "moving": "pinion.bore", "align": "same", "gap": "lift"},
                          {"id": "gear_on", "fixed": "plate.shaft_b", "moving": "gear.bore", "align": "same", "gap": "lift", "angle": "180 / gear_z"}],
                "joints": [{"id": "pinion_turn", "mate": "pinion_on", "type": "revolute", "range": [0, 360], "label": "小齿轮转动"},
                           {"id": "gear_turn", "mate": "gear_on", "type": "revolute", "range": [-360, 360], "label": "大齿轮转动"}],
                "couplings": [{"driver": "pinion_turn", "driven": "gear_turn", "ratio": "-pinion_z / gear_z", "kind": "gear"}]}
    checks = [{"id": "lift_gap", "type": "flush", "expected": "lift",
               "a": {"part": "plate", "kind": "faces", "where": [PLANE, ["geom.normal.z", ">=", 0.99], ["geom.center.z", "<=", "plate_t + 0.1"]]},
               "b": {"part": "pinion", "kind": "faces", "where": [PLANE, ["geom.normal.z", "<=", -0.99]]}},
              {"id": "half_speed", "type": "ratio", "driver": "pinion_turn", "driven": "gear_turn", "expected": "-pinion_z / gear_z"}]
    return build_ws("齿轮对", GEAR_PARAMS, parts, {"plate": plate, "pinion": _gear("pinion_z"), "gear": _gear("gear_z")},
                    assembly, checks, over)


REFERENCES = {"toolbox": (toolbox, {"box_h": 70, "lid_max": 95}),
              "drawer_cabinet": (drawer_cabinet, {"pull_max": 120}),
              "gear_pair": (gear_pair, {"gear_z": 50})}
