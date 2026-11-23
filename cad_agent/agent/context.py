"""发给模型的消息布局：每轮开头一张快照，轮内只追加，一轮结束后折叠成"用户原话 + 一条简短回复"。

这样同一轮里第 k+1 次调用的开头和第 k 次完全相同，服务端的前缀缓存才用得上（见设计文档第 5 节）。
"""

from __future__ import annotations

import json

USER_HEADER = "【用户说】"
NOTE_HEADER = "【你工作时用户补充的话，先看这条再继续】"
NOTE_MARK = "（中途补充）"
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


def with_warning(content: str, calls_left: int, text: str | None = None) -> str:
    """剩余工具调用次数不多时，给工具返回的 JSON 对象加一个 warning 字段；其他内容原样返回。

    text 是 warning 的文字（分阶段时按阶段算，见第二版提示词文档 7.4）；不给就用旧流程的写法。
    """
    if calls_left > WARNING_THRESHOLD:
        return content
    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        return content
    if not isinstance(data, dict):
        return content
    data["warning"] = text if text is not None else f"本轮工具调用只剩 {max(calls_left, 0)} 次"
    return json.dumps(data, ensure_ascii=False)


class Context:
    def __init__(self, system_prompt: str) -> None:
        self._system = {"role": "system", "content": system_prompt}
        self._past: list[dict] = []         # 之前各轮的折叠版：user（原话）+ assistant
        self._raw_user: str | None = None   # 本轮用户原话（折叠时用）
        self._turn_user: dict | None = None  # 本轮的 user 消息（快照 + 原话）
        self._current: list[dict] = []      # 本轮已发生的 assistant / tool 消息
        self._fold_at = 0                    # 分阶段时：本轮里上一个折叠点（_current 里的位置）
        self._notes: list[tuple[str, dict]] = []         # 本轮用户中途补充的话（折叠时保留）

    def restore(self, past: list[dict]) -> None:
        """直接设置"之前各轮的折叠版"（从会话目录恢复时用）。"""
        self._past = [dict(m) for m in past]

    def start_turn(self, user_content: str, snapshot: str) -> None:
        self._raw_user = user_content
        self._turn_user = {"role": "user", "content": f"{snapshot}\n\n{USER_HEADER}\n{user_content}"}
        self._current = []
        self._fold_at = 0
        self._notes = []

    def add_note(self, text: str) -> None:
        """用户在这一轮进行中补充的一句话：作为一条 user 消息追加，折叠和本轮结束时都保留。"""
        msg = {"role": "user", "content": f"{NOTE_HEADER}\n{text}"}
        self._notes.append((text, msg))
        self._current.append(msg)

    def fold(self, summary: str) -> None:
        """把本轮上一个折叠点之后的全部消息换成一条 user 消息（阶段小结），折叠点移到它后面。"""
        kept = [m for m in self._current[self._fold_at:] if any(m is n for _, n in self._notes)]
        self._current = self._current[: self._fold_at] + [{"role": "user", "content": summary}] + kept
        self._fold_at = len(self._current)

    def append(self, message: dict) -> None:
        self._current.append(message)

    def end_turn(self, kind: str, text: str) -> None:
        if self._raw_user is None:
            return
        said = "\n".join([self._raw_user] + [NOTE_MARK + t for t, _ in self._notes])
        self._past += [{"role": "user", "content": said}, {"role": "assistant", "content": compact_text(kind, text)}]
        self._raw_user, self._turn_user, self._current = None, None, []
        self._fold_at = 0

    def messages(self) -> list[dict]:
        """返回新列表：system；旧轮的折叠版；本轮 user（快照在前、原话在后）；本轮追加的消息。"""
        turn = [self._turn_user] if self._turn_user is not None else []
        return [self._system, *self._past, *turn, *self._current]
