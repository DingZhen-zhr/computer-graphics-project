"""桌面端的会话管理（第二版计划 3 Task 5）。"""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from cad_agent.agent.loop import Agent
from cad_agent.brief import Brief
from cad_agent.config import Config
from cad_agent.desk.hub import Hub
from cad_agent.desk.workbench import Busy
from cad_agent.llm.client import LLMReply
from cad_agent.llm.fake import ScriptedLLM
from cad_agent.notebook import FeatureList
from cad_agent.session import Session
from cad_agent.tools import ToolBox, Workspace
from helpers_staged import StageRunner, staged_brief
from test_desk_workbench import PLAN_TALK, GateLLM, say, wait_idle
from test_staged_loop import GATES_OFF, S1, S2

ROOT = Path(__file__).resolve().parent.parent
DEMO_DIR = ROOT / "demo"


class Factory:
    """make_agent：每次造智能体用 llms 里的下一个模型（用完了就用一个只会说"好"的）。"""

    def __init__(self, *llms) -> None:
        self.llms = list(llms)
        self.made: list[Agent] = []

    def __call__(self, session: Session) -> Agent:
        llm = self.llms.pop(0) if self.llms else ScriptedLLM([LLMReply("好", [], {})] * 5)
        box = ToolBox(Workspace(Brief(), FeatureList(), []), run_job=StageRunner(), gates=GATES_OFF)
        agent = Agent(llm, box, session, Config(base_url="http://x", model="m"))
        self.made.append(agent)
        return agent


def seeded(hub: Hub) -> str:
    """新建一个会话，并在目录里放好一份已确认的需求单（相当于前面几轮已经澄清完）。"""
    sid = hub.create()
    Session.open(hub.sessions_dir / sid).save_state(staged_brief(), [], [], "")
    return sid


def make_hub(tmp_path, factory=None, demo_dir=None) -> Hub:
    return Hub(make_agent=factory or Factory(), sessions_dir=tmp_path / "sessions", cases_dir=tmp_path / "cases", demo_dir=demo_dir)


def test_create_open_list(tmp_path):
    hub = make_hub(tmp_path)
    assert hub.list() == []
    a = hub.create()
    time.sleep(0.01)
    b = hub.create()
    assert a != b and (tmp_path / "sessions" / a).is_dir()
    listed = hub.list()
    assert [x["id"] for x in listed] == [b, a]
    assert listed[0] == {"id": b, "title": "新会话", "updated": listed[0]["updated"], "versions": 0, "demo": False}
    wb = hub.open(a)
    assert hub.open(a) is wb and wb.state()["session"]["id"] == a


def test_title_falls_back_to_part_name(tmp_path):
    hub = make_hub(tmp_path, Factory(ScriptedLLM([PLAN_TALK, S1, S2])))
    sid = seeded(hub)
    say(hub.open(sid), "开始建模吧")
    item = next(x for x in hub.list() if x["id"] == sid)
    assert item["title"] == "L 形支架" and item["versions"] == 1


def test_rename_persists(tmp_path):
    hub = make_hub(tmp_path)
    sid = hub.create()
    hub.rename(sid, "  我的底板  ")
    assert hub.list()[0]["title"] == "我的底板"
    assert make_hub(tmp_path).list()[0]["title"] == "我的底板"
    with pytest.raises(ValueError):
        hub.rename(sid, "   ")


def test_delete_removes_directory(tmp_path):
    hub = make_hub(tmp_path)
    sid = hub.create()
    hub.open(sid)
    hub.delete(sid)
    assert not (tmp_path / "sessions" / sid).exists() and hub.list() == []
    with pytest.raises(FileNotFoundError):
        hub.open(sid)


def test_delete_busy_is_refused(tmp_path):
    llm = GateLLM(LLMReply("好的", [], {}))
    hub = make_hub(tmp_path, Factory(llm))
    sid = hub.create()
    wb = hub.open(sid)
    wb.submit("你好")
    assert llm.entered.wait(5)
    with pytest.raises(Busy):
        hub.delete(sid)
    assert (tmp_path / "sessions" / sid).is_dir()
    llm.gate.set()
    wait_idle(wb)
    assert wb.state()["transcript"][-1]["text"] == "好的"
    hub.delete(sid)


@pytest.mark.parametrize("bad", ["..", "a/b", "", "a\\b", "../sessions", "demo-..", "demo-nope", ".", "x y"])
def test_bad_ids_are_not_found(tmp_path, bad):
    hub = make_hub(tmp_path, demo_dir=DEMO_DIR)
    (tmp_path / "outside").mkdir()
    for fn in (hub.open, hub.delete, lambda i: hub.rename(i, "t")):
        with pytest.raises(FileNotFoundError):
            fn(bad)


def test_reopen_after_restart_resumes(tmp_path):
    hub = make_hub(tmp_path, Factory(ScriptedLLM([PLAN_TALK, S1, S2])))
    sid = seeded(hub)
    say(hub.open(sid), "开始建模吧")
    before = hub.open(sid).state()
    hub.close()
    again = make_hub(tmp_path).open(sid).state()
    for key in ("phase", "transcript", "brief", "plan", "versions", "usage", "session"):
        assert again[key] == before[key], key


def test_demo_session_listed_last_and_read_only(tmp_path):
    hub = make_hub(tmp_path, demo_dir=DEMO_DIR)
    sid = hub.create()
    listed = hub.list()
    assert [x["id"] for x in listed] == [sid, "demo-phone_stand"]
    demo = listed[-1]
    assert demo["demo"] is True and demo["versions"] == 2 and demo["title"] == "桌面看视频小支架"
    wb = hub.open("demo-phone_stand")
    st = wb.state()
    assert st["session"]["demo"] is True and len(st["versions"]) == 2 and st["transcript"]
    with pytest.raises(PermissionError):
        wb.submit("你好")
    with pytest.raises(PermissionError):
        hub.delete("demo-phone_stand")
    with pytest.raises(PermissionError):
        hub.rename("demo-phone_stand", "改名")
    assert (DEMO_DIR / "phone_stand" / "log.jsonl").is_file()


def test_lru_closes_idle_workbench(tmp_path):
    hub = make_hub(tmp_path)
    ids = [hub.create() for _ in range(9)]
    first = hub.open(ids[0])
    for sid in ids[1:8]:
        hub.open(sid)
    hub.open(ids[0])          # 最近用过：不该被关
    hub.open(ids[8])          # 第 9 个：关掉最久没用的 ids[1]
    assert len(hub._open) == 8 and ids[1] not in hub._open and hub.open(ids[0]) is first


def test_lru_skips_busy_workbench(tmp_path):
    llm = GateLLM(LLMReply("好的", [], {}))
    hub = make_hub(tmp_path, Factory(llm))
    ids = [hub.create() for _ in range(9)]
    busy = hub.open(ids[0])
    busy.submit("你好")
    assert llm.entered.wait(5)
    for sid in ids[1:]:
        hub.open(sid)
    assert ids[0] in hub._open and ids[1] not in hub._open
    llm.gate.set()
    wait_idle(busy)


def test_refresh_agents_swaps_llm_for_idle_only(tmp_path):
    gate = GateLLM(LLMReply("老的", [], {}))
    factory = Factory(gate, ScriptedLLM([LLMReply("在", [], {})]))
    hub = make_hub(tmp_path, factory)
    busy_id, idle_id = hub.create(), hub.create()
    busy, idle = hub.open(busy_id), hub.open(idle_id)
    busy.submit("你好")
    assert gate.entered.wait(5)
    old_idle_agent = idle.agent
    factory.llms = [ScriptedLLM([LLMReply("新的", [], {})]), ScriptedLLM([LLMReply("新的忙", [], {})])]
    hub.refresh_agents()
    assert idle.agent is not old_idle_agent and busy.agent.llm is gate
    assert say(idle, "试试")[-2]["text"] == "新的"
    gate.gate.set()
    wait_idle(busy)
    wb = hub.open(busy_id)    # 空下来以后，下次打开时换上新的设置
    assert wb is busy and busy.agent.llm is not gate
    assert say(busy, "再来")[-2]["text"] == "新的忙"


def test_close_closes_all(tmp_path):
    llm = GateLLM(LLMReply("好", [], {}))
    hub = make_hub(tmp_path, Factory(llm))
    wb = hub.open(hub.create())
    wb.submit("你好")
    assert llm.entered.wait(5)
    import threading

    threading.Timer(0.2, llm.gate.set).start()
    hub.close()
    assert not wb.is_busy() and hub._open == {}
