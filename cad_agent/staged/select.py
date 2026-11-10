"""某个阶段该用哪些特征和检查（设计文档第 3.3 节）。纯数据，不运行模型。"""

from __future__ import annotations

from cad_agent.notebook import Feature
from cad_agent.plan import Plan
from cad_agent.tools import Workspace


def _stage_pos(plan: Plan, stage: str | None) -> int | None:
    """检查或特征写的阶段在计划里的位置；没写阶段时算第一个阶段，计划里没有这个阶段时是 None。"""
    if not stage:
        return 0
    ids = plan.ids()
    return ids.index(stage) if stage in ids else None


def features_upto(ws: Workspace, stage_id: str) -> list[Feature]:
    """这个阶段和它前面各阶段的特征，保持原顺序。"""
    assert ws.plan is not None
    last = ws.plan.index(stage_id)
    return [f for f in ws.features.items if (pos := _stage_pos(ws.plan, f.stage)) is not None and pos <= last]


def checks_for_stage(checks_raw: list[dict], plan: Plan, stage_id: str) -> list[dict]:
    """验证这个阶段时要跑的检查：stage 不晚于它的 from_here 检查，加上它自己的 here_only 检查；保持原顺序。"""
    here = plan.index(stage_id)
    out = []
    for c in checks_raw:
        pos = _stage_pos(plan, c.get("stage"))
        if pos is None:
            continue
        if c.get("holds", "from_here") == "here_only":
            if pos == here:
                out.append(c)
        elif pos <= here:
            out.append(c)
    return out


def final_checks(ws: Workspace) -> list[dict]:
    """终检和交付用的检查：没有计划（旧流程）时原样返回全部检查；否则是最后一个阶段该跑的那些。"""
    if ws.plan is None:
        return ws.checks_raw
    return checks_for_stage(ws.checks_raw, ws.plan, ws.plan.ids()[-1])


def stage_ready(ws: Workspace, stage_id: str) -> bool:
    """这个阶段既有特征又有检查。"""
    return bool(ws.features.in_stage(stage_id)) and any(c.get("stage") == stage_id for c in ws.checks_raw)


def insert_index(ws: Workspace, stage_id: str) -> int:
    """这个阶段的新特征默认插在哪里：它最后一个特征后面；它还没有特征时，排在它前面的各阶段里最后一个特征后面；都没有时是 0。"""
    assert ws.plan is not None
    last = ws.plan.index(stage_id)
    idx = 0
    for i, f in enumerate(ws.features.items):
        pos = _stage_pos(ws.plan, f.stage)
        if pos is not None and pos <= last:
            idx = i + 1
    return idx
