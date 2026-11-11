"""图片消息和识图测试：全部用假客户端或假服务端。"""

from __future__ import annotations

import base64
import io
import json
from types import SimpleNamespace

import pytest
from PIL import Image

from cad_agent.llm.client import LLMError, LLMReply, OpenAICompatLLM
from cad_agent.llm.fake import ScriptedLLM
from cad_agent.llm.vision import VISION_QUESTION, image_part, test_vision as run_vision_test, text_part, tiny_test_image
from cad_agent.session import Session
from test_anthropic_client import FakeServer as AnthropicServer
from test_anthropic_client import message

OK_TEXT = "这个模型能看图，看图审查已经可以用了。"
WRONG_TEXT = "这个模型没有认出测试图片，看图审查不会启用。"


def test_vision_question_is_verbatim():
    assert VISION_QUESTION == "这张图片左半边和右半边各是什么颜色？只回答两个颜色的名字。"


def test_image_part_is_data_url(tmp_path):
    png = tmp_path / "视图.png"
    png.write_bytes(tiny_test_image())
    part = image_part(png)
    assert part["type"] == "image_url" and set(part) == {"type", "image_url"}
    url = part["image_url"]["url"]
    assert url.startswith("data:image/png;base64,")
    assert base64.b64decode(url.split(",", 1)[1]) == png.read_bytes()
    assert text_part("等轴测图：") == {"type": "text", "text": "等轴测图："}


def test_tiny_test_image_is_valid_png():
    data = tiny_test_image()
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    img = Image.open(io.BytesIO(data)).convert("RGB")
    assert img.size == (64, 64)
    assert img.getpixel((5, 32)) == (255, 0, 0) and img.getpixel((31, 0)) == (255, 0, 0)
    assert img.getpixel((32, 63)) == (0, 0, 255) and img.getpixel((60, 10)) == (0, 0, 255)
    assert tiny_test_image() == data   # 每次生成的都一样


def _sent_user(llm: ScriptedLLM) -> dict:
    [msgs] = llm.calls
    assert len(msgs) == 1 and msgs[0]["role"] == "user" and llm.tool_lists == [[]]
    return msgs[0]


def test_test_vision_true():
    for answer in ("左边红色，右边蓝色", "Red and BLUE", "红、蓝"):
        llm = ScriptedLLM([LLMReply(answer, [], {})])
        assert run_vision_test(llm) == (True, OK_TEXT)
        content = _sent_user(llm)["content"]
        assert content[0]["type"] == "image_url" and content[1] == text_part(VISION_QUESTION)
        b64 = content[0]["image_url"]["url"].split(",", 1)[1]
        assert base64.b64decode(b64) == tiny_test_image()


def test_test_vision_false_on_wrong_answer():
    for answer in ("红色", "我看不到图片", "", "green and blue"):
        assert run_vision_test(ScriptedLLM([LLMReply(answer, [], {})])) == (False, WRONG_TEXT)


def test_test_vision_false_on_api_error():
    long = "模型服务返回错误 400：image input is not supported for this model, please use a vision model instead of this one"
    ok, text = run_vision_test(ScriptedLLM([LLMError(long)]))
    assert ok is False and text == f"这个模型不接受图片（{long[:80]}），看图审查不会启用。"


def test_openai_client_sends_image_parts_as_is():
    sent = []

    def create(**kw):
        sent.append(kw)
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="红和蓝", tool_calls=None))], usage=None)

    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    llm = OpenAICompatLLM("https://example.invalid/v1", "m", "test-key-0000", client=client)
    assert run_vision_test(llm)[0] is True
    msgs = sent[0]["messages"]
    assert msgs[0]["content"][0] == {"type": "image_url", "image_url": {"url": "data:image/png;base64," +
                                                                         base64.b64encode(tiny_test_image()).decode("ascii")}}
    assert "tools" not in sent[0]


def test_anthropic_client_converts_image_parts():
    server = AnthropicServer(message([{"type": "text", "text": "red / blue"}]))
    assert run_vision_test(server.llm()) == (True, OK_TEXT)
    [user] = server.requests[0]["messages"]
    img, txt = user["content"]
    assert img["type"] == "image" and img["source"]["type"] == "base64" and img["source"]["media_type"] == "image/png"
    assert base64.b64decode(img["source"]["data"]) == tiny_test_image()
    assert txt["type"] == "text" and txt["text"] == VISION_QUESTION
    assert "tools" not in server.requests[0]


def test_images_are_not_written_to_logs(tmp_path):
    session = Session(tmp_path / "sessions")
    png = tmp_path / "iso.png"
    png.write_bytes(tiny_test_image() * 3)
    part = image_part(png)
    b64 = part["image_url"]["url"].split(",", 1)[1]
    session.log("review_request", messages=[{"role": "user", "content": [text_part("等轴测图："), part]}])
    text = (session.dir / "log.jsonl").read_text(encoding="utf-8")
    assert b64[:50] not in text and "data:image" not in text
    row = json.loads(text.splitlines()[-1])
    assert row["messages"][0]["content"][1] == f"图片 {png.stat().st_size} 字节"
    assert row["messages"][0]["content"][0] == {"type": "text", "text": "等轴测图："}


@pytest.mark.parametrize("bad", ["not a data url", "data:image/png;base64,!!!"])
def test_log_redaction_never_crashes(tmp_path, bad):
    session = Session(tmp_path / "sessions")
    session.log("x", content=[{"type": "image_url", "image_url": {"url": bad}}])
    assert "图片" in (session.dir / "log.jsonl").read_text(encoding="utf-8")
