"""按脚本回复的假模型，单元测试用，不花钱。"""

from __future__ import annotations

import copy

from cad_agent.llm.client import LLMReply, ToolCall


def scripted_call(name: str, args: dict | None = None, content: str = "", *more: tuple[str, dict]) -> LLMReply:
    """造一条带工具调用的回复；more 里可以再追加几个 (工具名, 参数)，模拟一次回复里调用多个工具。"""
    calls = [ToolCall("call_1", name, args or {})]
    for i, (n, a) in enumerate(more, 2):
        calls.append(ToolCall(f"call_{i}", n, a))
    return LLMReply(content=content, tool_calls=calls, usage={"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0})


class ScriptedLLM:
    """按顺序返回预先写好的回复；脚本里放异常对象时，轮到它就抛出。

    calls 记录每次收到的 messages（拷贝，之后对原列表的改动不会影响记录）。
    """

    def __init__(self, replies: list[LLMReply | Exception]) -> None:
        self.replies = list(replies)
        self.calls: list[list[dict]] = []
        self.tool_lists: list[list[dict]] = []

    def chat(self, messages: list[dict], tools: list[dict]) -> LLMReply:
        self.calls.append(copy.deepcopy(messages))
        self.tool_lists.append(copy.deepcopy(tools))
        if not self.replies:
            raise AssertionError(f"ScriptedLLM 的脚本已用完，但第 {len(self.calls)} 次又被调用了")
        nxt = self.replies.pop(0)
        if isinstance(nxt, Exception):
            raise nxt
        return nxt
