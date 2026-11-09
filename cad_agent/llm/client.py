"""OpenAI 兼容接口的模型客户端（DeepSeek、GLM、通义、Kimi 等都适用）。"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any, Protocol

import openai


class LLMError(RuntimeError):
    """模型调用失败（网络、限流、鉴权等）；信息是中文，不含 API key。"""


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
    def chat(self, messages: list[dict], tools: list[dict]) -> LLMReply: ...


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
        timeout: float = 120,
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

    def chat(self, messages: list[dict], tools: list[dict]) -> LLMReply:
        kwargs: dict[str, Any] = {"model": self.model, "messages": messages, "temperature": self.temperature}
        if tools:
            kwargs["tools"] = tools
        if self.extra_body:  # 原样透传，代码里不认识里面的任何厂商参数
            kwargs["extra_body"] = dict(self.extra_body)
        last = ""
        for attempt in range(self.max_retries + 1):
            try:
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
            if attempt < self.max_retries:
                time.sleep(2**attempt)  # 1 秒、2 秒
        raise LLMError(f"{last}，已重试 {self.max_retries} 次")

    def _reply(self, resp: Any) -> LLMReply:
        if not getattr(resp, "choices", None):
            raise LLMError("模型返回里没有内容")
        msg = resp.choices[0].message
        calls = [ToolCall(tc.id, tc.function.name, parse_arguments(tc.function.arguments)) for tc in (msg.tool_calls or [])]
        usage = normalize_usage(getattr(resp, "usage", None))
        return LLMReply(content=msg.content or "", tool_calls=calls, usage=usage, cost=call_cost(usage, self.pricing))


def _short(e: Exception) -> str:
    return " ".join(str(e).split())[:200]
