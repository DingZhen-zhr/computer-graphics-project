"""桌面端的会话管理（第二版计划 3 Task 5）：列表、新建、打开（从目录恢复）、改名、删除。

会话 id 就是会话目录名，只能是字母、数字、短横线；别的一律当作不存在（防止路径穿越）。
示例会话的 id 是 demo-<目录名>，只读，必须正好是示例目录里有的那几个。
同时打开的工作台最多 MAX_OPEN 个；超过时关掉最久没用、而且空闲的那个。
"""

from __future__ import annotations

import datetime
import json
import logging
import re
import shutil
import threading
from collections import OrderedDict
from pathlib import Path
from typing import TYPE_CHECKING, Callable

from cad_agent.agent.resume import resume_agent
from cad_agent.desk.view import session_title
from cad_agent.desk.workbench import Busy, Workbench
from cad_agent.session import Session

if TYPE_CHECKING:
    from cad_agent.agent.loop import Agent

logger = logging.getLogger("caliper.desk")

ID_RE = re.compile(r"^[A-Za-z0-9-]+$")
DEMO_PREFIX = "demo-"
MAX_OPEN = 8
MAX_TITLE = 60


def _now() -> str:
    return datetime.datetime.now().isoformat(timespec="seconds")


def _brief_of(d: Path) -> dict | None:
    try:
        data = json.loads((d / "brief.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _mtime(p: Path) -> str:
    try:
        return datetime.datetime.fromtimestamp(p.stat().st_mtime).isoformat(timespec="seconds")
    except OSError:
        return ""


class Hub:
    def __init__(self, *, make_agent: Callable[[Session], Agent], sessions_dir: Path, cases_dir: Path, demo_dir: Path | None) -> None:
        self.make_agent = make_agent
        self.sessions_dir, self.cases_dir = Path(sessions_dir), Path(cases_dir)
        self.demo_dir = Path(demo_dir) if demo_dir is not None else None
        self._open: OrderedDict[str, Workbench] = OrderedDict()   # 最近用过的在最后
        self._stale: set[str] = set()                             # 设置改了、等空闲时换智能体
        self._lock = threading.RLock()

    # ---------------------------------------------------------------- 找目录
    def _demo_names(self) -> list[str]:
        if self.demo_dir is None or not self.demo_dir.is_dir():
            return []
        return sorted(p.name for p in self.demo_dir.iterdir() if p.is_dir() and (p / "log.jsonl").is_file())

    def _is_demo(self, session_id: str) -> bool:
        return isinstance(session_id, str) and session_id.startswith(DEMO_PREFIX) and session_id[len(DEMO_PREFIX):] in self._demo_names()

    def _dir(self, session_id: str) -> Path:
        """会话目录；id 不合法或目录不存在都抛 FileNotFoundError。"""
        if self._is_demo(session_id):
            return self.demo_dir / session_id[len(DEMO_PREFIX):]   # type: ignore[operator]
        if not isinstance(session_id, str) or not ID_RE.fullmatch(session_id) or session_id.startswith(DEMO_PREFIX):
            raise FileNotFoundError("没有这个会话")
        d = self.sessions_dir / session_id
        if not d.is_dir():
            raise FileNotFoundError("没有这个会话")
        return d

    # ---------------------------------------------------------------- 列表
    def _item(self, d: Path, session_id: str, demo: bool) -> dict:
        s = Session.open(d)
        meta = s.meta()
        updated = str(meta.get("updated") or meta.get("created") or _mtime(d / "log.jsonl") or _mtime(d))
        return {"id": session_id, "title": session_title(s, _brief_of(d)), "updated": updated, "versions": len(s.versions()), "demo": demo}

    def list(self) -> list[dict]:
        mine = []
        if self.sessions_dir.is_dir():
            for d in self.sessions_dir.iterdir():
                if d.is_dir() and ID_RE.fullmatch(d.name) and not d.name.startswith(DEMO_PREFIX):
                    mine.append(self._item(d, d.name, False))
        mine.sort(key=lambda x: (x["updated"], x["id"]), reverse=True)
        demos = [self._item(self.demo_dir / n, DEMO_PREFIX + n, True) for n in self._demo_names()]   # type: ignore[operator]
        return mine + demos

    def create(self) -> str:
        s = Session(self.sessions_dir)
        now = _now()
        s.set_meta(created=now, updated=now)
        return s.dir.name

    # ---------------------------------------------------------------- 打开
    def _new_workbench(self, session_id: str, d: Path) -> Workbench:
        if self._is_demo(session_id):
            return Workbench(None, Session.open(d), demo=True)   # type: ignore[arg-type]  # 示例会话没有智能体
        session = Session.open(d)
        agent = self.make_agent(session)
        resume_agent(agent)
        return Workbench(agent, session)

    def _evict(self) -> None:
        while len(self._open) > MAX_OPEN:
            victim = next((sid for sid, wb in self._open.items() if not wb.is_busy()), None)
            if victim is None:
                return   # 全都在忙：先不关
            self._open.pop(victim).close()
            self._stale.discard(victim)

    def open(self, session_id: str) -> Workbench:
        with self._lock:
            d = self._dir(session_id)
            wb = self._open.get(session_id)
            if wb is None:
                wb = self._new_workbench(session_id, d)
                self._open[session_id] = wb
                self._evict()
            else:
                self._open.move_to_end(session_id)
                if session_id in self._stale and not wb.is_busy():
                    self._swap(session_id, wb)
            return wb

    def _swap(self, session_id: str, wb: Workbench) -> None:
        try:
            agent = self.make_agent(wb.session)
            resume_agent(agent)
            wb._replace_agent(agent)
            self._stale.discard(session_id)
        except Busy:
            pass   # 刚好开始忙了：等下次
        except Exception:  # noqa: BLE001 - 新设置造不出智能体时，继续用旧的；原因写进程序日志
            logger.exception("按新的设置换智能体失败")

    def refresh_agents(self) -> None:
        with self._lock:
            for sid, wb in self._open.items():
                if wb.demo:
                    continue
                self._stale.add(sid)
                if not wb.is_busy():
                    self._swap(sid, wb)

    # ---------------------------------------------------------------- 改名、删除
    def rename(self, session_id: str, title: str) -> None:
        d = self._dir(session_id)
        if self._is_demo(session_id):
            raise PermissionError("示例会话不能改名。")
        if not isinstance(title, str) or not title.strip():
            raise ValueError("标题不能为空")
        Session.open(d).set_meta(title=title.strip()[:MAX_TITLE])

    def delete(self, session_id: str) -> None:
        with self._lock:
            d = self._dir(session_id)
            if self._is_demo(session_id):
                raise PermissionError("示例会话不能删除。")
            wb = self._open.get(session_id)
            if wb is not None:
                if wb.is_busy():
                    raise Busy("这个会话正在运行，等这一轮结束再删除。")
                wb.close()
                del self._open[session_id]
            self._stale.discard(session_id)
            try:
                shutil.rmtree(d)
            except OSError:
                logger.exception("删除会话目录失败")
                raise PermissionError("有文件正被别的程序占用，没能删干净。关掉打开着这个零件文件的程序，再删一次。") from None

    def close(self) -> None:
        with self._lock:
            for wb in self._open.values():
                wb.close()
            self._open.clear()
            self._stale.clear()
