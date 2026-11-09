"""发给模型的消息布局：每轮开头一张快照，轮内只追加，一轮结束后折叠成"用户原话 + 一条简短回复"。

这样同一轮里第 k+1 次调用的开头和第 k 次完全相同，服务端的前缀缓存才用得上（见设计文档第 5 节）。
"""

from __future__ import annotations

import json

USER_HEADER = "【用户说】"
CONFIRM_COMPACT = "（已把需求单发给用户确认）"
CHANGE_PREFIX = "本版变化："
WARNING_THRESHOLD = 5  # 本轮工具调用只剩这么多次或更少时，开始在工具返回里提醒


def compact_text(kind: str, text: str) -> str:
    """旧轮折叠后保留的 assistant 文字：按本轮结局决定（提示词文档第 3 节）。"""
    if kind == "confirm":
        return CONFIRM_COMPACT
    if kind == "delivered":
        lines = text.splitlines()
        kept = lines[:1]
        change = next((line for line in lines if line.startswith(CHANGE_PREFIX)), None)
        if change is not None:
            kept.append(change)
        return "\n".join(kept)
    return text  # question、reply、failed：给用户看的文字原样保留


def with_warning(content: str, calls_left: int) -> str:
    """剩余工具调用次数不多时，给工具返回的 JSON 对象加一个 warning 字段；其他内容原样返回。"""
    if calls_left > WARNING_THRESHOLD:
        return content
    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        return content
    if not isinstance(data, dict):
        return content
    data["warning"] = f"本轮工具调用只剩 {max(calls_left, 0)} 次"
    return json.dumps(data, ensure_ascii=False)


class Context:
    def __init__(self, system_prompt: str) -> None:
        self._system = {"role": "system", "content": system_prompt}
        self._past: list[dict] = []         # 之前各轮的折叠版：user（原话）+ assistant
        self._raw_user: str | None = None   # 本轮用户原话（折叠时用）
        self._turn_user: dict | None = None  # 本轮的 user 消息（快照 + 原话）
        self._current: list[dict] = []      # 本轮已发生的 assistant / tool 消息

    def start_turn(self, user_content: str, snapshot: str) -> None:
        self._raw_user = user_content
        self._turn_user = {"role": "user", "content": f"{snapshot}\n\n{USER_HEADER}\n{user_content}"}
        self._current = []

    def append(self, message: dict) -> None:
        self._current.append(message)

    def end_turn(self, kind: str, text: str) -> None:
        if self._raw_user is None:
            return
        self._past += [{"role": "user", "content": self._raw_user}, {"role": "assistant", "content": compact_text(kind, text)}]
        self._raw_user, self._turn_user, self._current = None, None, []

    def messages(self) -> list[dict]:
        """返回新列表：system；旧轮的折叠版；本轮 user（快照在前、原话在后）；本轮追加的消息。"""
        turn = [self._turn_user] if self._turn_user is not None else []
        return [self._system, *self._past, *turn, *self._current]
