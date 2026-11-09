"""网页后端的状态。两种模式，对外的接口完全一样：

- LiveApp：接着真实的智能体。一条消息放在后台线程里处理；智能体每写一条日志，就由后台线程生成一份快照，
  放进有锁保护的变量里，/api/state 只读这份快照，不会和智能体同时碰同一份数据。
- ReplayApp：只读回放一个已经保存的会话目录（log.jsonl、brief.json、versions/）。不需要 API key，
  也不花钱，用来预览界面，演示时断网也能当后备。

两种模式的对话记录都由 events.fold 从日志折叠出来，所以看到的东西一模一样。
"""

from __future__ import annotations

import copy
import json
import re
import sys
import threading
import time
import traceback
from pathlib import Path
from typing import Any, Callable

from cad_agent.agent.loop import Agent
from cad_agent.brief import Brief
from cad_agent.session import Session
from cad_agent.web.events import fold

VERSION_NAME_RE = re.compile(r"^v\d+$")
BUSY, EMPTY, READ_ONLY, OK, ACCEPTED = 409, 400, 403, 200, 202


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


# ---------------------------------------------------------------- 两种模式共用的部分


def _read_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def version_summary(path: Path) -> dict:
    """一个版本目录的摘要：有哪些文件、检查通过几条、相对上一版改了什么。"""
    checks = _read_json(path / "checks.json", [])
    checks = checks if isinstance(checks, list) else []
    try:
        changes = [line[2:] for line in (path / "changes.md").read_text(encoding="utf-8").splitlines() if line.startswith("- ")]
    except OSError:
        changes = []
    brief = _read_json(path / "brief.json", {})
    return {
        "name": path.name,
        "has_stl": (path / "model.stl").is_file(),
        "has_png": (path / "view.png").is_file(),
        "passed": sum(1 for c in checks if isinstance(c, dict) and c.get("passed")),
        "total": len(checks),
        "changes": [c for c in changes if not c.startswith("（")],
        "params": brief.get("params", []) if isinstance(brief, dict) else [],
    }


class _Base:
    mode = "live"

    def __init__(self, model_name: str) -> None:
        self.model_name = model_name
        self._lock = threading.RLock()
        self._version_cache: dict[str, dict] = {}  # 版本一旦生成就不会再变，摘要可以缓存

    # 子类提供
    def session_dir(self) -> Path:
        raise NotImplementedError

    def _versions(self) -> list[dict]:
        root = self.session_dir() / "versions"
        names = sorted((p for p in root.iterdir() if p.is_dir() and VERSION_NAME_RE.match(p.name)), key=lambda p: int(p.name[1:])) \
            if root.is_dir() else []
        out = []
        for p in names:
            if p.name not in self._version_cache:
                self._version_cache[p.name] = version_summary(p)
            out.append(self._version_cache[p.name])
        return out

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

    def _compose(self, events: list[tuple[str, dict]], brief: dict, checks: list[dict], facts: dict | None,
                 busy: bool, busy_since: float | None, error: str | None) -> dict:
        folded = fold(events, confirmed=bool(brief.get("confirmed")) and not brief.get("open_questions"), busy=busy)
        part = brief.get("part") or {}
        return {
            "mode": self.mode, "model": self.model_name, "busy": busy,
            "busy_seconds": round(time.monotonic() - busy_since, 1) if busy and busy_since else None,
            "part": {"name": part.get("name", ""), "purpose": part.get("purpose", "")},
            "stage": folded["stage"], "transcript": folded["transcript"], "activity": folded["activity"],
            "stats": folded["stats"], "brief": brief, "checks": checks, "facts": facts,
            "versions": self._versions(), "current_version": folded["last_version"], "error": error,
        }


# ---------------------------------------------------------------- 实时模式


class LiveApp(_Base):
    mode = "live"

    def __init__(self, make_agent: Callable[[], tuple[Agent, Session]], model_name: str) -> None:
        super().__init__(model_name)
        self._make_agent = make_agent
        self._idle = threading.Event()
        self._idle.set()
        self._start_session()

    def _start_session(self) -> None:
        agent, session = self._make_agent()
        if isinstance(session, LiveSession):
            session.listener = self._on_event
        with self._lock:
            self.agent, self.session = agent, session
            self._events: list[tuple[str, dict]] = []
            self._busy, self._busy_since, self._error = False, None, None
            self._view: dict = {"brief": Brief().to_dict(), "checks": [], "facts": None}
            self._version_cache = {}
        self._refresh_view()

    def session_dir(self) -> Path:
        with self._lock:
            return self.session.dir

    # ---- 只在处理消息的线程里（或空闲时）调用 ----
    def _refresh_view(self) -> None:
        ws = self.agent.toolbox.ws
        run = ws.last_run
        view = {
            "brief": copy.deepcopy(ws.brief.to_dict()),
            "checks": [c.to_dict() for c in run.checks] if run is not None else [],
            "facts": copy.deepcopy({k: run.facts[k] for k in ("size", "volume") if k in run.facts}) if run is not None and run.facts else None,
        }
        with self._lock:
            self._view = view

    def _on_event(self, kind: str, data: dict) -> None:
        if kind == "startup":
            return
        with self._lock:
            self._events.append((kind, copy.deepcopy(data)))
        self._refresh_view()

    def _work(self, text: str) -> None:
        try:
            self.agent.handle_user(text)
        except Exception as e:  # noqa: BLE001 - 演示时出任何错，页面都不能卡死，服务也不能退出
            traceback.print_exc(file=sys.stderr)
            message = f"处理这条消息时出了意外错误（{type(e).__name__}）：{e}。需求单和模型都还在，可以再发一次，或者开一个新会话。"
            with self._lock:
                self._error = message
                self._events.append(("error", {"text": message}))
        finally:
            try:
                self._refresh_view()
            except Exception:  # noqa: BLE001
                traceback.print_exc(file=sys.stderr)
            with self._lock:
                self._busy, self._busy_since = False, None
            self._idle.set()

    # ---- 接口用 ----
    def snapshot(self) -> dict:
        with self._lock:
            events, view = list(self._events), copy.deepcopy(self._view)
            busy, since, error = self._busy, self._busy_since, self._error
        return self._compose(events, view["brief"], view["checks"], view["facts"], busy, since, error)

    def submit(self, text: str) -> int:
        """202 开始处理；400 空消息；409 正在处理上一条。"""
        if not isinstance(text, str) or not text.strip():
            return EMPTY
        with self._lock:
            if self._busy:
                return BUSY
            self._busy, self._busy_since, self._error = True, time.monotonic(), None
            self._idle.clear()
        threading.Thread(target=self._work, args=(text.strip(),), daemon=True, name="agent-turn").start()
        return ACCEPTED

    def reset(self) -> int:
        with self._lock:
            if self._busy:
                return BUSY
        self._start_session()
        return OK

    def wait_idle(self, timeout: float) -> bool:
        return self._idle.wait(timeout)


AppState = LiveApp  # 旧名字，保持兼容


# ---------------------------------------------------------------- 回放模式


class ReplayApp(_Base):
    mode = "replay"

    def __init__(self, session_dir: Path) -> None:
        self._dir = Path(session_dir)
        if not (self._dir / "log.jsonl").is_file():
            raise FileNotFoundError(f"{self._dir} 不是会话目录（里面没有 log.jsonl）")
        self._events = self._load_events()
        startup = next((d for k, d in self._events if k == "startup"), {})
        super().__init__(str(startup.get("model") or "回放"))
        self._events = [(k, d) for k, d in self._events if k != "startup"]

    def _load_events(self) -> list[tuple[str, dict]]:
        events = []
        for line in (self._dir / "log.jsonl").read_text(encoding="utf-8").splitlines():
            try:
                row = json.loads(line)
            except ValueError:
                continue  # 坏掉的一行跳过，不影响其余内容
            if isinstance(row, dict) and isinstance(row.get("kind"), str):
                events.append((row.pop("kind"), row))
        return events

    def session_dir(self) -> Path:
        return self._dir

    def snapshot(self) -> dict:
        brief = _read_json(self._dir / "brief.json", Brief().to_dict())
        versions = self._versions()
        checks = _read_json(self._dir / "versions" / versions[-1]["name"] / "checks.json", []) if versions else []
        snap = self._compose(self._events, brief if isinstance(brief, dict) else Brief().to_dict(),
                             checks if isinstance(checks, list) else [], None, False, None, None)
        snap["replay_of"] = self._dir.name
        return snap

    def submit(self, text: str) -> int:
        return READ_ONLY

    def reset(self) -> int:
        return READ_ONLY

    def wait_idle(self, timeout: float) -> bool:
        return True
