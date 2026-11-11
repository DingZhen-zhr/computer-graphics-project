"""Claude 官方接口的适配层：对内呈现和 OpenAICompatLLM 一样的 LLM 接口和用量字段。

字段名、流式事件、缓存标记以 docs/llm-api-notes.md 第 8 节为准。**只经过假服务端测试，未用真实接口验证。**
和计划不同的两处见偏离 D14：不发 temperature；工具调用那一轮的思考块原样放回。
"""

from __future__ import annotations

import copy
import json
import time
from collections import OrderedDict
from typing import Any, Callable

import anthropic
import httpx2

from cad_agent.llm.anthropic_convert import add_cache_markers, to_anthropic_messages, to_anthropic_tools  # noqa: F401
from cad_agent.llm.client import RESET_DELTA, LLMError, LLMReply, LLMStopped, Pricing, ToolCall, call_cost, parse_arguments

REMEMBERED_REPLIES = 32   # 记住最近这么多次带工具调用的回复的原始内容块（放回思考块用）


def normalize_anthropic_usage(u: Any) -> dict[str, int]:
    """换算成内部的用量：prompt = 没命中的输入 + 缓存命中 + 缓存写入；cached = 缓存命中；思考 token 拿不到记 0。"""
    def n(name: str) -> int:
        v = getattr(u, name, None) if not isinstance(u, dict) else u.get(name)
        return int(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else 0

    hit = n("cache_read_input_tokens")
    prompt = n("input_tokens") + hit + n("cache_creation_input_tokens")
    out = n("output_tokens")
    return {"prompt_tokens": prompt, "completion_tokens": out, "total_tokens": prompt + out, "cached_tokens": hit,
            "reasoning_tokens": 0}


def _block_param(block: Any) -> dict | None:
    """回复里的内容块 → 可以原样放回请求里的写法。不认识的块类型不放回。"""
    b = block if isinstance(block, dict) else block.model_dump()
    kind = b.get("type")
    if kind == "text":
        return {"type": "text", "text": b.get("text", "")}
    if kind == "tool_use":
        return {"type": "tool_use", "id": b["id"], "name": b["name"], "input": b.get("input") or {}}
    if kind == "thinking":
        return {"type": "thinking", "thinking": b.get("thinking", ""), "signature": b.get("signature", "")}
    if kind == "redacted_thinking":
        return {"type": "redacted_thinking", "data": b.get("data", "")}
    return None


class _StreamState:
    """把流式事件拼回完整回复：每个内容块的原始写法、文字、工具参数文字、用量。"""

    def __init__(self) -> None:
        self.blocks: dict[int, dict] = {}
        self.json_parts: dict[int, list[str]] = {}
        self.usage: dict[str, int] = {}

    def add(self, event: Any) -> str:
        kind = getattr(event, "type", None)
        if kind == "message_start":
            self._usage(getattr(event.message, "usage", None))
        elif kind == "content_block_start":
            self.blocks[event.index] = _block_param(event.content_block) or {"type": "unknown"}
            self.json_parts[event.index] = []
        elif kind == "content_block_delta":
            d, block = event.delta, self.blocks.setdefault(event.index, {"type": "unknown"})
            if d.type == "text_delta":
                block["text"] = block.get("text", "") + d.text
                return d.text
            if d.type == "input_json_delta":
                self.json_parts.setdefault(event.index, []).append(d.partial_json)
            elif d.type == "thinking_delta":
                block["thinking"] = block.get("thinking", "") + d.thinking
            elif d.type == "signature_delta":
                block["signature"] = d.signature
        elif kind == "content_block_stop":
            block = self.blocks.get(event.index)
            if block is not None and block.get("type") == "tool_use" and self.json_parts.get(event.index):
                block["input"] = parse_arguments("".join(self.json_parts[event.index]))
        elif kind == "message_delta":
            self._usage(getattr(event, "usage", None))   # output_tokens 是累计值，直接覆盖
        return ""

    def _usage(self, u: Any) -> None:
        if u is None:
            return
        for name in ("input_tokens", "output_tokens", "cache_read_input_tokens", "cache_creation_input_tokens"):
            v = getattr(u, name, None)
            if isinstance(v, int):
                self.usage[name] = v

    def content(self) -> list[dict]:
        return [b for _, b in sorted(self.blocks.items()) if b.get("type") != "unknown"]


class AnthropicLLM:
    timeout: float = 600
    max_retries: int = 2

    def __init__(self, *, base_url: str, api_key: str, model: str, temperature: float = 0.2,
                 extra_body: dict | None = None, pricing: Pricing | None = None, max_tokens: int = 8192) -> None:
        self.model = model
        self.temperature = temperature   # 只保存，不发：API 版本 2026-10-21 起带 temperature 就 400（偏离 D14）
        self.extra_body: dict = dict(extra_body) if extra_body else {}
        self.pricing = pricing
        self.max_tokens = max_tokens
        self._secret = api_key           # 只用来把报错文字里的 key 抹掉，从不打印
        self._replies: OrderedDict[tuple[str, ...], list[dict]] = OrderedDict()
        # 重试由本类负责，所以 SDK 自带的重试关掉；测试会换掉 client
        self.client: Any = anthropic.Anthropic(base_url=base_url or None, api_key=api_key, timeout=self.timeout, max_retries=0)

    # ---------------------------------------------------------------- 组请求
    def _request(self, messages: list[dict], tools: list[dict]) -> dict[str, Any]:
        system, msgs = to_anthropic_messages(messages)
        for m in msgs:   # 偏离 D14：工具调用那一轮原样放回记下的内容块（含思考块）
            if m["role"] == "assistant":
                ids = tuple(b["id"] for b in m["content"] if b.get("type") == "tool_use")
                if ids and ids in self._replies:
                    m["content"] = copy.deepcopy(self._replies[ids])
        system_param = add_cache_markers(system, msgs)
        kwargs: dict[str, Any] = {"model": self.model, "max_tokens": self.max_tokens, "messages": msgs}
        if system_param is not None:
            kwargs["system"] = system_param
        if tools:
            kwargs["tools"] = to_anthropic_tools(tools)
        if self.extra_body:   # 原样透传，代码里不认识里面的任何参数
            kwargs["extra_body"] = dict(self.extra_body)
        return kwargs

    def _remember(self, blocks: list[dict]) -> None:
        ids = tuple(b["id"] for b in blocks if b.get("type") == "tool_use")
        if not ids:
            return
        self._replies[ids] = copy.deepcopy(blocks)
        while len(self._replies) > REMEMBERED_REPLIES:
            self._replies.popitem(last=False)

    def _reply(self, blocks: list[dict], usage: dict[str, int]) -> LLMReply:
        self._remember(blocks)
        text = "".join(b.get("text", "") for b in blocks if b.get("type") == "text")
        calls = [ToolCall(b["id"], b["name"], b.get("input") if isinstance(b.get("input"), dict) else {"__raw__": json.dumps(b.get("input"))})
                 for b in blocks if b.get("type") == "tool_use"]
        norm = normalize_anthropic_usage(usage)
        return LLMReply(content=text, tool_calls=calls, usage=norm, cost=call_cost(norm, self.pricing))

    # ---------------------------------------------------------------- 调用
    def chat(self, messages: list[dict], tools: list[dict], *,
             on_delta: Callable[[str], None] | None = None,
             should_stop: Callable[[], bool] | None = None) -> LLMReply:
        kwargs = self._request(messages, tools)
        streaming = on_delta is not None or should_stop is not None
        last = ""
        for attempt in range(self.max_retries + 1):
            emitted = [False]
            try:
                if streaming:
                    return self._stream(kwargs, on_delta, should_stop, emitted)
                resp = self.client.messages.create(**kwargs)
                blocks = [b for b in (_block_param(x) for x in (resp.content or [])) if b is not None]
                return self._reply(blocks, getattr(resp, "usage", None))
            except anthropic.APITimeoutError:
                last = "等待模型回复超时"
            except (anthropic.APIConnectionError, httpx2.TransportError):   # 流式读到一半断开时 SDK 不包装，是 httpx2 的异常
                last = "网络连接失败"
            except anthropic.RateLimitError:
                last = "请求太频繁被模型服务限流"
            except anthropic.APIStatusError as e:
                if e.status_code in (401, 403):
                    raise LLMError(f"模型服务拒绝了请求（{e.status_code}）：请检查 API key 是否正确、是否有该模型的权限") from None
                if 400 <= e.status_code < 500:
                    raise LLMError(f"模型服务返回错误 {e.status_code}：{self._short(e)}") from None
                last = f"模型服务出错（{e.status_code}）" if e.status_code >= 500 else "模型服务在输出途中出错"
            if attempt < self.max_retries:
                if emitted[0] and on_delta is not None:
                    on_delta(RESET_DELTA)
                time.sleep(2**attempt)  # 1 秒、2 秒
        raise LLMError(f"{last}，已重试 {self.max_retries} 次")

    def _stream(self, kwargs: dict[str, Any], on_delta: Callable[[str], None] | None,
                should_stop: Callable[[], bool] | None, emitted: list[bool]) -> LLMReply:
        stream = self.client.messages.create(**kwargs, stream=True)
        state = _StreamState()
        try:
            for event in stream:
                if should_stop is not None and should_stop():
                    raise LLMStopped()
                piece = state.add(event)
                if piece and on_delta is not None:
                    emitted[0] = True
                    on_delta(piece)
        finally:
            stream.close()
        return self._reply(state.content(), state.usage)

    def _short(self, e: Exception) -> str:
        text = " ".join(str(e).split())[:200]
        return text.replace(self._secret, "***") if self._secret else text
