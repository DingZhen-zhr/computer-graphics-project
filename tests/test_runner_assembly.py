"""3.0 计划 2 Task 7：沙盒里装配、量穿模、关节取样（真实 SCA，零件都是方块和圆柱）。"""

from __future__ import annotations

import pytest

from cad_agent.brief import Brief
from cad_agent.notebook import Feature, FeatureList
from cad_agent.product.spec import parse_assembly, parse_connectors
from cad_agent.product.workspace import ensure_parts, select_part
from cad_agent.sandbox.execute import run_assembly
from cad_agent.tools import Workspace

pytestmark = pytest.mark.sca

TOP = [["geom.type", "==", "PLANE"], ["geom.normal.z", ">=", 0.99]]
BOTTOM = [["geom.type", "==", "PLANE"], ["geom.normal.z", "<=", -0.99]]
HOLE = [["geom.type", "==", "CYLINDER"]]


def _p(name, value, part=None):
    d = {"name": name, "value": value, "unit": "mm", "source": "user", "note": ""}
    return {**d, "part": part} if part else d


def _ws(parts, params, feats, cons, asm) -> Workspace:
    b = Brief()
    b.apply_patch({"part": {"name": "测试"}, "parts": [{"id": i, "name": i, "material": "abs", "features": [i]} for i in parts],
                   "set_params": params})
    ws = Workspace(b, FeatureList(), [])
    ensure_parts(ws)
    names = {p["name"] for p in params}
    for pid in parts:
        select_part(ws, pid)
        for f in feats[pid]:
            ws.features.upsert(f)
        ws.parts[pid].connectors = parse_connectors(pid, cons.get(pid, []), names)
    select_part(ws, parts[0])
    ws.assembly = parse_assembly(asm, parts, {k: v.connectors for k, v in ws.parts.items()}, names)
    return ws


def _blocks(body_con=TOP, kind="faces") -> Workspace:
    feats = {"body": [Feature("shell", "build", "shell = scad.make_box_rsolid(width=40, height=40, depth=10, bottom_face_center=(0, 0, 0))", "s1")],
             "lid": [Feature("plate", "build", "plate = scad.make_box_rsolid(width=40, height=40, depth=4, bottom_face_center=(0, 0, 0))", "s1")]}
    cons = {"body": [{"name": "top", "kind": kind, "where": body_con}], "lid": [{"name": "bottom", "kind": "faces", "where": BOTTOM}]}
    asm = {"ground": "body", "mates": [{"id": "lid_on", "fixed": "body.top", "moving": "lid.bottom", "align": "opposite", "gap": "gap"}]}
    return _ws(["body", "lid"], [_p("gap", 0)], feats, cons, asm)


def _run(ws, **kw):
    return run_assembly(ws, mode=kw.pop("mode", "check"), samples=kw.pop("samples", 13), timeout_s=60, secret_names=(), **kw)


def test_two_blocks_rest_and_no_overlap():
    run = _run(_blocks())
    assert run.ok and run.error is None
    assert run.rest["body"] == [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]
    assert run.rest["lid"][11] == pytest.approx(10)
    assert run.overlaps == []
    assert run.connectors["body.top"] == {"selected": 1, "type": "PLANE", "center": [0, 0, 10], "direction": [0, 0, 1]}


def test_overlap_detected():
    ws = _blocks()
    ws.brief.params[0].value = -1
    run = _run(ws)
    assert run.overlaps == [{"a": "body", "b": "lid", "volume": pytest.approx(1600, abs=1e-3)}]


def test_connector_must_select_exactly_one():
    none = _run(_blocks([["geom.type", "==", "PLANE"], ["geom.normal.z", ">=", 2]]))
    assert not none.ok and none.connectors["body.top"]["selected"] == 0
    assert none.connectors["body.top"]["error"] == "零件 body 的连接点 top 选中了 0 个几何，要恰好 1 个。改一下 where 的条件。"
    two = _run(_blocks([["geom.type", "==", "PLANE"], ["geom.normal.y", ">=", -0.1], ["geom.normal.y", "<=", 0.1],
                        ["geom.normal.z", ">=", -0.1], ["geom.normal.z", "<=", 0.1]]))
    assert two.connectors["body.top"]["error"] == "零件 body 的连接点 top 选中了 2 个几何，要恰好 1 个。改一下 where 的条件。"
    assert two.rest == {} and not two.ok


def test_connector_wrong_type():
    run = _run(_blocks([["geom.type", "==", "LINE"], ["geom.center.x", ">=", 19.9], ["geom.center.z", ">=", 9.9]], kind="edges"))
    assert run.connectors["body.top"]["error"] == "零件 body 的连接点 top 选中的是 直线边，只能是圆柱面、平面或圆形的边。"
    assert not run.ok


def _swing() -> Workspace:
    base = [Feature("plate", "build", "plate = scad.make_box_rsolid(width=80, height=80, depth=4, bottom_face_center=(0, 0, 0))", "s1"),
            Feature("wall", "add", "_w = scad.make_box_rsolid(width=10, height=80, depth=20, bottom_face_center=(-35, 0, 4))\nwall = scad.union_rsolid(plate, _w)", "s1"),
            Feature("hole", "subtract", "_t = scad.make_cylinder_rsolid(radius=3, height=6, bottom_face_center=(0, 0, -1))\nhole = scad.cut_rsolid(wall, _t)", "s1")]
    arm = [Feature("bar", "build", "bar = scad.make_box_rsolid(width=50, height=10, depth=4, bottom_face_center=(19, 0, 0))", "s1"),
           Feature("bore", "subtract", "_t = scad.make_cylinder_rsolid(radius=3, height=6, bottom_face_center=(0, 0, -1))\nbore = scad.cut_rsolid(bar, _t)", "s1")]
    cons = {"base": [{"name": "axis", "kind": "faces", "where": HOLE}], "arm": [{"name": "axis", "kind": "faces", "where": HOLE}]}
    asm = {"ground": "base", "mates": [{"id": "pivot", "fixed": "base.axis", "moving": "arm.axis", "align": "same", "gap": 6}],
           "joints": [{"id": "swing", "mate": "pivot", "type": "revolute", "range": [0, 180], "label": "摆臂转动"}]}
    return _ws(["base", "arm"], [_p("t", 4)], {"base": base, "arm": arm}, cons, asm)


def test_hinge_sweep_detects_hit():
    run = _run(_swing())
    rows = run.samples["swing"]
    assert [r["value"] for r in rows][:3] == [0, 15, 30] and rows[-1]["value"] == 180
    assert run.overlaps == []
    assert all(r["hits"] == [] for r in rows if r["value"] <= 90)
    assert rows[-1]["hits"] and rows[-1]["hits"][0]["a"] == "base" and rows[-1]["hits"][0]["b"] == "arm"
    assert all(r["error"] is None for r in rows) and run.ok
    assert len(rows[-1]["poses"]["arm"]) == 16


def test_sample_error_is_reported_not_ignored(monkeypatch):
    monkeypatch.setenv("DATUM_TEST_FAIL_SAMPLE", "swing:3")
    run = _run(_swing())
    row = run.samples["swing"][3]
    assert row["error"] and "故意在这个位置出错" in row["error"]
    assert not run.ok
    assert run.samples["swing"][4]["error"] is None   # 别的位置照常量


def test_export_writes_product_and_part_files(tmp_path):
    run = _run(_blocks(), mode="export", out_dir=tmp_path)
    for name in ("product.step", "view.png", "assembly.py", "parts/body/model.step", "parts/body/model.stl", "parts/lid/model.stl"):
        assert (tmp_path / name).is_file() and (tmp_path / name).stat().st_size > 0, name
        assert run.files[name] == tmp_path / name
    assert "COLOUR_RGB" in (tmp_path / "product.step").read_text(encoding="utf-8", errors="replace")


def test_values_override():
    ws = _blocks()
    assert _run(ws).overlaps == []
    run = _run(ws, values={"gap": -2})
    assert run.overlaps[0]["volume"] == pytest.approx(3200, abs=1e-3)
    assert ws.brief.params[0].value == 0   # 原来的需求单不变
