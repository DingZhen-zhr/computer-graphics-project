"""3.0 计划 2 Task 12：多零件的参数直改（剧本模型 + 假的运行）。"""

from __future__ import annotations

from cad_agent.agent.manual import apply_params
from cad_agent.sandbox.runner_assembly import AssemblyRun
from helpers_staged import StageRunner, failing
from test_product_flow import BODY, CONNECT, LID, FakeAssembly, make_agent


def _delivered(tmp_path):
    agent, ws, llm, box, session = make_agent(tmp_path, BODY + LID + [CONNECT])
    assert agent.handle_user("开始").kind == "delivered"
    return agent, ws, box, session


def test_manual_multipart_rebuilds_affected_parts(tmp_path):
    agent, ws, box, session = _delivered(tmp_path)
    runner = StageRunner()
    box.run_job = runner
    res = apply_params(agent, {"lid_t": 5})
    assert res.ok and res.version_dir.name == "v2", res.text
    assert {c["slug"] for c in runner.calls} == {"plate"}           # 只重做 lid
    assert ws.brief.param_values()["lid_t"] == 5 and box.run_assembly.calls[-1]["mode"] == "export"
    runner.calls.clear()
    res = apply_params(agent, {"w": 50})
    assert res.ok and res.version_dir.name == "v3"
    assert {c["slug"] for c in runner.calls} == {"shell", "rim", "plate"}   # 两个零件都重做（各自所有步骤）
    assert res.changes == ["手动修改参数：w 40 → 50（mm）"]


def test_manual_multipart_failure_restores(tmp_path):
    agent, ws, box, session = _delivered(tmp_path)
    box.run_job = StageRunner({"plate": failing("lid-t")})
    res = apply_params(agent, {"lid_t": 5})
    assert not res.ok and res.text == "改成这些数值后模型没有通过检查，已经退回原来的数值。"
    assert ws.brief.param_values()["lid_t"] == 4 and all(st.done for st in ws.parts.values()) and ws.assembly_passed
    assert all(st.plan.complete() for st in ws.parts.values())
    assert not (session.dir / "versions" / "v2").exists()
    # 装配没过也退回
    box.run_job = StageRunner()
    bad = AssemblyRun(ok=True, error=None, connectors={"body.hinge": {"selected": 1}}, rest={"body": [1] * 16},
                      overlaps=[{"a": "body", "b": "lid", "volume": 9}], measures={}, samples={})
    box.run_assembly = FakeAssembly(bad)
    res = apply_params(agent, {"lid_t": 5})
    assert not res.ok and ws.brief.param_values()["lid_t"] == 4 and ws.assembly_passed
    assert res.failed_checks and res.failed_checks[0]["id"] == "no_overlap_at_rest"
