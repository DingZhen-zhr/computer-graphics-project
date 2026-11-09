"""网页后端的状态：一条消息放在后台线程里处理，状态快照由后台线程在每次写日志时生成。

线程规则：
- 同一时间只处理一条消息（submit 在忙时返回 409）。
- 智能体的数据（需求单、检查、版本）只由处理消息的那个线程读，生成快照后放进有锁保护的变量；
  /api/state 只读这份快照和几个有锁保护的计数，不会和智能体同时碰同一份数据。
- 后台线程里的任何异常都接住，写进 error 并显示在对话里，服务不退出。
"""

from __future__ import annotations

import copy
import re
import sys
import threading
import traceback
from pathlib import Path
from typing import Any, Callable

from cad_agent.agent.loop import Agent
from cad_agent.brief import Brief
from cad_agent.session import Session

VERSION_NAME_RE = re.compile(r"^v\d+$")
MAX_ACTIVITY = 40  # 实时进度最多留这么多条


# ---------------------------------------------------------------- 进度文字


def describe_event(kind: str, data: dict) -> str | None:
    """把一条日志变成一句给人看的进度；不需要显示的返回 None。"""
    if kind == "assistant":
        names = [c["name"] for c in data.get("tool_calls") or []]
        return "正在调用：" + "、".join(names) if names else "正在整理回复"
    if kind == "tool":
        name, args = data.get("name"), data.get("args") or {}
        if name == "upsert_feature":
            return f"写特征 {args.get('slug', '')}".rstrip()
        if name == "set_checks":
            return "写检查项"
        if name == "update_brief":
            return "更新需求单"
        return None  # build 由 build 记录负责，其余工具（api_help、inspect……）不显示
    if kind == "build":
        if data.get("passed"):
            return f"运行检查：{data.get('passed_checks', 0)}/{data.get('total_checks', 0)} 通过"
        return "运行没通过：" + _first_reason(data)
    if kind == "auto":
        if data.get("action") == "build":
            return "程序自动重新 build"
        if data.get("action") == "request_confirmation":
            return "程序自动请你确认"
    return None


def _first_reason(build: dict) -> str:
    if build.get("error"):
        return str(build["error"].get("message", "运行出错"))
    if build.get("failed_checks"):
        return f"检查 {build['failed_checks'][0]} 没通过"
    if build.get("missing_coverage"):
        return "缺少检查 " + "、".join(build["missing_coverage"])
    return "原因不明"


# ---------------------------------------------------------------- 有人在听的会话


class LiveSession(Session):
    """和 Session 一样写日志，写完再通知 listener（网页后端靠它拿到实时进度）。"""

    listener: Callable[[str, dict], None] | None = None

    def log(self, kind: str, **data: Any) -> None:
        super().log(kind, **data)
        if self.listener is not None:
            try:
                self.listener(kind, data)
            except Exception:  # noqa: BLE001 - 看进度的人出问题，不能打断智能体；原因打到终端，不吞掉
                traceback.print_exc(file=sys.stderr)


# ---------------------------------------------------------------- 状态


class AppState:
    def __init__(self, make_agent: Callable[[], tuple[Agent, Session]], model_name: str) -> None:
        self._make_agent = make_agent
        self.model_name = model_name
        self._lock = threading.RLock()
        self._idle = threading.Event()
        self._idle.set()
        self.agent: Agent
        self.session: Session
        self._start_session()

    # ---- 会话 ----
    def _start_session(self) -> None:
        agent, session = self._make_agent()
        if isinstance(session, LiveSession):
            session.listener = self._on_event
        with self._lock:
            self.agent, self.session = agent, session
            self._busy = False
            self._transcript: list[dict] = []
            self._activity: list[str] = []
            self._error: str | None = None
            self._stats = {"cost": 0.0, "cost_known": True, "prompt_tokens": 0, "cached_tokens": 0}
            self._view: dict = {}
        self._refresh_view()

    def session_dir(self) -> Path:
        with self._lock:
            return self.session.dir

    # ---- 智能体线程里调用 ----
    def _refresh_view(self) -> None:
        """生成需求单、检查、版本的快照。只在处理消息的线程里（或空闲时）调用。"""
        ws = self.agent.toolbox.ws
        run = ws.last_run
        view = {
            "brief": copy.deepcopy(ws.brief.to_dict()),
            "checks": [c.to_dict() for c in run.checks] if run is not None else [],
            "versions": [
                {"name": v.name, "has_stl": (v / "model.stl").is_file(), "has_png": (v / "view.png").is_file()}
                for v in self.session.versions()
            ],
        }
        with self._lock:
            self._view = view

    def _on_event(self, kind: str, data: dict) -> None:
        text = describe_event(kind, data)
        with self._lock:
            if text is not None:
                self._activity = [*self._activity, text][-MAX_ACTIVITY:]
            if kind == "assistant":
                usage = data.get("usage") or {}
                self._stats["prompt_tokens"] += int(usage.get("prompt_tokens", 0) or 0)
                self._stats["cached_tokens"] += int(usage.get("cached_tokens", 0) or 0)
                if data.get("cost") is None:
                    self._stats["cost_known"] = False
                else:
                    self._stats["cost"] += data["cost"]
        self._refresh_view()

    def _work(self, text: str) -> None:
        try:
            turn = self.agent.handle_user(text)
            entry = {"role": "assistant", "kind": turn.kind, "text": turn.text,
                     "version": turn.version_dir.name if turn.version_dir else None, "llm_calls": turn.llm_calls, "cost": turn.cost}
            with self._lock:
                self._transcript.append(entry)
        except Exception as e:  # noqa: BLE001 - 演示时出任何错，页面都不能卡死，服务也不能退出
            traceback.print_exc(file=sys.stderr)
            message = f"处理这条消息时出了意外错误（{type(e).__name__}）：{e}。可以再发一次，或者点重置开始新会话。"
            with self._lock:
                self._error = message
                self._transcript.append({"role": "assistant", "kind": "error", "text": message, "version": None, "llm_calls": 0, "cost": None})
        finally:
            try:
                self._refresh_view()
            except Exception:  # noqa: BLE001
                traceback.print_exc(file=sys.stderr)
            with self._lock:
                self._activity = []
                self._busy = False
            self._idle.set()

    # ---- 接口用 ----
    def snapshot(self) -> dict:
        """/api/state 的内容（加锁拷贝）。"""
        with self._lock:
            stats = self._stats
            return {
                "busy": self._busy,
                "model": self.model_name,
                "transcript": copy.deepcopy(self._transcript),
                "activity": list(self._activity),
                "brief": copy.deepcopy(self._view.get("brief", Brief().to_dict())),
                "checks": copy.deepcopy(self._view.get("checks", [])),
                "versions": copy.deepcopy(self._view.get("versions", [])),
                "stats": {"cost": stats["cost"] if stats["cost_known"] else None,
                          "prompt_tokens": stats["prompt_tokens"], "cached_tokens": stats["cached_tokens"]},
                "error": self._error,
            }

    def submit(self, text: str) -> int:
        """202 开始处理；400 空消息；409 正在处理上一条。"""
        if not isinstance(text, str) or not text.strip():
            return 400
        with self._lock:
            if self._busy:
                return 409
            self._busy = True
            self._error = None
            self._activity = ["正在思考…"]
            self._transcript.append({"role": "user", "kind": "user", "text": text.strip(), "version": None, "llm_calls": 0, "cost": None})
            self._idle.clear()
        threading.Thread(target=self._work, args=(text.strip(),), daemon=True, name="agent-turn").start()
        return 202

    def reset(self) -> int:
        """200 开了新会话；409 正在处理消息。"""
        with self._lock:
            if self._busy:
                return 409
        self._start_session()
        return 200

    def wait_idle(self, timeout: float) -> bool:
        return self._idle.wait(timeout)

    # ---- 文件和版本对比 ----
    def version_dir(self, name: str) -> Path | None:
        if not VERSION_NAME_RE.match(name):
            return None
        path = self.session_dir() / "versions" / name
        return path if path.is_dir() else None

    def diff(self, a: str, b: str) -> list[str] | None:
        """两个版本的参数变化（中文变化行）；版本不存在返回 None。"""
        from cad_agent.cli import _load_brief, diff_briefs

        va, vb = self.version_dir(a), self.version_dir(b)
        if va is None or vb is None:
            return None
        return diff_briefs(_load_brief(va), _load_brief(vb))
