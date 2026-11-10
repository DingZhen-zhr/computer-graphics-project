"""主循环接入分阶段流程（第二版计划 1 Task 10）。"""

import json

from cad_agent.agent.loop import Agent
from cad_agent.agent.state import load_system_prompt
from cad_agent.config import Config
from cad_agent.gates import Gates
from cad_agent.llm.client import LLMReply
from cad_agent.llm.fake import ScriptedLLM, scripted_call
from cad_agent.notebook import FeatureList
from cad_agent.sandbox.execute import RunResult
from cad_agent.session import Session
from cad_agent.staged import messages as msg
from cad_agent.tools import ToolBox, Workspace
from helpers import Runner, make_brief
from helpers_staged import BASE, CHECK_S1, CHECK_S2, STAGES2, TILT, WALL, StageRunner, failing, last_slug, passing, staged_brief
from test_staged_build import MutRunner

GATES_OFF = Gates(mutation_check=False, visual_review=False, cases=False)


def strip(c: dict) -> dict:
    return {k: v for k, v in c.items() if k != "stage"}


PLAN = scripted_call("set_plan", {"stages": STAGES2})
CHECKS_S1 = ("set_checks", {"stage": "s1", "checks": [strip(CHECK_S1), strip(TILT)]})
CHECKS_S2 = ("set_checks", {"stage": "s2", "checks": [strip(CHECK_S2)]})
UP_BASE = ("upsert_feature", {"slug": "base", "role": "build", "code": BASE})
UP_WALL = ("upsert_feature", {"slug": "wall", "role": "add", "code": WALL})
BUILD = ("build", {})
S1 = scripted_call(*CHECKS_S1, "", UP_BASE, BUILD)
S2 = scripted_call(*CHECKS_S2, "", UP_WALL, BUILD)


def make_staged_agent(tmp_path, replies, runner=None, gates: Gates = GATES_OFF, **config):
    ws = Workspace(staged_brief(), FeatureList(), [])
    runner = runner or StageRunner()
    llm = ScriptedLLM(replies)
    box = ToolBox(ws, run_job=runner, gates=gates)
    session = Session(tmp_path / "sessions")
    agent = Agent(llm, box, session, Config(base_url="http://x", model="m", **config))
    return agent, ws, llm, runner, session


def log_rows(session: Session) -> list[dict]:
    return [json.loads(line) for line in (session.dir / "log.jsonl").read_text(encoding="utf-8").splitlines()]


def tool_contents(messages: list[dict]) -> list[dict]:
    return [json.loads(m["content"]) for m in messages if m["role"] == "tool"]


def test_full_two_stage_flow_delivers(tmp_path):
    agent, ws, llm, runner, session = make_staged_agent(tmp_path, [PLAN, S1, S2])
    turn = agent.handle_user("开始建模吧")
    assert turn.kind == "delivered" and turn.llm_calls == 3
    v1 = session.dir / "versions" / "v1"
    for name in ("gate.json", "plan.json", "stages/s1.stl", "stages/s2.stl", "model.step", "view.png", "model.py"):
        assert (v1 / name).is_file(), name
    assert json.loads((v1 / "plan.json").read_text(encoding="utf-8"))[1]["passed"] is True
    assert json.loads((v1 / "gate.json").read_text(encoding="utf-8"))["unconstrained"] == []
    assert (session.dir / "plan.json").is_file()
    assert agent.toolbox.stage_dir == session.dir / "stages"
    assert llm.calls[0][0]["content"] == load_system_prompt(True)
    assert "阶段：规划中（还没有计划，先调用 set_plan）" in llm.calls[0][1]["content"]
    assert [s["function"]["name"] for s in llm.tool_lists[0]][3] == "set_plan"


def test_passed_stage_is_folded(tmp_path):
    agent, ws, llm, *_ = make_staged_agent(tmp_path, [PLAN, S1, S2])
    agent.handle_user("开始")
    third = llm.calls[2]
    assert third[0]["role"] == "system" and third[1]["role"] == "user" and "【当前状态" in third[1]["content"]
    assert [m["role"] for m in third] == ["system", "user", "user"]
    assert third[2]["content"].startswith("【阶段已通过（程序生成）】s1 底板")
    assert third[2]["content"].endswith("现在是 s2：立板。做完的标志：左端有立板")
    assert not any(m["role"] == "tool" for m in third)


def test_fold_keeps_prefix_stable_inside_a_stage(tmp_path):
    replies = [PLAN, scripted_call(*CHECKS_S1), scripted_call(*UP_BASE), scripted_call(*BUILD), S2]
    agent, ws, llm, *_ = make_staged_agent(tmp_path, replies)
    assert agent.handle_user("开始").kind == "delivered"
    for k in (1, 2, 3):
        assert llm.calls[k][:len(llm.calls[k - 1])] == llm.calls[k - 1], k
    assert llm.calls[4][2]["content"].startswith("【阶段已通过（程序生成）】s1")


def test_stage_failure_limit_ends_turn(tmp_path):
    b = scripted_call(*BUILD)
    agent, ws, llm, *_ = make_staged_agent(tmp_path, [PLAN, S1, b, b], StageRunner({"base": failing()}))
    turn = agent.handle_user("开始")
    assert turn.kind == "failed" and turn.llm_calls == 4 and "连续没通过 3 次" in turn.text
    assert agent.toolbox.build_failures == 3


def test_failure_count_is_per_stage(tmp_path):
    b = scripted_call(*BUILD)
    runner = StageRunner({"base": [failing(), failing(), passing("base-w", "tilt")], "wall": failing("wall-h")})
    replies = [PLAN, S1, b, b, S2, b, LLMReply("先停一下，看看墙高", [], {})]
    agent, ws, llm, *_ = make_staged_agent(tmp_path, replies, runner)
    turn = agent.handle_user("开始")
    assert turn.kind == "reply" and turn.text == "先停一下，看看墙高"
    assert agent.toolbox.build_failures == 2 and ws.plan.get("s1").passed and not ws.plan.get("s2").passed


def cap_script() -> list:
    return [PLAN, scripted_call(*CHECKS_S1, "", UP_BASE, ("upsert_feature", {"slug": "base", "role": "build", "code": BASE}), CHECKS_S1)]


def test_stage_tool_cap(tmp_path):
    agent, ws, llm, runner, session = make_staged_agent(tmp_path, cap_script(), max_tool_calls_per_stage=4)
    turn = agent.handle_user("开始")
    assert turn.kind == "failed" and turn.text == msg.stage_cap_text("s1", "底板", 4)
    assert ws.plan is not None and runner.calls == []


def test_total_tool_cap(tmp_path):
    agent, *_ = make_staged_agent(tmp_path, [PLAN, S1, S2], max_tool_calls_total=5)
    turn = agent.handle_user("开始")
    assert turn.kind == "failed"
    assert turn.text.startswith("这一轮工具调用已经达到上限（5 次），先停下来了。")


def test_continue_after_stage_cap(tmp_path):
    agent, ws, llm, *_ = make_staged_agent(tmp_path, cap_script() + [S1, S2], max_tool_calls_per_stage=4)
    assert agent.handle_user("开始").kind == "failed"
    n = len(llm.calls)
    turn = agent.handle_user("继续")
    snap = llm.calls[n][-1]["content"]
    assert "计划：" in snap and "阶段：建模中（当前阶段 s1）" in snap and snap.endswith("【用户说】\n继续")
    assert turn.kind == "delivered" and turn.llm_calls == 2


def test_warning_counts_stage_calls(tmp_path):
    four = scripted_call(*CHECKS_S1, "", UP_BASE, UP_BASE, CHECKS_S1)
    replies = [PLAN, four, scripted_call(*BUILD), LLMReply("s1 做好了", [], {})]
    agent, ws, llm, *_ = make_staged_agent(tmp_path, replies, max_tool_calls_per_stage=6)
    assert agent.handle_user("开始").kind == "reply"
    tools = tool_contents(llm.calls[2])
    assert "warning" not in tools[0]   # set_plan 之后这个阶段从 0 数起
    assert [t.get("warning") for t in tools[1:5]] == [msg.stage_calls_left(n) for n in (5, 4, 3, 2)]
    assert all("本轮工具调用" not in json.dumps(t, ensure_ascii=False) for t in tools)


def test_param_change_reverifies_all_stages(tmp_path):
    change = scripted_call("update_brief", {"set_params": [{"name": "phone_w", "value": 80, "unit": "mm", "source": "user", "note": "宽"}]})
    agent, ws, llm, runner, session = make_staged_agent(tmp_path, [PLAN, S1, S2, change])
    assert agent.handle_user("开始").kind == "delivered"
    runner.calls.clear()
    turn = agent.handle_user("宽度改成 80")
    assert turn.kind == "delivered" and turn.llm_calls == 1 and turn.version_dir.name == "v2"
    stage_calls = [c for c in runner.calls if c.get("export_step") is None]
    assert sorted(c["slug"] for c in stage_calls) == ["base", "wall"]
    assert "phone_w: 78 → 80 (mm)" in turn.text


class GateRunner(MutRunner):
    """tilt_deg 在没有 tilt-2 这条检查时不受约束。"""

    def __call__(self, rendered, checks_raw, param_names, **kw):
        self.unconstrained = set() if any(c["id"] == "tilt-2" for c in checks_raw) else {"tilt_deg"}
        return super().__call__(rendered, checks_raw, param_names, **kw)


def test_gate_failure_goes_back_to_model(tmp_path):
    tilt2 = {"id": "tilt-2", "type": "angle", "expected": "tilt_deg", "a": TILT["a"], "b": TILT["b"]}
    fix = scripted_call("set_checks", {"stage": "s1", "checks": [strip(CHECK_S1), strip(TILT), tilt2]}, "", BUILD)
    agent, ws, llm, runner, session = make_staged_agent(tmp_path, [PLAN, S1, S2, fix], GateRunner(set()), Gates(visual_review=False, cases=False))
    turn = agent.handle_user("开始")
    assert turn.kind == "delivered" and turn.llm_calls == 4
    gate_reply = [t for t in tool_contents(llm.calls[3]) if "final_gate" in t][-1]
    assert gate_reply["final_gate"]["unconstrained"] == ["tilt_deg"] and gate_reply["passed"] is False
    assert gate_reply["hint"] == msg.hint_unconstrained(["tilt_deg"])
    assert "参数扰动验证：2 个用户参数都被检查约束。" in turn.text


class UnbuildableRunner(MutRunner):
    def __call__(self, rendered, checks_raw, param_names, **kw):
        cv = kw.get("check_values")
        if cv and f'"phone_w", {cv["phone_w"]:g},' not in rendered.text:
            with self.lock:
                self.calls.append({"slug": last_slug(rendered.text), "check_ids": [], **kw})
            return RunResult(ok=False, error={"cell": "base", "type": "SimpleCADError", "message": "建不出来"})
        return super().__call__(rendered, checks_raw, param_names, **kw)


def test_delivery_text_lists_unbuildable(tmp_path):
    agent, *_ = make_staged_agent(tmp_path, [PLAN, S1, S2], UnbuildableRunner(set()), Gates(visual_review=False, cases=False))
    turn = agent.handle_user("开始")
    assert turn.kind == "delivered"
    lines = turn.text.splitlines()
    line = "参数扰动验证：1 个用户参数被检查约束；1 个无法单独扰动（phone_w）。"
    assert line in lines
    table_end = max(i for i, ln in enumerate(lines) if ln.startswith("|"))
    assert lines.index(line) == table_end + 1


def test_delivery_text_without_mutation_has_no_line(tmp_path):
    agent, *_ = make_staged_agent(tmp_path, [PLAN, S1, S2])
    assert "参数扰动验证" not in agent.handle_user("开始").text


def test_turn_end_safety_build_only_when_ready(tmp_path):
    replies = [PLAN, scripted_call(*CHECKS_S1), LLMReply("检查写好了", [], {})]
    agent, ws, llm, runner, session = make_staged_agent(tmp_path, replies)
    turn = agent.handle_user("开始")
    assert turn.kind == "reply" and turn.text == "检查写好了" and runner.calls == []
    assert agent.toolbox.unbuilt_edits


def test_turn_end_safety_build_when_stage_ready(tmp_path):
    replies = [PLAN, scripted_call(*CHECKS_S1, "", UP_BASE), LLMReply("写好了", [], {}), LLMReply("s1 过了", [], {})]
    agent, ws, llm, runner, session = make_staged_agent(tmp_path, replies)
    turn = agent.handle_user("开始")
    assert turn.kind == "reply" and turn.text == "s1 过了" and ws.plan.get("s1").passed
    assert [r for r in log_rows(session) if r["kind"] == "auto"][0]["reason"] == "turn_end"


def test_logs_have_stage_and_gate(tmp_path):
    agent, ws, llm, runner, session = make_staged_agent(tmp_path, [PLAN, S1, S2])
    agent.handle_user("开始")
    rows = log_rows(session)
    stages = [r for r in rows if r["kind"] == "stage"]
    assert [(r["id"], r["title"]) for r in stages] == [("s1", "底板"), ("s2", "立板")]
    assert stages[0]["checks"] == 5 and stages[0]["size"] == [78.0, 40.0, 8.0] and stages[0]["volume"] == 24960.0
    gates = [r for r in rows if r["kind"] == "gate"]
    assert len(gates) == 1 and gates[0]["missing_coverage"] == [] and gates[0]["mutation"] == []
    builds = [r for r in rows if r["kind"] == "build"]
    assert [b["stages_passed"] for b in builds] == [["s1"], ["s2"]] and [b["stage"] for b in builds] == ["s2", None]


def test_legacy_agent_is_unchanged(tmp_path):
    ws = Workspace(make_brief(True), FeatureList(), [])
    llm = ScriptedLLM([LLMReply("好的", [], {})])
    session = Session(tmp_path / "sessions")
    agent = Agent(llm, ToolBox(ws, run_job=Runner()), session, Config(base_url="http://x", model="m"))
    agent.handle_user("你好")
    assert llm.calls[0][0]["content"] == load_system_prompt() and agent.toolbox.stage_dir is None
    assert "计划：" not in llm.calls[0][1]["content"]
    kinds = {r["kind"] for r in log_rows(session)}
    assert "stage" not in kinds and "gate" not in kinds
    assert not (session.dir / "plan.json").exists()
