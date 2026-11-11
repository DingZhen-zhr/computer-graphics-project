"""交付前的看图审查这一步（计划 2 Task 6）：渲染四视图 → 独立的审查调用 → 决定交付还是退回建模模型。

只在分阶段流程里用；旧流程不经过这里，行为和 1.2 版逐字相同。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from cad_agent.agent.counters import _Counters
from cad_agent.agent.delivery import delivery_text, export_version
from cad_agent.llm.client import LLMError
from cad_agent.notebook import render_notebook
from cad_agent.review import MAX_REVIEW_ROUNDS, ReviewResult, objection_note, run_review
from cad_agent.staged.select import final_checks

if TYPE_CHECKING:
    from cad_agent.agent.loop import Agent
    from cad_agent.agent.turn import AgentTurn


@dataclass
class ReviewDecision:
    action: Literal["deliver", "back"]
    review: ReviewResult | None = None
    skipped: str | None = None    # 没做审查的原因（SKIP_REASONS 之一）
    rounds: int = 0

    def version_json(self) -> dict:
        """写进版本目录的 review.json。"""
        if self.review is None:
            return {"skipped": self.skipped}
        return {**self.review.to_dict(), "passed": self.review.passed, "rounds": self.rounds}


class ReviewStep:
    def __init__(self, agent: "Agent") -> None:
        self.agent = agent
        self.rounds = 0      # 本次交付已经审查了几轮；每次交付之后、每条新的用户消息开始时清零
        self._renders = 0    # 本会话一共渲染过几次，图片目录 review/round-<n> 用它编号，免得覆盖以前的

    def reset(self) -> None:
        self.rounds = 0

    def before_delivery(self, c: _Counters) -> ReviewDecision:
        a = self.agent
        if not a.toolbox.gates.visual_review:
            return ReviewDecision("deliver", skipped="已关闭")
        if a.review_llm is None:
            return ReviewDecision("deliver", skipped="模型不能识图")
        self.rounds += 1
        views = self._render()
        if not views:
            a.session.log("review_skipped", round=self.rounds, reason="没有渲染出图片")
            return ReviewDecision("deliver", skipped="没有渲染出图片", rounds=self.rounds)
        try:
            result, reply = run_review(a.review_llm, a.ws.brief, views)
        except LLMError as e:   # LLMError 的信息里不含 key
            a.session.log("review_error", round=self.rounds, message=str(e))
            return ReviewDecision("deliver", skipped="审查调用失败", rounds=self.rounds)
        c.add(reply)
        a.session.log("review", round=self.rounds, passed=result.passed, usage=reply.usage, cost=reply.cost, **result.to_dict())
        if result.passed or self.rounds >= MAX_REVIEW_ROUNDS:
            return ReviewDecision("deliver", review=result, rounds=self.rounds)
        return ReviewDecision("back", review=result, rounds=self.rounds)

    def _render(self) -> dict:
        a, box = self.agent, self.agent.toolbox
        ws = box.ws
        self._renders += 1
        out = a.session.dir / "review" / f"round-{self._renders}"
        rendered = render_notebook(ws.brief.params, ws.features.items)
        run = box.run_job(rendered, final_checks(ws), set(ws.brief.param_values()), mode="build", render_views=out,
                          timeout_s=box.timeout_s, secret_names=box.secret_names)
        if run.view_errors:
            a.session.log("review_render", round=self.rounds, errors=run.view_errors)
        return dict(run.view_paths) if run.ok else {}


def review_failure_text(review: ReviewResult) -> str:
    """审查退回后正好到了失败上限：给用户看的文字。"""
    lines = ["建模的检查都通过了，但看图审查认为下面这些地方和需求单不一致，已经到了失败次数的上限，我先停下来："]
    lines += [f"- {i.target}：{i.reason}" for i in review.objections]
    lines.append("你可以自己看一下模型，告诉我哪里要改；如果你觉得模型是对的，说「继续」我会再试一次。")
    return "\n".join(lines)


def review_then_deliver(agent: "Agent", c: _Counters) -> "AgentTurn | None":
    """分阶段：交付前先看图审查。退回时返回 None（本轮继续，意见等这次回复的工具都执行完再放进上下文）。"""
    decision = agent.review_step.before_delivery(c)
    if decision.action == "back":
        agent._review_note = objection_note(decision.review)
        agent.toolbox.build_failures += 1
        if agent.toolbox.build_failures >= agent.config.max_build_failures:
            return agent._end("failed", review_failure_text(decision.review), c)
        return None
    return deliver(agent, c, decision)


def deliver(agent: "Agent", c: _Counters, decision: ReviewDecision | None = None) -> "AgentTurn":
    """导出新版本并结束本轮（从 loop.py 搬过来；decision 是 None 时——旧流程——和以前逐字相同）。"""
    gate = agent.toolbox.last_gate if agent.staged else None
    extra = {"extra_json": {"gate": gate.to_dict(), "plan": agent.ws.plan.to_list()},
             "stages_src": agent.toolbox.stage_dir} if gate is not None else {}
    if decision is not None and extra:
        extra["extra_json"]["review"] = decision.version_json()
    exported = export_version(agent.toolbox, agent.session, agent._pending_changes, **extra)
    if isinstance(exported, str):
        return agent._end("failed", exported, c)
    version, checks = exported
    changes, agent._pending_changes = agent._pending_changes, []
    agent.review_step.reset()
    shown = decision is not None and decision.skipped != "已关闭"   # 关掉开关时交付文字和以前一样
    text = delivery_text(version, checks, changes, agent.toolbox.build_failures, gate=gate,
                         review=decision.review if shown else None, review_skipped=decision.skipped if shown else None)
    extra = {"passed": sum(1 for r in checks if r.passed), "total": len(checks), "changes": changes}
    return agent._end("delivered", text, c, version_dir=version, extra=extra)
