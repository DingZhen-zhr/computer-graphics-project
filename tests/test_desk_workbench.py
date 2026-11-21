"""桌面端的工作台：智能体 + 事件流 + 工作线程（第二版计划 3 Task 4）。"""

from __future__ import annotations

import json
import shutil
import threading
import time
from pathlib import Path

import pytest

from cad_agent.agent.loop import Agent
from cad_agent.agent.manual import ManualResult
from cad_agent.brief import Brief
from cad_agent.config import Config
from cad_agent.desk.workbench import Busy, Workbench
from cad_agent.llm.client import LLMReply, LLMStopped
from cad_agent.llm.fake import ScriptedLLM, scripted_call
from cad_agent.notebook import FeatureList
from cad_agent.session import Session
from cad_agent.tools import ToolBox, Workspace
from helpers_staged import STAGES2, StageRunner, staged_brief
from test_staged_loop import GATES_OFF, S1, S2

ROOT = Path(__file__).resolve().parent.parent
PLAN_TALK = scripted_call("set_plan", {"stages": STAGES2}, "我先分两步做：底板，然后立板。")
FAKE_KEY = "sk-test-NOT-A-REAL-KEY-7f3a9c"


def make_wb(tmp_path, llm, brief: Brief | None = None) -> tuple[Workbench, Session]:
    session = Session(tmp_path / "sessions")
    box = ToolBox(Workspace(brief if brief is not None else staged_brief(), FeatureList(), []), run_job=StageRunner(), gates=GATES_OFF)
    agent = Agent(llm, box, session, Config(base_url="http://x", model="m"))
    return Workbench(agent, session), session


def wait_idle(wb: Workbench, timeout: float = 15) -> None:
    deadline = time.monotonic() + timeout
    while wb.is_busy():
        assert time.monotonic() < deadline, "这一轮一直没结束"
        time.sleep(0.01)


def say(wb: Workbench, text: str) -> list[dict]:
    before = wb.bus.last_seq()
    wb.submit(text)
    wait_idle(wb)
    return wb.bus.since(before)


def types(events: list[dict]) -> list[str]:
    return [e["type"] for e in events]


def delivered(tmp_path) -> tuple[Workbench, Session]:
    wb, session = make_wb(tmp_path, ScriptedLLM([PLAN_TALK, S1, S2]))
    say(wb, "开始建模吧")
    assert wb.state()["phase"] == "delivered"
    return wb, session


class GateLLM:
    """第一次被调用时卡住，直到测试放行；放行时如果已经要求停止，就按停止处理。"""

    def __init__(self, reply: LLMReply) -> None:
        self.gate, self.entered, self.reply = threading.Event(), threading.Event(), reply

    def chat(self, messages, tools, *, on_delta=None, should_stop=None):
        self.entered.set()
        assert self.gate.wait(15), "测试没有放行"
        if should_stop is not None and should_stop():
            raise LLMStopped()
        return self.reply


class ResetLLM:
    def chat(self, messages, tools, *, on_delta=None, should_stop=None):
        on_delta("说到一半")
        on_delta("\x00")
        on_delta("重新说")
        return LLMReply("重新说", [], {})


class CrashOnceLLM:
    def __init__(self) -> None:
        self.calls = 0

    def chat(self, messages, tools, *, on_delta=None, should_stop=None):
        self.calls += 1
        if self.calls == 1:
            raise RuntimeError("内部细节 boom")
        return LLMReply("你好，我在。", [], {})


def test_events_for_a_full_turn(tmp_path):
    wb, _ = make_wb(tmp_path, ScriptedLLM([PLAN_TALK, S1, S2]))
    events = say(wb, "开始建模吧")
    seq = types(events)
    order = ["turn_start", "delta", "assistant", "tool_start", "tool_end", "plan", "stage", "build", "gate", "turn_end", "state"]
    pos = -1
    for t in order:
        pos = seq.index(t, pos + 1)
    assert seq[-2:] == ["turn_end", "state"]
    assert seq.count("tool_start") == seq.count("tool_end") == 7   # set_plan + 两个阶段各 3 个
    starts = [e for e in events if e["type"] == "tool_start"]
    ends = {e["id"]: e for e in events if e["type"] == "tool_end"}
    assert [e["id"] for e in starts] == list(ends) and all(isinstance(e["label"], str) and e["label"] for e in starts)
    assert all(ends[e["id"]]["name"] == e["name"] and ends[e["id"]]["ok"] is True for e in starts)
    assert "".join(e["text"] for e in events if e["type"] == "delta") == "我先分两步做：底板，然后立板。"
    stage = next(e for e in events if e["type"] == "stage")
    assert {"seq", "type", "id", "title", "checks", "size", "volume"} <= set(stage) and stage["id"] == "s1"
    plan = next(e for e in events if e["type"] == "plan")
    assert [s["id"] for s in plan["stages"]] == ["s1", "s2"] and plan["current"] == "s1"
    end = next(e for e in events if e["type"] == "turn_end")
    assert end["kind"] == "delivered" and end["text"].startswith("已交付 v1") and "usage" in end and "cost" in end
    assert events[-1]["state"]["phase"] == "delivered" and events[-1]["state"]["busy"] is False


def test_tool_starts_and_ends_alternate(tmp_path):
    wb, _ = make_wb(tmp_path, ScriptedLLM([PLAN_TALK, S1, S2]))
    tools = [e for e in say(wb, "开始") if e["type"] in ("tool_start", "tool_end")]
    assert [e["type"] for e in tools] == ["tool_start", "tool_end"] * 7
    assert all(a["id"] == b["id"] for a, b in zip(tools[::2], tools[1::2]))


def test_delta_reset_is_forwarded(tmp_path):
    wb, _ = make_wb(tmp_path, ResetLLM())
    events = say(wb, "你好")
    got = [(e["type"], e.get("text")) for e in events if e["type"] in ("delta", "delta_reset", "assistant")]
    assert got == [("delta", "说到一半"), ("delta_reset", None), ("delta", "重新说"), ("assistant", None)]
    assert next(e for e in events if e["type"] == "assistant")["content"] == "重新说"


def test_state_after_delivery(tmp_path):
    wb, session = delivered(tmp_path)
    st = wb.state()
    assert st["phase"] == "delivered" and st["busy"] is False
    assert st["session"] == {"id": session.dir.name, "title": "L 形支架", "demo": False}
    assert len(st["versions"]) == 1
    v = st["versions"][0]
    assert v["name"] == "v1" and v["has_stl"] is True and v["stages"] == ["s1", "s2"]
    assert set(v) >= {"name", "changes", "size", "volume", "has_stl", "stages", "gate", "review"}
    assert v["gate"]["missing_coverage"] == []
    work = [t for t in st["transcript"] if t["role"] == "work"]
    assert len(work) == 1 and [s["id"] for s in work[0]["stages"]] == ["s1", "s2"]
    assert all(s["passed"] and s["tools"] for s in work[0]["stages"])
    assert [t["name"] for t in work[0]["loose"]] == ["set_plan"]
    assert [t["role"] for t in st["transcript"]] == ["user", "work", "assistant"]
    assert st["transcript"][-1]["kind"] == "delivered" and st["transcript"][-1]["version"] == "v1"
    assert st["plan"]["current"] is None and [s["passed"] for s in st["plan"]["stages"]] == [True, True]
    assert {c["id"] for c in st["checks"]} >= {"base-w", "wall-h"}
    assert next(c for c in st["checks"] if c["id"] == "wall-h")["stage"] == "s2"
    assert set(st) >= {"session", "busy", "phase", "transcript", "brief", "plan", "checks", "gate", "review", "versions",
                       "stage_files", "usage", "cost", "last_seq"}
    assert st["last_seq"] == wb.bus.last_seq() and st["usage"]["llm_calls"] == 3


def test_state_phases(tmp_path):
    wb, _ = make_wb(tmp_path / "a", ScriptedLLM([]), brief=Brief())
    assert wb.state()["phase"] == "clarify" and wb.state()["plan"] is None

    unconfirmed = staged_brief()
    unconfirmed.confirmed = False
    wb, _ = make_wb(tmp_path / "b", ScriptedLLM([scripted_call("request_confirmation", {}, "整理好了")]), brief=unconfirmed)
    say(wb, "做一个支架")
    st = wb.state()
    assert st["phase"] == "confirm" and st["transcript"][-1]["kind"] == "confirm" and st["transcript"][-1]["brief"]["part"]["name"] == "L 形支架"

    wb, _ = make_wb(tmp_path / "c", ScriptedLLM([LLMReply("我想想怎么分阶段。", [], {})]))
    say(wb, "开始")
    assert wb.state()["phase"] == "planning"

    wb, _ = make_wb(tmp_path / "d", ScriptedLLM([PLAN_TALK, LLMReply("先停在这里。", [], {})]))
    say(wb, "开始")
    st = wb.state()
    assert st["phase"] == "modeling" and st["plan"]["current"] == "s1"


def test_question_entry_has_questions(tmp_path):
    ask = scripted_call("ask_user", {"questions": ["多宽？", "多高？"]}, "先问两件事")
    wb, _ = make_wb(tmp_path, ScriptedLLM([ask]), brief=Brief())
    say(wb, "做个盒子")
    last = wb.state()["transcript"][-1]
    assert last["kind"] == "question" and last["questions"] == ["多宽？", "多高？"]


def test_busy_rejects_params_message_and_delete(tmp_path):
    llm = GateLLM(LLMReply("好的", [], {}))
    wb, _ = make_wb(tmp_path, llm)
    wb.submit("第一条")
    assert llm.entered.wait(5) and wb.is_busy() and wb.state()["busy"] is True
    with pytest.raises(Busy):
        wb.submit("第二条")
    with pytest.raises(Busy):
        wb.apply_params({"phone_w": 90})
    llm.gate.set()
    wait_idle(wb)
    end = [e for e in wb.bus.since(0) if e["type"] == "turn_end"]
    assert len(end) == 1 and end[0]["kind"] == "reply" and end[0]["text"] == "好的"


def test_empty_message_is_value_error(tmp_path):
    wb, _ = make_wb(tmp_path, ScriptedLLM([]))
    with pytest.raises(ValueError):
        wb.submit("   ")
    assert not wb.is_busy()


def test_stop_ends_turn_with_stopped(tmp_path):
    llm = GateLLM(LLMReply("不该出现", [], {}))
    wb, _ = make_wb(tmp_path, llm)
    wb.submit("开始")
    assert llm.entered.wait(5)
    wb.stop()
    llm.gate.set()
    wait_idle(wb)
    end = [e for e in wb.bus.since(0) if e["type"] == "turn_end"]
    assert [e["kind"] for e in end] == ["stopped"]
    assert wb.state()["transcript"][-1]["kind"] == "stopped"


def test_agent_crash_becomes_error_event(tmp_path):
    wb, _ = make_wb(tmp_path, CrashOnceLLM())
    events = say(wb, "你好")
    errors = [e for e in events if e["type"] == "error"]
    assert len(errors) == 1 and "boom" not in errors[0]["message"] and "Traceback" not in errors[0]["message"]
    assert types(events)[-1] == "state" and wb.is_busy() is False
    assert wb.state()["transcript"][-1]["kind"] == "error"
    events = say(wb, "再试一次")
    assert next(e for e in events if e["type"] == "turn_end")["text"] == "你好，我在。"


def test_apply_params_publishes_state(tmp_path):
    wb, session = delivered(tmp_path)
    before = wb.bus.last_seq()
    result = wb.apply_params({"phone_w": 90})
    assert isinstance(result, ManualResult) and result.ok and result.version_dir == session.dir / "versions" / "v2"
    events = wb.bus.since(before)
    assert types(events)[-1] == "state" and "manual" in types(events)
    assert [v["name"] for v in events[-1]["state"]["versions"]] == ["v1", "v2"]
    assert not wb.is_busy()


def test_save_case_writes_user_case(tmp_path):
    wb, _ = delivered(tmp_path)
    cases = tmp_path / "cases"
    case_id = wb.save_case("L 形支架", ["支架", "两阶段"], cases)
    assert (cases / case_id / "case.yaml").is_file()


def test_demo_workbench_is_read_only(tmp_path):
    copy = tmp_path / "phone_stand"
    shutil.copytree(ROOT / "demo" / "phone_stand", copy)
    wb = Workbench(None, Session.open(copy), demo=True)
    with pytest.raises(PermissionError):
        wb.submit("你好")
    with pytest.raises(PermissionError):
        wb.apply_params({"device_w": 80})
    with pytest.raises(PermissionError):
        wb.save_case("x", ["y"], tmp_path / "cases")
    st = wb.state()
    assert st["session"]["demo"] is True and st["versions"] and st["transcript"] and st["phase"] == "delivered"
    assert st["versions"][0]["size"] is not None and len(st["versions"][0]["size"]) == 3


def test_no_key_in_events_or_state(tmp_path, monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", FAKE_KEY)
    wb, _ = delivered(tmp_path)
    wb.apply_params({"phone_w": 90})
    text = json.dumps(wb.bus.since(0), ensure_ascii=False) + json.dumps(wb.state(), ensure_ascii=False)
    assert FAKE_KEY not in text and FAKE_KEY[-12:] not in text


def test_close_stops_running_turn(tmp_path):
    llm = GateLLM(LLMReply("不该出现", [], {}))
    wb, _ = make_wb(tmp_path, llm)
    wb.submit("开始")
    assert llm.entered.wait(5)
    threading.Timer(0.2, llm.gate.set).start()
    wb.close(timeout=5)
    assert not wb.is_busy()


# ---------------------------------------------------------------- 第二版计划 3 最后整体复查后补的测试


def test_state_mid_turn_uses_the_replaced_agents_workspace(tmp_path):
    """设置改了、换过智能体以后：运行中的完整状态要用新智能体的工作区，不是旧的（复查 C1）。"""
    wb, session = make_wb(tmp_path, ScriptedLLM([]))
    gate = GateLLM(LLMReply("好", [], {}))
    fresh_brief = staged_brief()
    fresh_brief.part_name = "换过的零件"
    box = ToolBox(Workspace(fresh_brief, FeatureList(), []), run_job=StageRunner(), gates=GATES_OFF)
    wb._replace_agent(Agent(gate, box, session, Config(base_url="http://x", model="m")))
    wb.submit("你好")
    assert gate.entered.wait(5)
    assert wb.state()["brief"]["part"]["name"] == "换过的零件"
    gate.gate.set()
    wait_idle(wb)


def test_apply_params_clears_a_stale_stop_request(tmp_path):
    """一轮刚结束时点的"停止"不能留到下一次手动改参数（复查 I4）。"""
    wb, session = delivered(tmp_path)
    wb.stop()
    runner = wb.agent.toolbox._run_job
    runner.calls.clear()
    assert wb.apply_params({"phone_w": 90}).ok
    assert runner.calls and all(not c["should_stop"]() for c in runner.calls if "should_stop" in c)


# ---------------------------------------------------------------- 从旧网页的测试接过来的几项（计划 4 Task 6 Step 1 核对时补的）
# 旧的 tests/test_web.py 删除前逐条核对：下面这些断言在新测试里还没有，按新界面的写法补上。

from cad_agent.gates import Gates   # noqa: E402 - 只给下面这几条用
from helpers import BOX, PHONE_W, TILT, USER_PARAMS, Runner, bad_result, make_brief   # noqa: E402

LEGACY = Gates(staged=False, mutation_check=False, visual_review=False, cases=False)
OLD_ASK = scripted_call("update_brief", {"part": {"name": "手机支架"}, "open_questions": ["手机多宽？"]}, "先问两件事",
                        ("ask_user", {"questions": ["手机多宽？建议 78 mm", "要充电口吗？"]}))
OLD_FIRST_REQUEST = scripted_call("update_brief", {"part": {"name": "手机支架", "purpose": "放桌上看视频"}, "set_params": USER_PARAMS,
                                                   "features": ["底座"]})
OLD_UPSERT = scripted_call("upsert_feature", {"slug": "base", "role": "build", "code": BOX})
OLD_SET_CHECKS = scripted_call("set_checks", {"checks": [PHONE_W, TILT]})
OLD_BUILD = scripted_call("build", {})


def make_legacy_wb(tmp_path, llm, *, confirmed: bool, runner=None) -> tuple[Workbench, Session]:
    """1.2 版的单阶段流程（staged 关掉），旧网页测试用的就是它。"""
    session = Session(tmp_path / "sessions")
    ws = Workspace(make_brief(True) if confirmed else Brief(), FeatureList(), [])
    box = ToolBox(ws, run_job=runner or Runner(), gates=LEGACY)
    agent = Agent(llm, box, session, Config(base_url="http://x", model="m", gates=LEGACY))
    return Workbench(agent, session), session


def test_question_turn_keeps_user_text_lead_and_phase(tmp_path):
    """接替 test_web.py::test_question_flow。"""
    wb, _ = make_legacy_wb(tmp_path, ScriptedLLM([OLD_ASK]), confirmed=False)
    assert wb.state()["transcript"] == [] and wb.state()["phase"] == "clarify"
    say(wb, "做一个支架")
    st = wb.state()
    assert st["transcript"][0] == {"role": "user", "text": "做一个支架"}
    bot = st["transcript"][-1]
    assert bot["kind"] == "question" and bot["questions"] == ["手机多宽？建议 78 mm", "要充电口吗？"] and "先问两件事" in bot["text"]
    assert st["busy"] is False and st["phase"] == "clarify" and st["brief"]["part"]["name"] == "手机支架"


def test_confirm_entry_carries_the_brief(tmp_path):
    """接替 test_web.py::test_confirm_flow_carries_the_brief。"""
    wb, _ = make_legacy_wb(tmp_path, ScriptedLLM([OLD_FIRST_REQUEST]), confirmed=False)
    say(wb, "做一个支架")
    st = wb.state()
    bot = st["transcript"][-1]
    assert bot["kind"] == "confirm" and [p["name"] for p in bot["brief"]["params"]] == ["phone_w", "tilt_deg"]
    assert st["phase"] == "confirm" and st["brief"]["part"]["purpose"] == "放桌上看视频"


def test_delivered_entry_counts_checks(tmp_path):
    """接替 test_web.py::test_delivery_fills_checks_versions_and_stage 里交付卡片、检查、外形尺寸那几项。"""
    wb, _ = make_legacy_wb(tmp_path, ScriptedLLM([OLD_UPSERT, OLD_SET_CHECKS, OLD_BUILD]), confirmed=True)
    say(wb, "开始建模")
    st = wb.state()
    delivered_ = [t for t in st["transcript"] if t.get("kind") == "delivered"]
    assert [d["version"] for d in delivered_] == ["v1"] and delivered_[0]["total"] == delivered_[0]["passed"] == 4
    assert st["phase"] == "delivered" and {c["id"] for c in st["checks"]} >= {"valid", "width"}
    # 旧网页的状态里有"最近一次 build 量出来的外形尺寸"（facts）；新界面没有这一项，外形尺寸从 STL 读（test_state_after_delivery 查）


def test_failed_build_turn_shows_failure(tmp_path):
    """接替 test_web.py::test_failed_build_turn_shows_failure。"""
    runner = Runner(bad_result("e1"), bad_result("e2"), bad_result("e3"))
    llm = ScriptedLLM([OLD_UPSERT, OLD_SET_CHECKS, OLD_BUILD, OLD_BUILD, OLD_BUILD])
    wb, _ = make_legacy_wb(tmp_path, llm, confirmed=True, runner=runner)
    say(wb, "开始建模")
    st = wb.state()
    assert st["transcript"][-1]["kind"] == "failed" and "3 次" in st["transcript"][-1]["text"]
    assert st["versions"] == [] and st["phase"] == "modeling"


def test_busy_state_shows_the_users_message(tmp_path):
    """接替 test_web.py::test_busy_returns_409_and_reports_progress 里"处理中时已经能看到用户这句话"那一项。"""
    llm = GateLLM(LLMReply("好的", [], {}))
    wb, _ = make_wb(tmp_path, llm)
    wb.submit("第一句")
    assert llm.entered.wait(5)
    try:
        st = wb.state()
        assert st["busy"] is True and st["transcript"] == [{"role": "user", "text": "第一句"}]
    finally:
        llm.gate.set()
    wait_idle(wb)
    assert wb.state()["transcript"][-1]["text"] == "好的"


def test_confirming_the_brief_pushes_state_at_turn_start(tmp_path):
    """确认需求单的那一轮：一开始就推一次完整状态，界面才会把需求单收起来（3.0 桌面窗口走查发现）。"""
    unconfirmed = staged_brief()
    unconfirmed.confirmed = False
    llm = ScriptedLLM([scripted_call("request_confirmation", {}, "整理好了"), LLMReply("好，开始做。", [], {})])
    wb, _ = make_wb(tmp_path, llm, brief=unconfirmed)
    say(wb, "做一个支架")
    assert wb.state()["phase"] == "confirm"
    events = say(wb, "确认")   # 界面上"没问题，开始做"按钮发的就是这两个字
    seq = types(events)
    first = seq.index("state")
    assert first < seq.index("turn_end")
    assert events[first]["state"]["phase"] != "confirm"


def test_part_done_and_assembly_push_state(tmp_path):
    """多零件：每做完一个零件、装配检查完，都推一次完整状态，左边的零件清单和舞台才会跟着变。"""
    wb, session = make_wb(tmp_path, ScriptedLLM([]))
    for kind, data in (("part_done", {"id": "body", "name": "盒体"}),
                       ("assembly", {"passed": True, "failed": [], "hits": [], "reason": None})):
        before = wb.bus.last_seq()
        session.log(kind, **data)
        assert types(wb.bus.since(before)) == ["state"], kind
