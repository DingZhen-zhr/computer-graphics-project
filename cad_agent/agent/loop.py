"""主循环：阶段和关卡由程序掌握，模型只做判断。

一条用户消息 = 一轮：反复调用模型和工具，直到模型不再调用工具、遇到要等用户的工具（提问、确认）、
build 全部通过（程序自动交付）、或者触发失败上限。
确定的步骤由程序代模型去做（automation.py 里是判定）：需求单整理完自动请确认、只改参数数值时自动重建、
同一次回复里前面出错就跳过后面的 build。
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from cad_agent.agent.automation import (AUTO_BUILD_NOTE, AUTO_BUILD_PREFIX, SKIPPED_BUILD_MESSAGE, brief_shape, has_error,
                                        should_auto_build, should_auto_confirm, should_build_before_reply)
from cad_agent.agent.context import Context, with_warning
from cad_agent.agent.delivery import delivery_text, export_version, failure_text
from cad_agent.agent.state import load_system_prompt, render_snapshot
from cad_agent.config import Config
from cad_agent.llm.client import LLM, LLMError, LLMReply, ToolCall
from cad_agent.notebook import NotebookError, render_notebook
from cad_agent.session import Session
from cad_agent.tools import ToolBox, ToolOutcome, Workspace

Kind = Literal["reply", "question", "confirm", "delivered", "failed"]
AFFIRMATIVE = {"y", "yes", "ok", "确认", "可以", "没问题", "好", "对", "行"}
_EDGE_PUNCT = re.compile(r"^[\W_]+|[\W_]+$")
CONFIRMED_MESSAGE = "（用户已确认需求单）"


def is_affirmative(text: str) -> bool:
    """去掉首尾空白和标点后，整句必须恰好在 AFFIRMATIVE 里；“可以，但角度改成 70”不算。"""
    return _EDGE_PUNCT.sub("", text.strip()).lower() in AFFIRMATIVE


@dataclass
class AgentTurn:
    kind: Kind
    text: str
    version_dir: Path | None = None
    repairs: int = 0
    llm_calls: int = 0
    tokens: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cached_tokens: int = 0
    reasoning_tokens: int = 0
    cost: float | None = None   # 本轮每次调用都有 cost 时才是总和，否则 None（本轮没有成功的调用也是 None）


@dataclass
class _Counters:
    llm_calls: int = 0
    tokens: int = 0
    tool_calls: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cached_tokens: int = 0
    reasoning_tokens: int = 0
    cost_sum: float = 0.0
    costed_calls: int = 0

    def add(self, reply: LLMReply) -> None:
        """记下一次成功调用的用量和费用。"""
        self.llm_calls += 1
        u = reply.usage
        self.tokens += int(u.get("total_tokens", 0) or 0)
        self.prompt_tokens += int(u.get("prompt_tokens", 0) or 0)
        self.completion_tokens += int(u.get("completion_tokens", 0) or 0)
        self.cached_tokens += int(u.get("cached_tokens", 0) or 0)
        self.reasoning_tokens += int(u.get("reasoning_tokens", 0) or 0)
        if reply.cost is not None:
            self.cost_sum += reply.cost
            self.costed_calls += 1

    @property
    def cost(self) -> float | None:
        return self.cost_sum if self.llm_calls and self.costed_calls == self.llm_calls else None


def _raw_arguments(tc: ToolCall) -> str:
    """放回对话历史里的参数文本：解析失败的保留模型原文，其余重新序列化。"""
    if set(tc.arguments) == {"__raw__"}:
        return str(tc.arguments["__raw__"])
    return json.dumps(tc.arguments, ensure_ascii=False)


class Agent:
    def __init__(self, llm: LLM, toolbox: ToolBox, session: Session, config: Config, modeling_llm: LLM | None = None) -> None:
        self.llm, self.toolbox, self.session, self.config = llm, toolbox, session, config
        self.modeling_llm = modeling_llm  # 建模阶段（需求单已确认）用的模型；没有就一直用 llm
        self.toolbox.max_build_failures = config.max_build_failures
        self.system_prompt = load_system_prompt()
        self.context = Context(self.system_prompt)  # 发给模型的消息：旧轮折叠，本轮开头一张快照，轮内只追加
        self._pending_changes: list[str] = []  # 上次交付以来需求单的变化行
        self._auto_builds = 0                  # 程序自动重建的次数，给日志里的 id 编号

    @property
    def ws(self) -> Workspace:
        return self.toolbox.ws

    # ---------------------------------------------------------------- 一轮
    def handle_user(self, text: str) -> AgentTurn:
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
        self.context.start_turn(content, render_snapshot(self.ws))
        self.session.log("user", text=text, sent_as=content, phase=phase)
        built_before_reply = False  # 纯文字结束前的兜底 build，每轮最多一次

        while True:
            try:
                reply = llm.chat(self.context.messages(), self.toolbox.schemas())
            except LLMError as e:
                return self._end("failed", f"模型调用失败：{e}。需求单和已经写好的特征都还在，可以稍后再发一次。", c)
            c.add(reply)
            self.context.append(self._assistant_message(reply))
            self.session.log("assistant", content=reply.content, usage=reply.usage, cost=reply.cost,
                             tool_calls=[{"name": tc.name, "args": tc.arguments} for tc in reply.tool_calls])
            if not reply.tool_calls:
                if should_build_before_reply(self.ws, self.toolbox.unbuilt_edits, built_before_reply):
                    built_before_reply = True
                    ended = self._auto_build(reply, c, "turn_end")
                    if ended is not None:
                        return ended
                    continue
                return self._end("reply", reply.content.strip() or "（模型没有给出回复，可以换个说法再试一次）", c)
            ended = self._run_tools(reply, c)
            if ended is not None:
                return ended

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
            c.tool_calls += 1
            started = time.monotonic()
            skipped = tc.name == "build" and errored  # C3：同一次回复里前面的调用出错了，这个 build 不运行
            outcome = ToolOutcome(SKIPPED_BUILD_MESSAGE) if skipped else self.toolbox.call(tc.name, tc.arguments)
            ok = not has_error(outcome.content)
            errored = errored or not ok
            calls.append((tc.name, ok))
            sent = with_warning(outcome.content, self.config.max_tool_calls - c.tool_calls)
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
        started = time.monotonic()
        outcome = self.toolbox.call("build", {})
        sent = with_warning(outcome.content, self.config.max_tool_calls - c.tool_calls)
        # 服务端不接受程序补的 tool_call（偏离 D6），所以结果用一条 user 消息交给模型
        self.context.append({"role": "user", "content": AUTO_BUILD_NOTE + "\n" + sent})
        self.session.log("tool", name="build", args={}, content=sent, end_turn=False, deliverable=outcome.deliverable,
                         duration_s=round(time.monotonic() - started, 3), auto=True)
        return self._after_tool(ToolCall(call_id, "build", {}), outcome, reply, c)

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
        )

    # ---------------------------------------------------------------- 交付
    def _deliver(self, c: _Counters) -> AgentTurn:
        exported = export_version(self.toolbox, self.session, self._pending_changes)
        if isinstance(exported, str):
            return self._end("failed", exported, c)
        version, checks = exported
        changes, self._pending_changes = self._pending_changes, []
        text = delivery_text(version, checks, changes, self.toolbox.build_failures)
        extra = {"passed": sum(1 for r in checks if r.passed), "total": len(checks), "changes": changes}
        return self._end("delivered", text, c, version_dir=version, extra=extra)

    # ---------------------------------------------------------------- 结束一轮
    def _save(self) -> None:
        ws = self.ws
        try:
            text = render_notebook(ws.brief.params, ws.features.items).text
        except NotebookError as e:
            text = f"# 当前的特征还不能拼成 notebook：{e}\n"
        self.session.save_state(ws.brief, ws.features.to_list(), ws.checks_raw, text)

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
