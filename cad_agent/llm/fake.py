"""按脚本回复的假模型，单元测试用，不花钱。"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Callable

from cad_agent.llm.client import LLMReply, LLMStopped, ToolCall

DELTA_CHARS = 4  # 有 on_delta 时，回复的文字按每 4 个字符一段送出


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

    def chat(self, messages: list[dict], tools: list[dict], *,
             on_delta: Callable[[str], None] | None = None,
             should_stop: Callable[[], bool] | None = None) -> LLMReply:
        self.calls.append(copy.deepcopy(messages))
        self.tool_lists.append(copy.deepcopy(tools))
        if not self.replies:
            raise AssertionError(f"ScriptedLLM 的脚本已用完，但第 {len(self.calls)} 次又被调用了")
        nxt = self.replies.pop(0)
        if isinstance(nxt, Exception):
            raise nxt
        if on_delta is not None:
            for i in range(0, len(nxt.content), DELTA_CHARS):
                if should_stop is not None and should_stop():
                    raise LLMStopped()
                on_delta(nxt.content[i:i + DELTA_CHARS])
        if should_stop is not None and should_stop():
            raise LLMStopped()
        return nxt


def load_script(path: Path) -> list[LLMReply]:
    """读假模型剧本（开发和走查用）：JSON 数组，每项 {"content": "...", "tool_calls": [{"name", "args"}]}。

    写得不对时抛 ValueError（中文，带第几项）。工具调用的 id 按 call_1、call_2…编号。
    """
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError("剧本应该是一个 JSON 数组，每一项是模型的一次回复")
    replies: list[LLMReply] = []
    for i, item in enumerate(raw, 1):
        if not isinstance(item, dict) or not isinstance(item.get("content", ""), str):
            raise ValueError(f"剧本第 {i} 项应该是对象，content 是文字")
        calls = []
        for j, tc in enumerate(item.get("tool_calls") or [], 1):
            if not isinstance(tc, dict) or not isinstance(tc.get("name"), str) or not isinstance(tc.get("args", {}), dict):
                raise ValueError(f"剧本第 {i} 项的第 {j} 个工具调用要有 name（文字）和 args（对象）")
            calls.append(ToolCall(f"call_{j}", tc["name"], tc.get("args", {})))
        replies.append(LLMReply(item.get("content", ""), calls, {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}))
    return replies
