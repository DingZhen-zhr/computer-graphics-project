"""一个打开的会话：智能体 + 事件流 + 一个工作线程（第二版计划 3 Task 4）。

工作台给会话的 log 包一层：智能体每写一条日志，就翻译成界面要的事件发到事件流上；智能体的文字片段发成 delta。
写日志、发事件、取完整状态都在同一把锁里做，所以页面拿到的"完整状态 + 它的 last_seq"前后对得上：
从 last_seq 接着收事件，不会重复也不会漏。工作线程正在跑时，完整状态用的是最近一次写日志时拷下来的工作区。
监听器自己出错只记到程序日志，不打断智能体。
"""

from __future__ import annotations

import copy
import datetime
import logging
import threading
from pathlib import Path
from typing import TYPE_CHECKING, Any

from cad_agent import brand
from cad_agent.agent.manual import ManualResult, apply_params as manual_apply
from cad_agent.cases import save_case as save_user_case
from cad_agent.desk.bus import EventBus
from cad_agent.desk.labels import tool_label, tool_summary
from cad_agent.desk.view import build_state
from cad_agent.llm.client import RESET_DELTA
from cad_agent.session import Session

if TYPE_CHECKING:
    from cad_agent.agent.loop import Agent

logger = logging.getLogger(f"{brand.COMMAND}.desk")

CRASH_TEXT = "处理这条消息时出了意外的错误。需求单和已经写好的内容都还在，可以再发一次；一直这样的话，可以开一个新会话。"
DEMO_TEXT = "示例会话只能看，不能改。"
NOT_RUN_TEXT = "没有运行"
END_KINDS = ("reply", "question", "confirm", "delivered", "failed", "stopped")
PASS_THROUGH = ("gate", "review", "cases", "manual")
USAGE_KEYS = ("llm_calls", "tokens", "prompt_tokens", "completion_tokens", "cached_tokens", "reasoning_tokens")


class Busy(Exception):
    """智能体正在处理上一条消息。"""


class Workbench:
    def __init__(self, agent: Agent, session: Session, *, demo: bool = False) -> None:
        self.agent, self.session, self.demo = agent, session, demo   # 示例会话没有智能体（agent 是 None）
        self.bus = EventBus()
        self._mu = threading.RLock()          # 写日志 + 发事件 + 取状态
        self._busy = False
        self._thread: threading.Thread | None = None
        self._ws_copy: Any = None
        self._pending: list[tuple[str, Any]] = []   # 这次回复里还没开始的工具调用
        self._running: dict | None = None           # 正在执行的工具：id、name、label、stage
        self._auto_reason: str | None = None
        self._next_id = 0
        self._streaming = ""
        self._last_plan: Any = None
        if agent is not None and not demo:
            agent.on_delta = self._on_delta
            raw_log = session.log

            def log(kind: str, **data: Any) -> None:
                with self._mu:
                    if kind == "tool" and self._running is not None:
                        data = {**data, "stage_at": self._running["stage"]}   # 工具开始时的当前阶段，恢复时靠它分组
                    raw_log(kind, **data)
                    try:
                        self._on_record(kind, data)
                        self._ws_copy = copy.deepcopy(self.agent.ws)   # 换过智能体以后也要拷新的那个
                    except Exception:  # noqa: BLE001 - 监听器出错不能打断智能体；原因写进程序日志
                        logger.exception("把日志翻译成界面事件时出错（%s）", kind)

            session.log = log  # type: ignore[method-assign]
            self._last_plan = self._plan_view()

    # ---------------------------------------------------------------- 日志 → 事件
    def _plan_view(self) -> dict | None:
        plan = self.agent.ws.plan
        if plan is None:
            return None
        cur = plan.current()
        return {"stages": plan.to_list(), "current": cur.id if cur is not None else None}

    def _publish_plan_if_changed(self) -> None:
        view = self._plan_view()
        if view is not None and view != self._last_plan:
            self.bus.publish("plan", **view)
        self._last_plan = view

    def _start_tool(self, name: str, args: Any, auto_reason: str | None = None) -> None:
        self._next_id += 1
        plan = self.agent.ws.plan
        cur = plan.current() if plan is not None else None
        label = tool_label(name, args, auto_reason)
        self._running = {"id": f"t{self._next_id}", "name": name, "label": label, "stage": cur.id if cur is not None else None}
        self.bus.publish("tool_start", id=self._running["id"], name=name, label=label)

    def _start_next(self) -> None:
        if self._running is None and self._pending:
            name, args = self._pending.pop(0)
            self._start_tool(name, args)

    def _drop_running(self) -> None:
        """这一轮结束了，但开始了的工具没有执行（比如停止）：给它补一条结束，页面上不会一直转。"""
        if self._running is not None:
            r = self._running
            self.bus.publish("tool_end", id=r["id"], name=r["name"], ok=False, summary=NOT_RUN_TEXT)
        self._running, self._pending, self._auto_reason = None, [], None

    def _on_delta(self, text: str) -> None:
        with self._mu:
            if text == RESET_DELTA:
                self._streaming = ""
                self.bus.publish("delta_reset")
            else:
                self._streaming += text
                self.bus.publish("delta", text=text)

    def _on_record(self, kind: str, data: dict) -> None:
        if kind == "user":
            self._drop_running()
            self._streaming = ""
            self.bus.publish("turn_start", text=str(data.get("text", "")))
        elif kind == "assistant":
            self._streaming = ""
            self.bus.publish("assistant", content=str(data.get("content") or ""))
            self._pending = [(str(tc.get("name", "")), tc.get("args")) for tc in data.get("tool_calls") or []]
            self._start_next()
        elif kind == "auto" and data.get("action") == "build":
            self._auto_reason = str(data.get("reason") or "")
            if self._running is None:
                self._start_tool("build", {}, self._auto_reason)
        elif kind == "tool":
            name = str(data.get("name", ""))
            if self._running is None:   # 对不上时也补一条开始，免得页面少一个节点
                self._start_tool(name, data.get("args"), self._auto_reason if data.get("auto") else None)
            ok, summary = tool_summary(name, data.get("content"), skipped=bool(data.get("skipped")))
            self.bus.publish("tool_end", id=self._running["id"], name=name, ok=ok, summary=summary)
            self._running = None
            if data.get("auto"):
                self._auto_reason = None
            self._publish_plan_if_changed()
            self._start_next()
        elif kind == "build":
            self.bus.publish("build", **data)
            self._publish_plan_if_changed()
        elif kind == "stage":
            self.bus.publish("stage", **{k: data.get(k) for k in ("id", "title", "checks", "size", "volume")})
            self._publish_plan_if_changed()
        elif kind in PASS_THROUGH:
            self.bus.publish(kind, **data)
        elif kind in END_KINDS:
            self._drop_running()
            self._streaming = ""
            usage = {k: data.get(k) or 0 for k in USAGE_KEYS}
            extra = {k: v for k, v in data.items() if k not in ("text", "cost", *USAGE_KEYS)}
            self.bus.publish("turn_end", kind=kind, text=str(data.get("text", "")), extra=extra, usage=usage, cost=data.get("cost"))
            self._publish_plan_if_changed()

    # ---------------------------------------------------------------- 对外
    def state(self) -> dict:
        with self._mu:
            busy = self._busy
            ws = None
            if self.agent is not None:
                ws = self._ws_copy if busy and self._ws_copy is not None else self.agent.ws
            seq = self.bus.last_seq()
            st = build_state(self.session, ws, busy=busy, demo=self.demo)
            st["last_seq"] = seq
            r = self._running
            st["pending"] = {"streaming": self._streaming,
                             "running": {k: r[k] for k in ("id", "name", "label")} if r is not None else None} if busy else None
            return st

    def is_busy(self) -> bool:
        with self._mu:
            return self._busy

    def _claim(self) -> None:
        """标成正忙；已经在忙就抛 Busy。示例会话抛 PermissionError。"""
        if self.demo or self.agent is None:
            raise PermissionError(DEMO_TEXT)
        with self._mu:
            if self._busy:
                raise Busy("正在处理上一条消息，等这一轮结束再操作。")
            self._ws_copy = copy.deepcopy(self.agent.ws)
            self._busy = True

    def _release(self) -> None:
        with self._mu:
            self._busy = False
            self.session.set_meta(updated=datetime.datetime.now().isoformat(timespec="seconds"))
            self.bus.publish("state", state=self.state())

    def submit(self, text: str) -> None:
        if self.demo or self.agent is None:
            raise PermissionError(DEMO_TEXT)
        if not isinstance(text, str) or not text.strip():
            raise ValueError("消息不能为空")
        self._claim()
        self._thread = threading.Thread(target=self._work, args=(text.strip(),), daemon=True, name=f"{brand.COMMAND}-turn")
        self._thread.start()

    def _work(self, text: str) -> None:
        try:
            self.agent.handle_user(text)
        except Exception:  # noqa: BLE001 - 任何意外都变成一条 error 事件，界面不能卡死；堆栈只进程序日志
            logger.exception("处理消息时出了意外错误")
            with self._mu:
                self._drop_running()
                try:
                    self.session.log("error", text=CRASH_TEXT)
                except Exception:  # noqa: BLE001
                    logger.exception("写 error 日志失败")
                self.bus.publish("error", message=CRASH_TEXT)
        finally:
            self._release()

    def stop(self) -> None:
        if self.agent is not None:
            self.agent.request_stop()

    def apply_params(self, values: dict[str, float]) -> ManualResult:
        self._claim()
        self.agent._stop.clear()   # 上一轮刚结束时点的"停止"不能留到这里，不然沙盒一开始就被停掉
        try:
            return manual_apply(self.agent, values)
        finally:
            self._release()

    def save_case(self, title: str, tags: list[str], cases_dir: Path) -> str:
        if self.demo or self.agent is None:
            raise PermissionError(DEMO_TEXT)
        if self.is_busy():
            raise Busy("正在处理上一条消息，等这一轮结束再存。")
        return save_user_case(Path(cases_dir), title, tags, self.agent.ws).name

    def _replace_agent(self, agent: Agent) -> None:
        """设置改了以后换上新造的智能体（会话目录相同、已经恢复好）。正忙时抛 Busy。"""
        with self._mu:
            if self._busy:
                raise Busy("正在处理消息，等这一轮结束再换模型设置。")
            agent.on_delta = self._on_delta
            self.agent = agent
            self._ws_copy = None
            self._last_plan = self._plan_view()

    def close(self, timeout: float = 5) -> None:
        """请求停止，等工作线程结束。"""
        self.stop()
        t = self._thread
        if t is not None and t.is_alive():
            t.join(timeout)
