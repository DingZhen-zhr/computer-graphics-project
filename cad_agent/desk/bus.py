"""事件流：一个会话一条。工作线程往里发事件，页面通过 SSE 按 seq 取走。

每条事件是一个字典，带 seq（从 1 递增）和 type。只保留最近 MAX_EVENTS 条；
请求的位置比保留的最早一条还早（中间有事件已经丢了）时，返回一条 resync，页面据此重新取一次完整状态。
"""

from __future__ import annotations

import copy
import threading
from collections import deque

MAX_EVENTS = 2000


class EventBus:
    def __init__(self, max_events: int = MAX_EVENTS) -> None:
        self._events: deque[dict] = deque(maxlen=max_events)
        self._seq = 0
        self._cond = threading.Condition()

    def publish(self, type: str, **data: object) -> int:  # noqa: A002 - 名字照接口
        """发一条事件，返回它的 seq。数据先深拷贝一份，之后外面改原对象不影响已发的事件。"""
        with self._cond:
            self._seq += 1
            self._events.append({"seq": self._seq, "type": type, **copy.deepcopy(data)})
            self._cond.notify_all()
            return self._seq

    def _since_locked(self, seq: int) -> list[dict]:
        if seq >= self._seq:
            return []
        oldest = self._events[0]["seq"] if self._events else self._seq + 1
        if seq + 1 < oldest:
            return [{"seq": self._seq, "type": "resync"}]
        return [copy.deepcopy(e) for e in self._events if e["seq"] > seq]

    def since(self, seq: int) -> list[dict]:
        """seq 之后的全部事件（拷贝）。"""
        with self._cond:
            return self._since_locked(seq)

    def wait(self, seq: int, timeout: float) -> list[dict]:
        """seq 之后有事件就立刻返回；没有就等，最多 timeout 秒，超时返回空表。"""
        with self._cond:
            self._cond.wait_for(lambda: self._seq > seq, timeout=timeout)
            return self._since_locked(seq)

    def last_seq(self) -> int:
        with self._cond:
            return self._seq
