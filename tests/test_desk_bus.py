"""桌面端的事件流（第二版计划 3 Task 4）。"""

from __future__ import annotations

import threading
import time

from cad_agent.desk.bus import EventBus


def test_seq_increments():
    bus = EventBus()
    assert bus.last_seq() == 0
    assert [bus.publish("delta", text=str(i)) for i in range(3)] == [1, 2, 3]
    assert bus.last_seq() == 3


def test_since():
    bus = EventBus()
    bus.publish("turn_start", text="你好")
    bus.publish("delta", text="在")
    assert bus.since(0) == [{"seq": 1, "type": "turn_start", "text": "你好"}, {"seq": 2, "type": "delta", "text": "在"}]
    assert bus.since(1) == [{"seq": 2, "type": "delta", "text": "在"}]
    assert bus.since(2) == []


def test_wait_returns_when_published():
    bus = EventBus()
    threading.Timer(0.1, lambda: bus.publish("delta", text="x")).start()
    started = time.monotonic()
    got = bus.wait(0, timeout=5)
    assert [e["type"] for e in got] == ["delta"] and time.monotonic() - started < 2


def test_wait_times_out_empty():
    bus = EventBus()
    bus.publish("delta", text="x")
    started = time.monotonic()
    assert bus.wait(1, timeout=0.2) == []
    assert time.monotonic() - started >= 0.15


def test_resubscribe_since_seq_gets_only_newer_events():
    bus = EventBus()
    for t in "abc":
        bus.publish("delta", text=t)
    seen = bus.since(0)
    last = seen[-1]["seq"]
    for t in "de":
        bus.publish("delta", text=t)
    again = bus.since(last)
    assert [e["text"] for e in again] == ["d", "e"]
    assert not {e["seq"] for e in seen} & {e["seq"] for e in again}


def test_old_seq_gets_resync():
    bus = EventBus()
    for i in range(2100):
        bus.publish("delta", text=str(i))
    got = bus.since(5)
    assert len(got) == 1 and got[0]["type"] == "resync"
    assert len(bus.since(2099)) == 1 and bus.since(100)[0]["seq"] == 101   # 保留最近 2000 条：101 到 2100


def test_events_are_copies():
    bus = EventBus()
    data = {"a": [1]}
    bus.publish("build", info=data)
    data["a"].append(2)
    got = bus.since(0)[0]
    got["info"]["a"].append(3)
    assert bus.since(0)[0]["info"] == {"a": [1]}
