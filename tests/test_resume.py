"""从会话目录恢复智能体（第二版计划 3 Task 3）。"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from cad_agent.agent.context import Context
from cad_agent.agent.loop import Agent
from cad_agent.agent.resume import load_workspace, past_turns, resume_agent
from cad_agent.brief import Brief
from cad_agent.config import Config
from cad_agent.llm.client import LLMReply
from cad_agent.llm.fake import ScriptedLLM, scripted_call
from cad_agent.notebook import FeatureList
from cad_agent.session import Session
from cad_agent.tools import ToolBox, Workspace
from helpers_staged import StageRunner, staged_brief
from test_staged_loop import GATES_OFF, PLAN, S1, S2, make_staged_agent

ROOT = Path(__file__).resolve().parent.parent
CHANGE = scripted_call("update_brief", {"set_params": [{"name": "phone_w", "value": 80, "unit": "mm", "source": "user", "note": "宽"}]})


def fresh_agent(session: Session, replies: list, runner=None) -> tuple[Agent, ScriptedLLM, StageRunner]:
    """在已有的会话目录上造一个新的智能体（模拟重新打开程序）。"""
    llm = ScriptedLLM(replies)
    runner = runner or StageRunner()
    box = ToolBox(Workspace(Brief(), FeatureList(), []), run_job=runner, gates=GATES_OFF)
    agent = Agent(llm, box, session, Config(base_url="http://x", model="m"))
    return agent, llm, runner


def delivered_v1(tmp_path):
    agent, ws, llm, runner, session = make_staged_agent(tmp_path, [PLAN, S1, S2])
    assert agent.handle_user("开始建模吧").kind == "delivered"
    return agent, ws, session


def test_round_trip_after_delivery(tmp_path):
    old, ws, session = delivered_v1(tmp_path)
    opened = Session.open(session.dir)
    assert opened.dir == session.dir
    agent, llm, _ = fresh_agent(opened, [CHANGE])
    resume_agent(agent)
    new = agent.ws
    assert new.brief.to_dict() == ws.brief.to_dict()
    assert new.plan.to_list() == ws.plan.to_list() and new.plan.complete()
    assert new.features.to_list() == ws.features.to_list()
    assert new.checks_raw == ws.checks_raw
    assert new.last_build_content is None and new.awaiting_confirmation is False
    turn = agent.handle_user("宽度改成 80")
    assert turn.kind == "delivered" and turn.version_dir == session.dir / "versions" / "v2"
    assert [v.name for v in Session.open(session.dir).versions()] == ["v1", "v2"]


def test_past_turns_are_compacted(tmp_path):
    old, ws, session = delivered_v1(tmp_path)
    agent, llm, _ = fresh_agent(Session.open(session.dir), [LLMReply("好的，在的。", [], {})])
    resume_agent(agent)
    agent.handle_user("你好")
    first = llm.calls[0]
    assert [m["role"] for m in first] == ["system", "user", "assistant", "user"]
    assert first[1]["content"] == "开始建模吧"
    assert first[2]["content"].startswith("已交付 v1")
    assert "【当前状态" in first[3]["content"] and first[3]["content"].endswith("你好")
    assert not any(m["role"] == "tool" for m in first)


def test_resume_while_waiting_for_confirmation(tmp_path):
    brief = staged_brief()
    brief.confirmed = False
    session = Session(tmp_path / "sessions")
    box = ToolBox(Workspace(brief, FeatureList(), []), run_job=StageRunner(), gates=GATES_OFF)
    llm = ScriptedLLM([scripted_call("request_confirmation", {}, "整理好了")])
    first = Agent(llm, box, session, Config(base_url="http://x", model="m"))
    assert first.handle_user("做一个 L 形支架").kind == "confirm"

    agent, llm2, _ = fresh_agent(Session.open(session.dir), [PLAN, S1, S2])
    resume_agent(agent)
    assert agent.ws.awaiting_confirmation is True and agent.ws.brief.confirmed is False
    turn = agent.handle_user("确认")
    assert agent.ws.brief.confirmed is True
    assert "规划中" in llm2.calls[0][-1]["content"]
    assert turn.kind == "delivered"


def test_unfinished_last_turn_is_dropped(tmp_path):
    rows = [
        {"kind": "startup"},
        {"kind": "user", "text": "做一个盒子", "sent_as": "做一个盒子"},
        {"kind": "assistant", "content": "好"},
        {"kind": "question", "text": "多大？"},
        {"kind": "user", "text": "确认", "sent_as": "（用户已确认需求单）"},
        {"kind": "confirm", "text": "【需求单】很长的内容"},
        {"kind": "user", "text": "开始", "sent_as": "开始"},
        {"kind": "assistant", "content": "做到一半"},
    ]
    assert past_turns(rows) == [
        {"role": "user", "content": "做一个盒子"}, {"role": "assistant", "content": "多大？"},
        {"role": "user", "content": "（用户已确认需求单）"}, {"role": "assistant", "content": "（已把需求单发给用户确认）"},
    ]


def test_open_legacy_session(tmp_path):
    copy = tmp_path / "phone_stand"
    shutil.copytree(ROOT / "demo" / "phone_stand", copy)
    session = Session.open(copy)
    ws = load_workspace(session)
    assert ws.plan is not None and [s.id for s in ws.plan.stages] == ["s1"]
    assert ws.plan.stages[0].title == "整体" and ws.plan.stages[0].done_when == "零件完成" and ws.plan.complete()
    assert ws.features.items and all(f.stage == "s1" for f in ws.features.items)
    assert ws.checks_raw and all(c.get("stage") == "s1" for c in ws.checks_raw)
    agent, llm, _ = fresh_agent(session, [])
    resume_agent(agent)
    assert agent.ws.brief.part_name == "桌面看视频小支架"
    assert len(agent.context.messages()) > 1


def test_open_missing_dir_raises(tmp_path):
    import pytest

    with pytest.raises(FileNotFoundError):
        Session.open(tmp_path / "nope")


def test_empty_session_loads_empty_workspace(tmp_path):
    session = Session(tmp_path / "s")
    ws = load_workspace(session)
    assert ws.brief.to_dict() == Brief().to_dict() and ws.features.items == [] and ws.checks_raw == [] and ws.plan is None


def test_meta_round_trip(tmp_path):
    session = Session(tmp_path / "s")
    assert session.meta() == {}
    session.set_meta(title="底板", created="2026-11-11T10:00:00")
    session.set_meta(updated="2026-11-11T11:00:00")
    again = Session.open(session.dir)
    assert again.meta() == {"title": "底板", "created": "2026-11-11T10:00:00", "updated": "2026-11-11T11:00:00"}


def test_read_log_skips_broken_lines(tmp_path):
    session = Session(tmp_path / "s")
    session.log("user", text="你好")
    with (session.dir / "log.jsonl").open("a", encoding="utf-8") as f:
        f.write("{坏掉的一行\n[1, 2]\n\n")
    session.log("reply", text="在")
    rows = Session.open(session.dir).read_log()
    assert [r["kind"] for r in rows] == ["user", "reply"]
    assert Session(tmp_path / "t").read_log() == []


def test_context_restore():
    ctx = Context("系统")
    past = [{"role": "user", "content": "a"}, {"role": "assistant", "content": "b"}]
    ctx.restore(past)
    past.append({"role": "user", "content": "不该影响"})
    assert ctx.messages() == [{"role": "system", "content": "系统"}, {"role": "user", "content": "a"}, {"role": "assistant", "content": "b"}]


def test_corrupt_json_file_does_not_lock_the_session(tmp_path):
    """写到一半断电留下的坏 plan.json：会话照样能打开，按没有这个文件处理（复查 I3）。"""
    old, ws, session = delivered_v1(tmp_path)
    (session.dir / "plan.json").write_text('[{"id": "s1", "ti', encoding="utf-8")
    loaded = load_workspace(Session.open(session.dir))
    assert loaded.brief.part_name == ws.brief.part_name and loaded.plan is not None


def test_state_files_are_written_atomically(tmp_path, monkeypatch):
    """需求单等状态文件先写临时文件再改名，写到一半出错时旧文件还在（复查 I3）。"""
    import os

    from cad_agent import session as session_mod

    s = Session(tmp_path / "s")
    s.set_meta(title="旧标题")
    real_replace = os.replace
    monkeypatch.setattr(session_mod.os, "replace", lambda *a: (_ for _ in ()).throw(OSError("磁盘满了")))
    import pytest

    with pytest.raises(OSError):
        s.set_meta(title="新标题")
    monkeypatch.setattr(session_mod.os, "replace", real_replace)
    assert s.meta()["title"] == "旧标题" and not list(s.dir.glob("*.tmp"))
