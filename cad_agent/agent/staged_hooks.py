"""主循环在分阶段时多做的事（从 loop.py 拆出来）：每阶段的工具调用计数、阶段小结折叠、stage 和 gate 日志。

旧流程（gates.staged 为假）不创建这个对象，loop.py 的行为和 1.2 版逐字相同。
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from cad_agent.agent.automation import has_error
from cad_agent.agent.context import with_warning
from cad_agent.staged import messages as msg
from cad_agent.staged.build import Advance, StageRun
from cad_agent.staged.summary import stage_summary
from cad_agent.tools import ToolOutcome

if TYPE_CHECKING:
    from cad_agent.agent.loop import Agent

TOTAL_CAP_TEXT = ("这一轮工具调用已经达到上限（{n} 次），先停下来了。需求单和现有的模型都保留着，"
                  "你可以说「继续」让我接着做，或者告诉我该怎么调整。")


class StagedHooks:
    def __init__(self, agent: "Agent") -> None:
        self.agent = agent
        self._pending: dict[str, StageRun] = {}   # 通过了、还没折叠进小结的阶段
        self._seen: Advance | None = None          # 已经处理过的那次推进
        self._clean = False                        # 最近一次 build 是不是干净地停在"下一个阶段还没写"

    @property
    def box(self):  # noqa: ANN201 - ToolBox
        return self.agent.toolbox

    def begin_turn(self) -> None:
        self._pending.clear()
        self._seen = self.box.last_advance
        self._clean = False

    def after_tool(self, name: str, outcome: ToolOutcome, c: Any) -> None:
        """每次工具调用（含程序自动 build）之后、给模型的内容加提醒之前调用。"""
        if name == "set_plan" and not has_error(outcome.content):
            c.stage_tool_calls = 0   # 规划按一个阶段算：有了计划，第一个阶段从 0 数起
        adv = self.box.last_advance
        if name != "build" or outcome.build is None or adv is None or adv is self._seen:
            return
        self._seen = adv
        runs = {sr.stage_id: sr for sr in adv.runs}
        for sid in adv.passed:
            run = runs[sid].run
            self.agent.session.log("stage", id=sid, title=self.box.ws.plan.get(sid).title, checks=len(run.checks),
                                   size=run.facts.get("size"), volume=run.facts.get("volume"))
            self._pending[sid] = runs[sid]
        if adv.passed:
            c.stage_tool_calls = 0
        if json.loads(outcome.content).get("final_gate") is not None and self.box.last_gate is not None:
            self.agent.session.log("gate", **self.box.last_gate.to_dict())
        self._clean = adv.reason == "not_ready"

    def maybe_fold(self) -> None:
        """有新通过的阶段、而且最近一次 build 停在"下一个阶段还没写"时，把本轮的工具往来折叠成阶段小结。

        最近一次 build 没通过、或者终检没过时先不折叠：那次 build 的返回里有模型接下来要改的内容。
        """
        plan = self.box.ws.plan
        if not self._pending or not self._clean or plan is None:
            return
        passed = [sid for sid in plan.ids() if sid in self._pending and plan.get(sid).passed]
        if passed:
            adv = Advance(runs=[self._pending[s] for s in passed], passed=passed, stopped=None, reason="not_ready")
            self.agent.context.fold(stage_summary(self.box.ws, adv))
        self._pending.clear()

    def warning(self, content: str, c: Any) -> str:
        left = self.agent.config.max_tool_calls_per_stage - c.stage_tool_calls
        return with_warning(content, left, msg.stage_calls_left(max(left, 0)))

    def cap_text(self, c: Any) -> str | None:
        cfg = self.agent.config
        if c.stage_tool_calls >= cfg.max_tool_calls_per_stage:
            plan = self.box.ws.plan
            cur = plan.current() if plan is not None else None
            if cur is not None:
                return msg.stage_cap_text(cur.id, cur.title, cfg.max_tool_calls_per_stage)
            return TOTAL_CAP_TEXT.format(n=cfg.max_tool_calls_per_stage)   # 规划中或终检时：没有当前阶段
        if c.tool_calls >= cfg.max_tool_calls_total:
            return TOTAL_CAP_TEXT.format(n=cfg.max_tool_calls_total)
        return None
