"""参数直改的内核部分（设计文档第 3.8 节）：交付之后用户直接改参数数值，程序重新验证全部阶段，不调用大模型。

全过就存成新版本；没过就退回原来的数值，什么都不留。不做参数扰动验证，也不做看图审查。
"""

from __future__ import annotations

import copy
import dataclasses
import math
import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from cad_agent.agent.delivery import export_version
from cad_agent.staged.build import advance
from cad_agent.staged.final_gate import coverage_gaps
from cad_agent.tool_common import _error_for_model

if TYPE_CHECKING:
    from cad_agent.agent.loop import Agent

NOT_AVAILABLE = "现在还不能直接改参数：要先交付过一个版本。"
FAILED = "改成这些数值后模型没有通过检查，已经退回原来的数值。"   # 第二版提示词文档第 9 节


@dataclass
class ManualResult:
    ok: bool
    text: str                       # 给界面显示的一句话
    version_dir: Path | None = None
    changes: list[str] = field(default_factory=list)
    failed_checks: list[dict] = field(default_factory=list)   # 和 build 返回里的 failed_checks 相同格式
    error: dict | None = None


def _fmt(v: float) -> str:
    return f"{v:g}"


def _check_values(agent: "Agent", values: dict[str, float]) -> str | None:
    """数值有问题时返回给界面的一句话；没问题返回 None。"""
    current = agent.ws.brief.param_values()
    for name, v in values.items():
        if name not in current:
            return f"没有参数 {name}。"
        if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v):
            return f"参数 {name} 的数值必须是有限的数，收到 {v!r}。"
    if all(float(v) == current[n] for n, v in values.items()):
        return "这些数值和现在的一样，没有要改的。"
    return None


def _log(agent: "Agent", values: dict[str, float], ok: bool, version: str | None) -> None:
    agent.session.log("manual", values=values, ok=ok, version=version)


def _restore(agent: "Agent", backup: tuple) -> None:
    ws, box = agent.ws, agent.toolbox
    ws.brief, plan_list, ws.probes_used, ws.last_run, ws.last_build_content, box.last_advance = backup
    ws.plan = type(ws.plan).from_list(plan_list)


def apply_params(agent: "Agent", values: dict[str, float]) -> ManualResult:
    ws, box = agent.ws, agent.toolbox
    if not box.gates.staged or ws.plan is None or not ws.plan.complete() or not agent.session.versions():
        return ManualResult(ok=False, text=NOT_AVAILABLE)
    problem = _check_values(agent, values)
    if problem is not None:
        return ManualResult(ok=False, text=problem)

    backup = (copy.deepcopy(ws.brief), ws.plan.to_list(), ws.probes_used, ws.last_run, ws.last_build_content, box.last_advance)
    changed = {n: float(v) for n, v in values.items() if float(v) != ws.brief.param_values()[n]}
    changes = []
    for i, p in enumerate(ws.brief.params):
        if p.name in changed:
            changes.append(f"手动修改参数：{p.name} {_fmt(p.value)} → {_fmt(changed[p.name])}（{p.unit}）")
            ws.brief.params[i] = dataclasses.replace(p, value=changed[p.name], source="user")
    ws.plan.invalidate_all()

    with tempfile.TemporaryDirectory(prefix="cad-agent-manual-") as tmp:   # 阶段 STL 先放临时目录，通过了才换上
        stl_dir = Path(tmp) / "stages"
        adv = advance(ws, box.run_job, timeout_s=box.timeout_s, secret_names=box.secret_names, stl_dir=stl_dir)
        if adv.reason != "complete" or coverage_gaps(ws):
            run = adv.runs[-1].run if adv.runs else None
            _restore(agent, backup)
            _log(agent, values, False, None)
            failed = [{"id": c.id, "type": c.type, "expected": c.expected, "measured": c.measured, "tol": c.tol, "detail": c.detail}
                      for c in (run.checks if run else []) if not c.passed]
            return ManualResult(ok=False, text=FAILED, failed_checks=failed,
                                error=_error_for_model(run.error) if run and run.error else None)
        ws.last_run, box.last_advance = adv.runs[-1].run, adv
        if box.stage_dir is not None:
            for stl in stl_dir.glob("*.stl"):
                Path(box.stage_dir).mkdir(parents=True, exist_ok=True)
                shutil.copyfile(stl, Path(box.stage_dir) / stl.name)

    exported = export_version(box, agent.session, changes, extra_json={"plan": ws.plan.to_list()}, stages_src=box.stage_dir)
    if isinstance(exported, str):
        _restore(agent, backup)
        _log(agent, values, False, None)
        return ManualResult(ok=False, text=exported, changes=changes)
    version, _ = exported
    agent._save()   # 会话目录里的需求单、计划也换成新的
    _log(agent, values, True, version.name)
    return ManualResult(ok=True, text=f"已按新的参数重建，存为 {version.name}。", version_dir=version, changes=changes)
