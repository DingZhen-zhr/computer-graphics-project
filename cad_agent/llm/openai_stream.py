"""OpenAI 兼容接口的流式回复：把一个个片段拼回完整的回复（文字、工具调用、用量）。

写法依据 docs/llm-api-notes.md 第 9 节末尾：开 stream_options.include_usage 后，最后一个片段的 choices 是空的、usage 是整次的用量。
思考内容（DeepSeek 的 reasoning_content）不拼进文字，也不交给界面。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from cad_agent.llm.client import ToolCall, parse_arguments


@dataclass
class _PartialCall:
    id: str = ""
    name: str = ""
    arguments: str = ""


@dataclass
class StreamAccumulator:
    texts: list[str] = field(default_factory=list)
    calls: dict[int, _PartialCall] = field(default_factory=dict)
    usage: Any = None
    saw_choice: bool = False

    def add(self, chunk: Any) -> str:
        """收下一个片段，返回其中新到的文字（没有就是空文字）。"""
        if getattr(chunk, "usage", None) is not None:
            self.usage = chunk.usage
        text = ""
        for choice in getattr(chunk, "choices", None) or []:
            self.saw_choice = True
            delta = getattr(choice, "delta", None)
            if delta is None:
                continue
            piece = getattr(delta, "content", None)
            if piece:
                text += piece
            for tc in getattr(delta, "tool_calls", None) or []:
                part = self.calls.setdefault(int(getattr(tc, "index", 0) or 0), _PartialCall())
                if getattr(tc, "id", None):
                    part.id = tc.id
                fn = getattr(tc, "function", None)
                if fn is not None:
                    if getattr(fn, "name", None):
                        part.name += fn.name
                    if getattr(fn, "arguments", None):
                        part.arguments += fn.arguments
        if text:
            self.texts.append(text)
        return text

    @property
    def content(self) -> str:
        return "".join(self.texts)

    def tool_calls(self) -> list[ToolCall]:
        return [ToolCall(p.id, p.name, parse_arguments(p.arguments)) for _, p in sorted(self.calls.items())]
