"""多零件的流程：零件做完、换下一个零件、装配、产品终检、交付（设计文档第 5 节）。

主循环只在几个地方调用 ProductFlow；需求单不是多零件时它什么都不做，第二版的流程逐字不变。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ..agent.delivery import mutation_line
from .delivery import export_product_version, product_delivery_text
from .gate import run_product_gate
from .tools import invalidate_assembly
from .workspace import ensure_parts, select_part

if TYPE_CHECKING:
    from ..agent.loop import Agent
    from ..tools import ToolBox

__all__ = ["ProductFlow", "export_product_version", "finish_part", "part_finished", "run_product_gate"]
PART_HEAD = "【零件已做完（程序生成）】"
NEXT_PART = "现在做零件 {id} {name}。先用 set_plan 把它拆成几步。"
ALL_PARTS = "全部零件都做完了。现在装配：先用 set_connectors 给每个零件声明连接点，再 set_assembly、set_assembly_checks，最后 build_assembly。"
EDIT_TOOLS = ("set_plan", "upsert_feature", "remove_feature", "set_checks")
FAIL_TEXT = ("装配已经连续没通过 {n} 次，我先停下来，免得越改越乱。最后一次的问题：\n{why}\n"
             "你可以告诉我怎么调整（比如改尺寸、改动的范围），或者说「继续」让我再试。")


def _g(v: float) -> str:
    return f"{round(float(v), 3):g}"


def part_finished(box: "ToolBox") -> bool:
    """当前零件的计划全部通过，而且它自己的终检通过。"""
    ws = box.ws
    return (ws.active is not None and ws.plan is not None and ws.plan.complete()
            and box.last_gate is not None and box.last_gate.passed)


def finish_part(agent: "Agent") -> str:
    """标记当前零件做完，生成小结（提示词文档 4.1），切到下一个没做完的零件。返回小结。"""
    ws = agent.ws
    pid = ws.active
    st = ws.parts[pid]
    st.done = True
    run = ws.last_run
    st.results = [r.to_dict() for r in run.checks] if run is not None else []
    size = (run.facts.get("size") if run is not None else None) or [0, 0, 0]
    info = next(p for p in ws.brief.parts if p.id == pid)
    text = "\n".join([f"{PART_HEAD}{pid} {info.name}",
                      f"步骤：{'、'.join(s.title for s in ws.plan.stages)}",
                      f"检查：{len(st.results)} 项，全部通过。外形：{' × '.join(_g(v) for v in size)}"])
    nxt = next((p for p in ws.brief.parts if not ws.parts[p.id].done), None)
    if nxt is not None:
        select_part(ws, nxt.id)
        text += "\n\n" + NEXT_PART.format(id=nxt.id, name=nxt.name)
    else:
        select_part(ws, pid)
        text += "\n\n" + ALL_PARTS
    agent.session.log("part_done", id=pid, name=info.name)
    return text


class ProductFlow:
    def __init__(self, agent: "Agent") -> None:
        self.agent = agent
        self._summary: str | None = None   # 零件做完的小结：等这次回复的工具都执行完再折叠

    @property
    def ws(self):  # noqa: ANN201 - Workspace
        return self.agent.ws

    def active(self) -> bool:
        return self.ws.brief.is_multipart()

    def begin_turn(self) -> None:
        if self.active() and self.ws.brief.can_build()[0]:
            ensure_parts(self.ws)

    def total_cap(self, per_part: int) -> int:
        """工具调用总上限：多零件时每个零件一份，装配再加 100。"""
        return per_part * len(self.ws.brief.parts) + 100 if self.active() else per_part

    def after_call(self, name: str, ok: bool) -> None:
        """改了一个已经做完的零件（Review Focus 5）：这个零件要重新验证，装配和运动检查也要重跑。"""
        ws = self.ws
        if ok and name in EDIT_TOOLS and self.active() and ws.active in ws.parts and ws.parts[ws.active].done:
            ws.parts[ws.active].done = False
            invalidate_assembly(ws)

    def part_ready(self, c: Any) -> None:
        """当前零件的 build 全过（含它自己的终检）：收起来，换下一个零件；本轮的往来等这次回复执行完再折叠。"""
        if not part_finished(self.agent.toolbox):
            return
        self._summary = finish_part(self.agent)
        c.stage_tool_calls = 0
        self.agent.toolbox.build_failures = 0

    def maybe_fold(self) -> None:
        if self._summary is not None:
            self.agent.context.fold(self._summary)
            self._summary = None

    def deliver(self, c: Any) -> Any:
        agent = self.agent
        exported = export_product_version(agent, agent._pending_changes)
        if isinstance(exported, str):
            return agent._end("failed", exported, c)
        changes, agent._pending_changes = agent._pending_changes, []
        gate = agent.toolbox.last_gate
        text = product_delivery_text(self.ws, exported, changes, mutation_line(gate) if gate is not None else None)
        return agent._end("delivered", text, c, version_dir=exported, extra={"changes": changes, "parts": len(self.ws.brief.parts)})

    def failed(self, content: str, c: Any) -> Any:
        import json

        body = json.loads(content)
        why = "\n".join(f"- {f['detail']}" for f in body.get("failed_checks", [])[:3]) or f"- {body.get('hint', '')}"
        return self.agent._end("failed", FAIL_TEXT.format(n=self.agent.toolbox.build_failures, why=why), c)

    def log_assembly(self, content: str) -> None:
        import json

        body = json.loads(content)
        if "passed" in body:
            first = body["failed_checks"][0]["detail"] if body["failed_checks"] else (body.get("error") or {}).get("message")
            self.agent.session.log("assembly", passed=body["passed"], failed=[f["id"] for f in body["failed_checks"]],
                                   hits=body["hits"], reason=first)
