import json
from pathlib import Path

import pytest

from cad_agent.agent.loop import AFFIRMATIVE, Agent, AgentTurn, is_affirmative
from cad_agent.brief import Brief
from cad_agent.config import Config
from cad_agent.llm.client import LLMError, LLMReply
from cad_agent.llm.fake import ScriptedLLM, scripted_call
from cad_agent.notebook import FeatureList
from cad_agent.session import Session
from cad_agent.tools import ToolBox, Workspace
from helpers import BOX, PHONE_W, TILT, USER_PARAMS, Runner, bad_result, good_result

CONFIG = Config(base_url="http://x", model="m")
FIRST_REQUEST = scripted_call("update_brief", {
    "part": {"name": "手机支架", "purpose": "放桌上看视频"}, "set_params": USER_PARAMS, "features": ["底座"], "open_questions": []})
UPSERT = scripted_call("upsert_feature", {"slug": "base", "role": "build", "code": BOX})
SET_CHECKS = scripted_call("set_checks", {"checks": [PHONE_W, TILT]})
BUILD = scripted_call("build", {})


def make_agent(tmp_path, replies, runner=None, confirmed=True, **config):
    brief = Brief()
    ws = Workspace(brief, FeatureList(), [])
    if confirmed:
        from helpers import make_brief

        ws.brief = make_brief(confirmed=True)
    runner = runner or Runner()
    llm = ScriptedLLM(replies)
    toolbox = ToolBox(ws, run_job=runner)
    session = Session(tmp_path / "sessions")
    agent = Agent(llm, toolbox, session, Config(base_url="http://x", model="m", **config))
    return agent, ws, llm, runner, session


def log_rows(session: Session) -> list[dict]:
    return [json.loads(line) for line in (session.dir / "log.jsonl").read_text(encoding="utf-8").splitlines()]


def test_is_affirmative():
    assert AFFIRMATIVE == {"y", "yes", "ok", "确认", "可以", "没问题", "好", "对", "行"}
    for yes in ("确认。", " 确认 ", "可以", "OK!", "Yes", "好，", "没问题！", "行"):
        assert is_affirmative(yes), yes
    for no in ("可以，但角度改成70", "不", "确认一下角度", "", "好的", "确认，开始吧"):
        assert not is_affirmative(no), no


def test_clarify_then_question(tmp_path):
    first = scripted_call("update_brief", {"part": {"name": "手机支架"}, "open_questions": ["手机多厚？"]})
    ask = scripted_call("ask_user", {"questions": ["手机多厚？我建议 12 mm", "要横放吗？"]}, content="需要先确认两件事")
    agent, ws, llm, _, session = make_agent(tmp_path, [first, ask], confirmed=False)
    turn = agent.handle_user("做一个放在桌上看视频的小支架")
    assert isinstance(turn, AgentTurn) and turn.kind == "question" and turn.llm_calls == 2
    assert "需要先确认两件事" in turn.text and "1. 手机多厚？我建议 12 mm" in turn.text and "2. 要横放吗？" in turn.text
    assert ws.brief.part_name == "手机支架" and ws.brief.open_questions == ["手机多厚？"]
    assert llm.calls[0][-1] == {"role": "user", "content": "做一个放在桌上看视频的小支架"}
    assert [m["role"] for m in llm.calls[0][:2]] == ["system", "system"]


def test_plain_reply(tmp_path):
    agent, *_ = make_agent(tmp_path, [LLMReply("你好，要做什么零件？", [], {"total_tokens": 7})], confirmed=False)
    turn = agent.handle_user("你好")
    assert turn.kind == "reply" and turn.text == "你好，要做什么零件？" and turn.llm_calls == 1 and turn.tokens == 7


def test_confirmation_then_delivery(tmp_path):
    agent, ws, llm, runner, session = make_agent(tmp_path, [FIRST_REQUEST, scripted_call("request_confirmation", {}), UPSERT, SET_CHECKS, BUILD],
                                                 confirmed=False)
    turn1 = agent.handle_user("做一个支架")
    assert turn1.kind == "confirm" and "【需求单】" in turn1.text and "phone_w" in turn1.text
    assert ws.awaiting_confirmation and not ws.brief.confirmed
    turn2 = agent.handle_user("确认")
    assert turn2.kind == "delivered" and turn2.repairs == 0 and turn2.llm_calls == 3
    assert ws.brief.confirmed and not ws.awaiting_confirmation
    v1 = session.dir / "versions" / "v1"
    assert turn2.version_dir == v1
    assert sorted(p.name for p in v1.iterdir()) == ["brief.json", "changes.md", "checks.json", "model.py", "model.step", "view.png"]
    assert str(v1 / "view.png") in turn2.text and "width" in turn2.text and "通过" in turn2.text and "v1" in turn2.text
    assert (session.dir / "brief.json").exists() and (session.dir / "model.py").exists()
    assert llm.calls[2][-1]["content"] == "（用户已确认需求单）"
    export_call = [c for c in runner.calls if c.get("export_step") is not None]
    assert len(export_call) == 1 and export_call[0]["render_png"] is not None


def test_mixed_confirmation_not_accepted(tmp_path):
    reply = LLMReply("好，角度改成 70。", [], {})
    agent, ws, llm, *_ = make_agent(tmp_path, [FIRST_REQUEST, scripted_call("request_confirmation", {}), reply], confirmed=False)
    agent.handle_user("做一个支架")
    turn = agent.handle_user("可以，但角度改成70")
    assert not ws.brief.confirmed and not ws.awaiting_confirmation
    assert llm.calls[-1][-1] == {"role": "user", "content": "可以，但角度改成70"}
    assert turn.kind == "reply"


def test_non_affirmative_answer_still_clears_waiting_flag(tmp_path):
    agent, ws, *_ = make_agent(tmp_path, [FIRST_REQUEST, scripted_call("request_confirmation", {}), LLMReply("好", [], {})], confirmed=False)
    agent.handle_user("做一个支架")
    assert ws.awaiting_confirmation
    agent.handle_user("等等")
    assert not ws.awaiting_confirmation


def test_build_failure_then_repair(tmp_path):
    runner = Runner(bad_result("name 'wd' is not defined"), good_result())
    agent, ws, llm, runner, session = make_agent(tmp_path, [UPSERT, SET_CHECKS, BUILD, UPSERT, BUILD], runner=runner)
    turn = agent.handle_user("开始建模")
    assert turn.kind == "delivered" and turn.repairs == 1
    assert len([r for r in log_rows(session) if r["kind"] == "build"]) == 2
    builds = [r for r in log_rows(session) if r["kind"] == "build"]
    assert [b["passed"] for b in builds] == [False, True]


def test_failure_limit(tmp_path):
    runner = Runner(bad_result("第一次的错误"), bad_result("第二次的错误"), bad_result("name 'zz' is not defined 第三次"))
    agent, ws, llm, runner, session = make_agent(tmp_path, [UPSERT, SET_CHECKS, BUILD, BUILD, BUILD], runner=runner)
    turn = agent.handle_user("开始建模")
    assert turn.kind == "failed" and "第三次" in turn.text and "第一次的错误" not in turn.text
    assert "3 次" in turn.text and turn.repairs == 3 and llm.replies == []
    assert (session.dir / "model.py").exists()  # 失败后也保存当前状态
    assert [r["kind"] for r in log_rows(session)][-1] == "failed"


def test_failure_limit_follows_config(tmp_path):
    runner = Runner(bad_result("e1"), bad_result("e2"))
    agent, *_ = make_agent(tmp_path, [UPSERT, SET_CHECKS, BUILD, BUILD], runner=runner, max_build_failures=2)
    turn = agent.handle_user("开始建模")
    assert turn.kind == "failed" and "2 次" in turn.text


def test_failure_counter_resets_each_turn(tmp_path):
    runner = Runner(bad_result("e1"), bad_result("e2"), bad_result("e3"), bad_result("e4"), good_result())
    replies = [UPSERT, SET_CHECKS, BUILD, BUILD, LLMReply("我需要想一想怎么改", [], {}), BUILD, BUILD, BUILD]
    agent, *_ = make_agent(tmp_path, replies, runner=runner)
    assert agent.handle_user("开始").kind == "reply"
    turn = agent.handle_user("继续")
    assert turn.kind == "delivered" and turn.repairs == 2  # 本轮前两次没通过（e3、e4），第三次通过


def test_failed_check_summary_when_no_error(tmp_path):
    failing = good_result(ok=False)
    failing.checks[-1].passed = False
    failing.checks[-1].detail = "x 向尺寸 70.0000，期望 78.0000"
    agent, *_ = make_agent(tmp_path, [UPSERT, SET_CHECKS, BUILD, BUILD, BUILD], runner=Runner(failing))
    turn = agent.handle_user("开始")
    assert turn.kind == "failed" and "width" in turn.text and "70.0000" in turn.text


def test_tool_cap(tmp_path):
    replies = [scripted_call("api_help", {"name": "make_box_rsolid"}) for _ in range(40)]
    agent, ws, llm, runner, session = make_agent(tmp_path, replies)
    turn = agent.handle_user("查一下")
    assert turn.kind == "failed" and "上限" in turn.text and "40" in turn.text and turn.llm_calls == 40


def test_tool_cap_follows_config(tmp_path):
    replies = [scripted_call("api_help", {"name": "make_box_rsolid"}) for _ in range(3)]
    agent, *_ = make_agent(tmp_path, replies, max_tool_calls=3)
    turn = agent.handle_user("查一下")
    assert turn.kind == "failed" and "上限" in turn.text and "3" in turn.text


def test_malformed_and_unknown_tools_count_toward_cap(tmp_path):
    from cad_agent.llm.client import ToolCall

    bad = LLMReply("", [ToolCall("c1", "upsert_feature", {"__raw__": "{bad"}), ToolCall("c2", "make_cube", {})], {})
    done = LLMReply("我改正了", [], {})
    agent, ws, llm, *_ = make_agent(tmp_path, [bad, done], max_tool_calls=40)
    turn = agent.handle_user("来")
    assert turn.kind == "reply"
    # 两个调用都有对应的 tool 消息，而且内容是中文错误
    tool_msgs = [m for m in llm.calls[1] if m["role"] == "tool"]
    assert [m["tool_call_id"] for m in tool_msgs] == ["c1", "c2"]
    assert "不是合法 JSON" in tool_msgs[0]["content"] and "make_cube" in tool_msgs[1]["content"]
    assert [m for m in llm.calls[1] if m["role"] == "assistant"][0]["tool_calls"][0]["function"]["arguments"] == "{bad"


def test_every_tool_call_gets_a_tool_message_even_when_turn_ends_early(tmp_path):
    two = scripted_call("ask_user", {"questions": ["多厚？"]}, "", ("build", {}))
    agent, ws, llm, *_ = make_agent(tmp_path, [two, LLMReply("好", [], {})], confirmed=False)
    assert agent.handle_user("来").kind == "question"
    agent.handle_user("12")
    msgs = llm.calls[1]
    assistant = [m for m in msgs if m["role"] == "assistant"][0]
    tool_ids = [m["tool_call_id"] for m in msgs if m["role"] == "tool"]
    assert tool_ids == [tc["id"] for tc in assistant["tool_calls"]] == ["call_1", "call_2"]


def test_llm_error_preserves_state(tmp_path):
    agent, ws, llm, runner, session = make_agent(tmp_path, [UPSERT, LLMError("网络连接失败，已重试 2 次")])
    before_brief = ws.brief.to_dict()
    turn = agent.handle_user("开始建模")
    assert turn.kind == "failed" and turn.text.startswith("模型调用失败") and "网络连接失败" in turn.text
    assert ws.brief.to_dict() == before_brief and [f.slug for f in ws.features.items] == ["base"]
    assert (session.dir / "brief.json").exists()


def test_llm_error_on_first_call_then_retry_works(tmp_path):
    agent, ws, llm, *_ = make_agent(tmp_path, [LLMError("断网"), LLMReply("你好", [], {})], confirmed=False)
    assert agent.handle_user("你好").kind == "failed"
    assert agent.handle_user("你好").kind == "reply"


def deliver_v1(tmp_path, extra_replies, runner=None):
    agent, ws, llm, runner, session = make_agent(tmp_path, [UPSERT, SET_CHECKS, BUILD, *extra_replies], runner=runner)
    assert agent.handle_user("开始建模").kind == "delivered"
    return agent, ws, llm, runner, session


def test_modification_keeps_old_checks(tmp_path):
    change = scripted_call("update_brief", {"set_params": [{"name": "tilt_deg", "value": 70, "unit": "deg", "source": "user", "note": "支撑角度"}]})
    agent, ws, llm, runner, session = deliver_v1(tmp_path, [change, BUILD])
    checks_before = list(ws.checks_raw)
    turn = agent.handle_user("支撑角度改成 70 度")
    assert turn.kind == "delivered" and turn.version_dir.name == "v2"
    assert ws.checks_raw == checks_before == [PHONE_W, TILT]
    changes = (turn.version_dir / "changes.md").read_text(encoding="utf-8")
    assert "→" in changes and "65 → 70" in changes
    assert json.loads((turn.version_dir / "brief.json").read_text(encoding="utf-8"))["params"][1]["value"] == 70
    assert "65 → 70" not in (session.dir / "versions" / "v1" / "changes.md").read_text(encoding="utf-8")


def test_suggested_change_after_delivery_requires_reconfirmation(tmp_path):
    change = scripted_call("update_brief", {"set_params": [{"name": "lip_h", "value": 15, "unit": "mm", "source": "suggested", "note": "托唇"}]})
    blocked = scripted_call("build", {})
    agent, ws, llm, runner, session = deliver_v1(tmp_path, [change, blocked, LLMReply("需要你确认新增的托唇", [], {})])
    turn = agent.handle_user("加个托唇")
    assert turn.kind == "reply" and not ws.brief.confirmed
    assert "需求单" in llm.calls[-1][-1]["content"]  # build 被挡住，模型看到的是“需求单未确认”


def test_state_message_refreshed(tmp_path):
    agent, ws, llm, *_ = make_agent(tmp_path, [FIRST_REQUEST, LLMReply("好的", [], {})], confirmed=False)
    agent.handle_user("做一个支架")
    first_state, second_state = llm.calls[0][1]["content"], llm.calls[1][1]["content"]
    assert llm.calls[0][1]["role"] == "system" and llm.calls[1][1]["role"] == "system"
    assert '"phone_w"' not in first_state and '"phone_w"' in second_state
    assert first_state.startswith("【当前状态】") and "本轮剩余：建模失败还可 3 次，工具调用还可 40 次" in first_state
    assert "工具调用还可 39 次" in second_state


def test_state_message_is_not_kept_in_history(tmp_path):
    agent, ws, llm, *_ = make_agent(tmp_path, [FIRST_REQUEST, LLMReply("好的", [], {})], confirmed=False)
    agent.handle_user("做一个支架")
    second = llm.calls[1]
    assert [m["role"] for m in second].count("system") == 2


def test_system_prompt_is_first_message(tmp_path):
    agent, ws, llm, *_ = make_agent(tmp_path, [LLMReply("好", [], {})], confirmed=False)
    agent.handle_user("你好")
    first = llm.calls[0][0]
    assert first["role"] == "system" and "你是一个 CAD 建模助手" in first["content"] and "SCA 常用写法速查" in first["content"]


def test_tools_offered_depend_on_phase(tmp_path):
    agent, ws, llm, *_ = make_agent(tmp_path, [LLMReply("好", [], {})], confirmed=False)
    agent.handle_user("你好")
    assert [t["function"]["name"] for t in llm.tool_lists[0]] == ["update_brief", "ask_user", "request_confirmation", "api_help"]


def usage_of(prompt: int, completion: int, cached: int, reasoning: int) -> dict:
    return {"prompt_tokens": prompt, "completion_tokens": completion, "total_tokens": prompt + completion,
            "cached_tokens": cached, "reasoning_tokens": reasoning}


def test_turn_sums_usage_and_cost(tmp_path):
    lookup = scripted_call("api_help", {"name": "make_box_rsolid"})
    first = LLMReply("", lookup.tool_calls, usage_of(100, 10, 60, 4), cost=0.01)
    second = LLMReply("好的", [], usage_of(120, 20, 100, 8), cost=0.02)
    agent, ws, llm, runner, session = make_agent(tmp_path, [first, second], confirmed=False)
    turn = agent.handle_user("你好")
    assert turn.kind == "reply" and turn.llm_calls == 2
    assert (turn.prompt_tokens, turn.completion_tokens, turn.cached_tokens, turn.reasoning_tokens) == (220, 30, 160, 12)
    assert turn.tokens == 250 and turn.cost == pytest.approx(0.03)
    rows = log_rows(session)
    end = [r for r in rows if r["kind"] == "reply"][0]
    assert (end["prompt_tokens"], end["completion_tokens"], end["cached_tokens"], end["reasoning_tokens"]) == (220, 30, 160, 12)
    assert end["cost"] == pytest.approx(0.03)
    first_row = [r for r in rows if r["kind"] == "assistant"][0]   # 每次调用也记完整的用量和本次费用
    assert first_row["usage"] == usage_of(100, 10, 60, 4) and first_row["cost"] == pytest.approx(0.01)


def test_turn_cost_none_when_any_call_lacks_cost(tmp_path):
    lookup = scripted_call("api_help", {"name": "make_box_rsolid"})
    first = LLMReply("", lookup.tool_calls, usage_of(100, 10, 60, 4), cost=0.01)
    second = LLMReply("好的", [], usage_of(120, 20, 100, 8))   # 没有价目表时 cost 是 None
    agent, *_ = make_agent(tmp_path, [first, second], confirmed=False)
    turn = agent.handle_user("你好")
    assert turn.cost is None and turn.prompt_tokens == 220


def test_turn_cost_none_without_successful_call(tmp_path):
    agent, ws, llm, runner, session = make_agent(tmp_path, [LLMError("断网")], confirmed=False)
    turn = agent.handle_user("你好")
    assert turn.kind == "failed" and turn.llm_calls == 0 and turn.cost is None and turn.prompt_tokens == 0
    end = [r for r in log_rows(session) if r["kind"] == "failed"][0]
    assert end["cost"] is None and end["cached_tokens"] == 0


def test_log_records_everything(tmp_path):
    agent, ws, llm, runner, session = deliver_v1(tmp_path, [])
    kinds = [r["kind"] for r in log_rows(session)]
    assert kinds[0] == "user" and kinds.count("assistant") == 3 and kinds.count("tool") == 3 and kinds.count("build") == 1
    assert "delivered" in kinds
    tool_rows = [r for r in log_rows(session) if r["kind"] == "tool"]
    assert [r["name"] for r in tool_rows] == ["upsert_feature", "set_checks", "build"] and "args" in tool_rows[0] and "content" in tool_rows[0]


@pytest.mark.sca
def test_real_build_end_to_end(tmp_path):
    from cad_agent.sandbox.execute import run_job

    params = [{"name": n, "value": v, "unit": "mm", "source": "user", "note": n} for n, v in (("w", 60), ("h", 36), ("t", 8), ("r", 5))]
    brief = scripted_call("update_brief", {"part": {"name": "带孔板", "purpose": "测试"}, "set_params": params, "features": ["板", "孔"]})
    plate = scripted_call("upsert_feature", {"slug": "plate", "role": "build",
                          "code": "plate = scad.make_box_rsolid(width=w, height=h, depth=t, bottom_face_center=(0, 0, 0))"})
    hole = scripted_call("upsert_feature", {"slug": "hole", "role": "subtract", "code":
                         "_tool = scad.make_cylinder_rsolid(radius=r, height=t + 2, bottom_face_center=(0, 0, -1))\n"
                         "hole = scad.cut_rsolid(plate, _tool, skip_non_intersecting=False)"})
    checks = scripted_call("set_checks", {"checks": [
        {"id": "len-x", "type": "bbox", "axis": "x", "expected": "w"},
        {"id": "len-y", "type": "bbox", "axis": "y", "expected": "h"},
        {"id": "thick", "type": "bbox", "axis": "z", "expected": "t"},
        {"id": "bore", "type": "count", "kind": "faces", "expected": 1,
         "where": [["geom.type", "==", "CYLINDER"], ["geom.area", ">=", "2 * pi * r * t - 1"], ["geom.area", "<=", "2 * pi * r * t + 1"]]},
        {"id": "bore-empty", "type": "point_outside", "point": [0, 0, "t / 2"]},
    ]})
    ws = Workspace(Brief(), FeatureList(), [])
    llm = ScriptedLLM([brief, scripted_call("request_confirmation", {}), plate, hole, checks, BUILD])
    agent = Agent(llm, ToolBox(ws, run_job=run_job, timeout_s=60), Session(tmp_path / "sessions"), CONFIG)
    assert agent.handle_user("做一块带孔的板").kind == "confirm"
    turn = agent.handle_user("确认")
    assert turn.kind == "delivered", turn.text
    v1 = turn.version_dir
    assert (v1 / "model.step").stat().st_size > 0 and (v1 / "view.png").stat().st_size > 0
    assert "def _" in (v1 / "model.py").read_text(encoding="utf-8")
