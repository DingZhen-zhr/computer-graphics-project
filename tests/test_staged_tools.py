"""分阶段流程的工具（一）：计划、特征、检查的关卡（第二版计划 1 Task 6）。"""

import copy
import json
import re
from pathlib import Path

import pytest

from cad_agent.agent.state import PROMPT_DIR
from cad_agent.gates import Gates
from cad_agent.notebook import Feature, FeatureList
from cad_agent.plan import revise
from cad_agent.staged import messages as msg
from cad_agent.staged.specs import PRE_CONFIRM_TOOLS_V2, TOOL_NAMES_V2, TOOL_SPECS_V2
from cad_agent.tool_specs import TOOL_NAMES
from cad_agent.tools import ToolBox, Workspace
from helpers import BOX, PHONE_W, Runner, make_brief

PLANS = Path(__file__).resolve().parent.parent / "docs" / "superpowers" / "plans"
DOC_V2 = PLANS / "2026-11-10-caliper-1-kernel-prompts.md"
DOC_V11 = PLANS / "2026-11-09-cad-agent-v1.1-prompts.md"
DOC_V3 = DOC_V11.parent / "2026-11-20-datum-2-multipart-prompts.md"
STAGES = [{"title": "底板", "done_when": "有一块底板"}, {"title": "立板", "done_when": "左端有立板"}, {"title": "圆角", "done_when": "棱边倒圆"}]
WALL = "wall = scad.union_rsolid(base, scad.make_box_rsolid(width=8, height=40, depth=60, bottom_face_center=(-35, 0, 0)))"
ROUND = "round = wall"


def j(outcome) -> dict:
    return json.loads(outcome.content)


def make_box(confirmed: bool = True, plan: bool = False, passed: int = 0) -> ToolBox:
    ws = Workspace(make_brief(confirmed), FeatureList(), [])
    box = ToolBox(ws, run_job=Runner(), gates=Gates())
    if plan:
        ws.plan = revise(None, STAGES, {})
        for s in ws.plan.stages[:passed]:
            ws.plan.mark_passed(s.id)
    return box


def chk(cid: str, **extra) -> dict:
    return {"id": cid, "type": "bbox", "axis": "x", "expected": "phone_w", **extra}


def three_done() -> ToolBox:
    """三个阶段都写好了特征和检查，并且都已通过。"""
    box = make_box(plan=True)
    ws = box.ws
    ws.features = FeatureList([Feature("base", "build", BOX, "s1"), Feature("wall", "add", WALL, "s2"), Feature("round", "modify", ROUND, "s3")])
    ws.checks_raw = [chk("w1", stage="s1"), chk("w2", stage="s2"), chk("w3", stage="s3")]
    for s in ws.plan.stages:
        ws.plan.mark_passed(s.id)
    return box


def section(doc: Path, start: str, end: str) -> str:
    return doc.read_text(encoding="utf-8").split(start)[1].split(end)[0]


# ---------------------------------------------------------------- 原文


def test_system_v2_is_verbatim_copy():
    blocks = re.findall(r"```text\n(.*?)\n```", section(DOC_V2, "## 1. 系统提示词（分阶段流程）", "## 2. 文档目录"), flags=re.S)
    assert len(blocks) == 1
    assert (PROMPT_DIR / "system_v2.md").read_text(encoding="utf-8").rstrip("\n") == blocks[0]


def test_specs_v2_are_verbatim():
    sec6 = section(DOC_V2, "## 6. 工具说明（分阶段流程）", "## 7. build 的返回")
    new = {d["name"]: d for d in (json.loads(b) for b in re.findall(r"```json\n(.*?)\n```", sec6, flags=re.S))}
    assert set(new) == {"update_brief", "set_plan", "upsert_feature", "build", "probe", "read_reference"}
    old_sec = section(DOC_V11, "## 4. 工具说明", "## 5. 程序代按按钮时用到的原文")
    old = {d["name"]: d for d in (json.loads(b) for b in re.findall(r"```json\n(.*?)\n```", old_sec, flags=re.S))}
    order = re.search(r"顺序：(.+?)。", sec6).group(1).split("、")
    # 3.0 计划 2（要改的旧测试）：update_brief 对照 3.0 提示词文档第 3 节；工具 17 个，末尾 5 个也对照第 3 节
    sec3 = section(DOC_V3, "## 3. 工具说明", "## 4. 程序生成的消息")
    v3 = {d["name"]: d for d in (json.loads(b) for b in re.findall(r"```json\n(.*?)\n```", sec3, flags=re.S))}
    tail = ["select_part", "set_connectors", "set_assembly", "set_assembly_checks", "build_assembly"]
    assert TOOL_NAMES_V2 == order + tail and len(TOOL_NAMES_V2) == 17
    got = {s["function"]["name"]: s["function"] for s in TOOL_SPECS_V2}
    assert all(s["type"] == "function" for s in TOOL_SPECS_V2)
    for name in new:
        assert got[name] == (v3[name] if name == "update_brief" else new[name]), name
    for name in tail:
        assert got[name] == v3[name], name
    for name in ("ask_user", "request_confirmation", "remove_feature", "inspect", "api_help"):
        assert got[name] == old[name], name
    # set_checks：description 两段直接相连，parameters 在 1.1 版基础上改两处
    head = re.findall(r"```text\n(.*?)\n```", sec6.split("### set_checks")[1].split("### build")[0], flags=re.S)[0]
    old_desc = old["set_checks"]["description"]
    want_desc = head + old_desc[old_desc.index("\n表达式里可以用"):]
    params = copy.deepcopy(old["set_checks"]["parameters"])
    params["properties"]["stage"] = {"type": "string", "description": "阶段编号，如 s1"}
    params["required"] = ["stage", "checks"]
    params["properties"]["checks"]["items"]["properties"]["holds"] = {"type": "string", "enum": ["from_here", "here_only"]}
    assert got["set_checks"] == {"name": "set_checks", "description": want_desc, "parameters": params}
    assert PRE_CONFIRM_TOOLS_V2 == ["update_brief", "ask_user", "request_confirmation", "api_help", "read_reference"]


def test_messages_are_verbatim():
    sec7 = section(DOC_V2, "## 7. build 的返回、提示和关卡报错（分阶段流程）", "## 8. 速查表补充")
    blocks = re.findall(r"```text\n(.*?)\n```", sec7, flags=re.S)
    assert blocks[0] == "阶段 <id> 通过。现在是 <下一阶段 id>：<title>。先用 set_checks 写这个阶段的检查，再写特征，最后 build。"
    s2 = revise(None, STAGES, {}).stages[1]
    assert msg.hint_stage_passed(["s1"], s2) == blocks[0].replace("<id>", "s1").replace("<下一阶段 id>", "s2").replace("<title>", "立板")
    assert msg.hint_stage_passed(["s1", "s2"], s2).startswith("阶段 s1、s2 通过。")
    assert msg.hint_unconstrained(["a", "b"]) == blocks[1].replace("<参数名，用顿号连接>", "a、b")
    assert msg.NO_PLAN == blocks[2]
    assert msg.need_checks("s2") == blocks[3].replace("<id>", "s2")
    assert msg.all_passed() == blocks[4]
    assert msg.plan_locked("s1") == blocks[5].replace("<id>", "s1")
    assert msg.stage_has_features("s3", ["a", "b"]) == blocks[6].replace("<id>", "s3").replace("<slug，用顿号连接>", "a、b")
    assert msg.unknown_stage("s9", ["s1", "s2"]) == blocks[7].replace("<stage>", "s9").replace("<编号，用顿号连接>", "s1、s2")
    assert msg.future_stage("s3", "s1") == blocks[8].replace("<stage>", "s3").replace("<当前阶段 id>", "s1")
    assert msg.before_other_stage("s2") == blocks[9].replace("<id>", "s2")
    assert msg.build_no_features("s1") == blocks[10].replace("<id>", "s1")
    assert msg.build_no_checks("s1") == blocks[11].replace("<id>", "s1")
    assert msg.PROBE_LIMIT_REACHED == blocks[12]
    assert msg.ref_unknown("x", ["a", "b"]) == blocks[13].replace("<name>", "x").replace("<10 个名字，用顿号连接>", "a、b")
    assert msg.ref_no_section("a", "S", ["T", "U"]) == blocks[14].replace("<name>", "a").replace("<section>", "S").replace("<节标题，用顿号连接>", "T、U")
    assert msg.stage_calls_left(3) == blocks[15].replace("<n>", "3")
    assert msg.stage_cap_text("s2", "立板", 25) == blocks[16].replace("<id>", "s2").replace("<title>", "立板").replace("<n>", "25")


# ---------------------------------------------------------------- 开关与可用工具


def test_legacy_toolbox_is_untouched():
    ws = Workspace(make_brief(True), FeatureList(), [])
    box = ToolBox(ws, run_job=Runner())
    assert [s["function"]["name"] for s in box.schemas()] == TOOL_NAMES and len(TOOL_NAMES) == 9
    assert box.gates == Gates.legacy() and ws.brief.require_relations is False
    assert ToolBox(Workspace(make_brief(True), FeatureList(), []), run_job=Runner(), gates=Gates(staged=False)).available() == TOOL_NAMES


def test_schemas_by_phase_v2():
    box = make_box(confirmed=False)
    assert box.ws.brief.require_relations is True
    assert [s["function"]["name"] for s in box.schemas()] == PRE_CONFIRM_TOOLS_V2
    box.ws.brief.confirmed = True
    # 3.0 计划 2（偏离 D28，用户同意）：单零件时多零件的 5 个工具不出现，其余 12 个和第二版相同
    assert [s["function"]["name"] for s in box.schemas()] == TOOL_NAMES_V2[:12]
    out = make_box(confirmed=False).call("set_plan", {"stages": STAGES})
    assert "需求单现在不能建模" in j(out)["error"]


@pytest.mark.parametrize("name,args", [
    ("upsert_feature", {"slug": "base", "role": "build", "code": BOX}),
    ("remove_feature", {"slug": "base"}),
    ("set_checks", {"stage": "s1", "checks": [PHONE_W]}),
    ("build", {}),
    ("probe", {"code": "print(1)"}),
])
def test_modeling_tools_need_a_plan(name, args):
    box = make_box()
    assert j(box.call(name, args)) == {"error": msg.NO_PLAN}
    assert box.ws.features.items == [] and box.ws.checks_raw == [] and not box.unbuilt_edits


def test_missing_required_argument_uses_v2_table():
    box = make_box(plan=True)
    assert j(box.call("set_checks", {"checks": []}))["error"] == "工具 set_checks 缺少参数 stage"


# ---------------------------------------------------------------- set_plan


def test_set_plan_ok():
    box = make_box()
    body = j(box.call("set_plan", {"stages": STAGES}))
    assert body == {"ok": True, "stages": [{"id": "s1", "title": "底板", "passed": False}, {"id": "s2", "title": "立板", "passed": False},
                                           {"id": "s3", "title": "圆角", "passed": False}], "current": "s1"}
    assert box.ws.plan.ids() == ["s1", "s2", "s3"] and box.unbuilt_edits


def test_set_plan_errors_come_from_revise():
    box = make_box(plan=True, passed=1)
    changed = copy.deepcopy(STAGES)
    changed[0]["title"] = "换个名字"
    assert j(box.call("set_plan", {"stages": changed})) == {"error": msg.plan_locked("s1")}
    assert "1 到 12" in j(box.call("set_plan", {"stages": []}))["error"]
    assert box.ws.plan.stages[0].title == "底板" and not box.unbuilt_edits
    box.ws.features = FeatureList([Feature("base", "build", BOX, "s1"), Feature("fil", "modify", "fil = base", "s3")])
    assert j(box.call("set_plan", {"stages": STAGES[:2]})) == {"error": msg.stage_has_features("s3", ["fil"])}


def test_set_plan_after_all_passed_appends():
    box = three_done()
    body = j(box.call("set_plan", {"stages": STAGES + [{"title": "加孔", "done_when": "多一个孔"}]}))
    assert body["current"] == "s4" and [s["passed"] for s in body["stages"]] == [True, True, True, False]


# ---------------------------------------------------------------- upsert_feature


def test_new_feature_needs_checks_first():
    box = make_box(plan=True)
    assert j(box.call("upsert_feature", {"slug": "base", "role": "build", "code": BOX})) == {"error": msg.need_checks("s1")}
    assert box.ws.features.items == [] and not box.unbuilt_edits


def test_new_feature_goes_to_current_stage():
    box = make_box(plan=True, passed=1)
    box.ws.features = FeatureList([Feature("base", "build", BOX, "s1")])
    box.ws.checks_raw = [chk("w1", stage="s1"), chk("w2", stage="s2")]
    body = j(box.call("upsert_feature", {"slug": "wall", "role": "add", "code": WALL}))
    assert body == {"ok": True, "stage": "s2", "features": ["base(build, s1)", "wall(add, s2)"]}
    assert box.ws.features.items[1].stage == "s2" and box.unbuilt_edits
    body = j(box.call("upsert_feature", {"slug": "wall-2", "role": "add", "code": "wall_2 = wall"}))
    assert body["features"][-1] == "wall-2(add, s2)"


def test_before_must_be_in_same_stage():
    box = make_box(plan=True, passed=1)
    box.ws.features = FeatureList([Feature("base", "build", BOX, "s1"), Feature("wall", "add", WALL, "s2")])
    box.ws.checks_raw = [chk("w1", stage="s1"), chk("w2", stage="s2")]
    assert j(box.call("upsert_feature", {"slug": "rib", "role": "add", "code": "rib = base", "before": "base"})) == {"error": msg.before_other_stage("s2")}
    assert j(box.call("upsert_feature", {"slug": "rib", "role": "add", "code": "rib = base", "before": "nope"})) == {"error": msg.before_other_stage("s2")}
    assert [f.slug for f in box.ws.features.items] == ["base", "wall"]
    body = j(box.call("upsert_feature", {"slug": "rib", "role": "add", "code": "rib = base", "before": "wall"}))
    assert body["features"] == ["base(build, s1)", "rib(add, s2)", "wall(add, s2)"]


def test_new_feature_when_all_passed():
    box = three_done()
    assert j(box.call("upsert_feature", {"slug": "extra", "role": "add", "code": "extra = round"})) == {"error": msg.all_passed()}
    assert len(box.ws.features.items) == 3


def test_replacing_feature_invalidates_its_stage_and_later():
    box = three_done()
    body = j(box.call("upsert_feature", {"slug": "wall", "role": "add", "code": WALL + "  # 改过"}))
    assert body["stage"] == "s2"
    assert [s.passed for s in box.ws.plan.stages] == [True, False, False]
    assert [(f.slug, f.stage) for f in box.ws.features.items] == [("base", "s1"), ("wall", "s2"), ("round", "s3")]
    assert box.ws.features.items[1].code.endswith("# 改过")


def test_remove_feature_invalidates():
    box = three_done()
    body = j(box.call("remove_feature", {"slug": "round"}))
    assert body == {"ok": True, "features": ["base(build, s1)", "wall(add, s2)"]}
    assert [s.passed for s in box.ws.plan.stages] == [True, True, False] and box.unbuilt_edits
    assert "没有特征" in j(box.call("remove_feature", {"slug": "nope"}))["error"]


# ---------------------------------------------------------------- set_checks


def test_set_checks_replaces_only_that_stage():
    box = make_box(plan=True, passed=1)
    box.ws.plan.invalidate_all()
    assert j(box.call("set_checks", {"stage": "s1", "checks": [chk("a"), chk("b", holds="here_only")]}))["count"] == 2
    box.ws.plan.mark_passed("s1")
    assert j(box.call("set_checks", {"stage": "s2", "checks": [chk("c")]}))["count"] == 1
    body = j(box.call("set_checks", {"stage": "s1", "checks": [chk("d", stage="s9")]}))
    assert body == {"ok": True, "stage": "s1", "count": 1, "missing_coverage": ["tilt_deg"]}
    assert box.ws.checks_raw == [chk("d", stage="s1"), chk("c", stage="s2")]
    assert all("stage" in c for c in box.ws.checks_raw)


def test_set_checks_missing_coverage_counts_only_from_here():
    box = make_box(plan=True)
    tilt = {"id": "tilt", "type": "angle", "expected": "tilt_deg", "holds": "here_only",
            "a": [["geom.type", "==", "PLANE"], ["geom.normal.z", ">=", 0.99]], "b": [["geom.type", "==", "PLANE"], ["geom.normal.z", "<=", -0.99]]}
    assert j(box.call("set_checks", {"stage": "s1", "checks": [chk("w"), tilt]}))["missing_coverage"] == ["tilt_deg"]


def test_set_checks_rejects_unknown_and_future_stage():
    box = make_box(plan=True, passed=1)
    box.ws.checks_raw = [chk("w1", stage="s1")]
    before_checks, before_state = copy.deepcopy(box.ws.checks_raw), box.ws.plan.to_list()
    assert j(box.call("set_checks", {"stage": "s7", "checks": [chk("x")]})) == {"error": msg.unknown_stage("s7", ["s1", "s2", "s3"])}
    assert j(box.call("set_checks", {"stage": "s3", "checks": [chk("x")]})) == {"error": msg.future_stage("s3", "s2")}
    assert j(box.call("set_checks", {"stage": 2, "checks": [chk("x")]})) == {"error": msg.unknown_stage("2", ["s1", "s2", "s3"])}
    assert box.ws.checks_raw == before_checks and box.ws.plan.to_list() == before_state and not box.unbuilt_edits


def test_set_checks_on_passed_stage_invalidates():
    box = three_done()
    j(box.call("set_checks", {"stage": "s2", "checks": [chk("w2b")]}))
    assert [s.passed for s in box.ws.plan.stages] == [True, False, False]
    assert [c["id"] for c in box.ws.checks_raw] == ["w1", "w2b", "w3"]


def test_guard_and_spec_errors_keep_state():
    box = three_done()
    before = (copy.deepcopy(box.ws.checks_raw), box.ws.features.to_list(), box.ws.plan.to_list())
    out = j(box.call("upsert_feature", {"slug": "wall", "role": "add", "code": "import os\nwall = base"}))
    assert out["error"].startswith("特征 wall 的代码没有通过检查，没有改动：")
    out = j(box.call("set_checks", {"stage": "s2", "checks": [{"id": "bad", "type": "nope"}]}))
    assert out["error"].startswith("检查项没有通过校验，原有检查项保持不变：")
    out = j(box.call("set_checks", {"stage": "s2", "checks": [chk("w1")]}))   # 和 s1 的检查重名
    assert "重复" in out["error"]
    assert (box.ws.checks_raw, box.ws.features.to_list(), box.ws.plan.to_list()) == before and not box.unbuilt_edits


# ---------------------------------------------------------------- update_brief


def test_update_brief_change_invalidates_all():
    box = three_done()
    body = j(box.call("update_brief", {"set_params": [{"name": "phone_w", "value": 80, "unit": "mm", "source": "user", "note": "手机宽度"}]}))
    assert body["changes"] and all(not s.passed for s in box.ws.plan.stages)


def test_update_brief_without_change_does_not():
    box = three_done()
    body = j(box.call("update_brief", {"set_params": [{"name": "phone_w", "value": 78, "unit": "mm", "source": "user", "note": "手机宽度"}]}))
    assert body["changes"] == [] and all(s.passed for s in box.ws.plan.stages)


def test_unbuilt_edits_set_by_each_edit():
    for name, args, setup in [
        ("set_plan", {"stages": STAGES}, lambda b: None),
        ("set_checks", {"stage": "s1", "checks": [chk("w")]}, lambda b: setattr(b.ws, "plan", revise(None, STAGES, {}))),
        ("upsert_feature", {"slug": "base", "role": "build", "code": BOX},
         lambda b: (setattr(b.ws, "plan", revise(None, STAGES, {})), setattr(b.ws, "checks_raw", [chk("w", stage="s1")]))),
        ("remove_feature", {"slug": "round"}, lambda b: None),
    ]:
        box = three_done() if name == "remove_feature" else make_box()
        setup(box)
        box.unbuilt_edits = False
        assert "error" not in j(box.call(name, args)), name
        assert box.unbuilt_edits, name


ASK_ONCE = ("   - 要问的一次问完：把还没定的尺寸和做法都放进同一次提问，每个都给建议值，用户回\"都按建议\"就全部按建议值记下。"
            "用户回答以后，只有答案互相矛盾、或者缺了做不下去的东西时才再问；量法、对齐这类小事按常见做法定下，写进需求单，"
            "确认时用户能看到，不要为它单独再问一轮。")


def test_ask_once_with_suggestions():
    """计划 6 Task 4：问答一次问完（学老师平台；对应 toolbox 第二轮卡在问答轮数上的 F7）。"""
    text = (PROMPT_DIR / "system_v2.md").read_text(encoding="utf-8")
    assert ASK_ONCE in text.splitlines()
