"""多零件的参数直改（设计文档第 7.6 节）：改过的参数影响到的零件全部重做（各自所有步骤），再装配检查；
全过才存成新版本，不做扰动验证。没过就全部退回原来的数值。
"""

from __future__ import annotations

import copy
import dataclasses
from typing import TYPE_CHECKING

from ..agent.manual import FAILED, NOT_AVAILABLE, ManualResult, _check_values, _fmt, _log
from ..staged.build import advance
from ..staged.final_gate import coverage_gaps
from .checks import evaluate, mandatory_checks
from .delivery import export_product_version
from .gate import users_of
from .workspace import select_part

if TYPE_CHECKING:
    from ..agent.loop import Agent


def _failed(results: list) -> list[dict]:
    return [{"id": r.id, "type": r.type, "expected": r.expected, "measured": r.measured, "tol": r.tol, "detail": r.detail}
            for r in results if not r.passed]


def apply_params_multi(agent: "Agent", values: dict[str, float]) -> ManualResult:
    ws, box = agent.ws, agent.toolbox
    if not ws.assembly_passed or not all(st.done for st in ws.parts.values()) or not agent.session.versions():
        return ManualResult(ok=False, text=NOT_AVAILABLE)
    problem = _check_values(agent, values)
    if problem is not None:
        return ManualResult(ok=False, text=problem)
    active = ws.active
    select_part(ws, active)
    backup = (copy.deepcopy(ws.brief), {pid: (st.plan.to_list(), list(st.results)) for pid, st in ws.parts.items()},
              ws.last_assembly, ws.last_run)

    def restore() -> None:
        ws.brief, plans, ws.last_assembly, ws.last_run = backup
        for pid, (plan, results) in plans.items():
            st = ws.parts[pid]
            st.plan, st.results, st.done = type(st.plan).from_list(plan), results, True
        ws.assembly_passed = True
        ws.active = None   # 不要把工作区里改过的计划存回去，直接换成恢复好的
        select_part(ws, active)

    changed = {n: float(v) for n, v in values.items() if float(v) != ws.brief.param_values()[n]}
    changes = []
    for i, p in enumerate(ws.brief.params):
        if p.name in changed:
            changes.append(f"手动修改参数：{p.name} {_fmt(p.value)} → {_fmt(changed[p.name])}（{p.unit}）")
            ws.brief.params[i] = dataclasses.replace(p, value=changed[p.name], source="user")
    affected = [pid for pid in ws.parts if any(pid in users_of(ws, n) for n in changed)]
    for pid in affected:
        select_part(ws, pid)
        ws.plan.invalidate_all()
        adv = advance(ws, box.run_job, timeout_s=box.timeout_s, secret_names=box.secret_names)
        if adv.reason != "complete" or coverage_gaps(ws):
            run = adv.runs[-1].run if adv.runs else None
            restore()
            _log(agent, values, False, None)
            return ManualResult(ok=False, text=FAILED, failed_checks=_failed(run.checks if run else []))
        ws.parts[pid].results = [r.to_dict() for r in adv.runs[-1].run.checks]
    select_part(ws, active)
    run = box.run_assembly(ws, mode="check", samples=box.motion_samples, timeout_s=box.timeout_s, secret_names=box.secret_names)
    results = evaluate(run, mandatory_checks(ws.assembly, list(ws.parts)) + ws.assembly_checks_raw, ws.assembly, ws.brief.param_values())
    if run.error is not None or not all(r.passed for r in results):
        restore()
        _log(agent, values, False, None)
        return ManualResult(ok=False, text=FAILED, failed_checks=_failed(results), error=run.error)
    exported = export_product_version(agent, changes)
    if isinstance(exported, str):
        restore()
        _log(agent, values, False, None)
        return ManualResult(ok=False, text=exported, changes=changes)
    agent._save()
    _log(agent, values, True, exported.name)
    return ManualResult(ok=True, text=f"已按新的参数重建，存为 {exported.name}。", version_dir=exported, changes=changes)
