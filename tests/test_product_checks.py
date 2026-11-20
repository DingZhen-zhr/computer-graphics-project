"""3.0 计划 2 Task 8：装配和运动的检查（手造的 AssemblyRun，不跑沙盒）。"""

from __future__ import annotations

import pytest

from cad_agent.product.checks import evaluate, mandatory_checks, parse_assembly_checks
from cad_agent.product.model import Assembly, Coupling, Joint, Mate, ProductError
from cad_agent.sandbox.runner_assembly import AssemblyRun

I4 = [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]
IDS = ["body", "lid", "handle"]
CYL = [["geom.type", "==", "CYLINDER"]]


def _asm() -> Assembly:
    return Assembly("body", [Mate("lid_on", "body.hinge", "lid.hinge", "same"), Mate("handle_on", "lid.top", "handle.base", "opposite")],
                    [Joint("open", "lid_on", "revolute", 0, 110, None, "盖子翻开")], [])


def _gear_asm() -> Assembly:
    return Assembly("plate", [Mate("m1", "plate.s1", "g1.bore", "same"), Mate("m2", "plate.s2", "g2.bore", "same")],
                    [Joint("j1", "m1", "revolute", 0, 360, None, "小齿轮"), Joint("j2", "m2", "revolute", -180, 0, None, "大齿轮")],
                    [Coupling("j1", "j2", -0.5, "gear")])


def _row(v, hits=(), error=None, joints=None):
    return {"value": v, "poses": {}, "hits": list(hits), "error": error, "joints": joints or {}}


def _run(**kw) -> AssemblyRun:
    base = dict(ok=True, error=None, connectors={"body.hinge": {"selected": 1, "type": "CYLINDER"}},
                rest={"body": I4, "lid": I4, "handle": I4}, overlaps=[], measures={},
                samples={"open": [_row(0), _row(55), _row(110)]})
    base.update(kw)
    return AssemblyRun(**base)


def _one(run, check, asm=None, values=None):
    asm = asm or _asm()
    return evaluate(run, [check], asm, values or {})[0]


def _parse(raw, asm=None):
    asm = asm or _asm()
    ids = ["plate", "g1", "g2"] if asm.ground == "plate" else IDS
    return parse_assembly_checks(raw, asm, ids, {"gap"})


def test_mandatory_checks_order():
    assert [c["id"] for c in mandatory_checks(_asm(), IDS)] == ["connectors_anchored", "no_overlap_at_rest", "motion_clear_open"]
    assert [c["id"] for c in mandatory_checks(_gear_asm(), [])][2:] == ["motion_clear_j1", "motion_clear_j2"]


def test_connectors_anchored_pass_fail():
    c = mandatory_checks(_asm(), IDS)[0]
    assert _one(_run(), c).passed
    bad = _run(connectors={"body.hinge": {"selected": 0, "error": "零件 body 的连接点 hinge 选中了 0 个几何，要恰好 1 个。改一下 where 的条件。"}})
    r = _one(bad, c)
    assert not r.passed and "选中了 0 个几何" in r.detail


def test_contact_pairs_only_from_joints_and_gears():
    c = mandatory_checks(_asm(), IDS)[1]
    # 转动关节两边（body、lid）允许 0.5 立方毫米以内的接触
    assert _one(_run(overlaps=[{"a": "body", "b": "lid", "volume": 0.4}]), c).passed
    assert not _one(_run(overlaps=[{"a": "body", "b": "lid", "volume": 0.6}]), c).passed
    # 固定配合 handle_on 的两边（lid、handle）不豁免：0.02 就不行
    r = _one(_run(overlaps=[{"a": "lid", "b": "handle", "volume": 0.02}]), c)
    assert not r.passed and r.detail == "装好后零件 lid 和 handle 重叠了 0.02 立方毫米"
    # 齿轮联动的两个齿轮也豁免
    g = _gear_asm()
    run = _run(overlaps=[{"a": "g1", "b": "g2", "volume": 0.3}], samples={})
    assert _one(run, mandatory_checks(g, [])[1], g).passed


def test_interference_and_clearance():
    chk = _parse([{"id": "fit", "type": "interference", "a": "lid", "b": "handle"},
                  {"id": "gap", "type": "clearance", "a": "body", "b": "handle", "expected": "gap"}])
    run = _run(measures={"fit": {"volume": 0.0}, "gap": {"distance": 1.5}})
    res = evaluate(run, chk, _asm(), {"gap": 1})
    assert [r.passed for r in res] == [True, True]
    run = _run(measures={"fit": {"volume": 2.0}, "gap": {"distance": 0.5}})
    res = evaluate(run, chk, _asm(), {"gap": 1})
    assert [r.passed for r in res] == [False, False]
    assert res[1].detail == "零件 body 和 handle 最近 0.5 毫米，要 >= 1"


def test_coaxial_and_flush():
    chk = _parse([{"id": "ax", "type": "coaxial", "a": {"part": "body", "kind": "faces", "where": CYL}, "b": {"part": "lid", "where": CYL}},
                  {"id": "fl", "type": "flush", "a": {"part": "body", "where": CYL}, "b": {"part": "lid", "where": CYL}, "expected": 2}])
    ok = _run(measures={"ax": {"selected_a": 1, "selected_b": 1, "distance": 0.01, "angle": 0.1},
                        "fl": {"selected_a": 1, "selected_b": 1, "distance": 2.0, "angle": 0.0}})
    assert [r.passed for r in evaluate(ok, chk, _asm(), {})] == [True, True]
    bad = _run(measures={"ax": {"selected_a": 1, "selected_b": 1, "distance": 0.01, "angle": 3.0},
                         "fl": {"selected_a": 2, "selected_b": 1}})
    res = evaluate(bad, chk, _asm(), {})
    assert [r.passed for r in res] == [False, False]
    assert res[1].detail == "a（零件 body）选中了 2 个平面，要恰好 1 个"


def test_motion_clear_pass_fail_and_pair_filter():
    c = mandatory_checks(_asm(), IDS)[2]
    assert _one(_run(), c).passed
    run = _run(samples={"open": [_row(0), _row(55, [{"a": "body", "b": "handle", "volume": 3.2}]), _row(110)]})
    r = _one(run, c)
    assert not r.passed and r.detail == "盖子翻开 动到 55° 时，零件 body 和 handle 碰到了，重叠 3.2 立方毫米"
    only = _parse([{"id": "lid_free", "type": "motion_clear", "joint": "open", "a": "body", "b": "lid"}])[0]
    assert _one(run, only).passed


def test_sample_error_fails_motion_clear():
    run = _run(samples={"open": [_row(0), _row(55, error="RuntimeError：布尔运算失败"), _row(110)]})
    r = _one(run, mandatory_checks(_asm(), IDS)[2])
    assert not r.passed and r.detail == "盖子翻开 在 55° 时没量成：RuntimeError：布尔运算失败"


def test_reach_and_ratio():
    reach = _parse([{"id": "r95", "type": "reach", "joint": "open", "value": 95}])[0]
    assert not _one(_run(), reach).passed
    assert _one(_run(samples={"open": [_row(0), _row(95.2), _row(110)]}), reach).passed
    assert not _one(_run(samples={"open": [_row(0), _row(95, error="x"), _row(110)]}), reach).passed
    g = _gear_asm()
    ratio = _parse([{"id": "half", "type": "ratio", "driver": "j1", "driven": "j2", "expected": -0.5}], g)[0]
    rows = [_row(0, joints={"j1": 0, "j2": 0}), _row(360, joints={"j1": 360, "j2": -180})]
    assert _one(_run(samples={"j1": rows}), ratio, g).passed
    rows[1]["joints"]["j2"] = -120
    assert not _one(_run(samples={"j1": rows}), ratio, g).passed


def test_unknown_part_or_joint_rejected():
    for raw in ([{"id": "x", "type": "interference", "a": "body", "b": "nope"}],
                [{"id": "x", "type": "motion_clear", "joint": "spin"}],
                [{"id": "x", "type": "reach", "joint": "open", "value": "zz"}],
                [{"id": "x", "type": "coaxial", "a": {"part": "body", "where": CYL}, "b": {"part": "cap", "where": CYL}}],
                [{"id": "no_overlap_at_rest", "type": "interference", "a": "body", "b": "lid"}],
                [{"id": "x", "type": "wobble"}],
                [{"id": "x", "type": "clearance", "a": "body", "b": "lid"}]):
        with pytest.raises(ProductError):
            _parse(raw)


def test_details_are_chinese_and_specific():
    chk = mandatory_checks(_asm(), IDS)
    run = _run(overlaps=[{"a": "body", "b": "lid", "volume": 12.5}],
               samples={"open": [_row(0), _row(110, [{"a": "body", "b": "lid", "volume": 7}])]})
    res = evaluate(run, chk, _asm(), {})
    assert res[1].detail == "装好后零件 body 和 lid 重叠了 12.5 立方毫米"
    assert res[2].detail == "盖子翻开 动到 110° 时，零件 body 和 lid 碰到了，重叠 7 立方毫米"
    assert all(any("一" <= ch <= "鿿" for ch in r.detail) for r in res)
