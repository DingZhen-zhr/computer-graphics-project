"""内部消息（OpenAI 写法）→ Claude 接口的消息和工具定义。字段名以 docs/llm-api-notes.md 第 8 节为准（查文档，未用真实接口验证）。

规则（计划 2 Task 4）：
- 所有 system 消息按顺序用空行连起来，作为系统提示词。
- assistant：有文字就是一个文字块；每个 tool_call 是一个 tool_use 块，参数从 JSON 文字还原成对象（还原不了放进 {"__raw__": 原文}）。
- tool 消息变成 user 消息里的 tool_result 块；连续的几条合并进同一条 user 消息，紧跟其后的 user 消息也并进去。
- 其他连续的同角色消息合并成一条（这个接口要求 user 和 assistant 交替）。
- 图片（内部写法 {"type": "image_url", "image_url": {"url": "data:image/png;base64,…"}}）转成 image 块。
"""

from __future__ import annotations

import re
from typing import Any

from cad_agent.llm.client import parse_arguments

_DATA_URL = re.compile(r"^data:(image/[a-z0-9.+-]+);base64,(.*)$", re.IGNORECASE | re.DOTALL)
EMPTY_ASSISTANT = "…"   # 接口不接受空的 assistant 消息；旧轮折叠后万一没有文字，用它占位


def _image_block(part: dict) -> dict:
    url = str((part.get("image_url") or {}).get("url", ""))
    m = _DATA_URL.match(url)
    if m:
        return {"type": "image", "source": {"type": "base64", "media_type": m.group(1).lower(), "data": m.group(2)}}
    return {"type": "image", "source": {"type": "url", "url": url}}


def _content_blocks(content: Any) -> list[dict]:
    """user 消息的内容：文字，或由 text、image_url 组成的数组。空文字不产生块。"""
    if content is None:
        return []
    if isinstance(content, str):
        return [{"type": "text", "text": content}] if content else []
    blocks: list[dict] = []
    for part in content:
        kind = part.get("type") if isinstance(part, dict) else None
        if kind == "text" and part.get("text"):
            blocks.append({"type": "text", "text": part["text"]})
        elif kind == "image_url":
            blocks.append(_image_block(part))
    return blocks


def _assistant_blocks(msg: dict) -> list[dict]:
    blocks = _content_blocks(msg.get("content"))
    for tc in msg.get("tool_calls") or []:
        fn = tc.get("function") or {}
        blocks.append({"type": "tool_use", "id": tc.get("id", ""), "name": fn.get("name", ""),
                       "input": parse_arguments(fn.get("arguments"))})
    return blocks


def to_anthropic_messages(messages: list[dict]) -> tuple[str, list[dict]]:
    """返回（系统提示词, 消息列表）。消息的 content 一律是块数组。"""
    system_parts: list[str] = []
    out: list[dict] = []
    for msg in messages:
        role = msg.get("role")
        if role == "system":
            system_parts.append(str(msg.get("content") or ""))
            continue
        if role == "tool":
            role_out = "user"
            blocks = [{"type": "tool_result", "tool_use_id": msg.get("tool_call_id", ""), "content": str(msg.get("content") or "")}]
        elif role == "assistant":
            role_out, blocks = "assistant", _assistant_blocks(msg)
        else:
            role_out, blocks = "user", _content_blocks(msg.get("content"))
        if out and out[-1]["role"] == role_out:
            out[-1]["content"].extend(blocks)
        else:
            out.append({"role": role_out, "content": blocks})
    for m in out:
        if not m["content"]:
            m["content"] = [{"type": "text", "text": EMPTY_ASSISTANT}]
    return "\n\n".join(system_parts), out


def to_anthropic_tools(tools: list[dict]) -> list[dict]:
    """OpenAI 写法的工具定义 → {"name", "description", "input_schema"}；名字、说明、参数格式原样带过去。"""
    out = []
    for t in tools:
        fn = t.get("function", t)
        out.append({"name": fn["name"], "description": fn.get("description", ""),
                    "input_schema": fn.get("parameters") or {"type": "object", "properties": {}}})
    return out


def add_cache_markers(system: str, messages: list[dict]) -> list[dict] | None:
    """缓存标记加在两处：系统提示词的末尾；本轮快照所在的那条 user 消息的末尾。

    本轮快照 = 最后一条不含工具结果的 user 消息（旧轮折叠后在它前面，本轮的工具往来在它后面）。
    返回 system 参数（带标记的文字块数组；没有系统提示词时是 None）。messages 原地修改。
    """
    marker = {"type": "ephemeral"}
    for m in reversed(messages):
        if m["role"] == "user" and not any(b.get("type") == "tool_result" for b in m["content"]):
            m["content"][-1]["cache_control"] = dict(marker)
            break
    return [{"type": "text", "text": system, "cache_control": dict(marker)}] if system else None
