"""一轮里的计数：模型调用、用量、费用、工具调用（从 loop.py 拆出来，行为不变）。"""

from __future__ import annotations

from dataclasses import dataclass

from cad_agent.llm.client import LLMReply


@dataclass
class _Counters:
    llm_calls: int = 0
    tokens: int = 0
    tool_calls: int = 0
    stage_tool_calls: int = 0   # 分阶段时：当前阶段的工具调用次数（有阶段通过时清零）
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
