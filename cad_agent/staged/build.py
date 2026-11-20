"""分阶段的 build：从当前阶段尽量往后推进（设计文档第 3.3 节），最后一个阶段通过后做终检。

每个阶段各跑一次截断的 notebook（只含到这个阶段为止的特征），最多 workers 个同时跑；按顺序看结果，
遇到第一个没通过的阶段就停下。返回给模型的 JSON 按第二版提示词文档 7.1、7.2 节组装。
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Iterable, Literal

from cad_agent.checks.spec import CheckSpecError, parse_checks
from cad_agent.notebook import NotebookError
from cad_agent.product.scope import render_scoped, scoped_params
from cad_agent.sandbox.execute import RunResult
from cad_agent.staged import messages as msg
from cad_agent.staged.final_gate import run_final_gate
from cad_agent.staged.select import checks_for_stage, features_upto, stage_ready
from cad_agent.tool_common import ToolOutcome, _err, _error_for_model, _hint, _json

if TYPE_CHECKING:
    from cad_agent.tools import ToolBox, Workspace


@dataclass
class StageRun:
    stage_id: str
    run: RunResult


@dataclass
class Advance:
    runs: list[StageRun]                 # 这次实际验证过的阶段，按顺序
    passed: list[str]                    # 这次新通过的阶段编号
    stopped: str | None                  # 停在哪个阶段；全部通过时 None
    reason: Literal["failed", "not_ready", "complete"]


def _run_stage(ws: "Workspace", stage_id: str, run_job: Callable[..., RunResult], timeout_s: float,
               secret_names: tuple[str, ...], stl_dir: Path | None) -> RunResult:
    """验证一个阶段。渲染或解析检查就出错时不运行，结果和旧流程 _build_without_run 的一样。"""
    params = scoped_params(ws)
    names = {p.name for p in params}
    checks = checks_for_stage(ws.checks_raw, ws.plan, stage_id)
    try:
        rendered = render_scoped(ws, params, features_upto(ws, stage_id))
        parse_checks(checks, names)
    except NotebookError as e:
        return RunResult(ok=False, error={"cell": e.feature, "type": "NotebookError", "message": str(e)})
    except CheckSpecError as e:
        return RunResult(ok=False, error={"cell": None, "type": "CheckSpecError", "message": str(e)})
    extra = {"export_stl": stl_dir / f"{stage_id}.stl"} if stl_dir is not None else {}
    return run_job(rendered, checks, names, mode="build", timeout_s=timeout_s, secret_names=secret_names, **extra)


def advance(ws: "Workspace", run_job: Callable[..., RunResult], *, timeout_s: float, secret_names: Iterable[str],
            stl_dir: Path | None = None, workers: int = 4) -> Advance:
    plan = ws.plan
    cur = plan.current()
    if cur is None:
        return Advance(runs=[], passed=[], stopped=None, reason="complete")
    ready: list[str] = []
    for s in plan.stages[plan.index(cur.id):]:
        if not stage_ready(ws, s.id):
            break
        ready.append(s.id)
    if not ready:
        return Advance(runs=[], passed=[], stopped=cur.id, reason="not_ready")
    secrets = tuple(secret_names)
    with ThreadPoolExecutor(max_workers=max(1, min(workers, len(ready)))) as pool:
        futures = [pool.submit(_run_stage, ws, sid, run_job, timeout_s, secrets, stl_dir) for sid in ready]
        results = [f.result() for f in futures]
    runs: list[StageRun] = []
    passed: list[str] = []
    for sid, run in zip(ready, results):
        runs.append(StageRun(sid, run))
        if not run.ok:  # 停在第一个没通过的阶段，它后面已经跑完的结果不要
            return Advance(runs=runs, passed=passed, stopped=sid, reason="failed")
        plan.mark_passed(sid)
        ws.probes_used = 0
        passed.append(sid)
    nxt = plan.current()
    if nxt is None:
        return Advance(runs=runs, passed=passed, stopped=None, reason="complete")
    return Advance(runs=runs, passed=passed, stopped=nxt.id, reason="not_ready")


def _body(box: "ToolBox", adv: Advance, gate: Any) -> dict:
    ws = box.ws
    run = adv.runs[-1].run if adv.runs else RunResult(ok=False, error=None)
    error = _error_for_model(run.error) if run.error else None
    failed = [
        {"id": c.id, "type": c.type, "expected": c.expected, "measured": c.measured, "tol": c.tol, "detail": c.detail}
        for c in run.checks if not c.passed
    ]
    missing = list(gate.missing_coverage) if gate is not None else []
    if error or run.timed_out or failed:
        hint = _hint(error, run.timed_out, failed, [])
    elif adv.reason != "complete":
        hint = msg.hint_stage_passed(adv.passed, ws.plan.current())
    elif missing:
        hint = _hint(None, False, [], missing)
    elif gate.unconstrained:
        hint = msg.hint_unconstrained(gate.unconstrained)
    else:
        hint = _hint(None, False, [], [])
    cur = ws.plan.current()
    body: dict[str, Any] = {
        "passed": bool(gate is not None and gate.passed),
        "error": error,
        "failed_checks": failed,
        "passed_checks": sum(1 for c in run.checks if c.passed),
        "missing_coverage": missing,
        "facts": {"size": run.facts["size"], "volume": run.facts["volume"]} if run.facts else None,
        "failures_left": max(0, box.max_build_failures - box.build_failures),
        "hint": hint,
        "stage": cur.id if cur else None,
        "stages_passed": list(adv.passed),
        "final_gate": None if gate is None else {k: gate.to_dict()[k] for k in ("missing_coverage", "unconstrained", "unbuildable")},
    }
    if missing:  # 和旧流程一样（偏离 D4）：缺检查时多放一个字段
        body["coverage_note"] = f"缺少检查的用户参数：{'、'.join(missing)}"
    return body


def build_tool(box: "ToolBox") -> ToolOutcome:
    ws = box.ws
    plan = ws.plan
    if plan.complete():  # 全部通过后再 build：把最后一个阶段重新验证一次
        plan.invalidate_from(plan.ids()[-1])
    cur = plan.current()
    if not ws.features.in_stage(cur.id):
        return _err(msg.build_no_features(cur.id))
    if not any(c.get("stage") == cur.id for c in ws.checks_raw):
        return _err(msg.build_no_checks(cur.id))
    adv = advance(ws, box.run_job, timeout_s=box.timeout_s, secret_names=box.secret_names, stl_dir=box.stage_dir)
    box.last_advance = adv
    box.unbuilt_edits = False
    if adv.runs:
        ws.last_run = adv.runs[-1].run
    if adv.passed:
        box.build_failures = 0
    gate = None
    if adv.reason == "failed":
        box.build_failures += 1
    elif adv.reason == "complete":
        gate = run_final_gate(ws, box.run_job, box.gates, timeout_s=box.timeout_s, secret_names=box.secret_names)
        box.last_gate = gate
        if gate.unconstrained:
            box.build_failures += 1
    body = _body(box, adv, gate)
    ws.last_build_content = _json(body)
    return ToolOutcome(ws.last_build_content, build=ws.last_run, deliverable=body["passed"])
