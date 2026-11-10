"""终检（设计文档第 3.6 节）：最后一个阶段通过后，程序检查每个用户参数都有检查用到。

Task 7 的临时版本：只算缺检查；参数扰动验证由 Task 8 加上。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Callable, Iterable

from cad_agent.checks.spec import missing_coverage, parse_checks
from cad_agent.gates import Gates
from cad_agent.sandbox.execute import RunResult
from cad_agent.staged.select import final_checks

if TYPE_CHECKING:
    from cad_agent.tools import Workspace


@dataclass
class GateResult:
    passed: bool
    missing_coverage: list[str]
    mutation: list[Any] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)

    @property
    def unconstrained(self) -> list[str]:
        return [m.param for m in self.mutation if m.verdict == "unconstrained"]

    @property
    def unbuildable(self) -> list[str]:
        return [m.param for m in self.mutation if m.verdict == "unbuildable"]

    def to_dict(self) -> dict:
        return {"missing_coverage": list(self.missing_coverage), "unconstrained": self.unconstrained,
                "unbuildable": self.unbuildable, "skipped": list(self.skipped), "mutation": []}


def coverage_gaps(ws: "Workspace") -> list[str]:
    """哪些用户参数没有被任何 from_here 检查用到（按最终模型要跑的检查算）。"""
    checks = parse_checks(final_checks(ws), set(ws.brief.param_values()))
    return sorted(missing_coverage([c for c in checks if c.holds == "from_here"], ws.brief.user_param_names()))


def run_final_gate(ws: "Workspace", run_job: Callable[..., RunResult], gates: Gates, *,
                   timeout_s: float, secret_names: Iterable[str]) -> GateResult:
    missing = coverage_gaps(ws)
    return GateResult(passed=not missing, missing_coverage=missing)
