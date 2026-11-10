"""用假模型剧本加真实 SCA 沙盒走一遍分阶段的全流程（第二版计划 1 Task 15）。

剧本是"带孔的板"：两个阶段（板；孔），每个阶段先写检查、再写特征、最后 build；终检做参数扰动验证；
交付后在参数面板（内核部分）直接把孔改大，交付 v2，不再调用模型。不调用任何真实的大模型。
"""

import json

import pytest

from cad_agent.agent.loop import Agent
from cad_agent.agent.manual import apply_params
from cad_agent.brief import Brief, Param
from cad_agent.config import Config
from cad_agent.gates import Gates
from cad_agent.llm.fake import ScriptedLLM, scripted_call
from cad_agent.notebook import FeatureList
from cad_agent.sandbox.execute import run_job
from cad_agent.session import Session
from cad_agent.tools import ToolBox, Workspace

pytestmark = pytest.mark.sca

PLAN = scripted_call("set_plan", {"stages": [{"title": "板", "done_when": "有一块 plate_l × plate_w × plate_t 的板"},
                                             {"title": "孔", "done_when": "板正中有一个贯通的孔"}]})
S1 = scripted_call(
    "set_checks", {"stage": "s1", "checks": [
        {"id": "size-x", "type": "bbox", "axis": "x", "expected": "plate_l"},
        {"id": "size-y", "type": "bbox", "axis": "y", "expected": "plate_w"},
        {"id": "size-z", "type": "bbox", "axis": "z", "expected": "plate_t"},
    ]}, "",
    ("upsert_feature", {"slug": "plate", "role": "build",
                        "code": "plate = scad.make_box_rsolid(width=plate_l, height=plate_w, depth=plate_t, bottom_face_center=(0, 0, 0))"}),
    ("build", {}),
)
S2 = scripted_call(
    "set_checks", {"stage": "s2", "checks": [
        {"id": "hole-dia", "type": "count", "kind": "faces", "expected": 1,
         "where": [["geom.type", "==", "CYLINDER"], ["geom.area", ">=", "pi * hole_d * plate_t * 0.95"],
                   ["geom.area", "<=", "pi * hole_d * plate_t * 1.05"]]},
        {"id": "hole-center", "type": "point_outside", "point": [0, 0, "plate_t / 2"]},
    ]}, "",
    ("upsert_feature", {"slug": "hole", "role": "subtract",
                        "code": "_h = scad.make_cylinder_rsolid(radius=hole_d / 2, height=plate_t + 2, bottom_face_center=(0, 0, -1))\n"
                                "hole = scad.cut_rsolid(plate, _h, skip_non_intersecting=False)"}),
    ("build", {}),
)


def test_real_staged_flow(tmp_path):
    brief = Brief(part_name="带孔的板", purpose="测试", features=["板", "孔，在板正中"], relations=["孔在板的正中，贯通板厚"], confirmed=True,
                  params=[Param("plate_l", 80, "mm", "user", "长"), Param("plate_w", 50, "mm", "user", "宽"),
                          Param("plate_t", 5, "mm", "user", "厚"), Param("hole_d", 10, "mm", "user", "孔径")])
    llm = ScriptedLLM([PLAN, S1, S2])
    session = Session(tmp_path / "会话")   # 会话目录带中文，沙盒仍在英文临时目录里运行
    box = ToolBox(Workspace(brief, FeatureList(), []), run_job=run_job, timeout_s=120, gates=Gates(visual_review=False, cases=False))
    agent = Agent(llm, box, session, Config(base_url="http://x", model="m"))

    turn = agent.handle_user("开始建模")
    assert turn.kind == "delivered", turn.text
    v1 = turn.version_dir
    assert v1.name == "v1" and turn.llm_calls == 3
    for name in ("model.step", "view.png", "model.stl", "gate.json", "plan.json", "stages/s1.stl", "stages/s2.stl"):
        assert (v1 / name).is_file() and (v1 / name).stat().st_size > 0, name
    gate = json.loads((v1 / "gate.json").read_text(encoding="utf-8"))
    assert {m["param"]: m["verdict"] for m in gate["mutation"]} == {p: "constrained" for p in ("plate_l", "plate_w", "plate_t", "hole_d")}
    assert gate["unconstrained"] == [] and gate["missing_coverage"] == []
    assert "参数扰动验证：4 个用户参数都被检查约束。" in turn.text

    calls = len(llm.calls)
    result = apply_params(agent, {"hole_d": 14})
    assert result.ok, (result.text, result.failed_checks, result.error)
    assert result.version_dir.name == "v2" and len(llm.calls) == calls
    v2_brief = json.loads((result.version_dir / "brief.json").read_text(encoding="utf-8"))
    assert next(p for p in v2_brief["params"] if p["name"] == "hole_d")["value"] == 14
    assert (result.version_dir / "model.step").is_file() and (result.version_dir / "stages" / "s2.stl").is_file()
