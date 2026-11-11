"""中途停止：模型调用中、工具调用之间、沙盒运行中。"""

from __future__ import annotations

import json
import tempfile
import threading
import time

import pytest

from cad_agent.agent.loop import Agent
from cad_agent.brief import Param
from cad_agent.config import Config
from cad_agent.llm.client import LLMReply
from cad_agent.llm.fake import ScriptedLLM, scripted_call
from cad_agent.notebook import Feature, FeatureList, render_notebook
from cad_agent.sandbox.execute import run_job
from cad_agent.session import Session
from cad_agent.tools import ToolBox, Workspace
from helpers import BOX, Runner, make_brief

STOPPED_TEXT = "已停止。已经写下的内容都保留着，可以接着说。"


def make_agent(tmp_path, replies):
    ws = Workspace(make_brief(confirmed=True), FeatureList(), [])
    llm = ScriptedLLM(replies)
    box = ToolBox(ws, run_job=Runner())
    session = Session(tmp_path / "sessions")
    agent = Agent(llm, box, session, Config(base_url="http://x", model="m"))
    return agent, ws, llm, box, session


def log_rows(session: Session) -> list[dict]:
    return [json.loads(line) for line in (session.dir / "log.jsonl").read_text(encoding="utf-8").splitlines()]


def feature_call(slug: str) -> tuple[str, dict]:
    return ("upsert_feature", {"slug": slug, "role": "build" if slug == "base" else "modify",
                               "code": BOX if slug == "base" else f"{slug} = base"})


def test_stop_between_tool_calls(tmp_path):
    reply = scripted_call(*feature_call("base"), "", feature_call("b2"), feature_call("b3"))
    agent, ws, llm, box, session = make_agent(tmp_path, [reply])
    original = box.call

    def call_then_stop(name, args):
        out = original(name, args)
        agent.request_stop()
        return out

    box.call = call_then_stop
    turn = agent.handle_user("做底座")
    assert turn.kind == "stopped" and turn.text == STOPPED_TEXT
    assert [f.slug for f in ws.features.items] == ["base"]
    tools = [r for r in log_rows(session) if r["kind"] == "tool"]
    assert [r["args"]["slug"] for r in tools] == ["base"]


def test_stop_during_llm_call(tmp_path):
    agent, ws, llm, box, session = make_agent(tmp_path, [LLMReply("我先想一想这个零件怎么做比较好", [], {})])
    got: list[str] = []

    def on_delta(piece: str) -> None:
        got.append(piece)
        agent.request_stop()

    agent.on_delta = on_delta
    turn = agent.handle_user("做底座")
    assert turn.kind == "stopped" and got == ["我先想一"]
    assert not any(r["kind"] == "assistant" for r in log_rows(session))   # 这条回复没有进历史
    assert all("我先想" not in str(m["content"]) for m in agent.context.messages())
    assert agent.context.messages()[-1] == {"role": "assistant", "content": STOPPED_TEXT}


@pytest.mark.sca
def test_stop_during_sandbox_run(tmp_path, monkeypatch):
    work = tmp_path / "work"
    work.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(work))
    params = [Param("w", 60, "mm", "user")]
    plate = Feature("plate", "build", "plate = scad.make_box_rsolid(width=w, height=20, depth=8, bottom_face_center=(0, 0, 0))")
    spin = Feature("spin", "modify", "while True:\n    pass\nspin = plate")
    rendered = render_notebook(params, [plate, spin])
    flag = threading.Event()
    threading.Timer(0.5, flag.set).start()
    started = time.monotonic()
    r = run_job(rendered, [], {"w"}, timeout_s=60, should_stop=flag.is_set)
    assert time.monotonic() - started < 2.5   # 0.5 秒后置标志，2 秒内返回
    assert not r.ok and r.error == {"cell": None, "type": "Stopped", "message": "已按你的要求停止"}
    assert list(work.glob("cad-agent-*")) == []


def test_toolbox_passes_should_stop_to_run_job(tmp_path):
    runner = Runner()
    ws = Workspace(make_brief(confirmed=True), FeatureList([Feature("base", "build", BOX)]), [])
    box = ToolBox(ws, run_job=runner)
    box.call("build", {})
    assert "should_stop" not in runner.calls[-1]   # 没设时不传，和以前逐字相同
    box.should_stop = lambda: False
    box.call("build", {})
    assert runner.calls[-1]["should_stop"] is box.should_stop


def test_next_turn_after_stop_works(tmp_path):
    first = scripted_call(*feature_call("base"), "", feature_call("b2"))
    agent, ws, llm, box, session = make_agent(tmp_path, [first, LLMReply("好的，接着来", [], {})])
    original = box.call

    def call_then_stop(name, args):
        out = original(name, args)
        agent.request_stop()
        return out

    box.call = call_then_stop
    assert agent.handle_user("做底座").kind == "stopped"
    box.call = original
    turn = agent.handle_user("继续")
    assert turn.kind == "reply" and turn.text == "好的，接着来"
    snapshot = llm.calls[-1][-1]["content"] if llm.calls[-1][-1]["role"] == "user" else llm.calls[-1][-2]["content"]
    assert "base" in snapshot and "【用户说】\n继续" in snapshot


def test_stopped_turn_is_logged_and_compacted(tmp_path):
    first = scripted_call(*feature_call("base"), "", feature_call("b2"))
    agent, ws, llm, box, session = make_agent(tmp_path, [first])
    original = box.call

    def call_then_stop(name, args):
        out = original(name, args)
        agent.request_stop()
        return out

    box.call = call_then_stop
    agent.handle_user("做底座")
    rows = log_rows(session)
    assert rows[-1]["kind"] == "stopped" and rows[-1]["text"] == STOPPED_TEXT
    msgs = agent.context.messages()
    assert msgs[-2:] == [{"role": "user", "content": "做底座"}, {"role": "assistant", "content": STOPPED_TEXT}]
    saved = json.loads((session.dir / "features.json").read_text(encoding="utf-8"))
    assert [f["slug"] for f in saved] == ["base"]
