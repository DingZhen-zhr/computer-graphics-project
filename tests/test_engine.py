import math

import pytest

from cad_agent.brief import Param
from cad_agent.checks.engine import body_facts, query, run_checks
from cad_agent.checks.spec import parse_checks
from cad_agent.notebook import Feature, render_notebook

pytestmark = pytest.mark.sca

TOP = [["geom.type", "==", "PLANE"], ["geom.normal.z", ">=", 0.99]]
BOTTOM = [["geom.type", "==", "PLANE"], ["geom.normal.z", "<=", -0.99]]
SIDE_X = [["geom.type", "==", "PLANE"], ["geom.normal.x", ">=", 0.99]]
HOLE = [["geom.type", "==", "CYLINDER"]]


@pytest.fixture(scope="module")
def plate(tmp_path_factory):
    """60×36×8 的板，底面中心在原点，减去中心 r=5 的通孔。"""
    from simplecadapi.runtime import run_notebook

    params = [Param("w", 60, "mm", "user"), Param("h", 36, "mm", "user"), Param("t", 8, "mm", "user"), Param("r", 5, "mm", "user")]
    feats = [
        Feature("plate", "build", "plate = scad.make_box_rsolid(width=w, height=h, depth=t, bottom_face_center=(0, 0, 0))"),
        Feature(
            "hole", "subtract",
            "_tool = scad.make_cylinder_rsolid(radius=r, height=t + 2, bottom_face_center=(0, 0, -1))\n"
            "hole = scad.cut_rsolid(plate, _tool)",
        ),
    ]
    path = tmp_path_factory.mktemp("engine") / "model.py"
    path.write_text(render_notebook(params, feats).text, encoding="utf-8")
    return run_notebook(path, cache=False).product.body


VALUES = {"w": 60.0, "h": 36.0, "t": 8.0, "r": 5.0}


def run(plate, raw, values=None):
    values = VALUES if values is None else values
    results = run_checks(plate, parse_checks(raw, set(values)), values)
    assert [r.id for r in results[:3]] == ["valid", "single_solid", "positive_volume"]
    return results[3:]


def test_mandatory_pass(plate):
    results = run_checks(plate, parse_checks([], set()), {})
    assert len(results) == 3 and all(r.passed for r in results)


def test_bbox_pass_and_fail(plate):
    ok, bad = run(plate, [{"id": "x", "type": "bbox", "axis": "x", "expected": 60},
                          {"id": "x2", "type": "bbox", "axis": "x", "expected": 61}])
    assert ok.passed and not bad.passed and abs(bad.measured - 60) < 1e-6
    assert bad.expected == 61 and bad.tol == 0.1 and "x" in bad.detail


def test_bbox_uses_parameters(plate):
    r, = run(plate, [{"id": "zz", "type": "bbox", "axis": "z", "expected": "t"}])
    assert r.passed and r.expected == 8.0


def test_count_cylinder_faces(plate):
    r, = run(plate, [{"id": "holes", "type": "count", "kind": "faces", "where": HOLE, "expected": 1}])
    assert r.passed and r.measured == 1


def test_count_ops_and_edges(plate):
    ge, le, bad, edges = run(plate, [
        {"id": "ge", "type": "count", "kind": "faces", "where": [["geom.type", "==", "PLANE"]], "expected": 5, "op": ">="},
        {"id": "le", "type": "count", "kind": "faces", "where": [["geom.type", "==", "PLANE"]], "expected": 5, "op": "<="},
        {"id": "eq", "type": "count", "kind": "faces", "where": [["geom.type", "==", "PLANE"]], "expected": 5},
        {"id": "circles", "type": "count", "kind": "edges", "where": [["geom.type", "==", "CIRCLE"]], "expected": 2},
    ])
    assert ge.passed and not le.passed and not bad.passed and edges.passed and bad.measured == 6


def test_count_where_with_expression(plate):
    r, = run(plate, [{"id": "top", "type": "count", "kind": "faces",
                      "where": [["geom.type", "==", "PLANE"], ["geom.center.z", ">=", "t - 0.1"]], "expected": 1}])
    assert r.passed


def test_points(plate):
    hole, wall, wrong_in, wrong_out, on_surface_in, on_surface_out = run(plate, [
        {"id": "hole-empty", "type": "point_outside", "point": [0, 0, 4]},
        {"id": "wall-solid", "type": "point_inside", "point": [20, 0, "t / 2"]},
        {"id": "bad-in", "type": "point_inside", "point": [0, 0, 4]},
        {"id": "bad-out", "type": "point_outside", "point": [20, 0, 4]},
        {"id": "on-in", "type": "point_inside", "point": [30, 0, 4]},
        {"id": "on-out", "type": "point_outside", "point": [30, 0, 4]},
    ])
    assert hole.passed and wall.passed and not wrong_in.passed and not wrong_out.passed
    assert on_surface_in.passed and not on_surface_out.passed  # 点正好在表面上，算“在材料上”
    assert "材料外" in hole.detail and "材料里" in wall.detail


def test_angle_top_vs_side(plate):
    r, = run(plate, [{"id": "ang", "type": "angle", "a": TOP, "b": SIDE_X, "expected": 90}])
    assert r.passed and abs(r.measured - 90) < 1e-6 and r.tol == 0.5


def test_angle_top_vs_bottom_is_180_and_fail_reports_measured(plate):
    ok, bad = run(plate, [{"id": "flat", "type": "angle", "a": TOP, "b": BOTTOM, "expected": 180},
                          {"id": "wrong", "type": "angle", "a": TOP, "b": BOTTOM, "expected": 115}])
    assert ok.passed and not bad.passed and abs(bad.measured - 180) < 1e-6


def test_distance_hole_to_side(plate):
    r, ge, tight = run(plate, [
        {"id": "d", "type": "distance", "a": {"kind": "faces", "where": HOLE}, "b": {"kind": "faces", "where": SIDE_X}, "expected": 25},
        {"id": "d-ge", "type": "distance", "a": {"kind": "faces", "where": HOLE}, "b": {"kind": "faces", "where": SIDE_X}, "expected": 20, "op": ">="},
        {"id": "d-le", "type": "distance", "a": {"kind": "faces", "where": HOLE}, "b": {"kind": "faces", "where": SIDE_X}, "expected": 20, "op": "<="},
    ])
    assert r.passed and abs(r.measured - 25) < 1e-6
    assert ge.passed and not tight.passed


def test_volume(plate):
    expected = 60 * 36 * 8 - math.pi * 25 * 8
    ok, bad = run(plate, [{"id": "v", "type": "volume", "expected": expected},
                          {"id": "v-bad", "type": "volume", "expected": expected * 1.05}])
    assert ok.passed and abs(ok.measured - expected) < 1e-3 and not bad.passed


def test_zero_selection_is_failure_not_crash(plate):
    r, = run(plate, [{"id": "ang", "type": "angle", "a": [["geom.center.z", ">", 999]], "b": TOP, "expected": 0}])
    assert not r.passed and "选中 0 个" in r.detail


def test_distance_zero_selection_is_failure_not_crash(plate):
    r, = run(plate, [{"id": "d", "type": "distance", "a": {"kind": "faces", "where": [["geom.center.z", ">", 999]]},
                      "b": {"kind": "faces", "where": SIDE_X}, "expected": 1}])
    assert not r.passed and "选中 0 个" in r.detail


def test_detail_has_selection_card(plate):
    r, = run(plate, [{"id": "holes", "type": "count", "kind": "faces", "where": HOLE, "expected": 2}])
    assert not r.passed and "中心" in r.detail and "CYLINDER" in r.detail


def test_selection_card_lists_at_most_8(plate):
    r, = run(plate, [{"id": "all", "type": "count", "kind": "edges", "where": [], "expected": 99}])
    assert not r.passed and r.measured == 15 and r.detail.count("中心") == 8 and "共 15 个" in r.detail


def test_exception_in_one_check_does_not_stop_others(plate):
    checks = parse_checks([{"id": "x", "type": "bbox", "axis": "x", "expected": "w"},
                           {"id": "y", "type": "bbox", "axis": "y", "expected": "h"}], {"w", "h"})
    results = run_checks(plate, checks, {"w": 60.0})  # 故意缺少参数 h 的值
    by_id = {r.id: r for r in results}
    assert by_id["x"].passed and not by_id["y"].passed and "h" in by_id["y"].detail


def test_query_faces(plate):
    items = query(plate, "faces", HOLE, VALUES)
    assert len(items) == 1
    f = items[0]
    assert f["type"] == "CYLINDER" and abs(f["area"] - 2 * math.pi * 5 * 8) < 1e-3 and abs(f["center"][2] - 4) < 1e-6
    assert "normal" not in f
    top = query(plate, "faces", TOP, VALUES)[0]
    assert top["type"] == "PLANE" and top["normal"] == [0.0, 0.0, 1.0] and abs(top["center"][2] - 8) < 1e-6


def test_query_edges(plate):
    items = query(plate, "edges", [["geom.type", "==", "CIRCLE"]], VALUES)
    assert len(items) == 2 and all(abs(e["length"] - 2 * math.pi * 5) < 1e-3 for e in items)
    assert len(query(plate, "edges", [], VALUES)) == 15


def test_body_facts(plate):
    f = body_facts(plate)
    assert f["bbox"] == [-30.0, -18.0, 0.0, 30.0, 18.0, 8.0] and f["size"] == [60.0, 36.0, 8.0]
    assert abs(f["volume"] - (60 * 36 * 8 - math.pi * 25 * 8)) < 1e-3 and f["n_faces"] == 7 and f["n_edges"] == 15
