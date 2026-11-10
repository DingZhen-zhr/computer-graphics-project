"""分阶段的 build（第二版计划 1 Task 7）。"""

import json

from cad_agent.gates import Gates
from cad_agent.notebook import Feature
from cad_agent.staged import messages as msg
from cad_agent.staged.build import Advance, StageRun, advance
from cad_agent.tools import ToolBox
from helpers_staged import BASE, CHECK_S1, CHECK_S2, StageRunner, failing, passing, two_stage_ws

LEGACY_KEYS = {"passed", "error", "failed_checks", "passed_checks", "missing_coverage", "facts", "failures_left", "hint"}
ALL_PASSED_HINT = "全部通过，程序会自动交付。"


def run_adv(ws, runner, **kw) -> Advance:
    return advance(ws, runner, timeout_s=60, secret_names=(), **kw)


def box_for(ws, runner, gates: Gates = Gates(mutation_check=False)) -> ToolBox:
    return ToolBox(ws, run_job=runner, gates=gates)


def build(box) -> dict:
    return json.loads(box.call("build", {}).content)


# ---------------------------------------------------------------- advance


def test_advance_runs_ready_stages_in_order():
    ws, r = two_stage_ws(), StageRunner()
    adv = run_adv(ws, r)
    assert adv.passed == ["s1", "s2"] and adv.reason == "complete" and adv.stopped is None
    assert [sr.stage_id for sr in adv.runs] == ["s1", "s2"] and all(isinstance(sr, StageRun) for sr in adv.runs)
    s1 = next(c for c in r.calls if c["slug"] == "base")
    assert "# ---- feature: wall" not in s1["text"] and s1["mode"] == "build"
    assert ws.plan.complete()


def test_advance_stops_at_first_failure():
    ws, r = two_stage_ws(), StageRunner({"base": failing()})
    adv = run_adv(ws, r)
    assert adv.passed == [] and adv.stopped == "s1" and adv.reason == "failed"
    assert [sr.stage_id for sr in adv.runs] == ["s1"]
    assert not ws.plan.get("s1").passed and not ws.plan.get("s2").passed


def test_advance_not_ready():
    ws = two_stage_ws(s2_written=False)
    adv = run_adv(ws, StageRunner())
    assert adv.passed == ["s1"] and adv.reason == "not_ready" and adv.stopped == "s2"
    ws2 = two_stage_ws(s2_written=False)
    ws2.plan.mark_passed("s1")
    adv2 = run_adv(ws2, r2 := StageRunner())
    assert adv2 == Advance(runs=[], passed=[], stopped="s2", reason="not_ready") and r2.calls == []


def test_here_only_checks_only_run_in_their_stage():
    ws, r = two_stage_ws(), StageRunner()
    ws.checks_raw.append({"id": "pre-h", "type": "bbox", "axis": "z", "expected": 8, "stage": "s1", "holds": "here_only"})
    run_adv(ws, r)
    by = {c["slug"]: c["check_ids"] for c in r.calls}
    assert by["base"] == ["base-w", "tilt", "pre-h"]
    assert by["wall"] == ["base-w", "tilt", "wall-h"]


def test_stage_stl_is_exported(tmp_path):
    ws, r = two_stage_ws(), StageRunner()
    run_adv(ws, r, stl_dir=tmp_path / "stages")
    by = {c["slug"]: c["export_stl"] for c in r.calls}
    assert by == {"base": tmp_path / "stages" / "s1.stl", "wall": tmp_path / "stages" / "s2.stl"}
    assert (tmp_path / "stages" / "s2.stl").is_file()
    run_adv(two_stage_ws(), r2 := StageRunner())
    assert all(c.get("export_stl") is None for c in r2.calls)


def test_render_error_counts_as_failed_stage():
    ws, r = two_stage_ws(), StageRunner()
    ws.features.upsert(Feature("base", "build", "basee = 1", "s1"))   # 变量名不对
    adv = run_adv(ws, r)
    assert r.slugs() == ["wall"] or r.slugs() == []   # s1 渲染就出错，不会为它调用 run_job
    assert all(c["slug"] != "base" for c in r.calls)
    assert adv.reason == "failed" and adv.stopped == "s1" and adv.passed == []
    assert adv.runs[-1].run.error["type"] == "NotebookError" and adv.runs[-1].run.error["cell"] == "base"


def test_bad_check_counts_as_failed_stage():
    ws, r = two_stage_ws(), StageRunner()
    ws.checks_raw[0] = {**CHECK_S1, "expected": "nope_param"}
    adv = run_adv(ws, r)
    assert adv.reason == "failed" and adv.runs[-1].run.error["type"] == "CheckSpecError"


def test_advance_parallel_workers():
    ws, r = two_stage_ws(), StageRunner()
    adv = run_adv(ws, r, workers=1)
    assert adv.passed == ["s1", "s2"]


# ---------------------------------------------------------------- build 工具


def test_build_body_is_superset():
    body = build(box_for(two_stage_ws(s2_written=False), StageRunner()))
    assert LEGACY_KEYS | {"stage", "stages_passed", "final_gate"} <= set(body)
    assert body["stage"] == "s2" and body["stages_passed"] == ["s1"] and body["final_gate"] is None


def test_build_hint_after_stage_passed():
    ws = two_stage_ws(s2_written=False)
    box = box_for(ws, StageRunner())
    body = build(box)
    assert body["hint"] == msg.hint_stage_passed(["s1"], ws.plan.get("s2"))
    assert body["passed"] is False and body["failures_left"] == 3 and body["error"] is None and body["failed_checks"] == []
    assert box.last_advance.passed == ["s1"] and ws.last_run is box.last_advance.runs[-1].run
    assert not box.unbuilt_edits and ws.last_build_content == json.dumps(body, ensure_ascii=False)


def test_build_failure_hint_is_legacy():
    box = box_for(two_stage_ws(), StageRunner({"base": failing()}))
    body = build(box)
    assert body["hint"] == "先看每条 detail 里选中了哪些几何：选错了就改检查条件，选对了但数值不对就改模型。"
    assert body["stage"] == "s1" and body["failed_checks"][0]["id"] == "base-w" and body["failures_left"] == 2


def test_build_failure_counting_resets_when_a_stage_passes():
    r = StageRunner({"base": [failing(), failing(), passing("base-w", "tilt")], "wall": failing("wall-h")})
    box = box_for(two_stage_ws(), r)
    build(box)
    build(box)
    assert box.build_failures == 2
    body = build(box)
    assert body["stages_passed"] == ["s1"] and body["stage"] == "s2"
    assert box.build_failures == 1 and body["failures_left"] == 2


def test_build_without_features_or_checks_is_not_a_failure():
    ws = two_stage_ws(s2_written=False)
    ws.plan.mark_passed("s1")
    r = StageRunner()
    box = box_for(ws, r)
    assert json.loads(box.call("build", {}).content) == {"error": msg.build_no_features("s2")}
    ws.features.upsert(Feature("wall", "add", "wall = base", "s2"))
    assert json.loads(box.call("build", {}).content) == {"error": msg.build_no_checks("s2")}
    assert box.build_failures == 0 and r.calls == []


def test_build_deliverable_when_complete():
    box = box_for(two_stage_ws(), StageRunner())
    out = box.call("build", {})
    body = json.loads(out.content)
    assert out.deliverable and body["passed"] is True
    assert body["hint"] == ALL_PASSED_HINT and body["stage"] is None and body["stages_passed"] == ["s1", "s2"]
    assert body["final_gate"] == {"missing_coverage": [], "unconstrained": [], "unbuildable": []}
    assert box.last_gate is not None and box.last_gate.passed and box.build_failures == 0


def test_build_coverage_gap_at_final_gate_is_not_a_failure():
    ws = two_stage_ws()
    ws.checks_raw = [c for c in ws.checks_raw if c["id"] != "tilt"]
    box = box_for(ws, StageRunner())
    out = box.call("build", {})
    body = json.loads(out.content)
    assert not out.deliverable and body["passed"] is False
    assert body["final_gate"]["missing_coverage"] == ["tilt_deg"] and body["missing_coverage"] == ["tilt_deg"]
    assert body["hint"] == "模型和检查都通过了，但这些用户参数还没有检查：tilt_deg。补上检查后再 build。"
    assert box.build_failures == 0 and ws.plan.complete()


def test_build_coverage_ignores_here_only_checks():
    ws = two_stage_ws()
    ws.checks_raw = [c if c["id"] != "tilt" else {**c, "holds": "here_only"} for c in ws.checks_raw]
    body = build(box_for(ws, StageRunner()))
    assert body["final_gate"]["missing_coverage"] == ["tilt_deg"]


def test_build_again_when_complete_reverifies_last_stage():
    ws, r = two_stage_ws(), StageRunner()
    box = box_for(ws, r)
    build(box)
    r.calls.clear()
    body = build(box)
    assert r.slugs() == ["wall"] and body["stages_passed"] == ["s2"] and body["passed"] is True


def test_editing_earlier_stage_reverifies_from_there():
    ws, r = two_stage_ws(), StageRunner()
    ws.checks_raw.append({"id": "pre-h", "type": "bbox", "axis": "z", "expected": 8, "stage": "s1", "holds": "here_only"})
    box = box_for(ws, r)
    build(box)
    assert ws.plan.complete()
    r.calls.clear()
    box.call("upsert_feature", {"slug": "base", "role": "build", "code": BASE + "  # 改过"})
    assert [s.passed for s in ws.plan.stages] == [False, False]
    build(box)
    assert sorted(r.slugs()) == ["base", "wall"]
    by = {c["slug"]: c["check_ids"] for c in r.calls}
    assert "pre-h" in by["base"] and "pre-h" not in by["wall"]
    assert ws.plan.complete()


def test_probes_used_resets_on_pass():
    ws = two_stage_ws()
    ws.probes_used = 7
    build(box_for(ws, StageRunner({"base": failing()})))
    assert ws.probes_used == 7
    build(box_for(ws, StageRunner()))
    assert ws.probes_used == 0


def test_toolbox_stage_members_default():
    box = box_for(two_stage_ws(), StageRunner())
    assert box.stage_dir is None and box.last_advance is None and box.last_gate is None
    assert CHECK_S2["stage"] == "s2"
