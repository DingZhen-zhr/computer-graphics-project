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


@dataclass
class LLMReply:
    content: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    usage: dict = field(default_factory=dict)


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
    ) -> None:
        self.model = model
        self.temperature = temperature
        self.max_retries = max_retries
        # 重试由本类负责，所以 SDK 自带的重试关掉；client 参数供测试注入
        self.client = client or openai.OpenAI(base_url=base_url, api_key=api_key, timeout=timeout, max_retries=0)

    def chat(self, messages: list[dict], tools: list[dict]) -> LLMReply:
        kwargs: dict[str, Any] = {"model": self.model, "messages": messages, "temperature": self.temperature}
        if tools:
            kwargs["tools"] = tools
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

    @staticmethod
    def _reply(resp: Any) -> LLMReply:
        if not getattr(resp, "choices", None):
            raise LLMError("模型返回里没有内容")
        msg = resp.choices[0].message
        calls = [ToolCall(tc.id, tc.function.name, parse_arguments(tc.function.arguments)) for tc in (msg.tool_calls or [])]
        u = getattr(resp, "usage", None)
        usage = {
            "prompt_tokens": getattr(u, "prompt_tokens", 0) or 0,
            "completion_tokens": getattr(u, "completion_tokens", 0) or 0,
            "total_tokens": getattr(u, "total_tokens", 0) or 0,
        }
        return LLMReply(content=msg.content or "", tool_calls=calls, usage=usage)


def _short(e: Exception) -> str:
    return " ".join(str(e).split())[:200]
