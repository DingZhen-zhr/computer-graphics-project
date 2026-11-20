"""产品终检（设计文档第 5.6 节）：每个用户参数改一改，重做所有用到它的零件和装配，检查的期望值冻结在原来的数值上。

规则和第二版终检相同：先看每个用户参数都有检查用到，缺了就不扰动；至少一条检查不通过才算"管住了"；
改后建不出来换个方向，还不行记为"无法扰动"，不挡交付。
"""

from __future__ import annotations

import copy
import dataclasses
from concurrent.futures import ThreadPoolExecutor
from typing import TYPE_CHECKING

from ..checks.expr import expr_names
from ..checks.spec import MANDATORY_IDS, parse_checks
from ..notebook import NotebookError, _analyse
from ..plan import Plan
from ..staged.final_gate import GateResult
from ..staged.mutation import LIMIT, MutationResult, perturbations
from ..staged.select import final_checks
from .checks import evaluate, mandatory_checks
from .render import render_part_notebook
from .workspace import part_param_names, select_part

if TYPE_CHECKING:
    from ..tools import ToolBox, Workspace


def _part_ws(ws: "Workspace", pid: str) -> "Workspace":
    """某个零件的检查、计划拼成一个临时工作区（只给 final_checks 用）。"""
    from ..tools import Workspace

    st = ws.parts[pid]
    tmp = Workspace(ws.brief, st.features, st.checks_raw)
    tmp.plan = st.plan if isinstance(st.plan, Plan) else None
    return tmp


def users_of(ws: "Workspace", name: str) -> list[str]:
    """哪些零件用到了这个参数：零件自己的参数只属于它；产品参数看哪些零件的特征读了它。"""
    p = next(q for q in ws.brief.params if q.name == name)
    if p.part is not None:
        return [p.part]
    out = []
    for pid, st in ws.parts.items():
        reads: set[str] = set()
        for f in st.features.items:
            try:
                reads |= _analyse(f).reads
            except NotebookError:
                continue
        if name in reads:
            out.append(pid)
    return out


def product_coverage_gaps(ws: "Workspace") -> list[str]:
    """哪些用户参数没有被任何零件的检查、也没有被装配检查用到。"""
    refs: set[str] = set()
    for pid in ws.parts:
        names = set(part_param_names(ws, pid))
        refs |= {r for c in parse_checks(final_checks(_part_ws(ws, pid)), names) if c.holds == "from_here" for r in c.refs}
    for c in ws.assembly_checks_raw:
        for key in ("expected", "value"):
            if key in c:
                refs |= expr_names(c[key])
        for side in ("a", "b"):
            if isinstance(c.get(side), dict):
                for path, _, v in c[side]["where"]:
                    if path != "geom.type":
                        refs |= expr_names(v)
    return sorted(p.name for p in ws.brief.params if p.source == "user" and p.name not in refs)


def _mutate(box: "ToolBox", name: str) -> MutationResult:
    ws = box.ws
    p = next(q for q in ws.brief.params if q.name == name)
    original = ws.brief.param_values()
    tried: list[float] = []
    for value in perturbations(p):
        tried.append(value)
        brief = copy.deepcopy(ws.brief)
        brief.params = [dataclasses.replace(q, value=value) if q.name == name else q for q in brief.params]
        shadow = copy.copy(ws)
        shadow.brief = brief
        caught: list[str] = []
        built = True
        for pid in users_of(ws, name):
            try:
                rendered = render_part_notebook(shadow, pid)
            except NotebookError:
                built = False
                break
            checks = final_checks(_part_ws(ws, pid))
            run = box.run_job(rendered, checks, set(part_param_names(ws, pid)), mode="build", check_values=dict(original),
                              timeout_s=box.timeout_s, secret_names=box.secret_names)
            if run.error is not None or run.timed_out or any(c.id in MANDATORY_IDS and not c.passed for c in run.checks):
                built = False
                break
            caught += [f"{pid}.{c.id}" for c in run.checks if not c.passed]
        if not built:
            continue
        arun = box.run_assembly(ws, mode="check", samples=box.motion_samples, timeout_s=box.timeout_s,
                                secret_names=box.secret_names, values={name: value})
        results = evaluate(arun, mandatory_checks(ws.assembly, list(ws.parts)) + ws.assembly_checks_raw, ws.assembly, original)
        if arun.error is not None or arun.timed_out or not results[0].passed:
            continue   # 装不起来（零件出错、连接点挂不上）：换个方向
        caught += [f"assembly.{r.id}" for r in results if not r.passed]
        verdict = "constrained" if caught else "unconstrained"
        return MutationResult(name, verdict, tuple(tried), tuple(caught))
    return MutationResult(name, "unbuildable", tuple(tried), ())


def run_product_gate(box: "ToolBox", workers: int = 4) -> GateResult:
    ws = box.ws
    if ws.active is not None:
        select_part(ws, ws.active)   # 当前零件的字段存回 parts
    missing = product_coverage_gaps(ws)
    if missing or not box.gates.mutation_check:
        return GateResult(passed=not missing, missing_coverage=missing)
    users = [p.name for p in ws.brief.params if p.source == "user"]
    chosen, skipped = users[:LIMIT], users[LIMIT:]
    if not chosen:
        return GateResult(passed=True, missing_coverage=[], skipped=skipped)
    with ThreadPoolExecutor(max_workers=max(1, min(workers, len(chosen)))) as pool:
        results = list(pool.map(lambda n: _mutate(box, n), chosen))
    gate = GateResult(passed=True, missing_coverage=[], mutation=results, skipped=skipped)
    gate.passed = not gate.unconstrained
    return gate
