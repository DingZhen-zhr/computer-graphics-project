"""程序代模型按按钮的判定（设计文档第 6 节 C1~C3）：什么时候自动请确认、自动重建，以及怎么识别"前面的调用出错了"。

这里只做判定，不调用工具；主循环（loop.py）按判定结果去做。
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from cad_agent.brief import Brief
from cad_agent.tools import Workspace

# C3：同一次回复里前面的调用出错、后面的 build 被跳过时，这个 build 的 tool 消息内容（提示词文档第 5 节）
SKIPPED_BUILD_MESSAGE = json.dumps(
    {"error": "同一次回复里前面的调用出错了，这次 build 没有运行，也不算失败。先改好出错的调用，再调用 build。"}, ensure_ascii=False
)
AUTO_BUILD_PREFIX = "auto-build-"
# C2：服务端不接受程序补的 tool_call（偏离 D6），所以自动 build 的结果用一条 user 消息交给模型
AUTO_BUILD_NOTE = "【程序自动运行了 build，结果如下】"


@dataclass(frozen=True)
class BriefShape:
    """需求单的"形状"：用来比较一次回复前后，改的是不是只有已有参数的数值。"""

    confirmed: bool
    names: frozenset[str]
    features: tuple[str, ...]
    values: tuple[tuple[str, float], ...]   # 按参数名排序


def brief_shape(brief: Brief) -> BriefShape:
    return BriefShape(
        confirmed=brief.confirmed,
        names=frozenset(p.name for p in brief.params),
        features=tuple(brief.features),
        values=tuple(sorted((p.name, p.value) for p in brief.params)),
    )


def has_error(content: str) -> bool:
    """工具返回的是 JSON 对象，有 "error" 键且值不是 None。"""
    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        return False
    return isinstance(data, dict) and data.get("error") is not None


def should_auto_confirm(ws: Workspace, calls: list[tuple[str, bool]]) -> bool:
    """C1。calls：这次回复里执行过的每个工具调用（工具名, 成功与否）。"""
    names = [name for name, _ in calls]
    return (
        not ws.brief.confirmed
        and any(name == "update_brief" and ok for name, ok in calls)
        and "ask_user" not in names
        and "request_confirmation" not in names
        and bool(ws.brief.params)
        and not ws.brief.open_questions
    )


def should_auto_build(ws: Workspace, calls: list[tuple[str, bool]], before: BriefShape) -> bool:
    """C2。before：执行这次回复里的工具之前的需求单形状。"""
    now = brief_shape(ws.brief)
    return (
        before.confirmed
        and now.confirmed
        and bool(calls)
        and all(name == "update_brief" and ok for name, ok in calls)
        and now.names == before.names
        and now.features == before.features
        and now.values != before.values
        and not ws.brief.open_questions
        and bool(ws.features.items)
        and bool(ws.checks_raw)
    )


def should_build_before_reply(ws: Workspace, unbuilt_edits: bool, used_this_turn: bool) -> bool:
    """建模阶段模型用纯文字结束一轮、但还有没 build 的改动时，程序先替它 build 一次（每轮最多一次）。"""
    return (
        unbuilt_edits
        and not used_this_turn
        and ws.brief.can_build()[0]
        and bool(ws.features.items)
        and bool(ws.checks_raw)
    )
