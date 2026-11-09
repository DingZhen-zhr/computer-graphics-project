import math

import pytest

from cad_agent.checks.spec import (
    CHECK_TYPES,
    Check,
    CheckResult,
    CheckSpecError,
    eval_expr,
    missing_coverage,
    parse_checks,
)

TOP = [["geom.type", "==", "PLANE"], ["geom.normal.z", ">=", 0.99]]
BOTTOM = [["geom.type", "==", "PLANE"], ["geom.normal.z", "<=", -0.99]]


def one(raw: dict, params: set[str] | None = None) -> Check:
    [*_, c] = parse_checks([raw], params or set())
    return c


def test_check_types():
    assert CHECK_TYPES == {"bbox", "count", "angle", "point_inside", "point_outside", "distance", "volume"}


def test_eval_expr():
    assert eval_expr("a + 2*b", {"a": 1, "b": 3}) == 7
    assert eval_expr(5, {}) == 5.0
    assert abs(eval_expr("sin(radians(30))", {}) - 0.5) < 1e-9
    assert eval_expr("-pi", {}) == -math.pi
    assert eval_expr("max(2, a**2) / 4", {"a": 3}) == 2.25
    assert eval_expr("phone_t + 2*clearance", {"phone_t": 12, "clearance": 1}) == 14


@pytest.mark.parametrize("bad", ["__import__('os')", "a.b", "open('x')", "zz", "a if a else 1", "[1]", "a < 1", "'s'", "1 +"])
def test_eval_expr_rejects(bad):
    with pytest.raises(CheckSpecError):
        eval_expr(bad, {"a": 1})


def test_eval_expr_rejects_bool_division_by_zero_and_huge_power():
    for bad in (True, "1 / 0", "9 ** 9 ** 9"):
        with pytest.raises(CheckSpecError):
            eval_expr(bad, {})


def test_eval_expr_unknown_name_is_named():
    with pytest.raises(CheckSpecError, match="zz"):
        eval_expr("zz + 1", {"a": 1})


def test_parse_bbox_defaults():
    [*_, c] = parse_checks([{"id": "w", "type": "bbox", "axis": "x", "expected": "base_l"}], {"base_l"})
    assert c.tol == 0.1 and c.refs == {"base_l"} and c.type == "bbox" and c.args == {"axis": "x"} and c.expected == "base_l"


def test_bbox_axis_must_be_xyz():
    with pytest.raises(CheckSpecError, match="axis"):
        one({"id": "w", "type": "bbox", "axis": "w", "expected": 1})


def test_angle_default_tol():
    c = one({"id": "tilt", "type": "angle", "a": TOP, "b": BOTTOM, "expected": "180 - tilt_deg"}, {"tilt_deg"})
    assert c.tol == 0.5 and c.refs == {"tilt_deg"}


def test_explicit_tol_is_kept():
    assert one({"id": "w", "type": "bbox", "axis": "x", "expected": 5, "tol": 0.5}).tol == 0.5


def test_volume_uses_relative_tolerance():
    assert one({"id": "v", "type": "volume", "expected": 100}).tol == 0.01
    assert one({"id": "v", "type": "volume", "expected": 100, "rel_tol": 0.03}).tol == 0.03


def test_mandatory_first():
    assert [c.id for c in parse_checks([], set())] == ["valid", "single_solid", "positive_volume"]
    out = parse_checks([{"id": "w", "type": "bbox", "axis": "x", "expected": 1}], set())
    assert [c.id for c in out] == ["valid", "single_solid", "positive_volume", "w"]


def test_reserved_and_duplicate_ids_rejected():
    for reserved in ("valid", "single_solid", "positive_volume"):
        with pytest.raises(CheckSpecError, match=reserved):
            parse_checks([{"id": reserved, "type": "volume", "expected": 1}], set())
    dup = {"id": "w", "type": "bbox", "axis": "x", "expected": 1}
    with pytest.raises(CheckSpecError, match="重复"):
        parse_checks([dup, dup], set())


@pytest.mark.parametrize("bad_id", ["", "Bad Id", "1x", None, 5])
def test_bad_id_rejected(bad_id):
    with pytest.raises(CheckSpecError, match="id"):
        parse_checks([{"id": bad_id, "type": "volume", "expected": 1}], set())


def test_unknown_type_lists_allowed():
    with pytest.raises(CheckSpecError, match="bbox"):
        parse_checks([{"id": "x", "type": "weight", "expected": 1}], set())
    with pytest.raises(CheckSpecError, match="type"):
        parse_checks([{"id": "x", "expected": 1}], set())


def test_count_op_default_and_ge():
    base = {"id": "holes", "type": "count", "kind": "faces", "where": [["geom.type", "==", "CYLINDER"]], "expected": "bolt_n"}
    c_default = one(base, {"bolt_n"})
    c_ge = one({**base, "id": "holes2", "op": ">="}, {"bolt_n"})
    assert c_default.op == "==" and c_ge.op == ">=" and c_default.tol is None
    with pytest.raises(CheckSpecError, match="op"):
        one({**base, "op": "~"}, {"bolt_n"})


def test_count_requires_kind_where_expected():
    ok = {"id": "n", "type": "count", "kind": "faces", "where": [], "expected": 1}
    assert one(ok).args == {"kind": "faces", "where": []}
    for drop in ("kind", "where", "expected"):
        raw = {k: v for k, v in ok.items() if k != drop}
        with pytest.raises(CheckSpecError, match=drop):
            one(raw)
    with pytest.raises(CheckSpecError, match="kind"):
        one({**ok, "kind": "vertices"})


def test_unknown_param_in_expr_rejected():
    with pytest.raises(CheckSpecError, match="nope"):
        one({"id": "w", "type": "bbox", "axis": "x", "expected": "nope * 2"}, {"base_l"})


def test_params_in_where_values_and_points_are_refs():
    c = one({"id": "n", "type": "count", "kind": "faces",
             "where": [["geom.type", "==", "PLANE"], ["geom.center.z", ">=", "lip_h - 0.1"]], "expected": 1}, {"lip_h"})
    assert c.refs == {"lip_h"}
    p = one({"id": "gap", "type": "point_outside", "point": [0, "base_d / 2", "lip_h"]}, {"base_d", "lip_h"})
    assert p.refs == {"base_d", "lip_h"} and p.expected is None and p.args == {"point": [0, "base_d / 2", "lip_h"]}


def test_bad_where_rejected():
    def count(where):
        return {"id": "n", "type": "count", "kind": "faces", "where": where, "expected": 1}

    for bad, hint in (
        ([["center.z", ">=", 1]], "geom."),
        ([["geom.radius", ">=", 1]], "geom.radius"),
        ([["geom.center.z", "~", 1]], "~"),
        ([["geom.type", "==", "plane"]], "大写"),
        ([["geom.type", ">=", "PLANE"]], "geom.type"),
        ([["geom.center.z", ">=", "zz"]], "zz"),
        ([["geom.center.z", ">="]], "三项"),
        ("geom.type", "where"),
    ):
        with pytest.raises(CheckSpecError, match=hint):
            one(count(bad))


def test_point_needs_three_values():
    with pytest.raises(CheckSpecError, match="point"):
        one({"id": "p", "type": "point_inside", "point": [0, 0]})


def test_distance_spec():
    raw = {"id": "d", "type": "distance", "a": {"kind": "faces", "where": [["geom.type", "==", "CYLINDER"]]},
           "b": {"kind": "faces", "where": TOP}, "expected": "edge_gap", "op": ">="}
    c = one(raw, {"edge_gap"})
    assert c.op == ">=" and c.tol == 0.1 and c.refs == {"edge_gap"} and set(c.args) == {"a", "b"}
    with pytest.raises(CheckSpecError, match="kind"):
        one({**raw, "a": {"where": []}}, {"edge_gap"})


def test_unknown_key_rejected_and_irrelevant_known_key_ignored():
    with pytest.raises(CheckSpecError, match="axes"):
        one({"id": "w", "type": "bbox", "axes": "x", "expected": 1})
    # 共用 schema 里有的字段，写在不相关的类型上时忽略
    assert one({"id": "w", "type": "bbox", "axis": "x", "expected": 1, "kind": "faces", "rel_tol": 0.5}).tol == 0.1
    # 但 bbox 写了非 == 的 op，会让人误以为是区间检查，必须报错
    with pytest.raises(CheckSpecError, match="op"):
        one({"id": "w", "type": "bbox", "axis": "x", "expected": 1, "op": ">="})


def test_items_must_be_objects():
    with pytest.raises(CheckSpecError):
        parse_checks(["bbox"], set())  # type: ignore[list-item]


def test_missing_coverage():
    checks = parse_checks([{"id": "w", "type": "bbox", "axis": "x", "expected": "a"}], {"a", "b"})
    assert missing_coverage(checks, {"a", "b"}) == {"b"}
    assert missing_coverage(checks, set()) == set()


def test_check_result_round_trip():
    r = CheckResult("w", "bbox", False, 60.2, 60.0, 0.1, "x 向尺寸 60.2")
    assert CheckResult.from_dict(r.to_dict()) == r
    r2 = CheckResult("p", "point_inside", True, None, None, None, "")
    assert CheckResult.from_dict(r2.to_dict()) == r2
    assert r.to_dict() == {"id": "w", "type": "bbox", "passed": False, "measured": 60.2, "expected": 60.0, "tol": 0.1, "detail": "x 向尺寸 60.2"}
