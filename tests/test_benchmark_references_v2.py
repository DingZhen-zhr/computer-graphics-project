"""第二版六个评测任务的分阶段标准答案（第二版计划 1 Task 13，真实 SCA）。

每个函数接收修改用的那个参数值，返回一个工作区：已确认的需求单（参数全部 source=user）、分阶段的计划、
归属到阶段的特征、带 stage 的检查。测试确认：用真实沙盒能一路推进到全部阶段通过、终检（含参数扰动）通过，
并且人工写的验收也全过；没改的旧模型拿去对修改后的验收，恰好卡在计划写的那几项上。
写法只用 docs/sca-api-notes.md 里实测过的（草图第 18 节、标准件齿轮第 21 节）。
"""

import pytest

from benchmarks.run import load_task
from cad_agent.brief import Brief, Param
from cad_agent.gates import Gates
from cad_agent.notebook import Feature, FeatureList, render_notebook
from cad_agent.plan import revise
from cad_agent.sandbox.execute import run_job
from cad_agent.staged.build import advance
from cad_agent.staged.final_gate import run_final_gate
from cad_agent.staged.mutation import run_mutation
from cad_agent.tools import Workspace

pytestmark = pytest.mark.sca

TIMEOUT = 120


def area_count(cid: str, area: str, expected, stage: str, **extra) -> dict:
    """数 CYLINDER 面里面积在 area 的 ±5% 内的个数（速查表"孔径""圆角半径"的写法）。"""
    return {"id": cid, "type": "count", "kind": "faces", "expected": expected, "stage": stage, **extra,
            "where": [["geom.type", "==", "CYLINDER"], ["geom.area", ">=", f"{area} * 0.95"], ["geom.area", "<=", f"{area} * 1.05"]]}


def bbox(cid: str, axis: str, expected, stage: str, **extra) -> dict:
    return {"id": cid, "type": "bbox", "axis": axis, "expected": expected, "stage": stage, **extra}


def inside(cid: str, point: list, stage: str, **extra) -> dict:
    return {"id": cid, "type": "point_inside", "point": point, "stage": stage, **extra}


def outside(cid: str, point: list, stage: str, **extra) -> dict:
    return {"id": cid, "type": "point_outside", "point": point, "stage": stage, **extra}


def make_ws(name: str, params: list[tuple[str, float, str]], parts: list[str], relations: list[str],
            stages: list[tuple[str, str]], features: list[tuple[str, str, str, str]], checks: list[dict]) -> Workspace:
    brief = Brief(part_name=name, purpose="评测任务的标准答案", params=[Param(n, v, u, "user", n) for n, v, u in params],
                  features=parts, relations=relations, confirmed=True)
    ws = Workspace(brief, FeatureList([Feature(slug, role, code.strip("\n"), stage) for slug, role, stage, code in features]), checks)
    ws.plan = revise(None, [{"title": t, "done_when": d} for t, d in stages], {})
    return ws


# ---------------------------------------------------------------- 轴承座


def bearing_block(bore_d: float) -> Workspace:
    params = [("base_l", 100, "mm"), ("base_w", 40, "mm"), ("base_t", 10, "mm"), ("corner_r", 5, "mm"), ("hole_d", 9, "mm"),
              ("hole_x", 38, "mm"), ("axis_h", 40, "mm"), ("boss_d", 50, "mm"), ("bore_d", bore_d, "mm"), ("oil_d", 4, "mm")]
    features = [
        ("base", "build", "s1", "base = scad.make_box_rsolid(width=base_l, height=base_w, depth=base_t, bottom_face_center=(0, 0, 0))"),
        ("base-round", "modify", "s1", """
_edges = ql.edges().where(ql.and_(ql.prop("geom.type", "==", "LINE"), ql.prop("geom.center.z", ">=", base_t / 2 - 0.1), ql.prop("geom.center.z", "<=", base_t / 2 + 0.1))).exactly(4)
base_round = scad.fillet_rsolid(solid=base, edges=_edges, radius=corner_r)"""),
        ("mount-holes", "subtract", "s1", """
_h1 = scad.make_cylinder_rsolid(radius=hole_d / 2, height=base_t + 2, bottom_face_center=(hole_x, 0, -1))
_h2 = scad.make_cylinder_rsolid(radius=hole_d / 2, height=base_t + 2, bottom_face_center=(-hole_x, 0, -1))
mount_holes = scad.cut_rsolid(base_round, _h1, _h2, skip_non_intersecting=False)"""),
        ("support", "add", "s2", """
_s = scad.make_box_rsolid(width=boss_d, height=base_w, depth=axis_h - base_t, bottom_face_center=(0, 0, base_t))
support = scad.union_rsolid(mount_holes, _s)"""),
        ("boss", "add", "s2", """
_c = scad.make_cylinder_rsolid(radius=boss_d / 2, height=base_w, bottom_face_center=(0, -base_w / 2, axis_h), axis=(0, 1, 0))
boss = scad.union_rsolid(support, _c)"""),
        ("bore", "subtract", "s3", """
_b = scad.make_cylinder_rsolid(radius=bore_d / 2, height=base_w + 2, bottom_face_center=(0, -base_w / 2 - 1, axis_h), axis=(0, 1, 0))
bore = scad.cut_rsolid(boss, _b, skip_non_intersecting=False)"""),
        ("oil-hole", "subtract", "s3", """
_o = scad.make_cylinder_rsolid(radius=oil_d / 2, height=boss_d / 2 + 1, bottom_face_center=(0, 0, axis_h))
oil_hole = scad.cut_rsolid(bore, _o, skip_non_intersecting=False)"""),
    ]
    checks = [
        bbox("size-x", "x", "base_l", "s1"), bbox("size-y", "y", "base_w", "s1"),
        bbox("base-thick", "z", "base_t", "s1", holds="here_only"),
        outside("base-top", ["base_l / 2 - 2", 0, "base_t + 0.5"], "s1"),
        area_count("corners", "pi / 2 * corner_r * base_t", 4, "s1"),
        area_count("mount-holes", "pi * hole_d * base_t", 2, "s1"),
        outside("hole-1", ["hole_x", 0, "base_t / 2"], "s1"), outside("hole-2", ["-hole_x", 0, "base_t / 2"], "s1"),
        bbox("size-z", "z", "axis_h + boss_d / 2", "s2"),
        outside("support-side", ["boss_d / 2 + 0.5", 0, "base_t + 1"], "s2"),
        inside("support-in", ["boss_d / 2 - 0.5", 0, "base_t + 1"], "s2"),
        inside("boss-solid", [0, 0, "axis_h"], "s2", holds="here_only"),
        outside("bore-center", [0, 0, "axis_h"], "s3"),
        inside("bore-wall", ["bore_d / 2 + 0.5", 0, "axis_h"], "s3"),
        outside("oil", [0, 0, "axis_h + boss_d / 2 - 2"], "s3"),
        inside("oil-wall", ["oil_d / 2 + 0.2", 0, "axis_h + boss_d / 2 - 2"], "s3"),
    ]
    stages = [("底板和安装孔", "有一块带圆角和两个安装孔的底板"), ("支撑块和圆柱座", "底板上有支撑块和横放的圆柱座"),
              ("轴孔和油孔", "圆柱座有贯通的轴孔，顶部有油孔")]
    return make_ws("轴承座", params, ["底板", "安装孔", "圆柱座", "支撑块", "轴孔", "油孔"],
                   ["安装孔在底板两端", "圆柱座在底板中间上方，轴线沿宽度方向", "支撑块在底板顶面和圆柱座之间",
                    "轴孔沿圆柱座的轴线贯通", "油孔从圆柱座顶部打到轴孔"], stages, features, checks)


# ---------------------------------------------------------------- 电池盒

CX = "box_l / 2 - wall - post_d / 2"   # 柱心到中心的 x 距离（柱子贴着两面内壁）
CY = "box_w / 2 - wall - post_d / 2"


def battery_box(post_h: float) -> Workspace:
    params = [("box_l", 90, "mm"), ("box_w", 60, "mm"), ("box_h", 25, "mm"), ("wall", 2, "mm"), ("floor_t", 2, "mm"),
              ("div_t", 2, "mm"), ("post_d", 8, "mm"), ("post_h", post_h, "mm"), ("pin_d", 3, "mm"), ("pin_depth", 10, "mm"),
              ("notch_w", 10, "mm"), ("notch_depth", 8, "mm")]
    posts = """
_cx = box_l / 2 - wall - post_d / 2
_cy = box_w / 2 - wall - post_d / 2
"""
    features = [
        ("body", "build", "s1", "body = scad.make_box_rsolid(width=box_l, height=box_w, depth=box_h, bottom_face_center=(0, 0, 0))"),
        ("cavity", "subtract", "s1", """
_c = scad.make_box_rsolid(width=box_l - 2 * wall, height=box_w - 2 * wall, depth=box_h, bottom_face_center=(0, 0, floor_t))
cavity = scad.cut_rsolid(body, _c, skip_non_intersecting=False)"""),
        ("divider", "add", "s2", """
_d = scad.make_box_rsolid(width=div_t, height=box_w - wall, depth=box_h - floor_t / 2, bottom_face_center=(0, 0, floor_t / 2))
divider = scad.union_rsolid(cavity, _d)"""),
        ("posts", "add", "s3", posts + """
_posts = [scad.make_cylinder_rsolid(radius=post_d / 2, height=post_h + floor_t / 2, bottom_face_center=(_sx * _cx, _sy * _cy, floor_t / 2)) for _sx in (-1, 1) for _sy in (-1, 1)]
posts = scad.union_rsolid(divider, *_posts)"""),
        ("pin-holes", "subtract", "s3", posts + """
_pins = [scad.make_cylinder_rsolid(radius=pin_d / 2, height=pin_depth + 1, bottom_face_center=(_sx * _cx, _sy * _cy, floor_t + post_h - pin_depth)) for _sx in (-1, 1) for _sy in (-1, 1)]
pin_holes = scad.cut_rsolid(posts, _pins, skip_non_intersecting=False)"""),
        ("notch", "subtract", "s4", """
_n = scad.make_box_rsolid(width=wall + 2, height=notch_w, depth=notch_depth + 1, bottom_face_center=(box_l / 2 - wall / 2, 0, box_h - notch_depth))
notch = scad.cut_rsolid(pin_holes, _n, skip_non_intersecting=False)"""),
    ]
    top = "floor_t + post_h"
    checks = [
        bbox("size-x", "x", "box_l", "s1"), bbox("size-y", "y", "box_w", "s1"), bbox("size-z", "z", "box_h", "s1"),
        inside("wall-in", ["-(box_l / 2 - wall / 2)", 0, "box_h / 2"], "s1"),
        outside("wall-x", ["-(box_l / 2 - wall - 0.2)", 0, "box_h / 2"], "s1"),
        outside("wall-y", ["box_l / 4", "box_w / 2 - wall - 0.2", "box_h / 2"], "s1"),
        outside("floor", ["box_l / 4", 0, "floor_t + 0.2"], "s1"),
        inside("div-in", [0, "box_w / 4", "box_h / 2"], "s2"),
        outside("div-side", ["div_t / 2 + 0.1", "box_w / 4", "box_h / 2"], "s2"),
        inside("post-in", [f"{CX} + 2.5", CY, f"{top} - 0.3"], "s3"),
        outside("post-top", [f"{CX} + 2.5", CY, f"{top} + 0.3"], "s3"),
        outside("post-side", ["box_l / 2 - wall - post_d - 0.2", CY, "floor_t + 1"], "s3"),
        outside("pin-in", [CX, CY, f"{top} - pin_depth + 0.3"], "s3"),
        inside("pin-bottom", [CX, CY, f"{top} - pin_depth - 0.3"], "s3"),
        inside("pin-wall", [f"{CX} + pin_d / 2 + 0.2", CY, f"{top} - 1"], "s3"),
        outside("notch-in", ["box_l / 2 - wall / 2", 0, "box_h - 1"], "s4"),
        inside("notch-side", ["box_l / 2 - wall / 2", "notch_w / 2 + 0.2", "box_h - 1"], "s4"),
        inside("notch-bottom", ["box_l / 2 - wall / 2", 0, "box_h - notch_depth - 0.2"], "s4"),
    ]
    stages = [("盒体", "有一个敞口的薄壁盒"), ("隔板", "盒子正中间有隔板"), ("安装柱", "四个内角各有一根带盲孔的安装柱"),
              ("走线缺口", "+x 侧壁上有走线缺口")]
    return make_ws("电池盒", params, ["盒体", "隔板", "安装柱", "走线缺口"],
                   ["隔板在盒体正中，两端连到侧壁", "安装柱立在盒体的四个内角，贴着两面内壁", "走线缺口开在盒体 +x 侧壁的正中"],
                   stages, features, checks)


# ---------------------------------------------------------------- 直齿轮


def spur_gear(light_n: int) -> Workspace:
    params = [("gear_m", 2, "mm"), ("teeth_n", 30, "1"), ("face_w", 12, "mm"), ("hub_d", 24, "mm"), ("hub_h", 8, "mm"),
              ("bore_d", 10, "mm"), ("key_w", 3, "mm"), ("key_depth", 6.4, "mm"), ("light_n", light_n, "1"), ("light_d", 8, "mm"),
              ("light_pcd", 40, "mm")]
    features = [
        ("gear", "build", "s1", "gear = scad.std.gear.make_spur_gear_rsolid(n_teeth=teeth_n, module=gear_m, gear_height=face_w)"),
        ("hub", "add", "s1", """
_h = scad.make_cylinder_rsolid(radius=hub_d / 2, height=face_w + hub_h, bottom_face_center=(0, 0, 0))
hub = scad.union_rsolid(gear, _h)"""),
        ("bore", "subtract", "s2", """
_b = scad.make_cylinder_rsolid(radius=bore_d / 2, height=face_w + hub_h + 2, bottom_face_center=(0, 0, -1))
bore = scad.cut_rsolid(hub, _b, skip_non_intersecting=False)"""),
        ("keyway", "subtract", "s2", """
_k = scad.make_box_rsolid(width=key_w, height=key_depth, depth=face_w + hub_h + 2, bottom_face_center=(0, key_depth / 2, -1))
keyway = scad.cut_rsolid(bore, _k, skip_non_intersecting=False)"""),
        ("lightening", "pattern", "s3", """
_hole = scad.make_cylinder_rsolid(radius=light_d / 2, height=face_w + 2, bottom_face_center=(light_pcd / 2, 0, -1))
_holes = scad.radial_pattern_rsolidlist(shape=_hole, center=(0, 0, 0), axis=(0, 0, 1), count=light_n, total_rotation_angle=360)
lightening = scad.cut_rsolid(keyway, _holes, skip_non_intersecting=False)"""),
    ]
    mid = "face_w / 2"
    checks = [
        bbox("size-x", "x", "gear_m * (teeth_n + 2)", "s1", tol=1.0),
        bbox("size-z", "z", "face_w + hub_h", "s1"),
        outside("hub-side", ["hub_d / 2 + 0.3", 0, "face_w + 1"], "s1"),
        inside("hub-in", ["hub_d / 2 - 0.3", 0, "face_w + 1"], "s1"),
        inside("gear-solid", [0, 0, mid], "s1", holds="here_only"),
        outside("bore-center", [0, 0, mid], "s2"),
        inside("bore-wall", ["-(bore_d / 2 + 0.3)", 0, mid], "s2"),
        outside("key-in", [0, "key_depth - 0.3", mid], "s2"),
        inside("key-bottom", [0, "key_depth + 0.2", mid], "s2"),
        inside("key-side", ["key_w / 2 + 0.2", "bore_d / 2 + 0.7", mid], "s2"),
        area_count("light-count", "pi * light_d * face_w", "light_n", "s3"),
        outside("light-pos", ["light_pcd / 2", 0, mid], "s3"),
        inside("light-edge", ["light_pcd / 2 + light_d / 2 + 0.5", 0, mid], "s3"),
    ]
    stages = [("齿轮和轮毂", "有一个直齿轮，朝上的一面有轮毂"), ("轴孔和键槽", "中间有贯通的轴孔和 +y 方向的键槽"),
              ("减重孔", "齿轮盘上有均布的减重孔")]
    return make_ws("直齿轮", params, ["齿轮", "轮毂", "轴孔", "键槽", "减重孔"],
                   ["轮毂和齿轮同轴，在齿轮朝上的一面", "轴孔贯通齿轮和轮毂", "键槽开在轴孔的 +y 方向",
                    "减重孔均布在齿轮盘上，贯通齿宽"], stages, features, checks)


# ---------------------------------------------------------------- 散热器


def heatsink(fin_n: int) -> Workspace:
    params = [("base_l", 80, "mm"), ("base_w", 60, "mm"), ("base_t", 6, "mm"), ("fin_n", fin_n, "1"), ("fin_t", 2, "mm"),
              ("fin_len", 44, "mm"), ("fin_h", 24, "mm"), ("fin_x", 36, "mm"), ("post_d", 6, "mm"), ("post_x", 20, "mm"),
              ("corner_r", 3, "mm"), ("hole_d", 4.5, "mm"), ("hole_x", 34, "mm"), ("mount_y", 26, "mm"), ("pin_d", 2.5, "mm"),
              ("pin_depth", 8, "mm")]
    features = [
        ("base", "build", "s1", "base = scad.make_box_rsolid(width=base_l, height=base_w, depth=base_t, bottom_face_center=(0, 0, 0))"),
        ("base-round", "modify", "s1", """
_edges = ql.edges().where(ql.and_(ql.prop("geom.type", "==", "LINE"), ql.prop("geom.center.z", ">=", base_t / 2 - 0.1), ql.prop("geom.center.z", "<=", base_t / 2 + 0.1))).exactly(4)
base_round = scad.fillet_rsolid(solid=base, edges=_edges, radius=corner_r)"""),
        ("mount-holes", "subtract", "s1", """
_holes = [scad.make_cylinder_rsolid(radius=hole_d / 2, height=base_t + 2, bottom_face_center=(_sx * hole_x, _sy * mount_y, -1)) for _sx in (-1, 1) for _sy in (-1, 1)]
mount_holes = scad.cut_rsolid(base_round, _holes, skip_non_intersecting=False)"""),
        ("fins", "pattern", "s2", """
_fin = scad.make_box_rsolid(width=fin_t, height=fin_len, depth=fin_h + base_t / 2, bottom_face_center=(-fin_x, 0, base_t / 2))
_fins = scad.linear_pattern_rsolidlist(shape=_fin, direction=(1, 0, 0), count=fin_n, spacing=2 * fin_x / (fin_n - 1))
fins = scad.union_rsolid(mount_holes, *_fins)"""),
        ("posts", "add", "s3", """
_posts = [scad.make_cylinder_rsolid(radius=post_d / 2, height=fin_h + base_t / 2, bottom_face_center=(_sx * post_x, _sy * mount_y, base_t / 2)) for _sx in (-1, 1) for _sy in (-1, 1)]
posts = scad.union_rsolid(fins, *_posts)"""),
        ("pin-holes", "subtract", "s3", """
_pins = [scad.make_cylinder_rsolid(radius=pin_d / 2, height=pin_depth + 1, bottom_face_center=(_sx * post_x, _sy * mount_y, base_t + fin_h - pin_depth)) for _sx in (-1, 1) for _sy in (-1, 1)]
pin_holes = scad.cut_rsolid(posts, _pins, skip_non_intersecting=False)"""),
    ]
    tops = [["geom.type", "==", "PLANE"], ["geom.normal.z", ">=", 0.99], ["geom.center.z", ">=", "base_t + fin_h - 0.1"]]
    top, mid = "base_t + fin_h", "base_t + fin_h / 2"
    checks = [
        bbox("size-x", "x", "base_l", "s1"), bbox("size-y", "y", "base_w", "s1"),
        bbox("base-thick", "z", "base_t", "s1", holds="here_only"),
        outside("base-top", ["base_l / 2 - 1.5", 0, "base_t + 0.3"], "s1"),
        area_count("corners", "pi / 2 * corner_r * base_t", 4, "s1"),
        area_count("mount-holes", "pi * hole_d * base_t", 4, "s1"),
        outside("hole-pos", ["hole_x", "mount_y", "base_t / 2"], "s1"),
        bbox("size-z", "z", top, "s2"),
        {"id": "fin-tops", "type": "count", "kind": "faces", "where": tops, "expected": "fin_n", "stage": "s2", "holds": "here_only"},
        outside("fin-gap", ["-fin_x + fin_t / 2 + 0.1", 0, mid], "s2"),
        inside("fin-wall", ["-fin_x + fin_t / 2 - 0.1", 0, mid], "s2"),
        outside("fin-end", ["-fin_x", "fin_len / 2 + 0.3", mid], "s2"),
        inside("fin-outer", ["fin_x", 0, mid], "s2"),
        outside("fin-beyond", ["fin_x + fin_t / 2 + 0.3", 0, mid], "s2"),
        {"id": "all-tops", "type": "count", "kind": "faces", "where": tops, "expected": "fin_n + 4", "stage": "s3"},
        inside("post-in", ["post_x + post_d / 2 - 0.3", "mount_y", "base_t + 1"], "s3"),
        outside("post-side", ["post_x + post_d / 2 + 0.3", "mount_y", "base_t + 1"], "s3"),
        outside("pin-in", ["post_x", "mount_y", f"{top} - 1"], "s3"),
        inside("pin-wall", ["post_x + pin_d / 2 + 0.2", "mount_y", f"{top} - 1"], "s3"),
        inside("pin-bottom", ["post_x", "mount_y", f"{top} - pin_depth - 0.3"], "s3"),
    ]
    stages = [("底板和安装孔", "有一块带圆角和四个安装孔的底板"), ("鳍片", "底板上立着一排鳍片"),
              ("风扇安装柱", "底板上有四根带盲孔的风扇安装柱")]
    return make_ws("散热器", params, ["底板", "鳍片", "安装孔", "风扇安装柱"],
                   ["鳍片立在底板顶面上，沿长度方向排开", "安装孔在底板四角，贯通底板", "风扇安装柱立在底板顶面上，顶端和鳍片一样高"],
                   stages, features, checks)


# ---------------------------------------------------------------- 三通管接头

D45 = "cos(radians(45))"


def tee_fitting(branch_id: float) -> Workspace:
    params = [("pipe_l", 120, "mm"), ("axis_h", 35, "mm"), ("main_od", 40, "mm"), ("main_id", 30, "mm"), ("flange_od", 70, "mm"),
              ("flange_t", 8, "mm"), ("bolt_d", 7, "mm"), ("bolt_pcd", 56, "mm"), ("branch_top", 85, "mm"), ("branch_od", 30, "mm"),
              ("branch_id", branch_id, "mm"), ("top_flange_od", 56, "mm"), ("top_bolt_d", 6, "mm"), ("top_bolt_pcd", 44, "mm")]
    features = [
        ("main-pipe", "build", "s1",
         "main_pipe = scad.make_cylinder_rsolid(radius=main_od / 2, height=pipe_l, bottom_face_center=(-pipe_l / 2, 0, axis_h), axis=(1, 0, 0))"),
        ("end-flanges", "add", "s1", """
_f1 = scad.make_cylinder_rsolid(radius=flange_od / 2, height=flange_t, bottom_face_center=(pipe_l / 2 - flange_t, 0, axis_h), axis=(1, 0, 0))
_f2 = scad.make_cylinder_rsolid(radius=flange_od / 2, height=flange_t, bottom_face_center=(-pipe_l / 2, 0, axis_h), axis=(1, 0, 0))
end_flanges = scad.union_rsolid(main_pipe, _f1, _f2)"""),
        ("branch", "add", "s2", """
_b = scad.make_cylinder_rsolid(radius=branch_od / 2, height=branch_top - axis_h, bottom_face_center=(0, 0, axis_h))
branch = scad.union_rsolid(end_flanges, _b)"""),
        ("top-flange", "add", "s2", """
_t = scad.make_cylinder_rsolid(radius=top_flange_od / 2, height=flange_t, bottom_face_center=(0, 0, branch_top - flange_t))
top_flange = scad.union_rsolid(branch, _t)"""),
        ("main-bore", "subtract", "s3", """
_m = scad.make_cylinder_rsolid(radius=main_id / 2, height=pipe_l + 2, bottom_face_center=(-pipe_l / 2 - 1, 0, axis_h), axis=(1, 0, 0))
main_bore = scad.cut_rsolid(top_flange, _m, skip_non_intersecting=False)"""),
        ("branch-bore", "subtract", "s3", """
_v = scad.make_cylinder_rsolid(radius=branch_id / 2, height=branch_top - axis_h + 1, bottom_face_center=(0, 0, axis_h))
branch_bore = scad.cut_rsolid(main_bore, _v, skip_non_intersecting=False)"""),
        ("end-bolts", "pattern", "s4", """
_r = bolt_pcd / 2 * math.cos(math.radians(45))
_tools = [scad.make_cylinder_rsolid(radius=bolt_d / 2, height=flange_t + 2, bottom_face_center=(_x, _sy * _r, axis_h + _sz * _r), axis=(1, 0, 0)) for _x in (pipe_l / 2 - flange_t - 1, -pipe_l / 2 - 1) for _sy in (-1, 1) for _sz in (-1, 1)]
end_bolts = scad.cut_rsolid(branch_bore, _tools, skip_non_intersecting=False)"""),
        ("top-bolts", "pattern", "s4", """
_r = top_bolt_pcd / 2 * math.cos(math.radians(45))
_tools = [scad.make_cylinder_rsolid(radius=top_bolt_d / 2, height=flange_t + 2, bottom_face_center=(_sx * _r, _sy * _r, branch_top - flange_t - 1)) for _sx in (-1, 1) for _sy in (-1, 1)]
top_bolts = scad.cut_rsolid(end_bolts, _tools, skip_non_intersecting=False)"""),
    ]
    branch_z = "(axis_h + main_od / 2 + branch_top - flange_t) / 2"   # 支管露在主管和顶法兰之间那一段的中间高度
    fx = "pipe_l / 2 - flange_t / 2"
    checks = [
        bbox("size-x", "x", "pipe_l", "s1"), bbox("size-y", "y", "flange_od", "s1"),
        bbox("flange-height", "z", "axis_h + flange_od / 2", "s1", holds="here_only"),
        inside("flange-in", [fx, 0, "axis_h + flange_od / 2 - 0.5"], "s1"),
        outside("flange-out", ["pipe_l / 2 - flange_t - 0.5", 0, "axis_h + flange_od / 2 - 0.5"], "s1"),
        inside("pipe-wall", [30, "main_od / 2 - 0.3", "axis_h"], "s1"),
        outside("pipe-out", [30, "main_od / 2 + 0.3", "axis_h"], "s1"),
        bbox("size-z", "z", "branch_top", "s2"),
        outside("branch-out", ["branch_od / 2 + 0.3", 0, branch_z], "s2"),
        inside("branch-in", ["branch_od / 2 - 0.3", 0, branch_z], "s2"),
        inside("top-flange-in", ["top_flange_od / 2 - 0.5", 0, "branch_top - flange_t / 2"], "s2"),
        outside("top-flange-out", ["top_flange_od / 2 + 0.3", 0, "branch_top - flange_t / 2"], "s2"),
        outside("top-flange-under", ["top_flange_od / 2 - 2", 0, "branch_top - flange_t - 0.3"], "s2"),
        inside("branch-solid", [0, 0, branch_z], "s2", holds="here_only"),
        outside("main-bore", [30, 0, "axis_h"], "s3"),
        inside("main-bore-wall", [30, "main_id / 2 + 0.3", "axis_h"], "s3"),
        outside("branch-bore", [0, 0, branch_z], "s3"),
        inside("branch-bore-wall", ["branch_id / 2 + 0.3", 0, branch_z], "s3"),
        outside("bores-meet", [0, 0, "axis_h + main_od / 2 - 2"], "s3"),
        outside("bolt-hole", [fx, f"bolt_pcd / 2 * {D45}", f"axis_h + bolt_pcd / 2 * {D45}"], "s4"),
        inside("bolt-wall", [fx, f"(bolt_pcd / 2 + bolt_d / 2 + 0.3) * {D45}", f"axis_h + (bolt_pcd / 2 + bolt_d / 2 + 0.3) * {D45}"], "s4"),
        outside("top-bolt", [f"top_bolt_pcd / 2 * {D45}", f"top_bolt_pcd / 2 * {D45}", "branch_top - flange_t / 2"], "s4"),
        inside("top-bolt-wall", [f"(top_bolt_pcd / 2 + top_bolt_d / 2 + 0.3) * {D45}", f"(top_bolt_pcd / 2 + top_bolt_d / 2 + 0.3) * {D45}",
                                 "branch_top - flange_t / 2"], "s4"),
    ]
    stages = [("主管和端法兰", "有一根水平的主管，两端各有一个法兰"), ("支管和顶法兰", "主管正中竖直伸出支管，顶端有法兰"),
              ("内孔", "主管内孔贯通，支管内孔通到主管内孔"), ("螺栓孔", "三个法兰上各有 4 个螺栓孔")]
    return make_ws("三通管接头", params, ["主管", "端法兰", "支管", "顶法兰", "螺栓孔"],
                   ["端法兰在主管两端，算在主管全长之内", "支管从主管正中竖直向上伸出", "顶法兰在支管顶端，顶面和支管顶端平齐",
                    "螺栓孔在三个法兰上，斜 45° 分布"], stages, features, checks)


# ---------------------------------------------------------------- 支架臂


def bracket_arm(arm_h: float) -> Workspace:
    # 前 12 个参与扰动验证（第 3.6 节最多 12 个），后 6 个按顺序跳过，但同样有检查用到
    params = [("base_l", 120, "mm"), ("part_w", 30, "mm"), ("base_t", 8, "mm"), ("arm_w", 20, "mm"), ("arm_h", arm_h, "mm"),
              ("ear_d", 12, "mm"), ("ear_drop", 15, "mm"), ("slot_l", 30, "mm"), ("slot_w", 12, "mm"), ("rib_len", 30, "mm"),
              ("rib_t", 6, "mm"), ("chamfer_c", 2, "mm"), ("hole_d", 5, "mm"), ("cb_d", 10, "mm"), ("cb_depth", 3, "mm"),
              ("hole1_x", 48, "mm"), ("hole2_x", 25, "mm"), ("hole2_y", 9, "mm")]
    features = [
        ("body", "build", "s1", """
_s = scad.make_sketch_rsketch("l_profile", plane="XZ")
_pts = [(-base_l / 2, 0), (base_l / 2, 0), (base_l / 2, base_t), (-base_l / 2 + arm_w, base_t), (-base_l / 2 + arm_w, arm_h), (-base_l / 2, arm_h)]
for _i, (_u, _v) in enumerate(_pts):
    _s = scad.add_point_rsketch(_s, f"p{_i}", _u, _v)
for _i in range(6):
    _s = scad.add_line_rsketch(_s, f"e{_i}", f"p{_i}", f"p{(_i + 1) % 6}")
_face = scad.make_face_from_sketch_rface(_s)
_solid = scad.extrude_rsolid(profile=_face, direction=(0, 1, 0), distance=part_w)
body = scad.translate_shape(shape=_solid, vector=(0, -part_w / 2, 0))"""),
        ("rib", "add", "s2", """
_x0 = -base_l / 2 + arm_w
_wire = scad.make_polyline_rwire(points=[(_x0, 0, base_t), (_x0 + rib_len, 0, base_t), (_x0, 0, base_t + rib_len)], closed=True)
_profile = scad.make_face_from_wire_rface(wire=_wire, normal=(0, -1, 0))
_rib = scad.extrude_rsolid(profile=_profile, direction=(0, 1, 0), distance=rib_t)
_rib = scad.translate_shape(shape=_rib, vector=(0, -rib_t / 2, 0))
rib = scad.union_rsolid(body, _rib)"""),
        ("ear-hole", "subtract", "s3", """
_e = scad.make_cylinder_rsolid(radius=ear_d / 2, height=arm_w + 2, bottom_face_center=(-base_l / 2 - 1, 0, arm_h - ear_drop), axis=(1, 0, 0))
ear_hole = scad.cut_rsolid(rib, _e, skip_non_intersecting=False)"""),
        ("slot", "subtract", "s3", """
_t = scad.make_box_rsolid(width=slot_l, height=slot_w, depth=base_t + 2, bottom_face_center=(slot_l / 2, 0, -1))
slot = scad.cut_rsolid(ear_hole, _t, skip_non_intersecting=False)"""),
        ("counterbores", "subtract", "s3", """
_tools = []
for _x, _y in ((hole1_x, 0), (-hole2_x, hole2_y)):
    _tools.append(scad.make_cylinder_rsolid(radius=hole_d / 2, height=base_t + 2, bottom_face_center=(_x, _y, -1)))
    _tools.append(scad.make_cylinder_rsolid(radius=cb_d / 2, height=cb_depth + 1, bottom_face_center=(_x, _y, base_t - cb_depth)))
counterbores = scad.cut_rsolid(slot, _tools, skip_non_intersecting=False)"""),
        ("end-chamfer", "modify", "s4", """
_edge = ql.edges().where(ql.and_(ql.prop("geom.type", "==", "LINE"), ql.prop("geom.center.x", ">=", base_l / 2 - 0.1), ql.prop("geom.center.z", ">=", base_t - 0.1), ql.prop("geom.center.z", "<=", base_t + 0.1))).exactly(1)
end_chamfer = scad.chamfer_rsolid(solid=counterbores, edges=_edge, distance=chamfer_c)"""),
    ]
    arm_x = "-base_l / 2 + arm_w / 2"
    ear_z = "arm_h - ear_drop"
    rib_x = "-base_l / 2 + arm_w + 5"
    chamfer_face = {"id": "chamfer", "type": "count", "kind": "faces", "expected": 1, "stage": "s4",
                    "where": [["geom.type", "==", "PLANE"], ["geom.normal.x", ">=", 0.6], ["geom.normal.x", "<=", 0.8],
                              ["geom.normal.z", ">=", 0.6], ["geom.normal.z", "<=", 0.8],
                              ["geom.area", ">=", "sqrt(2) * chamfer_c * part_w * 0.95"], ["geom.area", "<=", "sqrt(2) * chamfer_c * part_w * 1.05"]]}
    checks = [
        bbox("size-x", "x", "base_l", "s1"), bbox("size-y", "y", "part_w", "s1"), bbox("size-z", "z", "arm_h", "s1"),
        outside("base-top", [20, 10, "base_t + 0.3"], "s1"), inside("base-in", [20, 10, "base_t - 0.3"], "s1"),
        outside("arm-side", ["-base_l / 2 + arm_w + 0.3", 10, "base_t + 20"], "s1"),
        inside("arm-in", ["-base_l / 2 + arm_w - 0.3", 10, "base_t + 20"], "s1"),
        inside("rib-in", [rib_x, 0, "base_t + 5"], "s2"),
        inside("rib-wall", [rib_x, "rib_t / 2 - 0.2", "base_t + 5"], "s2"),
        outside("rib-side", [rib_x, "rib_t / 2 + 0.2", "base_t + 5"], "s2"),
        outside("rib-tip", ["-base_l / 2 + arm_w + rib_len + 0.5", 0, "base_t + 0.3"], "s2"),
        outside("ear-center", [arm_x, 0, ear_z], "s3"),
        inside("ear-below", [arm_x, 0, f"{ear_z} - ear_d / 2 - 0.3"], "s3"),
        inside("ear-above", [arm_x, 0, f"{ear_z} + ear_d / 2 + 0.3"], "s3"),
        inside("ear-side", [arm_x, "ear_d / 2 + 0.3", ear_z], "s3"),
        outside("slot-in", ["slot_l / 2", 0, "base_t / 2"], "s3"),
        inside("slot-end", ["slot_l + 0.3", 0, "base_t / 2"], "s3"),
        inside("slot-side", ["slot_l / 2", "slot_w / 2 + 0.3", "base_t / 2"], "s3"),
        area_count("hole-count", "pi * hole_d * (base_t - cb_depth)", 2, "s3"),
        area_count("cb-count", "pi * cb_d * cb_depth", 2, "s3"),
        outside("hole-1", ["hole1_x", 0, 2], "s3"),
        outside("hole-2", ["-hole2_x", "hole2_y", 2], "s3"),
        inside("hole-2-edge", ["-hole2_x", "hole2_y + hole_d / 2 + 0.3", 2], "s3"),
        chamfer_face,
        outside("chamfer-cut", ["base_l / 2 - 0.5", 0, "base_t - 0.5"], "s4"),
    ]
    stages = [("L 形主体", "草图画的 L 形轮廓拉伸成底板和立臂"), ("加强筋", "立臂和底板的内角有三角加强筋"),
              ("孔和槽", "立臂有耳孔，底板有减重槽和两个沉头孔"), ("倒角", "底板右端上棱倒角")]
    return make_ws("支架臂", params, ["底板", "立臂", "耳孔", "减重槽", "沉头孔", "加强筋", "倒角"],
                   ["立臂在底板左端，外侧面和底板左端面平齐，下端和底板重叠", "耳孔穿透立臂", "减重槽贯穿底板",
                    "沉头孔从底板顶面往下", "加强筋贴着底板顶面和立臂内侧面", "倒角在底板右端的上棱"], stages, features, checks)


# ---------------------------------------------------------------- 测试

CASES = [
    ("bearing_block", "after_initial", lambda: bearing_block(25)),
    ("bearing_block", "after_mod_1", lambda: bearing_block(30)),
    ("battery_box", "after_initial", lambda: battery_box(20)),
    ("battery_box", "after_mod_1", lambda: battery_box(15)),
    ("spur_gear", "after_initial", lambda: spur_gear(6)),
    ("spur_gear", "after_mod_1", lambda: spur_gear(4)),
    ("heatsink", "after_initial", lambda: heatsink(9)),
    ("heatsink", "after_mod_1", lambda: heatsink(11)),
    ("tee_fitting", "after_initial", lambda: tee_fitting(20)),
    ("tee_fitting", "after_mod_1", lambda: tee_fitting(24)),
    ("bracket_arm", "after_initial", lambda: bracket_arm(60)),
    ("bracket_arm", "after_mod_1", lambda: bracket_arm(70)),
]


def report(run) -> str:
    if run.error:
        return f"出错：{run.error}"
    return "\n".join(f"{c.id}: passed={c.passed} measured={c.measured} expected={c.expected} {c.detail}" for c in run.checks if not c.passed)


@pytest.mark.parametrize("task_id,stage,build", CASES, ids=[f"{t}-{s}" for t, s, _ in CASES])
def test_reference_passes_all_gates_and_acceptance(task_id, stage, build):
    ws = build()
    assert 2 <= len(ws.plan.stages) <= 5 and all(p.source == "user" for p in ws.brief.params)
    adv = advance(ws, run_job, timeout_s=TIMEOUT, secret_names=())
    assert adv.reason == "complete", f"停在 {adv.stopped}：{report(adv.runs[-1].run) if adv.runs else '没有可跑的阶段'}"
    gate = run_final_gate(ws, run_job, Gates(), timeout_s=TIMEOUT, secret_names=())
    assert gate.missing_coverage == [] and gate.unconstrained == [], gate.to_dict()
    assert gate.passed
    acceptance = load_task(task_id)["acceptance"][stage]
    result = run_job(render_notebook(ws.brief.params, ws.features.items), acceptance, set(), timeout_s=TIMEOUT)
    assert result.ok, report(result)
    assert len(result.checks) == 3 + len(acceptance)


WRONG = [
    ("bearing_block", lambda: bearing_block(25), {"out-6"}),
    ("battery_box", lambda: battery_box(20), {"out-3", "out-4"}),
    ("spur_gear", lambda: spur_gear(6), {"in-5", "out-5"}),
    ("heatsink", lambda: heatsink(9), {"fin-tops", "in-3", "out-6"}),
    ("tee_fitting", lambda: tee_fitting(20), {"out-7"}),
    ("bracket_arm", lambda: bracket_arm(60), {"size-z", "in-5", "in-6", "out-4"}),
]


@pytest.mark.parametrize("task_id,build,failing", WRONG, ids=[t for t, _, _ in WRONG])
def test_acceptance_catches_an_unmodified_model(task_id, build, failing):
    ws = build()
    result = run_job(render_notebook(ws.brief.params, ws.features.items), load_task(task_id)["acceptance"]["after_mod_1"], set(),
                     timeout_s=TIMEOUT)
    assert result.error is None and not result.ok
    assert {c.id for c in result.checks if not c.passed} == failing


SKIPPED = [
    ("heatsink", lambda: heatsink(9), ["hole_x", "mount_y", "pin_d", "pin_depth"]),
    ("tee_fitting", lambda: tee_fitting(20), ["top_bolt_d", "top_bolt_pcd"]),
    ("bracket_arm", lambda: bracket_arm(60), ["hole_d", "cb_d", "cb_depth", "hole1_x", "hole2_x", "hole2_y"]),
]


@pytest.mark.parametrize("task_id,build,names", SKIPPED, ids=[t for t, _, _ in SKIPPED])
def test_params_beyond_the_limit_are_also_constrained(task_id, build, names):
    """超过 12 个的参数终检不扰动；这里把它们挪到最前面单独扰动一次，确认标准答案里它们同样被检查约束。"""
    ws = build()
    users = [p.name for p in ws.brief.params if p.source == "user"]
    assert users[12:] == names   # 按需求单的顺序，正好是终检跳过的这几个
    ws.brief.params = [p for p in ws.brief.params if p.name in names] + [p for p in ws.brief.params if p.name not in names]
    results, _ = run_mutation(ws, run_job, timeout_s=TIMEOUT, secret_names=())
    verdicts = {r.param: r.verdict for r in results if r.param in names}
    assert verdicts == {n: "constrained" for n in names}
