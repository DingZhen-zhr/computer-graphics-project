"""用真实 SCA 为 3 个测试任务各写一个“标准答案”模型，确认人工写的验收检查本身是对的。

如果这里的验收过不了，说明验收条件和坐标约定对不上；联调时才不会冤枉模型。
"""

import pytest

from benchmarks.run import load_task
from cad_agent.brief import Param
from cad_agent.notebook import Feature, render_notebook
from cad_agent.sandbox.execute import run_job

pytestmark = pytest.mark.sca


def P(name: str, value: float, unit: str = "mm") -> Param:
    return Param(name, value, unit, "user")


def phone_stand(tilt: float):
    params = [P("stand_w", 90), P("tilt_deg", tilt, "deg"), P("plate_len", 110), P("plate_t", 5), P("lip_h", 15),
              P("gap_w", 20), P("base_d", 60), P("base_t", 5)]
    features = [
        Feature("base", "build", "base = scad.make_box_rsolid(width=stand_w, height=base_d, depth=base_t, bottom_face_center=(0, 0, 0))"),
        Feature("support-plate", "add",
                "_plate = scad.make_box_rsolid(width=stand_w, height=plate_len, depth=plate_t, bottom_face_center=(0, plate_len / 2, 0))\n"
                "_tilted = scad.rotate_shape(shape=_plate, angle=tilt_deg, axis=(1, 0, 0), origin=(0, 0, 0))\n"
                "_placed = scad.translate_shape(shape=_tilted, vector=(0, 20, 3))\n"
                "support_plate = scad.union_rsolid(base, _placed)"),
        Feature("lip", "add",
                "_lip = scad.make_box_rsolid(width=stand_w, height=5, depth=lip_h, bottom_face_center=(0, -1, base_t))\n"
                "lip = scad.union_rsolid(support_plate, _lip)"),
        Feature("charging-gap", "subtract",
                "_tool = scad.make_box_rsolid(width=gap_w, height=10, depth=lip_h + 10, bottom_face_center=(0, -1, base_t))\n"
                "charging_gap = scad.cut_rsolid(lip, _tool, skip_non_intersecting=False)"),
    ]
    return render_notebook(params, features)


def flange(bolt_n: int):
    params = [P("flange_od", 100), P("base_t", 10), P("boss_d", 55), P("total_h", 30), P("bore_d", 30), P("bolt_n", bolt_n, "1"),
              P("bolt_d", 11), P("pcd", 78), P("fillet_r", 3)]
    features = [
        Feature("body", "build",
                "_pts = [(bore_d / 2, 0, 0), (flange_od / 2, 0, 0), (flange_od / 2, 0, base_t),\n"
                "        (boss_d / 2, 0, base_t), (boss_d / 2, 0, total_h), (bore_d / 2, 0, total_h)]\n"
                "_wire = scad.make_polyline_rwire(points=_pts, closed=True)\n"
                "_profile = scad.make_face_from_wire_rface(wire=_wire, normal=(0, -1, 0))\n"
                "body = scad.revolve_rsolid(profile=_profile, axis=(0, 0, 1), angle=360, origin=(0, 0, 0))"),
        Feature("bolt-holes", "pattern",
                "_hole = scad.make_cylinder_rsolid(radius=bolt_d / 2, height=base_t + 2, bottom_face_center=(pcd / 2, 0, -1))\n"
                "_holes = scad.radial_pattern_rsolidlist(shape=_hole, center=(0, 0, 0), axis=(0, 0, 1), count=bolt_n, total_rotation_angle=360)\n"
                "bolt_holes = scad.cut_rsolid(body, _holes, skip_non_intersecting=False)"),
        Feature("root-fillet", "modify",
                "_edges = ql.edges().where(ql.and_(ql.prop('geom.type', '==', 'CIRCLE'), ql.prop('geom.center.z', '>=', base_t - 0.1),\n"
                "    ql.prop('geom.center.z', '<=', base_t + 0.1), ql.prop('geom.length', '>=', 3.14159 * boss_d - 1),\n"
                "    ql.prop('geom.length', '<=', 3.14159 * boss_d + 1))).exactly(1)\n"
                "root_fillet = scad.fillet_rsolid(solid=bolt_holes, edges=_edges, radius=fillet_r)"),
    ]
    return render_notebook(params, features)


def l_bracket(hole_d: float):
    params = [P("plate_l", 60), P("plate_w", 40), P("plate_t", 5), P("hole_d", hole_d), P("hole_edge", 12), P("rib_leg", 40)]
    features = [
        Feature("base-plate", "build",
                "base_plate = scad.make_box_rsolid(width=plate_l, height=plate_w, depth=plate_t, bottom_face_center=(0, 0, 0))"),
        Feature("upright-plate", "add",
                "_up = scad.make_box_rsolid(width=plate_t, height=plate_w, depth=plate_l, bottom_face_center=(plate_l / 2 - plate_t / 2, 0, 0))\n"
                "upright_plate = scad.union_rsolid(base_plate, _up)"),
        Feature("rib", "add",
                "_x = plate_l / 2 - plate_t\n"
                "_wire = scad.make_polyline_rwire(points=[(_x, 0, plate_t), (_x - rib_leg, 0, plate_t), (_x, 0, plate_t + rib_leg)], closed=True)\n"
                "_profile = scad.make_face_from_wire_rface(wire=_wire, normal=(0, 1, 0))\n"
                "_rib = scad.extrude_rsolid(profile=_profile, direction=(0, 1, 0), distance=plate_t)\n"
                "_rib = scad.translate_shape(shape=_rib, vector=(0, -plate_t / 2, 0))\n"
                "rib = scad.union_rsolid(upright_plate, _rib)"),
        Feature("holes", "subtract",
                "_dy = plate_w / 2 - hole_edge\n"
                "_b1 = scad.make_cylinder_rsolid(radius=hole_d / 2, height=plate_t + 2, bottom_face_center=(-plate_l / 2 + hole_edge, _dy, -1))\n"
                "_b2 = scad.make_cylinder_rsolid(radius=hole_d / 2, height=plate_t + 2, bottom_face_center=(-plate_l / 2 + hole_edge, -_dy, -1))\n"
                "_u1 = scad.make_cylinder_rsolid(radius=hole_d / 2, height=plate_t + 2, bottom_face_center=(plate_l / 2 - plate_t - 1, _dy, plate_l - hole_edge), axis=(1, 0, 0))\n"
                "_u2 = scad.make_cylinder_rsolid(radius=hole_d / 2, height=plate_t + 2, bottom_face_center=(plate_l / 2 - plate_t - 1, -_dy, plate_l - hole_edge), axis=(1, 0, 0))\n"
                "holes = scad.cut_rsolid(rib, _b1, _b2, _u1, _u2, skip_non_intersecting=False)"),
        Feature("top-chamfer", "modify",
                "_edges = ql.edges().where(ql.and_(ql.prop('geom.type', '==', 'LINE'), ql.prop('geom.center.z', '>=', plate_l - 0.1))).exactly(4)\n"
                "top_chamfer = scad.chamfer_rsolid(solid=holes, edges=_edges, distance=1)"),
    ]
    return render_notebook(params, features)


def enclosure(wall: float):
    params = [P("box_l", 80), P("box_w", 50), P("box_h", 30), P("wall", wall), P("floor_t", 2), P("usb_w", 12), P("usb_h", 6), P("usb_z", 8)]
    features = [
        Feature("shell", "build",
                "shell = scad.make_box_rsolid(width=box_l, height=box_w, depth=box_h, bottom_face_center=(0, 0, 0))"),
        Feature("cavity", "subtract",
                "_tool = scad.make_box_rsolid(width=box_l - 2 * wall, height=box_w - 2 * wall, depth=box_h, bottom_face_center=(0, 0, floor_t))\n"
                "cavity = scad.cut_rsolid(shell, _tool, skip_non_intersecting=False)"),
        # USB 口：穿过前墙（朝 -y 的那面墙，y 从 -box_w/2 到 -box_w/2+wall），两头各多出 1 mm
        Feature("usb-port", "subtract",
                "_tool = scad.make_box_rsolid(width=usb_w, height=wall + 2, depth=usb_h, bottom_face_center=(0, -box_w / 2 + wall / 2, usb_z))\n"
                "usb_port = scad.cut_rsolid(cavity, _tool, skip_non_intersecting=False)"),
    ]
    return render_notebook(params, features)


def stepped_shaft(top_d: float):
    params = [P("d1", 20), P("l1", 30), P("d2", 30), P("l2", 20), P("d3", top_d), P("l3", 40), P("cross_d", 6), P("cross_z", 40)]
    features = [
        Feature("seg-1", "build", "seg_1 = scad.make_cylinder_rsolid(radius=d1 / 2, height=l1, bottom_face_center=(0, 0, 0))"),
        Feature("seg-2", "add",
                "_c = scad.make_cylinder_rsolid(radius=d2 / 2, height=l2, bottom_face_center=(0, 0, l1))\n"
                "seg_2 = scad.union_rsolid(seg_1, _c)"),
        Feature("seg-3", "add",
                "_c = scad.make_cylinder_rsolid(radius=d3 / 2, height=l3, bottom_face_center=(0, 0, l1 + l2))\n"
                "seg_3 = scad.union_rsolid(seg_2, _c)"),
        # 横向通孔：轴线沿 y，从 y=-20 穿到 y=20（比第二段的半径 15 长）
        Feature("cross-hole", "subtract",
                "_tool = scad.make_cylinder_rsolid(radius=cross_d / 2, height=40, bottom_face_center=(0, -20, cross_z), axis=(0, 1, 0))\n"
                "cross_hole = scad.cut_rsolid(seg_3, _tool, skip_non_intersecting=False)"),
    ]
    return render_notebook(params, features)


CASES = [
    ("enclosure", "after_initial", lambda: enclosure(2)),
    ("enclosure", "after_mod_1", lambda: enclosure(3)),
    ("stepped_shaft", "after_initial", lambda: stepped_shaft(16)),
    ("stepped_shaft", "after_mod_1", lambda: stepped_shaft(18)),
    ("phone_stand", "after_initial", lambda: phone_stand(65)),
    ("phone_stand", "after_mod_1", lambda: phone_stand(70)),
    ("flange", "after_initial", lambda: flange(6)),
    ("flange", "after_mod_1", lambda: flange(8)),
    ("l_bracket", "after_initial", lambda: l_bracket(6.6)),
    ("l_bracket", "after_mod_1", lambda: l_bracket(8.4)),
]


@pytest.mark.parametrize("task_id,stage,build", CASES, ids=[f"{t}-{s}" for t, s, _ in CASES])
def test_reference_model_passes_acceptance(task_id, stage, build):
    task = load_task(task_id)
    result = run_job(build(), task["acceptance"][stage], set(), timeout_s=120)
    assert result.error is None, result.error
    report = "\n".join(f"{c.id}: passed={c.passed} measured={c.measured} expected={c.expected} {c.detail}" for c in result.checks)
    assert result.ok, report
    assert len(result.checks) == 3 + len(task["acceptance"][stage])


WRONG = [
    # 参数没改的版本，拿去对“修改之后”的验收：应当恰好卡在被修改的那一项上
    ("phone_stand", "after_mod_1", lambda: phone_stand(65), {"tilt-angle"}),
    ("flange", "after_mod_1", lambda: flange(6), {"bolt-holes"}),
    ("l_bracket", "after_mod_1", lambda: l_bracket(6.6), {"hole-faces"}),
    ("l_bracket", "after_initial", lambda: l_bracket(8.4), {"hole-faces"}),
    # 留出任务：壁厚还是 2、顶段直径还是 16 的旧模型，过不了修改后的验收
    ("enclosure", "after_mod_1", lambda: enclosure(2), {"volume", "in-2", "in-3"}),
    ("stepped_shaft", "after_mod_1", lambda: stepped_shaft(16), {"in-3"}),
]


@pytest.mark.parametrize("task_id,stage,build,failing", WRONG, ids=[f"{t}-{s}" for t, s, _, _ in WRONG])
def test_acceptance_catches_an_unmodified_model(task_id, stage, build, failing):
    result = run_job(build(), load_task(task_id)["acceptance"][stage], set(), timeout_s=120)
    assert result.error is None and not result.ok
    assert {c.id for c in result.checks if not c.passed} == failing
