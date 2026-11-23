"""一轮的结果：结局种类、给用户看的文字、用量。从 loop.py 拆出来，名字仍可从 cad_agent.agent.loop 导入。"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from cad_agent.llm.client import LLMReply, ToolCall

Kind = Literal["reply", "question", "confirm", "delivered", "failed", "stopped"]
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


def _raw_arguments(tc: ToolCall) -> str:
    """放回对话历史里的参数文本：解析失败的保留模型原文，其余重新序列化。"""
    if set(tc.arguments) == {"__raw__"}:
        return str(tc.arguments["__raw__"])
    return json.dumps(tc.arguments, ensure_ascii=False)


def assistant_message(reply: LLMReply) -> dict:
    """放回对话历史里的 assistant 消息（带工具调用）。"""
    msg: dict = {"role": "assistant", "content": reply.content}
    if reply.tool_calls:
        msg["tool_calls"] = [
            {"id": tc.id, "type": "function", "function": {"name": tc.name, "arguments": _raw_arguments(tc)}}
            for tc in reply.tool_calls
        ]
    return msg


STOPPED_TEXT = "已停止。已经写下的内容都保留着，可以接着说。"
