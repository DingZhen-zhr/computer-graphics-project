"""多零件工作区：每个零件各有一套特征、检查、计划；切换零件时整体换进换出（设计文档第 5 节）。

换进来之后，第二版的分阶段工具、build、probe 照常作用于 ws.features 等字段，就是当前零件。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from ..notebook import FeatureList
from ..plan import Plan
from .model import Connector, ProductError

if TYPE_CHECKING:
    from ..tools import Workspace

SWAP_FIELDS = ("features", "checks_raw", "plan", "probes_used", "last_build_content")


@dataclass
class PartState:
    features: FeatureList
    checks_raw: list[dict]
    plan: Plan | None = None
    probes_used: int = 0
    last_build_content: str | None = None
    done: bool = False
    connectors: list[Connector] = field(default_factory=list)
    results: list[dict] = field(default_factory=list)   # 做完时最后一次 build 的检查结果（交付时写进 checks.json）


def _store(ws: "Workspace") -> None:
    """把工作区当前的字段存回当前零件。"""
    if ws.active is not None and ws.active in ws.parts:
        st = ws.parts[ws.active]
        for name in SWAP_FIELDS:
            setattr(st, name, getattr(ws, name))


def _load(ws: "Workspace", part_id: str) -> None:
    st = ws.parts[part_id]
    for name in SWAP_FIELDS:
        setattr(ws, name, getattr(st, name))
    ws.active = part_id


def select_part(ws: "Workspace", part_id: str) -> None:
    """切换到零件 part_id：先把当前零件存回去，再换成它。"""
    if part_id not in ws.parts:
        have = "、".join(ws.parts) or "（没有）"
        raise ProductError(f"没有零件 {part_id!r}。现在的零件：{have}")
    _store(ws)
    _load(ws, part_id)


def ensure_parts(ws: "Workspace") -> None:
    """按需求单的 parts 建好各零件；需求单里没有的零件，没有特征才删掉。当前零件设成第一个没做完的。"""
    first_time = ws.active is None
    _store(ws)
    for p in ws.brief.parts:
        if p.id not in ws.parts:
            if first_time and not ws.parts:   # 第一次：工作区里原有的内容归第一个零件
                ws.parts[p.id] = PartState(ws.features, ws.checks_raw, ws.plan, ws.probes_used, ws.last_build_content)
            else:
                ws.parts[p.id] = PartState(FeatureList(), [])
    wanted = [p.id for p in ws.brief.parts]
    for pid in [k for k in ws.parts if k not in wanted]:
        if not ws.parts[pid].features.items:
            del ws.parts[pid]
    order = [k for k in wanted if k in ws.parts] + [k for k in ws.parts if k not in wanted]
    ws.parts = {k: ws.parts[k] for k in order}
    target = next((k for k in order if not ws.parts[k].done), order[0] if order else None)
    if target is not None:
        _load(ws, target)


def part_param_names(ws: "Workspace", part_id: str) -> list[str]:
    """这个零件能用的参数：产品参数 + 它自己的参数，按需求单里的顺序。"""
    return [p.name for p in ws.brief.params if p.part is None or p.part == part_id]


def product_state(ws: "Workspace") -> dict[str, Any] | None:
    """保存用：各零件的特征、检查、计划、连接点，装配声明和装配检查。单零件返回 None。"""
    if not ws.parts:
        return None
    _store(ws)
    return {
        "active": ws.active,
        "parts": {pid: {"features": st.features.to_list(), "checks": st.checks_raw,
                        "plan": st.plan.to_list() if st.plan is not None else None, "done": st.done, "results": st.results,
                        "connectors": [c.to_dict() for c in st.connectors]} for pid, st in ws.parts.items()},
        "assembly": ws.assembly.to_dict() if ws.assembly is not None else None,
        "assembly_checks": ws.assembly_checks_raw,
        "assembly_passed": ws.assembly_passed,
    }


def restore_product(ws: "Workspace", data: dict[str, Any]) -> None:
    """product_state 的反过程（恢复会话用）。装配声明重新校验；校验不过就当没有。"""
    from .spec import parse_assembly, parse_connectors   # 放这里：spec 依赖 checks，避免导入时转圈

    names = {p.name for p in ws.brief.params}
    ws.parts = {}
    for pid, raw in (data.get("parts") or {}).items():
        plan = Plan.from_list(raw["plan"]) if raw.get("plan") else None
        st = PartState(FeatureList.from_list(raw.get("features") or []), list(raw.get("checks") or []), plan,
                       done=bool(raw.get("done")), results=list(raw.get("results") or []))
        try:
            st.connectors = parse_connectors(pid, raw.get("connectors") or [], names)
        except ProductError:
            st.connectors = []
        ws.parts[pid] = st
    if data.get("assembly"):
        cons = {pid: st.connectors for pid, st in ws.parts.items()}
        try:
            ws.assembly = parse_assembly(data["assembly"], list(ws.parts), cons, names)
        except ProductError:
            ws.assembly = None
    ws.assembly_checks_raw = list(data.get("assembly_checks") or [])
    ws.assembly_passed = bool(data.get("assembly_passed")) and ws.assembly is not None
    active = data.get("active")
    ws.active = None
    if active in ws.parts:
        _load(ws, active)
    elif ws.parts:
        _load(ws, next(iter(ws.parts)))
