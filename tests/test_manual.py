"""不经过模型直接改参数（第二版计划 1 Task 12）。"""

import json
import math

import pytest

from cad_agent.agent.manual import ManualResult, apply_params
from helpers_staged import failing
from test_staged_loop import PLAN, S1, S2, log_rows, make_staged_agent

NOT_YET = "现在还不能直接改参数：要先交付过一个版本。"
FAILED = "改成这些数值后模型没有通过检查，已经退回原来的数值。"


def delivered(tmp_path):
    agent, ws, llm, runner, session = make_staged_agent(tmp_path, [PLAN, S1, S2])
    assert agent.handle_user("开始").kind == "delivered"
    runner.calls.clear()
    return agent, ws, llm, runner, session


def test_not_available_before_first_delivery(tmp_path):
    agent, ws, llm, runner, session = make_staged_agent(tmp_path, [])
    r = apply_params(agent, {"phone_w": 90})
    assert isinstance(r, ManualResult) and r == ManualResult(ok=False, text=NOT_YET)
    assert ws.brief.param_values()["phone_w"] == 78 and runner.calls == []


def test_not_available_when_plan_not_finished(tmp_path):
    agent, ws, *_ = delivered(tmp_path)
    ws.plan.invalidate_from("s2")
    assert apply_params(agent, {"phone_w": 90}).text == NOT_YET


@pytest.mark.parametrize("values,hint", [
    ({"nope": 3}, "nope"),
    ({"phone_w": math.nan}, "phone_w"),
    ({"phone_w": math.inf}, "phone_w"),
    ({"phone_w": "90"}, "phone_w"),
    ({"phone_w": True}, "phone_w"),
    ({"phone_w": 78, "tilt_deg": 65}, "一样"),
    ({}, "一样"),
])
def test_rejects_unknown_param_nan_and_no_change(tmp_path, values, hint):
    agent, ws, llm, runner, session = delivered(tmp_path)
    before = ws.brief.to_dict()
    r = apply_params(agent, values)
    assert not r.ok and hint in r.text and r.version_dir is None
    assert ws.brief.to_dict() == before and runner.calls == [] and len(session.versions()) == 1


def test_success_creates_version(tmp_path):
    agent, ws, llm, runner, session = delivered(tmp_path)
    ws.brief.params[0].source = "suggested"
    n_llm = len(llm.calls)
    r = apply_params(agent, {"phone_w": 90, "tilt_deg": 65})
    assert r.ok and r.text == "已按新的参数重建，存为 v2。" and r.version_dir == session.dir / "versions" / "v2"
    assert r.changes == ["手动修改参数：phone_w 78 → 90（mm）"] and r.failed_checks == [] and r.error is None
    brief = json.loads((r.version_dir / "brief.json").read_text(encoding="utf-8"))
    p = next(p for p in brief["params"] if p["name"] == "phone_w")
    assert p["value"] == 90 and p["source"] == "user" and p["unit"] == "mm" and p["note"] == "宽"
    assert "手动修改参数：phone_w 78 → 90（mm）" in (r.version_dir / "changes.md").read_text(encoding="utf-8")
    assert (r.version_dir / "plan.json").is_file() and (r.version_dir / "stages" / "s2.stl").is_file()
    assert len(llm.calls) == n_llm and ws.plan.complete() and ws.brief.param_values()["phone_w"] == 90


def test_failure_restores_everything(tmp_path):
    agent, ws, llm, runner, session = delivered(tmp_path)
    before_brief, before_plan = ws.brief.to_dict(), ws.plan.to_list()
    stl_before = (session.dir / "stages" / "s1.stl").read_bytes()
    runner.results["wall"] = [failing("wall-h")]
    r = apply_params(agent, {"phone_w": 90})
    assert not r.ok and r.text == FAILED and r.version_dir is None and r.changes == []
    assert [f["id"] for f in r.failed_checks] == ["wall-h"]
    assert set(r.failed_checks[0]) == {"id", "type", "expected", "measured", "tol", "detail"}
    assert ws.brief.to_dict() == before_brief and ws.plan.to_list() == before_plan
    assert len(session.versions()) == 1
    assert (session.dir / "stages" / "s1.stl").read_bytes() == stl_before


def test_failure_reports_error(tmp_path):
    agent, ws, llm, runner, session = delivered(tmp_path)
    bad = failing()
    bad.error = {"cell": "base", "type": "SimpleCADError", "message": "建不出来"}
    runner.results["base"] = [bad]
    r = apply_params(agent, {"phone_w": 900})
    assert not r.ok and r.error == {"feature": "base", "type": "SimpleCADError", "message": "建不出来"}


def test_all_stages_are_reverified(tmp_path):
    agent, ws, llm, runner, session = delivered(tmp_path)
    apply_params(agent, {"tilt_deg": 70})
    stage_calls = [c for c in runner.calls if c.get("export_step") is None]
    assert sorted(c["slug"] for c in stage_calls) == ["base", "wall"]
    assert all(c.get("check_values") is None for c in runner.calls)   # 不做扰动验证


def test_manual_is_logged(tmp_path):
    agent, ws, llm, runner, session = delivered(tmp_path)
    apply_params(agent, {"phone_w": 90})
    runner.results["wall"] = [failing("wall-h")]
    apply_params(agent, {"phone_w": 95})
    rows = [r for r in log_rows(session) if r["kind"] == "manual"]
    assert [(r["values"], r["ok"], r["version"]) for r in rows] == [({"phone_w": 90}, True, "v2"), ({"phone_w": 95}, False, None)]


def test_success_updates_session_state(tmp_path):
    agent, ws, llm, runner, session = delivered(tmp_path)
    apply_params(agent, {"phone_w": 90})
    saved = json.loads((session.dir / "brief.json").read_text(encoding="utf-8"))
    assert next(p for p in saved["params"] if p["name"] == "phone_w")["value"] == 90
    assert json.loads((session.dir / "plan.json").read_text(encoding="utf-8"))[-1]["passed"] is True
