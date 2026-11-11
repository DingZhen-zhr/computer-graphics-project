"""OpenAI 兼容接口的模型客户端（DeepSeek、GLM、通义、Kimi 等都适用）。"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Protocol

import openai


class LLMError(RuntimeError):
    """模型调用失败（网络、限流、鉴权等）；信息是中文，不含 API key。"""


class LLMStopped(Exception):
    """用户要求停止；不是 LLMError，不重试。"""


RESET_DELTA = "\x00"  # on_delta 收到它：前面送出的片段作废（流式中途出错、要重试了）


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict  # 参数不是合法 JSON 对象时为 {"__raw__": 原文}


USAGE_KEYS: tuple[str, ...] = ("prompt_tokens", "completion_tokens", "total_tokens", "cached_tokens", "reasoning_tokens")


@dataclass(frozen=True)
class Pricing:
    """价格，单位：元 / 百万 token。由用户照模型服务的价目页写在配置里，代码里不放任何价格。"""

    input_hit: float
    input_miss: float
    output: float


@dataclass
class LLMReply:
    content: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    usage: dict = field(default_factory=dict)
    cost: float | None = None


class LLM(Protocol):
    """模型客户端。

    on_delta：有文字片段到达时调用（思考内容不送）。流式中途出错要重试时，先送一个 "\x00"，
    表示前面送出的片段作废，重试成功后片段从头再来。
    should_stop：每收到一个片段检查一次，为真就中断请求并抛 LLMStopped（不重试）。
    两个都不传时走非流式请求，发出去的请求和以前逐字相同。
    """

    def chat(self, messages: list[dict], tools: list[dict], *,
             on_delta: Callable[[str], None] | None = None,
             should_stop: Callable[[], bool] | None = None) -> LLMReply: ...


def parse_arguments(text: str | None) -> dict:
    """工具参数：合法 JSON 对象就解析；空字符串当作没有参数；其余保留原文。"""
    raw = (text or "").strip()
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return {"__raw__": text}
    return parsed if isinstance(parsed, dict) else {"__raw__": text}


def _first_count(*candidates: Any) -> int:
    """按顺序取第一个是数字的候选值；都不是（None、缺字段）就是 0。"""
    for v in candidates:
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            return int(v)
    return 0


def normalize_usage(u: Any) -> dict[str, int]:
    """把接口返回的用量统一成 USAGE_KEYS 里的 5 个整数；取不到的记 0。取法见 docs/llm-api-notes.md 第 7 节。"""
    prompt_details = getattr(u, "prompt_tokens_details", None)
    completion_details = getattr(u, "completion_tokens_details", None)
    return {
        "prompt_tokens": _first_count(getattr(u, "prompt_tokens", None)),
        "completion_tokens": _first_count(getattr(u, "completion_tokens", None)),
        "total_tokens": _first_count(getattr(u, "total_tokens", None)),
        "cached_tokens": _first_count(getattr(u, "prompt_cache_hit_tokens", None), getattr(prompt_details, "cached_tokens", None)),
        "reasoning_tokens": _first_count(getattr(completion_details, "reasoning_tokens", None)),
    }


def call_cost(usage: dict[str, int], pricing: Pricing | None) -> float | None:
    """一次调用的费用（元）；没有价目表时是 None。没命中缓存的输入 = 输入 − 命中（不会小于 0）。"""
    if pricing is None:
        return None
    cached = usage.get("cached_tokens", 0)
    miss = max(usage.get("prompt_tokens", 0) - cached, 0)
    return (cached * pricing.input_hit + miss * pricing.input_miss + usage.get("completion_tokens", 0) * pricing.output) / 1_000_000


class OpenAICompatLLM:
    def __init__(
        self,
        base_url: str,
        model: str,
        api_key: str,
        temperature: float = 0.2,
        timeout: float = 600,  # 会思考的模型一次调用可能要好几分钟；超时就重试会把已经计费的思考白白扔掉
        max_retries: int = 2,
        client: Any = None,
        extra_body: dict | None = None,
        pricing: Pricing | None = None,
    ) -> None:
        self.model = model
        self.temperature = temperature
        self.max_retries = max_retries
        self.extra_body: dict = dict(extra_body) if extra_body else {}
        self.pricing = pricing
        # 重试由本类负责，所以 SDK 自带的重试关掉；client 参数供测试注入
        self.client = client or openai.OpenAI(base_url=base_url, api_key=api_key, timeout=timeout, max_retries=0)

    def chat(self, messages: list[dict], tools: list[dict], *,
             on_delta: Callable[[str], None] | None = None,
             should_stop: Callable[[], bool] | None = None) -> LLMReply:
        kwargs: dict[str, Any] = {"model": self.model, "messages": messages, "temperature": self.temperature}
        if tools:
            kwargs["tools"] = tools
        if self.extra_body:  # 原样透传，代码里不认识里面的任何厂商参数
            kwargs["extra_body"] = dict(self.extra_body)
        streaming = on_delta is not None or should_stop is not None
        if streaming:  # 让服务端在最后一个片段里给出整次的用量（笔记第 9 节末尾）
            kwargs["stream"] = True
            kwargs["stream_options"] = {"include_usage": True}
        last = ""
        for attempt in range(self.max_retries + 1):
            emitted = [False]
            try:
                if streaming:
                    return self._stream(kwargs, on_delta, should_stop, emitted)
                resp = self.client.chat.completions.create(**kwargs)
                return self._reply(resp)
            except openai.APITimeoutError:
                last = "等待模型回复超时"
            except openai.APIConnectionError:
                last = "网络连接失败"
            except openai.RateLimitError:
                last = "请求太频繁被模型服务限流"
            except openai.APIStatusError as e:
                if e.status_code == 401 or e.status_code == 403:
                    raise LLMError(f"模型服务拒绝了请求（{e.status_code}）：请检查 API key 是否正确、是否有该模型的权限") from None
                if e.status_code < 500:
                    raise LLMError(f"模型服务返回错误 {e.status_code}：{_short(e)}") from None
                last = f"模型服务出错（{e.status_code}）"
            except openai.APIError:  # 流式输出到一半，服务端在流里发了错误
                last = "模型服务在输出途中出错"
            if attempt < self.max_retries:
                if emitted[0] and on_delta is not None:
                    on_delta(RESET_DELTA)
                time.sleep(2**attempt)  # 1 秒、2 秒
        raise LLMError(f"{last}，已重试 {self.max_retries} 次")

    def _stream(self, kwargs: dict[str, Any], on_delta: Callable[[str], None] | None,
                should_stop: Callable[[], bool] | None, emitted: list[bool]) -> LLMReply:
        from cad_agent.llm.openai_stream import StreamAccumulator  # 放这里，避免循环导入

        stream = self.client.chat.completions.create(**kwargs)
        acc = StreamAccumulator()
        try:
            for chunk in stream:
                if should_stop is not None and should_stop():
                    raise LLMStopped()
                piece = acc.add(chunk)
                if piece and on_delta is not None:
                    emitted[0] = True
                    on_delta(piece)
        finally:
            stream.close()
        if not acc.saw_choice:
            raise LLMError("模型返回里没有内容")
        usage = normalize_usage(acc.usage)
        return LLMReply(content=acc.content, tool_calls=acc.tool_calls(), usage=usage, cost=call_cost(usage, self.pricing))

    def _reply(self, resp: Any) -> LLMReply:
        if not getattr(resp, "choices", None):
            raise LLMError("模型返回里没有内容")
        msg = resp.choices[0].message
        calls = [ToolCall(tc.id, tc.function.name, parse_arguments(tc.function.arguments)) for tc in (msg.tool_calls or [])]
        usage = normalize_usage(getattr(resp, "usage", None))
        return LLMReply(content=msg.content or "", tool_calls=calls, usage=usage, cost=call_cost(usage, self.pricing))


def _short(e: Exception) -> str:
    return " ".join(str(e).split())[:200]
