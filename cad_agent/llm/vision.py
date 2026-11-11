"""图片消息和识图测试。

内部约定：消息的 content 可以是文字，也可以是由 text_part、image_part 组成的数组（OpenAI 的写法）。
OpenAICompatLLM 原样发出；AnthropicLLM 转成它的图片块（见 anthropic_convert.py）。
日志里不记图片的内容，只记"图片 <字节数> 字节"（redact_images）。
"""

from __future__ import annotations

import base64
import binascii
import re
import struct
import zlib
from pathlib import Path
from typing import Any

from cad_agent.llm.client import LLM, LLMError

VISION_QUESTION = "这张图片左半边和右半边各是什么颜色？只回答两个颜色的名字。"
VISION_OK = "这个模型能看图，看图审查已经可以用了。"
VISION_WRONG = "这个模型没有认出测试图片，看图审查不会启用。"
VISION_ERROR = "这个模型不接受图片（{reason}），看图审查不会启用。"
TEST_IMAGE_SIZE = 64
_DATA_URL = re.compile(r"^data:image/[a-z0-9.+-]+;base64,(.*)$", re.IGNORECASE | re.DOTALL)


def image_part(png_path: Path) -> dict:
    data = base64.b64encode(Path(png_path).read_bytes()).decode("ascii")
    return {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{data}"}}


def text_part(text: str) -> dict:
    return {"type": "text", "text": text}


def _png(width: int, height: int, rows: list[bytes]) -> bytes:
    def chunk(tag: bytes, body: bytes) -> bytes:
        return struct.pack(">I", len(body)) + tag + body + struct.pack(">I", zlib.crc32(tag + body) & 0xFFFFFFFF)

    raw = b"".join(b"\x00" + row for row in rows)   # 每行前面一个"不过滤"标记
    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)   # 8 位 RGB
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b"")


def tiny_test_image() -> bytes:
    """程序生成的 64×64 PNG：左半红、右半蓝。只用标准库，每次生成的字节都一样。"""
    half = TEST_IMAGE_SIZE // 2
    row = b"\xff\x00\x00" * half + b"\x00\x00\xff" * (TEST_IMAGE_SIZE - half)
    return _png(TEST_IMAGE_SIZE, TEST_IMAGE_SIZE, [row] * TEST_IMAGE_SIZE)


def _answer_ok(text: str) -> bool:
    low = text.lower()
    return ("红" in text and "蓝" in text) or ("red" in low and "blue" in low)


def test_vision(llm: LLM) -> tuple[bool, str]:
    """发一张测试图问颜色，不带工具。回答里同时有红和蓝（或 red 和 blue）算能识图；接口报错算不能，不抛异常。

    这一步会调用真实模型、花用户自己的钱，所以只在用户点"测试识图"时运行。
    """
    data = base64.b64encode(tiny_test_image()).decode("ascii")
    content = [{"type": "image_url", "image_url": {"url": f"data:image/png;base64,{data}"}}, text_part(VISION_QUESTION)]
    try:
        reply = llm.chat([{"role": "user", "content": content}], [])
    except LLMError as e:
        return False, VISION_ERROR.format(reason=str(e)[:80])
    return (True, VISION_OK) if _answer_ok(reply.content or "") else (False, VISION_WRONG)


test_vision.__test__ = False   # type: ignore[attr-defined]  # 名字以 test 开头，告诉 pytest 这不是测试


def _image_summary(part: dict) -> str:
    url = str((part.get("image_url") or {}).get("url", ""))
    m = _DATA_URL.match(url)
    if m is None:
        return "图片（不是内嵌的图片数据）"
    try:
        size = len(base64.b64decode(m.group(1), validate=True))
    except (binascii.Error, ValueError):
        return "图片（数据不完整）"
    return f"图片 {size} 字节"


def redact_images(value: Any) -> Any:
    """写日志前用：把所有图片块换成"图片 <字节数> 字节"，其余原样。"""
    if isinstance(value, dict):
        if value.get("type") == "image_url":
            return _image_summary(value)
        return {k: redact_images(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [redact_images(v) for v in value]
    return value
