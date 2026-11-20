"""参数扰动验证（设计文档第 3.6 节第 (2) 项）：把一个用户参数改掉，重建模型，检查的期望值冻结在原来的数值上。

至少一条检查不通过，说明这个参数被真正约束了；检查仍然全过，说明模型没用上它，或者没有检查管它。
改后建不出来就换个方向再试一次，还是不行就记为"无法扰动"，不挡交付。这一步不调用大模型。
"""

from __future__ import annotations

import dataclasses
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable, Iterable, Literal

from cad_agent.brief import Param
from cad_agent.checks.spec import MANDATORY_IDS
from cad_agent.notebook import NotebookError
from cad_agent.product.scope import gate_params, render_scoped, scoped_params
from cad_agent.sandbox.execute import RunResult
from cad_agent.staged.select import final_checks

if TYPE_CHECKING:
    from cad_agent.tools import Workspace

LIMIT = 12  # 最多扰动这么多个用户参数，多出来的按需求单里的顺序跳过


@dataclass(frozen=True)
class MutationResult:
    param: str
    verdict: Literal["constrained", "unconstrained", "unbuildable"]
    tried: tuple[float, ...]        # 实际试过的数值
    caught_by: tuple[str, ...]      # constrained 时：是哪些检查发现的


def perturbations(p: Param) -> list[float]:
    """按顺序要试的数值：0 改成 1；个数类的整数加 1（减 1 后还不小于 1 时再试减 1）；其余乘 1.2、乘 0.8。"""
    v = float(p.value)
    if v == 0:
        return [1.0]
    if p.unit == "1" and v.is_integer():
        return [v + 1] + ([v - 1] if v - 1 >= 1 else [])
    return [v * 1.2, v * 0.8]


def _mutate_one(ws: "Workspace", p: Param, run_job: Callable[..., RunResult], timeout_s: float,
                secret_names: tuple[str, ...]) -> MutationResult:
    scoped = scoped_params(ws)
    original = {q.name: float(q.value) for q in scoped}
    checks = final_checks(ws)
    tried: list[float] = []
    for value in perturbations(p):
        tried.append(value)
        params = [dataclasses.replace(q, value=value) if q.name == p.name else q for q in scoped]
        try:
            rendered = render_scoped(ws, params, ws.features.items)
        except NotebookError:
            continue  # 拼不出来也算这个方向建不出来
        run = run_job(rendered, checks, set(original), mode="build", check_values=dict(original),
                      timeout_s=timeout_s, secret_names=secret_names)
        if run.error is not None or run.timed_out or any(c.id in MANDATORY_IDS and not c.passed for c in run.checks):
            continue  # 建不出来：换个方向再试
        failed = tuple(c.id for c in run.checks if not c.passed)
        if failed:
            return MutationResult(p.name, "constrained", tuple(tried), failed)
        return MutationResult(p.name, "unconstrained", tuple(tried), ())
    return MutationResult(p.name, "unbuildable", tuple(tried), ())


def run_mutation(ws: "Workspace", run_job: Callable[..., RunResult], *, timeout_s: float,
                 secret_names: Iterable[str], workers: int = 4) -> tuple[list[MutationResult], list[str]]:
    """扰动前 LIMIT 个用户参数（按需求单里的顺序），各参数之间并行。返回 (结果, 超出上限没扰动的参数名)。"""
    users = [p for p in gate_params(ws) if p.source == "user"]
    chosen, skipped = users[:LIMIT], [p.name for p in users[LIMIT:]]
    if not chosen:
        return [], skipped
    secrets = tuple(secret_names)
    with ThreadPoolExecutor(max_workers=max(1, min(workers, len(chosen)))) as pool:
        futures = [pool.submit(_mutate_one, ws, p, run_job, timeout_s, secrets) for p in chosen]
        return [f.result() for f in futures], skipped
