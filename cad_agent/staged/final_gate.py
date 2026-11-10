"""终检（设计文档第 3.6 节的 (1)、(2) 项）：最后一个阶段通过后，程序先看每个用户参数都有 from_here 的检查用到，
再做参数扰动验证。看图审查（第 (3) 项）在计划 2 里做。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Callable, Iterable

from cad_agent.checks.spec import missing_coverage, parse_checks
from cad_agent.gates import Gates
from cad_agent.sandbox.execute import RunResult
from cad_agent.staged.mutation import MutationResult, run_mutation
from cad_agent.staged.select import final_checks

if TYPE_CHECKING:
    from cad_agent.tools import Workspace


@dataclass
class GateResult:
    passed: bool
    missing_coverage: list[str]
    mutation: list[MutationResult] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)   # 超过 12 个而没有扰动的参数

    @property
    def unconstrained(self) -> list[str]:
        return [m.param for m in self.mutation if m.verdict == "unconstrained"]

    @property
    def unbuildable(self) -> list[str]:
        return [m.param for m in self.mutation if m.verdict == "unbuildable"]

    def to_dict(self) -> dict:
        return {"missing_coverage": list(self.missing_coverage), "unconstrained": self.unconstrained,
                "unbuildable": self.unbuildable, "skipped": list(self.skipped),
                "mutation": [{"param": m.param, "verdict": m.verdict, "tried": list(m.tried), "caught_by": list(m.caught_by)}
                             for m in self.mutation]}


def coverage_gaps(ws: "Workspace") -> list[str]:
    """哪些用户参数没有被任何 from_here 检查用到（按最终模型要跑的检查算）。"""
    checks = parse_checks(final_checks(ws), set(ws.brief.param_values()))
    return sorted(missing_coverage([c for c in checks if c.holds == "from_here"], ws.brief.user_param_names()))


def run_final_gate(ws: "Workspace", run_job: Callable[..., RunResult], gates: Gates, *,
                   timeout_s: float, secret_names: Iterable[str]) -> GateResult:
    """先算缺检查，有缺的就不做扰动；开关 mutation_check 关掉时也不做。通过 = 不缺检查且没有 unconstrained。"""
    missing = coverage_gaps(ws)
    if missing or not gates.mutation_check:
        return GateResult(passed=not missing, missing_coverage=missing)
    results, skipped = run_mutation(ws, run_job, timeout_s=timeout_s, secret_names=secret_names)
    gate = GateResult(passed=True, missing_coverage=[], mutation=results, skipped=skipped)
    gate.passed = not gate.unconstrained
    return gate
