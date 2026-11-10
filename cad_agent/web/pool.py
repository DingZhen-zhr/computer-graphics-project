"""公网测试时的多人支持：每个登录的人有自己的会话，大家共用一个花费上限，同时在跑的人数有上限。

- Budget：所有会话共用的花费上限（元）。到了就不再接新消息，开新会话也不清零。
- VisitorPool：登录一次发一个访问令牌，对应一个独立的 LiveApp（自己的需求单、对话、版本）。
  长时间不用的会话会被回收；同时在处理消息的会话数有上限，超过的人收到"稍等"。
"""

from __future__ import annotations

import secrets
import threading
import time
from typing import Callable

from cad_agent.web.app import LiveApp


class Budget:
    def __init__(self, limit: float) -> None:
        self.limit = float(limit)
        self.spent = 0.0
        self._lock = threading.Lock()

    def add(self, cost: float | None) -> None:
        with self._lock:
            self.spent += float(cost or 0.0)

    def exhausted(self) -> bool:
        with self._lock:
            return self.spent >= self.limit

    def view(self) -> dict:
        with self._lock:
            return {"limit": self.limit, "spent": round(self.spent, 4)}


class VisitorPool:
    def __init__(self, make_app: Callable[[], LiveApp], *, max_visitors: int = 30, max_busy: int = 3, idle_seconds: float = 7200) -> None:
        self._make_app = make_app
        self.max_visitors, self.max_busy, self.idle_seconds = max_visitors, max_busy, idle_seconds
        self._apps: dict[str, tuple[LiveApp, float]] = {}
        self._lock = threading.Lock()

    def busy_count(self) -> int:
        with self._lock:
            apps = [a for a, _ in self._apps.values()]
        return sum(1 for a in apps if a.is_busy())

    def can_start(self) -> bool:
        return self.busy_count() < self.max_busy

    def _evict_idle(self) -> None:
        now = time.monotonic()
        for token, (app, seen) in list(self._apps.items()):
            if now - seen > self.idle_seconds and not app.is_busy():
                del self._apps[token]

    def new_visitor(self) -> str | None:
        """登录成功时调用：发一个新令牌，并为它开一个会话。人数已满时返回 None。"""
        with self._lock:
            self._evict_idle()
            if len(self._apps) >= self.max_visitors:
                return None
        app = self._make_app()  # 造智能体可能要一点时间，不占着锁
        token = secrets.token_urlsafe(32)
        with self._lock:
            self._apps[token] = (app, time.monotonic())
        return token

    def get(self, token: str | None) -> LiveApp | None:
        if not token:
            return None
        with self._lock:
            hit = self._apps.get(token)
            if hit is None:
                return None
            self._apps[token] = (hit[0], time.monotonic())
            return hit[0]

    def __len__(self) -> int:
        with self._lock:
            return len(self._apps)
