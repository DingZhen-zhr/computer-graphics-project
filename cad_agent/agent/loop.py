"""主循环：阶段和关卡由程序掌握，模型只做判断。

一条用户消息 = 一轮：反复调用模型和工具，直到模型不再调用工具、遇到要等用户的工具（提问、确认）、
build 全部通过（程序自动交付）、或者触发失败上限。
确定的步骤由程序代模型去做（automation.py 里是判定）：需求单整理完自动请确认、只改参数数值时自动重建、
同一次回复里前面出错就跳过后面的 build。
"""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Callable

from cad_agent.agent.automation import (AUTO_BUILD_NOTE, AUTO_BUILD_PREFIX, SKIPPED_BUILD_MESSAGE, brief_shape, has_error,
                                        should_auto_build, should_auto_confirm, should_build_before_reply, staged_build_ready)
from cad_agent.agent.context import Context, with_warning
from cad_agent.agent.counters import _Counters
from cad_agent.agent.delivery import delivery_text, export_version, failure_text
from cad_agent.agent.staged_hooks import StagedHooks
from cad_agent.cases import Case, pick_cases, render_cases
from cad_agent.agent.state import load_system_prompt, render_snapshot
from cad_agent.config import Config
from cad_agent.agent.turn import (AFFIRMATIVE, CONFIRMED_MESSAGE, STOPPED_TEXT, AgentTurn, Kind, _raw_arguments,  # noqa: F401
                                  is_affirmative)
from cad_agent.llm.client import LLM, LLMError, LLMReply, LLMStopped, ToolCall
from cad_agent.notebook import NotebookError, render_notebook
from cad_agent.session import Session
from cad_agent.tools import ToolBox, ToolOutcome, Workspace


class Agent:
    def __init__(self, llm: LLM, toolbox: ToolBox, session: Session, config: Config, modeling_llm: LLM | None = None, *,
                 cases: list[Case] | None = None) -> None:
        self.llm, self.toolbox, self.session, self.config = llm, toolbox, session, config
        self.cases = list(cases or [])   # 案例库（分阶段且开关 cases 打开时，规划那一轮挑相似的给模型）
        self.case_problems: list[str] = []   # 读案例库时跳过的案例和原因（由组装智能体的地方填，写进启动日志）
        self.modeling_llm = modeling_llm  # 建模阶段（需求单已确认）用的模型；没有就一直用 llm
        self.toolbox.max_build_failures = config.max_build_failures
        self.staged = toolbox.gates.staged
        self.hooks = StagedHooks(self) if self.staged else None   # 旧流程没有它，行为和 1.2 版逐字相同
        if self.staged:
            self.toolbox.stage_dir = session.dir / "stages"
        self.system_prompt = load_system_prompt(self.staged)
        self.context = Context(self.system_prompt)  # 发给模型的消息：旧轮折叠，本轮开头一张快照，轮内只追加
        self._pending_changes: list[str] = []  # 上次交付以来需求单的变化行
        self._auto_builds = 0                  # 程序自动重建的次数，给日志里的 id 编号
        self.on_delta: Callable[[str], None] | None = None   # 界面设置；有文字片段时调用（设了才用流式请求）
        self._stop = threading.Event()         # 用户要求停止；每轮开始时清掉
        self.toolbox.should_stop = self._stop.is_set   # 沙盒运行中也能停

    def request_stop(self) -> None:
        """线程安全：置停止标志。主循环在每次模型调用、每个片段、每次工具调用之前检查，沙盒子进程会被结束。"""
        self._stop.set()

    @property
    def ws(self) -> Workspace:
        return self.toolbox.ws

    # ---------------------------------------------------------------- 一轮
    def handle_user(self, text: str) -> AgentTurn:
        self._stop.clear()
        self.toolbox.begin_turn()
        c = _Counters()
        content = text
        if self.ws.awaiting_confirmation:
            if is_affirmative(text) and not self.ws.brief.open_questions:
                self.ws.brief.confirmed = True
                content = CONFIRMED_MESSAGE
            self.ws.awaiting_confirmation = False  # 无论用户怎么回，都不再等确认
        # 阶段在一轮开始、处理完确认之后决定，这一轮内不换模型（换了缓存就断了）
        phase = "modeling" if self.ws.brief.can_build()[0] else "clarify"
        llm = self.modeling_llm if phase == "modeling" and self.modeling_llm is not None else self.llm
        self.context.start_turn(content, self._snapshot())
        if self.hooks is not None:
            self.hooks.begin_turn()
        self.session.log("user", text=text, sent_as=content, phase=phase)
        built_before_reply = False  # 纯文字结束前的兜底 build，每轮最多一次

        while True:
            if self._stop.is_set():
                return self._end("stopped", STOPPED_TEXT, c)
            try:
                reply = self._chat(llm)
            except LLMStopped:
                return self._end("stopped", STOPPED_TEXT, c)   # 这条没说完的回复不进历史
            except LLMError as e:
                return self._end("failed", f"模型调用失败：{e}。需求单和已经写好的特征都还在，可以稍后再发一次。", c)
            c.add(reply)
            self.context.append(self._assistant_message(reply))
            self.session.log("assistant", content=reply.content, usage=reply.usage, cost=reply.cost,
                             tool_calls=[{"name": tc.name, "args": tc.arguments} for tc in reply.tool_calls])
            if not reply.tool_calls:
                if should_build_before_reply(self.ws, self.toolbox.unbuilt_edits, built_before_reply) and (
                        not self.staged or staged_build_ready(self.ws)):
                    built_before_reply = True
                    ended = self._auto_build(reply, c, "turn_end")
                    if ended is not None:
                        return ended
                    continue
                return self._end("reply", reply.content.strip() or "（模型没有给出回复，可以换个说法再试一次）", c)
            ended = self._run_tools(reply, c)
            if ended is not None:
                return ended

    def _chat(self, llm: LLM) -> LLMReply:
        """调用模型。界面设了 on_delta 时用流式并带上停止检查；没设时调用方式和以前逐字相同。"""
        if self.on_delta is None:
            return llm.chat(self.context.messages(), self.toolbox.schemas())
        return llm.chat(self.context.messages(), self.toolbox.schemas(), on_delta=self.on_delta, should_stop=self._stop.is_set)

    def _snapshot(self) -> str:
        """本轮的快照。分阶段、开着案例库、需求单可以建模但还没有计划时，后面接上相似的参考案例。"""
        snap = render_snapshot(self.ws, self.staged)
        if self.staged and self.toolbox.gates.cases and self.ws.brief.can_build()[0] and self.ws.plan is None:
            picked = pick_cases(self.ws.brief, self.cases)
            if picked:
                self.session.log("cases", ids=[c.id for c in picked])
                snap += "\n\n" + render_cases(picked)
        return snap

    @staticmethod
    def _assistant_message(reply: LLMReply) -> dict:
        msg: dict = {"role": "assistant", "content": reply.content}
        if reply.tool_calls:
            msg["tool_calls"] = [
                {"id": tc.id, "type": "function", "function": {"name": tc.name, "arguments": _raw_arguments(tc)}}
                for tc in reply.tool_calls
            ]
        return msg

    # ---------------------------------------------------------------- 工具
    def _run_tools(self, reply: LLMReply, c: _Counters) -> AgentTurn | None:
        before = brief_shape(self.ws.brief)
        calls: list[tuple[str, bool]] = []
        errored = False
        for tc in reply.tool_calls:
            if self._stop.is_set():   # 停止：后面的调用不执行，已经执行的效果保留
                return self._end("stopped", STOPPED_TEXT, c)
            c.tool_calls += 1
            c.stage_tool_calls += 1
            started = time.monotonic()
            skipped = tc.name == "build" and errored  # C3：同一次回复里前面的调用出错了，这个 build 不运行
            outcome = ToolOutcome(SKIPPED_BUILD_MESSAGE) if skipped else self.toolbox.call(tc.name, tc.arguments)
            ok = not has_error(outcome.content)
            errored = errored or not ok
            calls.append((tc.name, ok))
            sent = self._warn(tc.name, outcome, c)
            self.context.append({"role": "tool", "tool_call_id": tc.id, "content": sent})
            extra = {"skipped": True} if skipped else {}
            self.session.log("tool", name=tc.name, args=tc.arguments, content=sent, end_turn=outcome.end_turn,
                             deliverable=outcome.deliverable, duration_s=round(time.monotonic() - started, 3), **extra)
            ended = self._after_tool(tc, outcome, reply, c)
            if ended is not None:
                return ended  # 本轮结束时整轮都折叠掉，本次回复里后面没执行的调用不会再发给模型
        return self._after_reply(reply, calls, before, c)

    def _after_reply(self, reply: LLMReply, calls: list[tuple[str, bool]], before, c: _Counters) -> AgentTurn | None:
        """一次回复里的工具全部执行完、本轮还没结束时：程序代模型按按钮（C1 自动请确认、C2 自动重建）。"""
        if self.hooks is not None:
            self.hooks.maybe_fold()
        if should_auto_confirm(self.ws, calls):
            outcome = self.toolbox.call("request_confirmation", {})
            if not has_error(outcome.content):
                self.session.log("auto", action="request_confirmation")
                lead = reply.content.strip() + "\n\n" if reply.content.strip() else ""
                return self._end("confirm", lead + self.ws.brief.render_text(), c, extra=self._confirm_extra(reply))
        elif should_auto_build(self.ws, calls, before):
            return self._auto_build(reply, c, "param_change")
        return None

    def _auto_build(self, reply: LLMReply, c: _Counters, reason: str) -> AgentTurn | None:
        """程序替模型 build 一次；之后和模型自己调用 build 完全一样处理。

        reason：param_change（C2，只改了已有参数的数值）或 turn_end（模型用纯文字结束一轮，但还有没 build 的改动）。
        """
        self._auto_builds += 1
        call_id = f"{AUTO_BUILD_PREFIX}{self._auto_builds}"
        self.session.log("auto", action="build", id=call_id, reason=reason)
        c.tool_calls += 1
        c.stage_tool_calls += 1
        started = time.monotonic()
        outcome = self.toolbox.call("build", {})
        sent = self._warn("build", outcome, c)
        # 服务端不接受程序补的 tool_call（偏离 D6），所以结果用一条 user 消息交给模型
        self.context.append({"role": "user", "content": AUTO_BUILD_NOTE + "\n" + sent})
        self.session.log("tool", name="build", args={}, content=sent, end_turn=False, deliverable=outcome.deliverable,
                         duration_s=round(time.monotonic() - started, 3), auto=True)
        ended = self._after_tool(ToolCall(call_id, "build", {}), outcome, reply, c)
        if ended is None and self.hooks is not None:
            self.hooks.maybe_fold()
        return ended

    def _warn(self, name: str, outcome: ToolOutcome, c: _Counters) -> str:
        """给模型看的工具返回：剩余次数不多时加提醒（分阶段时按阶段算，先让 hooks 处理阶段通过、计数清零）。"""
        if self.hooks is None:
            return with_warning(outcome.content, self.config.max_tool_calls - c.tool_calls)
        self.hooks.after_tool(name, outcome, c)
        return self.hooks.warning(outcome.content, c)

    def _after_tool(self, tc: ToolCall, outcome: ToolOutcome, reply: LLMReply, c: _Counters) -> AgentTurn | None:
        if tc.name == "update_brief":  # 工具返回的 content 一定是 JSON；出错时是 {"error": ...}，没有 changes
            self._pending_changes.extend(json.loads(outcome.content).get("changes", []))
        if tc.name == "build" and outcome.build is not None:
            self._log_build(outcome)
            if outcome.deliverable:
                return self._deliver(c)
            if self.toolbox.build_failures >= self.config.max_build_failures:
                return self._end("failed", failure_text(self.toolbox, outcome), c)
        if outcome.end_turn:
            lead = reply.content.strip() + "\n\n" if reply.content.strip() else ""
            if outcome.kind == "question":
                questions = tc.arguments["questions"]
                return self._end("question", lead + "\n".join(f"{i}. {q}" for i, q in enumerate(questions, 1)), c,
                                 extra={"lead": reply.content.strip(), "questions": list(questions)})
            return self._end("confirm", lead + self.ws.brief.render_text(), c, extra=self._confirm_extra(reply))
        if self.hooks is not None:
            cap = self.hooks.cap_text(c)
            return self._end("failed", cap, c) if cap is not None else None
        if c.tool_calls >= self.config.max_tool_calls:
            return self._end(
                "failed",
                f"这一轮工具调用已经达到上限（{self.config.max_tool_calls} 次），先停下来了。需求单和现有的模型都保留着，"
                "你可以说「继续」让我接着做，或者告诉我该怎么调整。",
                c,
            )
        return None

    def _log_build(self, outcome: ToolOutcome) -> None:
        body = json.loads(outcome.content)
        self.session.log(
            "build", passed=body["passed"], error=body["error"], failed_checks=[f["id"] for f in body["failed_checks"]],
            missing_coverage=body["missing_coverage"], failures=self.toolbox.build_failures,
            passed_checks=body["passed_checks"], total_checks=body["passed_checks"] + len(body["failed_checks"]),  # 网页进度条用
            duration_s=round(outcome.build.duration_s, 3),
            **({k: body[k] for k in ("stage", "stages_passed")} if "stages_passed" in body else {}),
        )

    # ---------------------------------------------------------------- 交付
    def _deliver(self, c: _Counters) -> AgentTurn:
        gate = self.toolbox.last_gate if self.staged else None
        extra = {"extra_json": {"gate": gate.to_dict(), "plan": self.ws.plan.to_list()},
                 "stages_src": self.toolbox.stage_dir} if gate is not None else {}
        exported = export_version(self.toolbox, self.session, self._pending_changes, **extra)
        if isinstance(exported, str):
            return self._end("failed", exported, c)
        version, checks = exported
        changes, self._pending_changes = self._pending_changes, []
        text = delivery_text(version, checks, changes, self.toolbox.build_failures, gate=gate)
        extra = {"passed": sum(1 for r in checks if r.passed), "total": len(checks), "changes": changes}
        return self._end("delivered", text, c, version_dir=version, extra=extra)

    # ---------------------------------------------------------------- 结束一轮
    def _save(self) -> None:
        ws = self.ws
        try:
            text = render_notebook(ws.brief.params, ws.features.items).text
        except NotebookError as e:
            text = f"# 当前的特征还不能拼成 notebook：{e}\n"
        self.session.save_state(ws.brief, ws.features.to_list(), ws.checks_raw, text,
                                plan=ws.plan.to_list() if ws.plan is not None else None)

    def _confirm_extra(self, reply: LLMReply) -> dict:
        return {"lead": reply.content.strip(), "brief": self.ws.brief.to_dict()}

    def _end(self, kind: Kind, text: str, c: _Counters, version_dir: Path | None = None, extra: dict | None = None) -> AgentTurn:
        """结束一轮。extra 是给网页和回放用的结构化内容（问题列表、需求单、检查通过数），一起写进日志。"""
        self._save()
        self.context.end_turn(kind, text)
        repairs = self.toolbox.build_failures
        self.session.log(kind, text=text, llm_calls=c.llm_calls, tool_calls=c.tool_calls, tokens=c.tokens, repairs=repairs,
                         version=version_dir.name if version_dir else None, prompt_tokens=c.prompt_tokens,
                         completion_tokens=c.completion_tokens, cached_tokens=c.cached_tokens,
                         reasoning_tokens=c.reasoning_tokens, cost=c.cost, **(extra or {}))
        return AgentTurn(kind, text, version_dir, repairs=repairs, llm_calls=c.llm_calls, tokens=c.tokens,
                         prompt_tokens=c.prompt_tokens, completion_tokens=c.completion_tokens, cached_tokens=c.cached_tokens,
                         reasoning_tokens=c.reasoning_tokens, cost=c.cost)
