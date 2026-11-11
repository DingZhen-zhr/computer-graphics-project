"""逐字输出：OpenAI 兼容客户端的流式请求，用 httpx2 的假传输层造响应，不连任何真实服务。"""

from __future__ import annotations

import json

import httpx2
import openai
import pytest

from cad_agent.llm.client import LLMError, LLMReply, LLMStopped, OpenAICompatLLM, Pricing, ToolCall
from cad_agent.llm.fake import ScriptedLLM, scripted_call

MESSAGES = [{"role": "system", "content": "你是助手"}, {"role": "user", "content": "你好"}]
TOOLS = [{"type": "function", "function": {"name": "build", "description": "d", "parameters": {"type": "object", "properties": {}}}}]
FAKE_KEY = "test-key-0000"


def chunk(delta: dict | None = None, *, finish: str | None = None, usage: dict | None = None) -> dict:
    choices = [] if delta is None else [{"index": 0, "delta": delta, "finish_reason": finish}]
    out = {"id": "c", "object": "chat.completion.chunk", "created": 0, "model": "m", "choices": choices}
    if usage is not None:
        out["usage"] = usage
    return out


def sse(chunks: list[dict], done: bool = True) -> list[bytes]:
    parts = [f"data: {json.dumps(c, ensure_ascii=False)}\n\n".encode("utf-8") for c in chunks]
    return parts + ([b"data: [DONE]\n\n"] if done else [])


USAGE = {"prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120, "prompt_cache_hit_tokens": 64,
         "prompt_tokens_details": {"cached_tokens": 64}, "completion_tokens_details": {"reasoning_tokens": 5}}
TEXT_CHUNKS = [chunk({"role": "assistant", "content": "你"}), chunk({"content": "好，"}), chunk({"content": "我在"}),
               chunk({}, finish="stop"), chunk(None, usage=USAGE)]


class FakeServer:
    """按顺序给出每次请求的响应：一串字节片段（流式）、一个 dict（非流式 JSON），或者"发几段后断开"。"""

    def __init__(self, *responses) -> None:
        self.responses = list(responses)
        self.requests: list[dict] = []

    def handler(self, request: httpx2.Request) -> httpx2.Response:
        self.requests.append(json.loads(request.content.decode("utf-8")))
        resp = self.responses[min(len(self.requests), len(self.responses)) - 1]
        if isinstance(resp, dict):
            return httpx2.Response(200, json=resp)
        if isinstance(resp, tuple) and resp[0] == "break":
            def broken():
                yield from resp[1]
                raise httpx2.ReadError("连接断了")
            return httpx2.Response(200, headers={"content-type": "text/event-stream"}, content=broken())
        return httpx2.Response(200, headers={"content-type": "text/event-stream"}, content=iter(resp))

    def llm(self, **kw) -> OpenAICompatLLM:
        client = openai.OpenAI(base_url="https://example.invalid/v1", api_key=FAKE_KEY, max_retries=0,
                               http_client=httpx2.Client(transport=httpx2.MockTransport(self.handler)))
        return OpenAICompatLLM("https://example.invalid/v1", "m", FAKE_KEY, client=client, **kw)


@pytest.fixture
def sleeps(monkeypatch):
    recorded = []
    monkeypatch.setattr("cad_agent.llm.client.time.sleep", recorded.append)
    return recorded


NON_STREAM = {"id": "x", "object": "chat.completion", "created": 0, "model": "m",
              "choices": [{"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": "好"}}],
              "usage": {"prompt_tokens": 3, "completion_tokens": 1, "total_tokens": 4}}


def test_non_streaming_request_is_unchanged():
    server = FakeServer(NON_STREAM)
    reply = server.llm().chat(MESSAGES, TOOLS)
    assert reply.content == "好"
    body = server.requests[0]
    assert "stream" not in body and "stream_options" not in body
    assert body == {"model": "m", "messages": MESSAGES, "temperature": 0.2, "tools": TOOLS}


def test_stream_text_deltas():
    server = FakeServer(sse(TEXT_CHUNKS))
    got: list[str] = []
    reply = server.llm().chat(MESSAGES, TOOLS, on_delta=got.append)
    assert got == ["你", "好，", "我在"]
    assert "".join(got) == reply.content == "你好，我在"
    body = server.requests[0]
    assert body["stream"] is True and body["stream_options"] == {"include_usage": True}


def test_stream_tool_calls_are_assembled():
    chunks = [
        chunk({"role": "assistant", "content": "先建"}),
        chunk({"tool_calls": [{"index": 0, "id": "c1", "type": "function", "function": {"name": "upsert_feature", "arguments": ""}}]}),
        chunk({"tool_calls": [{"index": 0, "function": {"arguments": '{"slug": '}}]}),
        chunk({"tool_calls": [{"index": 0, "function": {"arguments": '"base"}'}}]}),
        chunk({"tool_calls": [{"index": 1, "id": "c2", "type": "function", "function": {"name": "build", "arguments": "{"}}]}),
        chunk({"tool_calls": [{"index": 1, "function": {"arguments": "}"}}]}),
        chunk({}, finish="tool_calls"), chunk(None, usage=USAGE),
    ]
    reply = FakeServer(sse(chunks)).llm().chat(MESSAGES, TOOLS, on_delta=lambda s: None)
    assert reply.content == "先建"
    assert reply.tool_calls == [ToolCall("c1", "upsert_feature", {"slug": "base"}), ToolCall("c2", "build", {})]


def test_stream_usage_is_read_from_the_last_chunk():
    pricing = Pricing(1.0, 2.0, 4.0)
    streamed = FakeServer(sse(TEXT_CHUNKS)).llm(pricing=pricing).chat(MESSAGES, TOOLS, on_delta=lambda s: None)
    plain_resp = dict(NON_STREAM, usage=USAGE)
    plain = FakeServer(plain_resp).llm(pricing=pricing).chat(MESSAGES, TOOLS)
    assert streamed.usage == plain.usage == {"prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120,
                                             "cached_tokens": 64, "reasoning_tokens": 5}
    assert streamed.cost == pytest.approx(plain.cost)


def test_reasoning_deltas_are_not_forwarded():
    chunks = [chunk({"role": "assistant", "reasoning_content": "想一想"}), chunk({"reasoning_content": "再想"}),
              chunk({"content": "答案"}), chunk({}, finish="stop"), chunk(None, usage=USAGE)]
    got: list[str] = []
    reply = FakeServer(sse(chunks)).llm().chat(MESSAGES, TOOLS, on_delta=got.append)
    assert got == ["答案"] and reply.content == "答案"


def test_stream_broken_midway_retries_from_scratch(sleeps):
    first_two = sse(TEXT_CHUNKS[:2], done=False)
    server = FakeServer(("break", first_two), sse(TEXT_CHUNKS))
    got: list[str] = []
    reply = server.llm().chat(MESSAGES, TOOLS, on_delta=got.append)
    assert got == ["你", "好，", "\x00", "你", "好，", "我在"]
    assert reply.content == "你好，我在" and len(server.requests) == 2 and sleeps == [1]


def test_stream_broken_every_time_raises_llm_error(sleeps):
    server = FakeServer(("break", sse(TEXT_CHUNKS[:1], done=False)))
    got: list[str] = []
    with pytest.raises(LLMError, match="网络"):
        server.llm().chat(MESSAGES, TOOLS, on_delta=got.append)
    assert len(server.requests) == 3 and got == ["你", "\x00", "你", "\x00", "你"]


def test_stop_raises_llm_stopped(sleeps):
    server = FakeServer(sse(TEXT_CHUNKS))
    got: list[str] = []
    with pytest.raises(LLMStopped):
        server.llm().chat(MESSAGES, TOOLS, on_delta=got.append, should_stop=lambda: len(got) >= 2)
    assert got == ["你", "好，"] and len(server.requests) == 1 and sleeps == []
    assert not issubclass(LLMStopped, LLMError)


def test_should_stop_alone_also_streams():
    server = FakeServer(sse(TEXT_CHUNKS))
    reply = server.llm().chat(MESSAGES, TOOLS, should_stop=lambda: False)
    assert reply.content == "你好，我在" and server.requests[0]["stream"] is True


def test_scripted_llm_emits_deltas():
    llm = ScriptedLLM([LLMReply("一二三四五六七八九", [], {}), scripted_call("build", {})])
    got: list[str] = []
    assert llm.chat([], [], on_delta=got.append).content == "一二三四五六七八九"
    assert got == ["一二三四", "五六七八", "九"]
    got.clear()
    llm.chat([], [], on_delta=got.append)   # 没有文字的回复不送片段
    assert got == []


def test_scripted_llm_can_be_stopped():
    llm = ScriptedLLM([LLMReply("一二三四五六七八九", [], {})])
    got: list[str] = []
    with pytest.raises(LLMStopped):
        llm.chat([], [], on_delta=got.append, should_stop=lambda: len(got) >= 1)
    assert got == ["一二三四"]
