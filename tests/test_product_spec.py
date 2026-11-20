"""3.0 计划 2 Task 3：连接点、配合、关节、联动的声明和校验。"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from cad_agent.product.materials import MATERIALS
from cad_agent.product.spec import (ProductError, contact_pairs, mate_tree, moving_parts, parse_assembly,
                                    parse_connectors)

PROMPTS = Path(__file__).resolve().parents[1] / "docs/superpowers/plans/2026-11-20-datum-2-multipart-prompts.md"
TOP = [["geom.type", "==", "PLANE"], ["geom.normal.z", ">=", 0.99]]
BOT = [["geom.type", "==", "PLANE"], ["geom.normal.z", "<=", -0.99]]
AXIS = [["geom.type", "==", "CYLINDER"]]


def test_materials_verbatim():
    text = PROMPTS.read_text(encoding="utf-8")
    block = text.split("## 2. 材料表", 1)[1].split("```json", 1)[1].split("```", 1)[0]
    assert [vars(m) for m in MATERIALS.values()] == json.loads(block)


def _cons(part: str, *names: str) -> list:
    return parse_connectors(part, [{"name": n, "kind": "faces", "where": TOP} for n in names], {"h"})


def test_parse_connectors_ok_and_errors():
    cs = parse_connectors("lid", [{"name": "hinge_axis", "kind": "faces", "where": AXIS, "offset": "h / 2", "flip": True},
                                  {"name": "rim", "kind": "edges", "where": [["geom.type", "==", "CIRCLE"]]}], {"h"})
    assert [c.name for c in cs] == ["hinge_axis", "rim"]
    assert cs[0].offset == "h / 2" and cs[0].flip and cs[1].offset == 0.0 and cs[0].part == "lid"
    bad = [
        [{"name": "A", "kind": "faces", "where": TOP}],
        [{"name": "a", "kind": "solids", "where": TOP}],
        [{"name": "a", "kind": "faces", "where": [["geom.radius", "==", 3]]}],
        [{"name": "a", "kind": "faces", "where": TOP, "offset": "zz + 1"}],
        [{"name": "a", "kind": "faces", "where": TOP}, {"name": "a", "kind": "faces", "where": BOT}],
        [{"name": "a", "kind": "faces", "where": TOP, "flip": "yes"}],
    ]
    for raw in bad:
        with pytest.raises(ProductError):
            parse_connectors("lid", raw, {"h"})


def _box_cons() -> dict:
    return {"body": _cons("body", "top", "back"), "lid": _cons("lid", "bottom", "hinge"), "handle": _cons("handle", "base")}


def _raw(**over) -> dict:
    raw = {"ground": "body",
           "mates": [{"id": "lid_on", "fixed": "body.back", "moving": "lid.hinge", "align": "same"},
                     {"id": "handle_on", "fixed": "lid.bottom", "moving": "handle.base", "align": "opposite", "gap": "h"}],
           "joints": [{"id": "open", "mate": "lid_on", "type": "revolute", "range": [0, 110], "label": "盖子翻开"}]}
    raw.update(over)
    return raw


IDS = ["body", "lid", "handle"]


def test_mates_must_form_a_tree():
    asm = parse_assembly(_raw(), IDS, _box_cons(), {"h"})
    assert mate_tree(asm) == {"lid": ("body", "lid_on"), "handle": ("lid", "handle_on")}
    cases = {
        "漏连": [{"id": "lid_on", "fixed": "body.back", "moving": "lid.hinge", "align": "same"}],
        "成圈": [{"id": "m1", "fixed": "handle.base", "moving": "lid.hinge", "align": "same"},
                 {"id": "m2", "fixed": "lid.bottom", "moving": "handle.base", "align": "same"}],
        "同一个零件": [{"id": "lid_on", "fixed": "lid.bottom", "moving": "lid.hinge", "align": "same"},
                       {"id": "handle_on", "fixed": "lid.bottom", "moving": "handle.base", "align": "opposite"}],
    }
    for why, mates in cases.items():
        with pytest.raises(ProductError) as e:
            parse_assembly(_raw(mates=mates, joints=[]), IDS, _box_cons(), {"h"})
        msg = str(e.value)
        if why != "同一个零件":
            assert msg.startswith("装配关系有问题：") and msg.endswith("除了 ground，每个零件都要被恰好一个配合连到已经装好的零件上，不能连成一圈。"), why
    with pytest.raises(ProductError, match="handle"):
        parse_assembly(_raw(mates=cases["漏连"], joints=[]), IDS, _box_cons(), {"h"})
    with pytest.raises(ProductError, match="连成了一圈"):
        parse_assembly(_raw(mates=cases["成圈"], joints=[]), IDS, _box_cons(), {"h"})
    with pytest.raises(ProductError, match="不存在"):
        parse_assembly(_raw(mates=[{"id": "x", "fixed": "body.nope", "moving": "lid.hinge", "align": "same"}]), IDS, _box_cons(), {"h"})


def test_joint_range_normalized_and_zero_rejected():
    asm = parse_assembly(_raw(joints=[{"id": "open", "mate": "lid_on", "type": "revolute", "range": [110, 0], "label": "盖子翻开"}]),
                         IDS, _box_cons(), {"h"})
    assert (asm.joints[0].lo, asm.joints[0].hi) == (0, 110)
    assert asm.notes == ["关节 open 的范围写反了，已经按从小到大处理"]
    with pytest.raises(ProductError, match="相等"):
        parse_assembly(_raw(joints=[{"id": "open", "mate": "lid_on", "type": "revolute", "range": [30, 30], "label": "x"}]),
                       IDS, _box_cons(), {"h"})
    assert parse_assembly(_raw(), IDS, _box_cons(), {"h"}).notes == []


def test_prismatic_needs_direction():
    j = {"id": "pull", "mate": "lid_on", "type": "prismatic", "range": [0, 100], "label": "拉出"}
    with pytest.raises(ProductError, match="direction"):
        parse_assembly(_raw(joints=[j]), IDS, _box_cons(), {"h"})
    with pytest.raises(ProductError, match="零向量"):
        parse_assembly(_raw(joints=[{**j, "direction": [0, 0, 0]}]), IDS, _box_cons(), {"h"})
    asm = parse_assembly(_raw(joints=[{**j, "direction": [0, -2, 0]}]), IDS, _box_cons(), {"h"})
    assert asm.joints[0].direction == (0.0, -1.0, 0.0)


def _gears() -> tuple[dict, list]:
    cons = {"plate": _cons("plate", "s1", "s2"), "g1": _cons("g1", "bore"), "g2": _cons("g2", "bore")}
    raw = {"ground": "plate",
           "mates": [{"id": "m1", "fixed": "plate.s1", "moving": "g1.bore", "align": "same"},
                     {"id": "m2", "fixed": "plate.s2", "moving": "g2.bore", "align": "same"}],
           "joints": [{"id": "j1", "mate": "m1", "type": "revolute", "range": [0, 360], "label": "小齿轮"},
                      {"id": "j2", "mate": "m2", "type": "revolute", "range": [-180, 0], "label": "大齿轮"}],
           "couplings": [{"driver": "j1", "driven": "j2", "ratio": -0.5, "kind": "gear"}]}
    return cons, raw


def test_couplings_validated():
    cons, raw = _gears()
    ids = ["plate", "g1", "g2"]
    asm = parse_assembly(raw, ids, cons, set())
    assert asm.couplings[0].ratio == -0.5
    for bad in ([{"driver": "j1", "driven": "j9", "ratio": 1, "kind": "gear"}],
                [{"driver": "j1", "driven": "j1", "ratio": 1, "kind": "gear"}],
                [{"driver": "j1", "driven": "j2", "ratio": 1, "kind": "chain"}],
                [{"driver": "j1", "driven": "j2", "ratio": 1, "kind": "gear"}, {"driver": "j2", "driven": "j1", "ratio": 1, "kind": "gear"}]):
        with pytest.raises(ProductError):
            parse_assembly({**raw, "couplings": bad}, ids, cons, set())


def test_moving_parts_is_subtree():
    asm = parse_assembly(_raw(), IDS, _box_cons(), {"h"})
    assert moving_parts(asm, "open") == {"lid", "handle"}


def test_contact_pairs_only_from_joints_and_gears():
    asm = parse_assembly(_raw(), IDS, _box_cons(), {"h"})
    assert contact_pairs(asm) == {frozenset({"body", "lid"})}     # 固定的 handle_on 不在里面
    cons, raw = _gears()
    pairs = contact_pairs(parse_assembly(raw, ["plate", "g1", "g2"], cons, set()))
    assert pairs == {frozenset({"plate", "g1"}), frozenset({"plate", "g2"}), frozenset({"g1", "g2"})}
    assert re  # 保持导入
