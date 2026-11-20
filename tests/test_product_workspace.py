"""3.0 计划 2 Task 4：多零件工作区和会话目录。"""

from __future__ import annotations

from cad_agent.agent.resume import load_workspace
from cad_agent.brief import Brief
from cad_agent.notebook import Feature, FeatureList
from cad_agent.plan import Plan, Stage
from cad_agent.product.spec import parse_assembly, parse_connectors
from cad_agent.product.workspace import ensure_parts, part_param_names, product_state, select_part
from cad_agent.session import Session
from cad_agent.tools import Workspace

TOP = [["geom.type", "==", "PLANE"], ["geom.normal.z", ">=", 0.99]]


def _brief() -> Brief:
    b = Brief()
    b.apply_patch({"part": {"name": "盒子"},
                   "parts": [{"id": "body", "name": "盒体", "material": "abs", "features": ["盒体"]},
                             {"id": "lid", "name": "盖子", "material": "aluminum", "features": ["盖板"]}],
                   "set_params": [{"name": "w", "value": 40, "unit": "mm", "source": "user", "note": ""},
                                  {"name": "lid_t", "value": 4, "unit": "mm", "source": "user", "note": "", "part": "lid"},
                                  {"name": "wall", "value": 2, "unit": "mm", "source": "user", "note": "", "part": "body"}]})
    return b


def _ws() -> Workspace:
    ws = Workspace(_brief(), FeatureList(), [])
    ensure_parts(ws)
    return ws


def _feat(slug: str) -> Feature:
    return Feature(slug, "build", f"{slug} = scad.make_box_rsolid(width=w, height=w, depth=2, bottom_face_center=(0, 0, 0))", "s1")


def test_select_part_swaps_state():
    ws = _ws()
    assert ws.active == "body"
    select_part(ws, "lid")
    ws.features.upsert(_feat("plate"))
    ws.checks_raw = [{"id": "c1", "type": "volume", "expected": 1}]
    ws.probes_used = 2
    select_part(ws, "body")
    assert ws.features.items == [] and ws.checks_raw == [] and ws.probes_used == 0
    select_part(ws, "lid")
    assert [f.slug for f in ws.features.items] == ["plate"] and ws.checks_raw[0]["id"] == "c1" and ws.probes_used == 2


def test_ensure_parts_follows_brief():
    ws = _ws()
    assert list(ws.parts) == ["body", "lid"]
    ws.parts["body"].done = True
    ensure_parts(ws)
    assert ws.active == "lid"
    ws.brief.apply_patch({"parts": [{"id": "body", "name": "盒体", "material": "abs", "features": ["盒体"]},
                                    {"id": "handle", "name": "提手", "material": "rubber", "features": ["提手"]}],
                          "remove_params": ["lid_t"]})
    ensure_parts(ws)
    assert list(ws.parts) == ["body", "handle"] and ws.active == "handle"
    # 有特征的零件不删
    select_part(ws, "handle")
    ws.features.upsert(_feat("grip"))
    ws.brief.apply_patch({"parts": [{"id": "body", "name": "盒体", "material": "abs", "features": ["盒体"]},
                                    {"id": "cap", "name": "帽", "material": "abs", "features": ["帽"]}]})
    ensure_parts(ws)
    assert set(ws.parts) == {"body", "cap", "handle"}


def test_single_part_workspace_unchanged():
    ws = Workspace(Brief(), FeatureList(), [])
    assert ws.parts == {} and ws.active is None and ws.assembly is None and ws.assembly_checks_raw == []
    assert ws.assembly_passed is False and ws.last_assembly is None
    assert product_state(ws) is None


def test_part_dir_layout(tmp_path):
    s = Session(tmp_path)
    assert s.part_dir() == s.dir and s.part_dir("main") == s.dir
    assert s.part_dir("lid") == s.dir / "parts" / "lid" and (s.dir / "parts" / "lid").is_dir()


def test_save_and_resume_multipart(tmp_path):
    ws = _ws()
    ws.features.upsert(_feat("shell"))
    ws.plan = Plan([Stage("s1", "外形", "有外形", passed=True)])
    ws.parts["body"].connectors = parse_connectors("body", [{"name": "top", "kind": "faces", "where": TOP}], {"w"})
    select_part(ws, "lid")
    ws.features.upsert(_feat("plate"))
    ws.parts["lid"].connectors = parse_connectors("lid", [{"name": "bottom", "kind": "faces", "where": TOP}], {"w"})
    ws.parts["body"].done = True
    ws.assembly = parse_assembly({"ground": "body", "mates": [{"id": "m", "fixed": "body.top", "moving": "lid.bottom", "align": "opposite"}]},
                                 ["body", "lid"], {k: v.connectors for k, v in ws.parts.items()}, {"w"})
    ws.assembly_checks_raw = [{"id": "gap", "type": "interference", "a": "body", "b": "lid"}]
    s = Session(tmp_path)
    s.save_state(ws.brief, ws.features.to_list(), ws.checks_raw, "# x\n", product=product_state(ws))
    assert (s.dir / "parts" / "body" / "features.json").is_file() and (s.dir / "assembly.json").is_file()
    back = load_workspace(s)
    assert back.active == "lid" and [f.slug for f in back.features.items] == ["plate"]
    assert back.parts["body"].done and not back.parts["lid"].done
    assert [f.slug for f in back.parts["body"].features.items] == ["shell"]
    assert back.parts["body"].plan.stages[0].passed
    assert [c.name for c in back.parts["lid"].connectors] == ["bottom"]
    assert back.assembly is not None and back.assembly.mates[0].moving == "lid.bottom"
    assert back.assembly_checks_raw[0]["id"] == "gap"


def test_part_param_names():
    ws = _ws()
    assert part_param_names(ws, "lid") == ["w", "lid_t"]
    assert part_param_names(ws, "body") == ["w", "wall"]
