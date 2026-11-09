import json
import re
from pathlib import Path

import pytest

from cad_agent.brief import Brief, Param
from cad_agent.checks.spec import CheckResult
from cad_agent.notebook import FeatureList
from cad_agent.sandbox.execute import RunResult
from cad_agent.tools import ToolBox, ToolOutcome, Workspace

PROMPTS_DOC = Path(__file__).resolve().parent.parent / "docs" / "superpowers" / "plans" / "2026-11-09-cad-agent-v1-prompts.md"
BOX = "base = scad.make_box_rsolid(width=phone_w, height=40, depth=8, bottom_face_center=(0, 0, 0))"
PHONE_W = {"id": "width", "type": "bbox", "axis": "x", "expected": "phone_w"}
TILT = {"id": "tilt", "type": "angle", "expected": "tilt_deg",
        "a": [["geom.type", "==", "PLANE"], ["geom.normal.z", ">=", 0.99]], "b": [["geom.type", "==", "PLANE"], ["geom.normal.z", "<=", -0.99]]}
ALL_TOOLS = ["update_brief", "ask_user", "request_confirmation", "upsert_feature", "remove_feature", "set_checks", "build", "inspect", "api_help"]
PRE_CONFIRM_TOOLS = ["update_brief", "ask_user", "request_confirmation", "api_help"]


def j(outcome: ToolOutcome) -> dict:
    assert isinstance(outcome, ToolOutcome)
    return json.loads(outcome.content)


def make_brief(confirmed: bool = True) -> Brief:
    return Brief(
        part_name="手机支架", purpose="放桌上看视频",
        params=[Param("phone_w", 78, "mm", "user", "手机宽度"), Param("tilt_deg", 65, "deg", "user", "支撑角度"),
                Param("lip_h", 15, "mm", "suggested", "托唇高度")],
        features=["底座"], confirmed=confirmed,
    )


def good_result(**over) -> RunResult:
    checks = [CheckResult(i, i, True, None, None, None, "") for i in ("valid", "single_solid", "positive_volume")]
    base = dict(ok=True, error=None, values={"phone_w": 78.0, "tilt_deg": 65.0, "lip_h": 15.0}, checks=checks,
                facts={"bbox": [0, 0, 0, 90, 52.1, 99.7], "size": [90.0, 52.1, 99.7], "volume": 12345.6, "n_faces": 9, "n_edges": 20},
                duration_s=0.5)
    base.update(over)
    return RunResult(**base)


class Stub:
    """代替 run_job：记录调用，返回事先给定的结果。"""

    def __init__(self, result: RunResult | None = None) -> None:
        self.result = result or good_result()
        self.calls: list[tuple] = []

    def __call__(self, rendered, checks_raw, param_names, **kw):
        self.calls.append((rendered, checks_raw, param_names, kw))
        return self.result


def make_box(confirmed: bool = True, result: RunResult | None = None, with_feature: bool = True, checks=None):
    ws = Workspace(make_brief(confirmed), FeatureList(), [])
    stub = Stub(result)
    tb = ToolBox(ws, run_job=stub, timeout_s=12, secret_names=("MY_KEY",))
    if with_feature:
        assert j(tb.call("upsert_feature", {"slug": "base", "role": "build", "code": BOX}))["ok"] is True
    if checks is not None:
        assert "error" not in j(tb.call("set_checks", {"checks": checks}))
    return tb, ws, stub


def test_modeling_tools_blocked_before_confirmation():
    tb, ws, stub = make_box(confirmed=False, with_feature=False)
    for name, args in (("build", {}), ("upsert_feature", {"slug": "base", "role": "build", "code": BOX}),
                       ("set_checks", {"checks": []}), ("inspect", {"kind": "faces"}), ("remove_feature", {"slug": "base"})):
        out = tb.call(name, args)
        assert "需求单" in out.content and not out.end_turn and not out.deliverable, name
    assert stub.calls == [] and ws.features.items == [] and ws.checks_raw == []


def test_blocked_when_open_questions_even_if_confirmed():
    tb, ws, stub = make_box(with_feature=False)
    ws.brief.open_questions = ["手机多厚？"]
    out = tb.call("build", {})
    assert "需求单" in out.content and "手机多厚" in out.content and stub.calls == []


def test_schemas_by_phase():
    tb, ws, _ = make_box(confirmed=False, with_feature=False)
    assert [s["function"]["name"] for s in tb.schemas()] == PRE_CONFIRM_TOOLS
    ws.brief.confirmed = True
    assert [s["function"]["name"] for s in tb.schemas()] == ALL_TOOLS
    assert all(s["type"] == "function" and set(s["function"]) == {"name", "description", "parameters"} for s in tb.schemas())


def test_schemas_are_verbatim_copy_of_prompts_doc():
    text = PROMPTS_DOC.read_text(encoding="utf-8")
    section = text.split("## 3. 工具说明")[1].split("## 4. build 返回给模型的格式")[0]
    expected = [json.loads(b) for b in re.findall(r"```json\n(.*?)\n```", section, flags=re.S)]
    assert [e["name"] for e in expected] == ALL_TOOLS
    tb, _, _ = make_box(with_feature=False)
    assert [s["function"] for s in tb.schemas()] == expected


def test_update_brief_reports_changes():
    tb, ws, _ = make_box(with_feature=False)
    out = j(tb.call("update_brief", {"set_params": [{"name": "tilt_deg", "value": 70, "unit": "deg", "source": "user", "note": "角度"}]}))
    assert any("65 → 70" in c for c in out["changes"]) and out["can_build"] is True
    assert ws.brief.param_values()["tilt_deg"] == 70
    out = j(tb.call("update_brief", {"set_params": [{"name": "gap", "value": 2, "unit": "mm", "source": "suggested", "note": "余量"}]}))
    assert out["can_build"] is False and "未确认" in out["why_not"]


def test_update_brief_error_keeps_state():
    tb, ws, _ = make_box(with_feature=False)
    before = ws.brief.to_dict()
    out = j(tb.call("update_brief", {"set_params": [{"name": "w", "value": 7.8, "unit": "cm", "source": "user", "note": ""}]}))
    assert "mm" in out["error"] and ws.brief.to_dict() == before
    assert "error" in j(tb.call("update_brief", {"nonsense": 1}))


def test_ask_user_ends_turn():
    tb, *_ = make_box(confirmed=False, with_feature=False)
    out = tb.call("ask_user", {"questions": ["手机多厚？建议 12 mm", "要横放吗？"]})
    assert out.end_turn and out.kind == "question" and not out.deliverable
    assert j(out)["questions"] == ["手机多厚？建议 12 mm", "要横放吗？"]


@pytest.mark.parametrize("bad", [[], ["a"] * 6, "手机多厚", [1], [""]])
def test_ask_user_validates_questions(bad):
    tb, *_ = make_box(confirmed=False, with_feature=False)
    out = tb.call("ask_user", {"questions": bad})
    assert not out.end_turn and "error" in j(out)


def test_request_confirmation_shows_brief():
    tb, ws, _ = make_box(confirmed=False, with_feature=False)
    out = tb.call("request_confirmation", {})
    assert out.end_turn and out.kind == "confirm" and ws.awaiting_confirmation
    assert "phone_w" in out.content and "用户给的" in out.content and "智能体建议" in out.content


def test_request_confirmation_refused_with_open_questions():
    tb, ws, _ = make_box(confirmed=False, with_feature=False)
    ws.brief.open_questions = ["手机多厚？"]
    out = tb.call("request_confirmation", {})
    assert not out.end_turn and not ws.awaiting_confirmation and "手机多厚" in out.content


def test_upsert_feature_ok_and_before():
    tb, ws, _ = make_box()
    out = j(tb.call("upsert_feature", {"slug": "fillet", "role": "modify", "code": "fillet = base"}))
    assert out["ok"] and out["features"] == ["base(build)", "fillet(modify)"]
    tb.call("upsert_feature", {"slug": "hole", "role": "subtract", "code": "hole = base", "before": "fillet"})
    assert [f.slug for f in ws.features.items] == ["base", "hole", "fillet"]
    assert "error" in j(tb.call("upsert_feature", {"slug": "x", "role": "add", "code": "x = 1", "before": "nope"}))


def test_upsert_guard_failure_keeps_state():
    tb, ws, _ = make_box()
    before = ws.features.to_list()
    out = j(tb.call("upsert_feature", {"slug": "base", "role": "build", "code": "import os\nbase = open('x')"}))
    assert "import" in out["error"] and "open" in out["error"]
    assert ws.features.to_list() == before
    bad_role = j(tb.call("upsert_feature", {"slug": "x", "role": "weld", "code": "x = 1"}))
    assert "role" in bad_role["error"] and ws.features.to_list() == before


def test_remove_feature():
    tb, ws, _ = make_box()
    assert j(tb.call("remove_feature", {"slug": "base"}))["ok"] and ws.features.items == []
    assert "error" in j(tb.call("remove_feature", {"slug": "base"}))


def test_set_checks_ok_replaces_and_reports_coverage():
    tb, ws, _ = make_box()
    out = j(tb.call("set_checks", {"checks": [PHONE_W]}))
    assert out["ok"] and out["count"] == 1 and out["missing_coverage"] == ["tilt_deg"]
    assert ws.checks_raw == [PHONE_W]
    tb.call("set_checks", {"checks": [PHONE_W, TILT]})
    assert ws.checks_raw == [PHONE_W, TILT]


def test_set_checks_error_keeps_state():
    tb, ws, _ = make_box(checks=[PHONE_W])
    out = j(tb.call("set_checks", {"checks": [{"id": "bad", "type": "bbox", "axis": "x", "expected": "nope"}]}))
    assert "nope" in out["error"] and ws.checks_raw == [PHONE_W]
    assert "error" in j(tb.call("set_checks", {"checks": "not a list"}))


def test_build_coverage_gap_not_deliverable():
    tb, ws, stub = make_box(checks=[PHONE_W])
    out = tb.call("build", {})
    body = j(out)
    assert not out.deliverable and body["passed"] is False
    assert "缺少检查" in out.content and "tilt_deg" in out.content
    assert body["missing_coverage"] == ["tilt_deg"] and "tilt_deg" in body["hint"] and "还没有检查" in body["hint"]
    assert out.build is stub.result and ws.last_run is stub.result


def test_build_success_deliverable():
    tb, ws, stub = make_box(checks=[PHONE_W, TILT])
    out = tb.call("build", {})
    body = j(out)
    assert out.deliverable and body["passed"] is True and body["error"] is None and body["failed_checks"] == []
    assert body["passed_checks"] == 3 and body["missing_coverage"] == [] and body["hint"] == "全部通过，程序会自动交付。"
    assert body["facts"] == {"size": [90.0, 52.1, 99.7], "volume": 12345.6} and body["failures_left"] == 3
    rendered, checks_raw, names, kw = stub.calls[0]
    assert checks_raw == [PHONE_W, TILT] and names == {"phone_w", "tilt_deg", "lip_h"}
    assert kw["mode"] == "build" and kw["timeout_s"] == 12 and kw["secret_names"] == ("MY_KEY",)
    assert "phone_w = scad.var" in rendered.text and tb.build_failures == 0


def test_build_records_last_build_content():
    tb, ws, stub = make_box(checks=[PHONE_W, TILT])
    assert ws.last_build_content is None
    out = tb.call("build", {})
    assert ws.last_build_content == out.content
    tb2, ws2, _ = make_box(with_feature=False)   # 没有特征：不运行，走 _build_without_run
    out2 = tb2.call("build", {})
    assert ws2.last_build_content == out2.content and "NotebookError" in out2.content


def test_build_failure_reports_cell():
    result = good_result(ok=False, error={"cell": "base", "type": "NameError", "message": "name 'wd' is not defined"}, checks=[], facts={})
    tb, ws, _ = make_box(result=result, checks=[PHONE_W, TILT])
    out = tb.call("build", {})
    body = j(out)
    assert not out.deliverable and body["passed"] is False and "base" in out.content
    assert body["error"] == {"feature": "base", "type": "NameError", "message": "name 'wd' is not defined"}
    assert body["facts"] is None and body["failures_left"] == 2 and tb.build_failures == 1
    assert body["hint"] == "只修改特征 base。拿不准函数用法时先用 api_help 查。"


def test_build_hints_for_each_condition():
    failed = CheckResult("tilt", "angle", False, 112.3, 115.0, 0.5, "两个平面法向夹角 112.3°")
    cases = [
        (good_result(ok=False, timed_out=True, error={"cell": None, "type": "TimeoutError", "message": "运行超过 60 秒被终止"}, checks=[], facts={}),
         "运行超时了。检查是否写了很慢的操作，比如过多的阵列数量或过细的样条。"),
        (good_result(ok=False, error={"cell": None, "type": "NameError", "message": "x"}),
         "出错位置不在某个特征里，多半是参数或特征之间的引用有问题。先检查参数名和变量名是否一致。"),
        (good_result(ok=False, checks=[*good_result().checks, failed]),
         "先看每条 detail 里选中了哪些几何：选错了就改检查条件，选对了但数值不对就改模型。"),
    ]
    for result, hint in cases:
        tb, *_ = make_box(result=result, checks=[PHONE_W, TILT])
        assert j(tb.call("build", {}))["hint"] == hint


def test_build_failed_check_fields():
    failed = CheckResult("tilt", "angle", False, 112.3, 115.0, 0.5, "两个平面法向夹角 112.3°")
    tb, *_ = make_box(result=good_result(ok=False, checks=[*good_result().checks, failed]), checks=[PHONE_W, TILT])
    body = j(tb.call("build", {}))
    assert body["failed_checks"] == [{"id": "tilt", "type": "angle", "expected": 115.0, "measured": 112.3, "tol": 0.5, "detail": "两个平面法向夹角 112.3°"}]
    assert body["passed_checks"] == 3 and body["error"] is None


def test_failures_counted_and_reset():
    tb, ws, _ = make_box(result=good_result(ok=False, error={"cell": "base", "type": "E", "message": "m"}), checks=[PHONE_W, TILT])
    tb.max_build_failures = 3
    lefts = [j(tb.call("build", {}))["failures_left"] for _ in range(4)]
    assert lefts == [2, 1, 0, 0] and tb.build_failures == 4
    tb.begin_turn()
    assert tb.build_failures == 0


def test_coverage_gap_counts_as_failure():
    tb, *_ = make_box(checks=[PHONE_W])
    tb.call("build", {})
    assert tb.build_failures == 1


def test_build_without_features_is_a_notebook_error_without_running():
    tb, ws, stub = make_box(with_feature=False)
    out = tb.call("build", {})
    body = j(out)
    assert body["error"]["type"] == "NotebookError" and body["error"]["feature"] is None and "特征" in body["error"]["message"]
    assert stub.calls == [] and not out.deliverable and tb.build_failures == 1
    assert ws.last_run is not None and not ws.last_run.ok


def test_build_render_error_names_the_feature():
    tb, ws, stub = make_box(checks=[PHONE_W, TILT])
    tb.call("upsert_feature", {"slug": "base", "role": "build", "code": "_x = 1"})  # 没有给 base 赋值
    body = j(tb.call("build", {}))
    assert body["error"]["type"] == "NotebookError" and body["error"]["feature"] == "base"
    assert stub.calls == [] and body["hint"].startswith("只修改特征 base")


def test_build_with_stale_checks_is_reported_without_running():
    tb, ws, stub = make_box(checks=[PHONE_W, TILT])
    ws.brief.apply_patch({"remove_params": ["tilt_deg"]})  # 检查里还在引用这个参数
    body = j(tb.call("build", {}))
    assert body["error"]["type"] == "CheckSpecError" and "tilt_deg" in body["error"]["message"] and stub.calls == []


def test_inspect():
    items = [{"type": "PLANE", "center": [0, 0, i], "area": 1.0, "normal": [0, 0, 1]} for i in range(40)]
    result = good_result(query=items)
    tb, ws, stub = make_box(result=result)
    body = j(tb.call("inspect", {"kind": "faces", "where": [["geom.type", "==", "PLANE"]]}))
    assert len(body["items"]) == 30 and body["total"] == 40 and body["truncated"] is True
    assert body["facts"]["size"] == [90.0, 52.1, 99.7] and body["facts"]["n_faces"] == 9
    kw = stub.calls[0][3]
    assert kw["mode"] == "inspect" and kw["query_spec"] == {"kind": "faces", "where": [["geom.type", "==", "PLANE"]]}
    assert tb.build_failures == 0


def test_inspect_validates_arguments_without_running():
    tb, _, stub = make_box()
    assert "kind" in j(tb.call("inspect", {"kind": "vertices"}))["error"]
    assert "geom." in j(tb.call("inspect", {"kind": "faces", "where": [["center.z", ">", 1]]}))["error"]
    assert stub.calls == []


def test_inspect_reports_run_error():
    tb, *_ = make_box(result=good_result(ok=False, error={"cell": "base", "type": "NameError", "message": "m"}, facts={}))
    body = j(tb.call("inspect", {"kind": "edges"}))
    assert body["error"] == {"feature": "base", "type": "NameError", "message": "m"}


def test_malformed_args():
    tb, ws, _ = make_box()
    for name in ("upsert_feature", "build", "update_brief", "api_help"):
        out = tb.call(name, {"__raw__": "{bad"})
        assert "不是合法 JSON" in out.content and name in out.content and "{bad" in out.content and not out.end_turn
    assert [f.slug for f in ws.features.items] == ["base"]


def test_missing_required_argument():
    tb, *_ = make_box()
    out = tb.call("upsert_feature", {"slug": "x", "role": "add"})
    assert "缺少参数" in out.content and "code" in out.content
    assert "缺少参数" in tb.call("api_help", {}).content


def test_unknown_tool():
    tb, *_ = make_box()
    out = tb.call("make_cube", {})
    assert "make_cube" in out.content and all(n in out.content for n in ALL_TOOLS)
    tb2, *_ = make_box(confirmed=False, with_feature=False)
    out2 = tb2.call("make_cube", {})
    assert "api_help" in out2.content and "build" not in out2.content.split("可用的工具")[1]


def test_call_never_raises():
    tb, *_ = make_box()
    for name in ALL_TOOLS:
        for args in ({}, {"questions": 5, "slug": 5, "checks": 5, "kind": 5, "name": 5, "set_params": 5}, {"slug": None, "role": None, "code": None}):
            assert isinstance(tb.call(name, args), ToolOutcome)


def test_api_help_returns_docs():
    tb, *_ = make_box(confirmed=False, with_feature=False)
    body = j(tb.call("api_help", {"name": "make_box_rsolid"}))
    assert "bottom_face_center" in body["doc"] and body["name"] == "make_box_rsolid"
    assert "make_box_rsolid" in j(tb.call("api_help", {"name": "scad.make_box_rsolid"}))["name"]
    assert len(tb.call("api_help", {"name": "make_box_rsolid"}).content) < 6000


def test_api_help_suggests():
    tb, *_ = make_box(confirmed=False, with_feature=False)
    body = j(tb.call("api_help", {"name": "make_bx_rsolid"}))
    assert "make_box_rsolid" in body["similar"] and "error" in body
    assert "make_box_rsolid" in tb.call("api_help", {"name": "make_bx_rsolid"}).content


def test_api_names_and_lookup():
    from cad_agent.agent.api_docs import api_names, lookup_api

    names = api_names()
    assert len(names) > 300 and "make_box_rsolid" in names and names == sorted(names)
    assert lookup_api("make_box_rsolid").startswith("# make_box_rsolid")
    assert lookup_api("no_such_function") is None and lookup_api("../secrets") is None
