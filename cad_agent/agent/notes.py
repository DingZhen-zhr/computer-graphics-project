"""智能体工作时用户补充的话：界面线程放进来，主循环在下一次调用模型前取走（计划 6 Task 2）。"""

from __future__ import annotations

import threading


class NoteBox:
    """线程安全的信箱，按先后顺序取。"""

    def __init__(self) -> None:
        self._mu = threading.Lock()
        self._items: list[str] = []

    def put(self, text: str) -> None:
        with self._mu:
            self._items.append(text)

    def drain(self) -> list[str]:
        """取出全部并清空。"""
        with self._mu:
            items, self._items = self._items, []
            return items
