"""Claude 适配层：消息转换、请求格式、用量、流式、停止、重试。全部用假的 HTTP 服务端，不连真实接口。

字段名以 docs/llm-api-notes.md 第 8 节为准（查文档，未用真实接口验证）。
"""

from __future__ import annotations

import json

import anthropic
import httpx2
import pytest

from cad_agent.config import Config, PhaseOverride
from cad_agent.llm.anthropic_client import AnthropicLLM, to_anthropic_messages, to_anthropic_tools
from cad_agent.llm.client import LLMError, LLMStopped, OpenAICompatLLM, Pricing, ToolCall
from cad_agent.llm.factory import make_llm

FAKE_KEY = "test-key-0000"
BUILD_TOOL = {"type": "function", "function": {"name": "build", "description": "运行并检查", "parameters": {"type": "object", "properties": {}}}}
UPSERT_TOOL = {"type": "function", "function": {
    "name": "upsert_feature", "description": "写一个特征",
    "parameters": {"type": "object", "properties": {"slug": {"type": "string"}}, "required": ["slug"]}}}
USAGE = {"input_tokens": 30, "output_tokens": 12, "cache_read_input_tokens": 500, "cache_creation_input_tokens": 70}


def call(cid: str, name: str, args: str) -> dict:
    return {"id": cid, "type": "function", "function": {"name": name, "arguments": args}}


def message(content: list[dict], usage: dict | None = None, stop: str = "end_turn") -> dict:
    return {"id": "msg_1", "type": "message", "role": "assistant", "model": "claude-opus-5-5", "content": content,
            "stop_reason": stop, "stop_sequence": None, "usage": usage or dict(USAGE)}


def sse(events: list[dict]) -> list[bytes]:
    return [f"event: {e['type']}\ndata: {json.dumps(e, ensure_ascii=False)}\n\n".encode("utf-8") for e in events]


def stream_events(text_parts: list[str], tool: tuple[str, str, list[str]] | None = None, usage: dict | None = None) -> list[dict]:
    u = usage or USAGE
    start_usage = {k: v for k, v in u.items() if k != "output_tokens"} | {"output_tokens": 1}
    ev = [{"type": "message_start", "message": {"id": "msg_1", "type": "message", "role": "assistant", "model": "claude-opus-5-5",
                                                "content": [], "stop_reason": None, "stop_sequence": None, "usage": start_usage}},
          {"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}}, {"type": "ping"}]
    ev += [{"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": t}} for t in text_parts]
    ev.append({"type": "content_block_stop", "index": 0})
    if tool is not None:
        tid, name, parts = tool
        ev.append({"type": "content_block_start", "index": 1, "content_block": {"type": "tool_use", "id": tid, "name": name, "input": {}}})
        ev += [{"type": "content_block_delta", "index": 1, "delta": {"type": "input_json_delta", "partial_json": p}} for p in parts]
        ev.append({"type": "content_block_stop", "index": 1})
    ev += [{"type": "message_delta", "delta": {"stop_reason": "tool_use" if tool else "end_turn", "stop_sequence": None},
            "usage": {"output_tokens": u["output_tokens"]}}, {"type": "message_stop"}]
    return ev


class FakeServer:
    """按顺序给出响应：dict（JSON 回复）、list（SSE 片段）、("status", 码)、("break", 片段)。"""

    def __init__(self, *responses) -> None:
        self.responses = list(responses)
        self.requests: list[dict] = []
        self.headers: list[dict] = []

    def handler(self, request: httpx2.Request) -> httpx2.Response:
        self.requests.append(json.loads(request.content.decode("utf-8")))
        self.headers.append(dict(request.headers))
        resp = self.responses[min(len(self.requests), len(self.responses)) - 1]
        if isinstance(resp, dict):
            return httpx2.Response(200, json=resp)
        if isinstance(resp, tuple) and resp[0] == "status":
            body = {"type": "error", "error": {"type": "x_error", "message": f"出错了，key 是 {FAKE_KEY}"}}
            return httpx2.Response(resp[1], json=body)
        if isinstance(resp, tuple) and resp[0] == "break":
            def broken():
                yield from resp[1]
                raise httpx2.ReadError("连接断了")
            return httpx2.Response(200, headers={"content-type": "text/event-stream"}, content=broken())
        return httpx2.Response(200, headers={"content-type": "text/event-stream"}, content=iter(resp))

    def llm(self, **kw) -> AnthropicLLM:
        llm = AnthropicLLM(base_url="https://example.invalid", api_key=FAKE_KEY, model="claude-opus-5-5", **kw)
        llm.client = anthropic.Anthropic(base_url="https://example.invalid", api_key=FAKE_KEY, max_retries=0,
                                         http_client=httpx2.Client(transport=httpx2.MockTransport(self.handler)))
        return llm


@pytest.fixture
def sleeps(monkeypatch):
    recorded = []
    monkeypatch.setattr("cad_agent.llm.anthropic_client.time.sleep", recorded.append)
    return recorded


# ---------------------------------------------------------------- 消息转换


def test_system_messages_are_joined():
    system, msgs = to_anthropic_messages([
        {"role": "system", "content": "第一段"}, {"role": "user", "content": "你好"}, {"role": "system", "content": "第二段"}])
    assert system == "第一段\n\n第二段"
    assert msgs == [{"role": "user", "content": [{"type": "text", "text": "你好"}]}]


def test_tool_calls_become_blocks():
    _, msgs = to_anthropic_messages([
        {"role": "user", "content": "做"},
        {"role": "assistant", "content": "先写特征", "tool_calls": [call("c1", "upsert_feature", '{"slug": "base"}'), call("c2", "build", "")]},
        {"role": "tool", "tool_call_id": "c1", "content": "{\"ok\": true}"},
        {"role": "tool", "tool_call_id": "c2", "content": "{\"passed\": true}"},
    ])
    assert msgs[1] == {"role": "assistant", "content": [
        {"type": "text", "text": "先写特征"},
        {"type": "tool_use", "id": "c1", "name": "upsert_feature", "input": {"slug": "base"}},
        {"type": "tool_use", "id": "c2", "name": "build", "input": {}}]}


def test_tool_results_are_merged_into_one_user_message():
    _, msgs = to_anthropic_messages([
        {"role": "user", "content": "做"},
        {"role": "assistant", "content": "", "tool_calls": [call("c1", "build", "{}"), call("c2", "build", "{}")]},
        {"role": "tool", "tool_call_id": "c1", "content": "结果一"},
        {"role": "tool", "tool_call_id": "c2", "content": "结果二"},
    ])
    assert [m["role"] for m in msgs] == ["user", "assistant", "user"]
    assert msgs[1]["content"] == [{"type": "tool_use", "id": "c1", "name": "build", "input": {}},
                                  {"type": "tool_use", "id": "c2", "name": "build", "input": {}}]   # 没有空的文字块
    assert msgs[2]["content"] == [{"type": "tool_result", "tool_use_id": "c1", "content": "结果一"},
                                  {"type": "tool_result", "tool_use_id": "c2", "content": "结果二"}]


def test_user_after_tool_results_is_merged():
    _, msgs = to_anthropic_messages([
        {"role": "user", "content": "做"},
        {"role": "assistant", "content": "", "tool_calls": [call("c1", "build", "{}")]},
        {"role": "tool", "tool_call_id": "c1", "content": "结果"},
        {"role": "user", "content": "【看图审查没有通过（程序生成）】"},
    ])
    assert len(msgs) == 3 and msgs[2] == {"role": "user", "content": [
        {"type": "tool_result", "tool_use_id": "c1", "content": "结果"}, {"type": "text", "text": "【看图审查没有通过（程序生成）】"}]}


def test_consecutive_users_are_merged():
    _, msgs = to_anthropic_messages([
        {"role": "system", "content": "s"},
        {"role": "user", "content": "快照"},
        {"role": "user", "content": "【阶段已通过】S1 底板：通过"},
        {"role": "assistant", "content": "好"},
        {"role": "user", "content": "【程序自动运行了 build，结果如下】\n{}"},
        {"role": "assistant", "content": "收到"},
        {"role": "assistant", "content": "继续"},
    ])
    assert [m["role"] for m in msgs] == ["user", "assistant", "user", "assistant"]
    assert msgs[0]["content"] == [{"type": "text", "text": "快照"}, {"type": "text", "text": "【阶段已通过】S1 底板：通过"}]
    assert msgs[3]["content"] == [{"type": "text", "text": "收到"}, {"type": "text", "text": "继续"}]


def test_bad_tool_arguments_keep_raw():
    _, msgs = to_anthropic_messages([
        {"role": "user", "content": "做"},
        {"role": "assistant", "content": "", "tool_calls": [call("c1", "upsert_feature", "{bad"), call("c2", "build", "[1]")]},
    ])
    assert msgs[1]["content"][0]["input"] == {"__raw__": "{bad"}
    assert msgs[1]["content"][1]["input"] == {"__raw__": "[1]"}


def test_tools_are_converted():
    assert to_anthropic_tools([BUILD_TOOL, UPSERT_TOOL]) == [
        {"name": "build", "description": "运行并检查", "input_schema": {"type": "object", "properties": {}}},
        {"name": "upsert_feature", "description": "写一个特征",
         "input_schema": {"type": "object", "properties": {"slug": {"type": "string"}}, "required": ["slug"]}}]
    assert to_anthropic_tools([]) == []


# ---------------------------------------------------------------- 请求和回复


MESSAGES = [{"role": "system", "content": "你是建模助手"}, {"role": "user", "content": "做一块板"}]


def test_request_shape():
    server = FakeServer(message([{"type": "text", "text": "好"}]))
    server.llm(max_tokens=1234, extra_body={"metadata": {"user_id": "u"}}).chat(MESSAGES, [BUILD_TOOL])
    body = server.requests[0]
    assert body["model"] == "claude-opus-5-5" and body["max_tokens"] == 1234 and body["metadata"] == {"user_id": "u"}
    assert "temperature" not in body and "stream" not in body   # 偏离 D14：新 API 版本不接受 temperature
    assert body["tools"] == to_anthropic_tools([BUILD_TOOL])
    # anthropic 2.8.0 用 Authorization: Bearer 带 key（笔记第 8 节第 15 条）
    assert server.headers[0]["authorization"] == f"Bearer {FAKE_KEY}" and server.headers[0]["anthropic-version"] == "2026-10-21"


def test_reply_is_parsed():
    content = [{"type": "thinking", "thinking": "", "signature": "sig-1"},
               {"type": "text", "text": "先写特征再 build"},
               {"type": "tool_use", "id": "toolu_1", "name": "upsert_feature", "input": {"slug": "base"}},
               {"type": "tool_use", "id": "toolu_2", "name": "build", "input": {}}]
    reply = FakeServer(message(content, stop="tool_use")).llm().chat(MESSAGES, [BUILD_TOOL, UPSERT_TOOL])
    assert reply.content == "先写特征再 build"
    assert reply.tool_calls == [ToolCall("toolu_1", "upsert_feature", {"slug": "base"}), ToolCall("toolu_2", "build", {})]


def test_usage_is_normalized():
    raw = {"input_tokens": 30, "output_tokens": 12, "cache_read_input_tokens": 500, "cache_creation_input_tokens": 70}
    pricing = Pricing(input_hit=1.0, input_miss=10.0, output=100.0)
    reply = FakeServer(message([{"type": "text", "text": "好"}], usage=raw)).llm(pricing=pricing).chat(MESSAGES, [])
    assert reply.usage == {"prompt_tokens": 600, "completion_tokens": 12, "total_tokens": 612, "cached_tokens": 500,
                           "reasoning_tokens": 0}
    assert reply.cost == pytest.approx((500 * 1.0 + (30 + 70) * 10.0 + 12 * 100.0) / 1_000_000)   # 缓存写入按没命中算
    missing = FakeServer(message([{"type": "text", "text": "好"}], usage={"input_tokens": 5, "output_tokens": 2})).llm().chat(MESSAGES, [])
    assert missing.usage == {"prompt_tokens": 5, "completion_tokens": 2, "total_tokens": 7, "cached_tokens": 0, "reasoning_tokens": 0}
    assert missing.cost is None


def test_cache_markers_are_on_system_and_first_user():
    msgs = [{"role": "system", "content": "系统提示词"},
            {"role": "user", "content": "上一轮的原话"}, {"role": "assistant", "content": "上一轮的回复"},
            {"role": "user", "content": "【当前状态】快照\n\n【用户说】\n改一下"},
            {"role": "assistant", "content": "", "tool_calls": [call("c1", "build", "{}")]},
            {"role": "tool", "tool_call_id": "c1", "content": "结果"}]
    server = FakeServer(message([{"type": "text", "text": "好"}]))
    server.llm().chat(msgs, [BUILD_TOOL])
    body = server.requests[0]
    assert body["system"] == [{"type": "text", "text": "系统提示词", "cache_control": {"type": "ephemeral"}}]
    marked = [(i, j) for i, m in enumerate(body["messages"]) for j, b in enumerate(m["content"]) if "cache_control" in b]
    assert marked == [(2, 0)]   # 本轮快照那条 user 消息的末尾；旧轮的 user 和工具结果不标
    assert body["messages"][2]["content"][0]["text"].startswith("【当前状态】")
    assert json.dumps(body, ensure_ascii=False).count("cache_control") == 2


def test_cache_marker_on_snapshot_in_first_turn():
    server = FakeServer(message([{"type": "text", "text": "好"}]))
    server.llm().chat(MESSAGES, [])
    body = server.requests[0]
    assert body["messages"][0]["content"][-1]["cache_control"] == {"type": "ephemeral"}


def test_thinking_blocks_are_replayed_in_tool_turn():
    first = [{"type": "thinking", "thinking": "", "signature": "sig-abc"},
             {"type": "text", "text": "先 build"},
             {"type": "tool_use", "id": "toolu_9", "name": "build", "input": {}}]
    server = FakeServer(message(first, stop="tool_use"), message([{"type": "text", "text": "好了"}]))
    llm = server.llm()
    reply = llm.chat(MESSAGES, [BUILD_TOOL])
    history = MESSAGES + [{"role": "assistant", "content": reply.content, "tool_calls": [call("toolu_9", "build", "{}")]},
                          {"role": "tool", "tool_call_id": "toolu_9", "content": "{\"passed\": true}"}]
    llm.chat(history, [BUILD_TOOL])
    assert server.requests[1]["messages"][1] == {"role": "assistant", "content": first}   # 原样放回，思考块在前


def test_unknown_tool_turn_is_converted_by_rules():
    server = FakeServer(message([{"type": "text", "text": "好"}]))
    history = MESSAGES + [{"role": "assistant", "content": "", "tool_calls": [call("toolu_x", "build", "{}")]},
                          {"role": "tool", "tool_call_id": "toolu_x", "content": "r"}]
    server.llm().chat(history, [BUILD_TOOL])
    assert server.requests[0]["messages"][1]["content"] == [{"type": "tool_use", "id": "toolu_x", "name": "build", "input": {}}]


# ---------------------------------------------------------------- 流式和停止


def test_streaming_text_and_tool_args():
    server = FakeServer(sse(stream_events(["先", "写特征"], ("toolu_1", "upsert_feature", ["", '{"slug"', ': "base"}']))))
    got: list[str] = []
    reply = server.llm(pricing=Pricing(1.0, 10.0, 100.0)).chat(MESSAGES, [UPSERT_TOOL], on_delta=got.append)
    assert got == ["先", "写特征"] and reply.content == "先写特征"
    assert reply.tool_calls == [ToolCall("toolu_1", "upsert_feature", {"slug": "base"})]
    assert server.requests[0]["stream"] is True
    assert reply.usage == {"prompt_tokens": 600, "completion_tokens": 12, "total_tokens": 612, "cached_tokens": 500,
                           "reasoning_tokens": 0}


def test_streaming_thinking_is_not_forwarded_but_replayed():
    ev = stream_events(["答"], ("toolu_5", "build", ["{}"]))
    thinking = [{"type": "content_block_start", "index": 0, "content_block": {"type": "thinking", "thinking": "", "signature": ""}},
                {"type": "content_block_delta", "index": 0, "delta": {"type": "thinking_delta", "thinking": "想"}},
                {"type": "content_block_delta", "index": 0, "delta": {"type": "signature_delta", "signature": "sig-z"}},
                {"type": "content_block_stop", "index": 0}]
    for e in ev:   # 文字和工具块的序号往后挪一位
        if "index" in e:
            e["index"] += 1
    ev = ev[:1] + thinking + ev[1:]
    server = FakeServer(sse(ev), message([{"type": "text", "text": "好"}]))
    llm = server.llm()
    got: list[str] = []
    reply = llm.chat(MESSAGES, [BUILD_TOOL], on_delta=got.append)
    assert got == ["答"] and reply.content == "答"
    history = MESSAGES + [{"role": "assistant", "content": "答", "tool_calls": [call("toolu_5", "build", "{}")]},
                          {"role": "tool", "tool_call_id": "toolu_5", "content": "r"}]
    llm.chat(history, [BUILD_TOOL])
    assert server.requests[1]["messages"][1]["content"] == [
        {"type": "thinking", "thinking": "想", "signature": "sig-z"}, {"type": "text", "text": "答"},
        {"type": "tool_use", "id": "toolu_5", "name": "build", "input": {}}]


def test_stop_raises_llm_stopped(sleeps):
    server = FakeServer(sse(stream_events(["一", "二", "三"])))
    got: list[str] = []
    with pytest.raises(LLMStopped):
        server.llm().chat(MESSAGES, [], on_delta=got.append, should_stop=lambda: len(got) >= 2)
    assert got == ["一", "二"] and len(server.requests) == 1 and sleeps == []


def test_stream_broken_midway_retries_from_scratch(sleeps):
    events = sse(stream_events(["一", "二", "三"]))
    server = FakeServer(("break", events[:5]), events)
    got: list[str] = []
    reply = server.llm().chat(MESSAGES, [], on_delta=got.append)
    assert got == ["一", "二", "\x00", "一", "二", "三"] and reply.content == "一二三" and sleeps == [1]


def test_error_event_in_stream_is_retried(sleeps):
    events = sse(stream_events(["一"]))
    overloaded = events[:4] + [b'event: error\ndata: {"type": "error", "error": {"type": "overloaded_error", "message": "Overloaded"}}\n\n']
    server = FakeServer(overloaded, events)
    got: list[str] = []
    assert server.llm().chat(MESSAGES, [], on_delta=got.append).content == "一"
    assert got == ["一", "\x00", "一"] and len(server.requests) == 2


# ---------------------------------------------------------------- 重试和报错


@pytest.mark.parametrize("status", [429, 500, 503, 529])
def test_retry_rules(status, sleeps):
    server = FakeServer(("status", status), message([{"type": "text", "text": "好了"}]))
    assert server.llm().chat(MESSAGES, []).content == "好了"
    assert len(server.requests) == 2 and sleeps == [1]
    always = FakeServer(("status", status))
    with pytest.raises(LLMError, match="已重试 2 次"):
        always.llm().chat(MESSAGES, [])
    assert len(always.requests) == 3


@pytest.mark.parametrize("status", [400, 401, 403, 404])
def test_no_retry_for_client_errors(status, sleeps):
    server = FakeServer(("status", status))
    with pytest.raises(LLMError, match=str(status)):
        server.llm().chat(MESSAGES, [])
    assert len(server.requests) == 1 and sleeps == []


def test_error_text_has_no_key(sleeps):
    for status in (400, 401, 429, 500):
        with pytest.raises(LLMError) as e:
            FakeServer(("status", status)).llm().chat(MESSAGES, [])
        assert FAKE_KEY not in str(e.value) and "0000" not in str(e.value)
        assert e.value.__suppress_context__ or e.value.__cause__ is None
    with pytest.raises(LLMError) as e:
        FakeServer(("status", 401)).llm().chat(MESSAGES, [])
    assert "API key" in str(e.value)


def test_connection_error_is_retried(sleeps):
    server = FakeServer(("break", []))
    with pytest.raises(LLMError, match="网络"):
        server.llm().chat(MESSAGES, [], on_delta=lambda s: None)
    assert len(server.requests) == 3 and sleeps == [1, 2]


# ---------------------------------------------------------------- 工厂


def test_make_llm_picks_client_by_kind():
    openai_cfg = Config(base_url="https://api.deepseek.com", model="deepseek-flash")
    assert isinstance(make_llm(openai_cfg, "base", FAKE_KEY), OpenAICompatLLM)
    claude_cfg = Config(base_url="https://api.anthropic.com", model="claude-opus-5-5", kind="anthropic",
                        pricing=Pricing(1.0, 2.0, 3.0), extra_body={"metadata": {"user_id": "u"}})
    llm = make_llm(claude_cfg, "modeling", FAKE_KEY)
    assert isinstance(llm, AnthropicLLM) and llm.model == "claude-opus-5-5" and llm.pricing == Pricing(1.0, 2.0, 3.0)
    assert llm.extra_body == {"metadata": {"user_id": "u"}}


def test_make_llm_review_phase_can_use_another_kind():
    cfg = Config(base_url="https://api.deepseek.com", model="deepseek-flash",
                 review=PhaseOverride(model="claude-sonnet-5-5", kind="anthropic", base_url="https://api.anthropic.com",
                                      api_key_env="ANTHROPIC_API_KEY"))
    assert isinstance(make_llm(cfg, "modeling", FAKE_KEY), OpenAICompatLLM)
    review = make_llm(cfg, "review", FAKE_KEY)
    assert isinstance(review, AnthropicLLM) and review.model == "claude-sonnet-5-5"
    assert str(review.client.base_url).startswith("https://api.anthropic.com")
