from types import SimpleNamespace

import openai
import pytest

try:  # openai 3.x 用 httpx2，旧版本用 httpx；测试只需要用它造请求和响应对象
    import httpx2 as httpx
except ImportError:  # pragma: no cover
    import httpx

from cad_agent.llm.client import LLMError, LLMReply, OpenAICompatLLM, ToolCall
from cad_agent.llm.fake import ScriptedLLM, scripted_call

REQ = httpx.Request("POST", "https://example.invalid/v1/chat/completions")
MESSAGES = [{"role": "system", "content": "你是助手"}, {"role": "user", "content": "你好"}]
TOOLS = [{"type": "function", "function": {"name": "build", "description": "d", "parameters": {"type": "object", "properties": {}}}}]


def response(content="", tool_calls=None, usage=(10, 5, 15)):
    calls = [SimpleNamespace(id=i, type="function", function=SimpleNamespace(name=n, arguments=a)) for i, n, a in (tool_calls or [])]
    u = SimpleNamespace(prompt_tokens=usage[0], completion_tokens=usage[1], total_tokens=usage[2]) if usage else None
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content, tool_calls=calls or None))], usage=u)


class FakeClient:
    """按顺序返回响应或抛出异常；记录每次调用的参数。"""

    def __init__(self, *outcomes):
        self.outcomes = list(outcomes)
        self.calls = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        outcome = self.outcomes[min(len(self.calls), len(self.outcomes)) - 1]
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


@pytest.fixture
def sleeps(monkeypatch):
    recorded = []
    monkeypatch.setattr("cad_agent.llm.client.time.sleep", recorded.append)
    return recorded


def make(client, **kw):
    return OpenAICompatLLM("https://example.invalid/v1", "m", "k", client=client, **kw)


def test_parse_tool_calls():
    client = FakeClient(response("好的", [("c1", "upsert_feature", '{"slug": "base"}')]))
    reply = make(client).chat(MESSAGES, TOOLS)
    assert reply.content == "好的"
    assert reply.tool_calls == [ToolCall("c1", "upsert_feature", {"slug": "base"})]
    assert reply.tool_calls[0].arguments == {"slug": "base"}
    assert reply.usage == {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}


def test_request_parameters():
    client = FakeClient(response("ok"))
    make(client, temperature=0.3).chat(MESSAGES, TOOLS)
    sent = client.calls[0]
    assert sent["model"] == "m" and sent["messages"] == MESSAGES and sent["tools"] == TOOLS and sent["temperature"] == 0.3


def test_no_tools_key_when_tool_list_empty():
    client = FakeClient(response("ok"))
    make(client).chat(MESSAGES, [])
    assert "tools" not in client.calls[0]


def test_plain_reply_without_usage_or_content():
    reply = make(FakeClient(response(None, usage=None))).chat(MESSAGES, TOOLS)
    assert reply == LLMReply(content="", tool_calls=[], usage={"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0})


def test_malformed_arguments_kept_raw():
    client = FakeClient(response("", [("c1", "upsert_feature", "{bad"), ("c2", "build", ""), ("c3", "x", "[1, 2]")]))
    calls = make(client).chat(MESSAGES, TOOLS).tool_calls
    assert calls[0].arguments == {"__raw__": "{bad"}
    assert calls[1].arguments == {}  # 无参数工具有的模型会发空字符串
    assert calls[2].arguments == {"__raw__": "[1, 2]"}  # 合法 JSON 但不是对象，也当作原文处理


def test_network_error_raises_llmerror(sleeps):
    client = FakeClient(openai.APIConnectionError(request=REQ))
    with pytest.raises(LLMError, match="网络"):
        make(client).chat(MESSAGES, TOOLS)
    assert len(client.calls) == 3 and sleeps == [1, 2]


def test_timeout_is_retried_too(sleeps):
    client = FakeClient(openai.APITimeoutError(request=REQ))
    with pytest.raises(LLMError, match="超时"):
        make(client).chat(MESSAGES, TOOLS)
    assert len(client.calls) == 3


def test_rate_limit_then_success(sleeps):
    limited = openai.RateLimitError("slow down", response=httpx.Response(429, request=REQ), body=None)
    client = FakeClient(limited, response("好了"))
    assert make(client).chat(MESSAGES, TOOLS).content == "好了"
    assert len(client.calls) == 2 and sleeps == [1]


def test_server_error_is_retried(sleeps):
    boom = openai.InternalServerError("boom", response=httpx.Response(503, request=REQ), body=None)
    client = FakeClient(boom)
    with pytest.raises(LLMError, match="503"):
        make(client).chat(MESSAGES, TOOLS)
    assert len(client.calls) == 3


def test_auth_error_not_retried_and_message_has_no_key(sleeps):
    bad = openai.AuthenticationError("Incorrect API key provided: sk-secret", response=httpx.Response(401, request=REQ), body=None)
    client = FakeClient(bad)
    with pytest.raises(LLMError) as e:
        make(client).chat(MESSAGES, TOOLS)
    assert len(client.calls) == 1 and sleeps == []
    assert "API key" in str(e.value) and "sk-secret" not in str(e.value)


def test_bad_request_not_retried(sleeps):
    bad = openai.BadRequestError("tools not supported", response=httpx.Response(400, request=REQ), body=None)
    client = FakeClient(bad)
    with pytest.raises(LLMError, match="400"):
        make(client).chat(MESSAGES, TOOLS)
    assert len(client.calls) == 1


def test_empty_choices_raises_llmerror():
    with pytest.raises(LLMError, match="没有内容"):
        make(FakeClient(SimpleNamespace(choices=[], usage=None))).chat(MESSAGES, TOOLS)


def test_max_retries_is_configurable(sleeps):
    client = FakeClient(openai.APIConnectionError(request=REQ))
    with pytest.raises(LLMError):
        make(client, max_retries=0).chat(MESSAGES, TOOLS)
    assert len(client.calls) == 1


def test_scripted_llm_order_and_record():
    r1 = LLMReply("第一条", [], {})
    r2 = scripted_call("build", {})
    llm = ScriptedLLM([r1, r2])
    msgs = [{"role": "user", "content": "a"}]
    assert llm.chat(msgs, TOOLS) is r1
    msgs.append({"role": "user", "content": "b"})  # 之后改动传入的列表，不应影响已经记录的内容
    assert llm.chat(msgs, TOOLS) is r2
    assert llm.calls == [[{"role": "user", "content": "a"}], [{"role": "user", "content": "a"}, {"role": "user", "content": "b"}]]
    assert r2.tool_calls == [ToolCall("call_1", "build", {})]
    with pytest.raises(AssertionError, match="用完"):
        llm.chat(msgs, TOOLS)


def test_scripted_llm_can_raise():
    llm = ScriptedLLM([LLMReply("ok", [], {}), LLMError("断网")])
    llm.chat([], [])
    with pytest.raises(LLMError, match="断网"):
        llm.chat([], [])
