"""终检用真实 SCA 拦住两种历史失败（设计文档成功标准 3；第二版计划 1 Task 8）。

1. 参数改了但几何没变（1.1 版留出任务 enclosure 的失败）：壁厚是用户参数，代码里却把壁厚写死了。
2. 用户参数没有被检查真正约束：唯一用到孔径的检查，期望值和孔径无关。
"""

import pytest

from cad_agent.brief import Brief, Param
from cad_agent.gates import Gates
from cad_agent.notebook import Feature, FeatureList
from cad_agent.plan import revise
from cad_agent.sandbox.execute import run_job
from cad_agent.staged.final_gate import run_final_gate
from cad_agent.tools import Workspace

pytestmark = pytest.mark.sca

ONE_STAGE = [{"title": "主体", "done_when": "做完了"}]


def ws_of(params: list[tuple[str, float]], features: list[Feature], checks: list[dict]) -> Workspace:
    brief = Brief(part_name="测试件", params=[Param(n, v, "mm", "user", "") for n, v in params], features=["主体"], confirmed=True)
    ws = Workspace(brief, FeatureList(features), [{**c, "stage": "s1"} for c in checks])
    ws.plan = revise(None, ONE_STAGE, {})
    ws.plan.mark_passed("s1")
    return ws


def gate(ws: Workspace):
    return run_final_gate(ws, run_job, Gates(), timeout_s=60, secret_names=())


def test_dead_param_is_caught():
    box = Feature("box", "build", "box = scad.make_box_rsolid(width=box_l, height=box_w, depth=box_h, bottom_face_center=(0, 0, 0))", "s1")
    # 内腔把壁厚写死成 2，没有用参数 wall
    cavity = Feature("cavity", "subtract",
                     "_c = scad.make_box_rsolid(width=box_l - 4, height=box_w - 4, depth=box_h, bottom_face_center=(0, 0, 2))\n"
                     "cavity = scad.cut_rsolid(box, _c, skip_non_intersecting=False)", "s1")
    checks = [
        {"id": "size-x", "type": "bbox", "axis": "x", "expected": "box_l"},
        {"id": "size-y", "type": "bbox", "axis": "y", "expected": "box_w"},
        {"id": "size-z", "type": "bbox", "axis": "z", "expected": "box_h"},
        {"id": "in-wall", "type": "point_inside", "point": ["box_l / 2 - wall / 2", 0, "box_h / 2"]},
        {"id": "cavity-empty", "type": "point_outside", "point": [0, 0, "box_h / 2"]},
    ]
    ws = ws_of([("box_l", 60), ("box_w", 40), ("box_h", 20), ("wall", 2)], [box, cavity], checks)
    g = gate(ws)
    assert g.missing_coverage == []
    assert g.unconstrained == ["wall"] and not g.passed
    verdicts = {m.param: m.verdict for m in g.mutation}
    assert verdicts == {"box_l": "constrained", "box_w": "constrained", "box_h": "constrained", "wall": "unconstrained"}


PLATE = Feature("plate", "build", "plate = scad.make_box_rsolid(width=80, height=50, depth=plate_t, bottom_face_center=(0, 0, 0))", "s1")
HOLE = Feature("hole", "subtract",
               "_h = scad.make_cylinder_rsolid(radius=hole_d / 2, height=plate_t + 2, bottom_face_center=(0, 0, -1))\n"
               "hole = scad.cut_rsolid(plate, _h, skip_non_intersecting=False)", "s1")
THICK = {"id": "thick", "type": "bbox", "axis": "z", "expected": "plate_t"}


def test_weak_check_is_caught():
    weak = {"id": "len", "type": "bbox", "axis": "x", "expected": "hole_d * 0 + 80"}
    g = gate(ws_of([("hole_d", 10), ("plate_t", 5)], [PLATE, HOLE], [THICK, weak]))
    assert g.missing_coverage == []
    assert g.unconstrained == ["hole_d"] and not g.passed


def test_good_model_passes():
    hole_dia = {"id": "hole-dia", "type": "count", "kind": "faces", "expected": 1,
                "where": [["geom.type", "==", "CYLINDER"], ["geom.area", ">=", "pi * hole_d * plate_t * 0.95"],
                          ["geom.area", "<=", "pi * hole_d * plate_t * 1.05"]]}
    g = gate(ws_of([("hole_d", 10), ("plate_t", 5)], [PLATE, HOLE], [THICK, hole_dia]))
    assert g.passed and g.unconstrained == [] and g.unbuildable == []
    assert {m.param: m.verdict for m in g.mutation} == {"hole_d": "constrained", "plate_t": "constrained"}
    caught = {m.param: m.caught_by for m in g.mutation}
    assert "hole-dia" in caught["hole_d"] and "thick" in caught["plate_t"]
