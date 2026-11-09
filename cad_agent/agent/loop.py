"""主循环：阶段和关卡由程序掌握，模型只做判断。

一条用户消息 = 一轮：反复调用模型和工具，直到模型不再调用工具、遇到要等用户的工具（提问、确认）、
build 全部通过（程序自动交付）、或者触发失败上限。
"""

from __future__ import annotations

import json
import re
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from cad_agent.agent.context import Context, with_warning
from cad_agent.agent.state import load_system_prompt, render_snapshot
from cad_agent.checks.spec import CheckResult
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


def _fmt(v: float | None) -> str:
    return "-" if v is None else f"{v:.4f}".rstrip("0").rstrip(".")


class Agent:
    def __init__(self, llm: LLM, toolbox: ToolBox, session: Session, config: Config) -> None:
        self.llm, self.toolbox, self.session, self.config = llm, toolbox, session, config
        self.toolbox.max_build_failures = config.max_build_failures
        self.system_prompt = load_system_prompt()
        self.context = Context(self.system_prompt)  # 发给模型的消息：旧轮折叠，本轮开头一张快照，轮内只追加
        self._pending_changes: list[str] = []  # 上次交付以来需求单的变化行

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
        self.context.start_turn(content, render_snapshot(self.ws))
        self.session.log("user", text=text, sent_as=content)

        while True:
            try:
                reply = self.llm.chat(self.context.messages(), self.toolbox.schemas())
            except LLMError as e:
                return self._end("failed", f"模型调用失败：{e}。需求单和已经写好的特征都还在，可以稍后再发一次。", c)
            c.add(reply)
            self.context.append(self._assistant_message(reply))
            self.session.log("assistant", content=reply.content, usage=reply.usage, cost=reply.cost,
                             tool_calls=[{"name": tc.name, "args": tc.arguments} for tc in reply.tool_calls])
            if not reply.tool_calls:
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
        for tc in reply.tool_calls:
            c.tool_calls += 1
            started = time.monotonic()
            outcome = self.toolbox.call(tc.name, tc.arguments)
            sent = with_warning(outcome.content, self.config.max_tool_calls - c.tool_calls)
            self.context.append({"role": "tool", "tool_call_id": tc.id, "content": sent})
            self.session.log("tool", name=tc.name, args=tc.arguments, content=sent, end_turn=outcome.end_turn,
                             deliverable=outcome.deliverable, duration_s=round(time.monotonic() - started, 3))
            ended = self._after_tool(tc, outcome, reply, c)
            if ended is not None:
                return ended  # 本轮结束时整轮都折叠掉，本次回复里后面没执行的调用不会再发给模型
        return None

    def _after_tool(self, tc: ToolCall, outcome: ToolOutcome, reply: LLMReply, c: _Counters) -> AgentTurn | None:
        if tc.name == "update_brief":  # 工具返回的 content 一定是 JSON；出错时是 {"error": ...}，没有 changes
            self._pending_changes.extend(json.loads(outcome.content).get("changes", []))
        if tc.name == "build" and outcome.build is not None:
            self._log_build(outcome)
            if outcome.deliverable:
                return self._deliver(c)
            if self.toolbox.build_failures >= self.config.max_build_failures:
                return self._end("failed", self._failure_text(outcome), c)
        if outcome.end_turn:
            lead = reply.content.strip() + "\n\n" if reply.content.strip() else ""
            if outcome.kind == "question":
                questions = tc.arguments["questions"]
                return self._end("question", lead + "\n".join(f"{i}. {q}" for i, q in enumerate(questions, 1)), c)
            return self._end("confirm", lead + self.ws.brief.render_text(), c)
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
            duration_s=round(outcome.build.duration_s, 3),
        )

    # ---------------------------------------------------------------- 失败与交付
    def _failure_text(self, outcome: ToolOutcome) -> str:
        run = outcome.build
        lines = [f"建模已经连续没通过 {self.toolbox.build_failures} 次，我先停下来，免得越改越乱。最后一次的问题："]
        if run.error:
            where = f"特征 {run.error['cell']}" if run.error.get("cell") else "不在某个具体特征里"
            lines.append(f"- {where}（{run.error['type']}）：{run.error['message']}")
        failed = [r for r in run.checks if not r.passed]
        lines += [f"- 检查 {r.id} 没通过：{r.detail}" for r in failed[:3]]
        missing = json.loads(outcome.content)["missing_coverage"]
        if missing:
            lines.append(f"- 这些你给的参数还没有对应的检查：{'、'.join(missing)}")
        lines.append("你可以告诉我怎么调整（比如换个做法、放宽某个要求），或者说「继续」让我再试。")
        return "\n".join(lines)

    def _deliver(self, c: _Counters) -> AgentTurn:
        ws = self.ws
        rendered = render_notebook(ws.brief.params, ws.features.items)
        with tempfile.TemporaryDirectory(prefix="cad-agent-out-") as tmp:
            out = Path(tmp)
            result = self.toolbox.run_job(
                rendered, ws.checks_raw, set(ws.brief.param_values()), mode="build",
                export_step=out / "model.step", render_png=out / "view.png",
                timeout_s=self.toolbox.timeout_s, secret_names=self.toolbox.secret_names,
            )
            if not result.ok or result.step_path is None or result.png_path is None:
                why = result.error["message"] if result.error else "检查没有全部通过或没有生成导出文件"
                return self._end("failed", f"检查已经通过，但交付时导出出了问题：{why}", c)
            version = self.session.new_version(
                notebook_text=rendered.text, brief=ws.brief, check_results=result.checks, changes=self._pending_changes,
                step_src=result.step_path, png_src=result.png_path,
            )
        changes, self._pending_changes = self._pending_changes, []
        return self._end("delivered", self._delivery_text(version, result.checks, changes), c, version_dir=version)

    def _delivery_text(self, version: Path, checks: list[CheckResult], changes: list[str]) -> str:
        repairs = self.toolbox.build_failures
        head = f"已交付 {version.name}" + (f"（建模中自动修复了 {repairs} 次）" if repairs else "") + "。"
        rows = ["| 检查 | 结果 | 实测 | 期望 |", "|---|---|---|---|"]
        rows += [f"| {r.id} | {'通过' if r.passed else '没通过'} | {_fmt(r.measured)} | {_fmt(r.expected)} |" for r in checks]
        lines = [head, f"检查结果（共 {len(checks)} 项，全部通过）：", *rows]
        if changes:
            lines.append("本版变化：" + "；".join(changes))
        lines += [f"截图：{version / 'view.png'}", f"STEP：{version / 'model.step'}"]
        return "\n".join(lines)

    # ---------------------------------------------------------------- 结束一轮
    def _save(self) -> None:
        ws = self.ws
        try:
            text = render_notebook(ws.brief.params, ws.features.items).text
        except NotebookError as e:
            text = f"# 当前的特征还不能拼成 notebook：{e}\n"
        self.session.save_state(ws.brief, ws.features.to_list(), ws.checks_raw, text)

    def _end(self, kind: Kind, text: str, c: _Counters, version_dir: Path | None = None) -> AgentTurn:
        self._save()
        self.context.end_turn(kind, text)
        repairs = self.toolbox.build_failures
        self.session.log(kind, text=text, llm_calls=c.llm_calls, tool_calls=c.tool_calls, tokens=c.tokens, repairs=repairs,
                         version=version_dir.name if version_dir else None, prompt_tokens=c.prompt_tokens,
                         completion_tokens=c.completion_tokens, cached_tokens=c.cached_tokens,
                         reasoning_tokens=c.reasoning_tokens, cost=c.cost)
        return AgentTurn(kind, text, version_dir, repairs=repairs, llm_calls=c.llm_calls, tokens=c.tokens,
                         prompt_tokens=c.prompt_tokens, completion_tokens=c.completion_tokens, cached_tokens=c.cached_tokens,
                         reasoning_tokens=c.reasoning_tokens, cost=c.cost)
