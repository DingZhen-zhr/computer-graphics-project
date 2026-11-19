"""会话日志通知、回放读取、版本摘要（第二版计划 4 Task 6 从旧网页的 cad_agent/web/app.py 搬来，行为不变）。

- LiveSession：和 Session 一样写日志，写完再通知 listener。
- version_summary：一个版本目录的摘要（桌面端 view.py 用它）。
- ReplayApp：只读回放一个已经保存的会话目录（log.jsonl、brief.json、versions/），对话记录由 events.fold 折叠出来。
旧网页的实时模式（LiveApp）和它的 HTTP 服务一起退役了，没有搬过来。
"""

from __future__ import annotations

import json
import re
import sys
import threading
import time
import traceback
from pathlib import Path
from typing import Any, Callable

from cad_agent.brief import Brief
from cad_agent.desk.events import fold
from cad_agent.session import Session

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


# ---------------------------------------------------------------- 回放


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
