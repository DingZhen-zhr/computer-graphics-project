"""参数扰动验证（第二版计划 1 Task 8，假 run_job）。"""

import re
import threading

import pytest

from cad_agent.brief import Brief, Param
from cad_agent.checks.spec import CheckResult
from cad_agent.notebook import Feature, FeatureList
from cad_agent.plan import revise
from cad_agent.sandbox.execute import RunResult
from cad_agent.staged.mutation import LIMIT, MutationResult, perturbations, run_mutation
from cad_agent.tools import Workspace

MANDATORY = ("valid", "single_solid", "positive_volume")
VAR_RE = re.compile(r'^\s+(\w+) = scad\.var\("\w+", ([-0-9.e]+), unit="\w+"\)$', re.M)
INT_RE = re.compile(r"^\s+(\w+) = (-?[0-9.]+)$", re.M)


def values_in(text: str) -> dict[str, float]:
    """渲染出的 notebook 参数单元里的数值。"""
    params = text.split("# ---- params ----")[1].split("return")[0]
    out = {n: float(v) for n, v in VAR_RE.findall(params)}
    out.update({n: float(v) for n, v in INT_RE.findall(params)})
    return out


class FakeRun:
    """按改后的参数值决定结果：decide(参数名, 改后的值) 返回 "pass"、"fail:<检查 id>"、"error"、"timeout" 或 "mandatory"。"""

    def __init__(self, decide) -> None:
        self.decide = decide
        self.calls: list[dict] = []
        self.lock = threading.Lock()

    def __call__(self, rendered, checks_raw, param_names, **kw):
        vals = values_in(rendered.text)
        orig = kw["check_values"]
        changed = [n for n in vals if vals[n] != orig[n]]
        with self.lock:
            self.calls.append({"text": rendered.text, "values": vals, "changed": changed, "check_ids": [c["id"] for c in checks_raw], **kw})
        name = changed[0] if changed else None
        what = self.decide(name, vals.get(name)) if name else "pass"
        checks = [CheckResult(i, i, what != "mandatory", None, None, None, "") for i in MANDATORY]
        checks += [CheckResult(c["id"], c["type"], not (what == f"fail:{c['id']}"), 1.0, 1.0, 0.1, "") for c in checks_raw]
        if what == "error":
            return RunResult(ok=False, error={"cell": "base", "type": "SimpleCADError", "message": "建不出来"})
        if what == "timeout":
            return RunResult(ok=False, timed_out=True, error={"cell": None, "type": "TimeoutError", "message": "超时"})
        return RunResult(ok=all(c.passed for c in checks), error=None, checks=checks, values=vals)


def ws_with(params: list[Param]) -> Workspace:
    ws = Workspace(Brief(part_name="板", params=params, features=["板"], confirmed=True),
                   FeatureList([Feature("base", "build", "base = 1", "s1")]),
                   [{"id": "w", "type": "bbox", "axis": "x", "expected": "a", "stage": "s1"},
                    {"id": "pre", "type": "bbox", "axis": "x", "expected": "a", "stage": "s1", "holds": "here_only"},
                    {"id": "fin", "type": "bbox", "axis": "y", "expected": "b", "stage": "s2"}])
    ws.plan = revise(None, [{"title": "一", "done_when": "一"}, {"title": "二", "done_when": "二"}], {})
    return ws


def mm(name: str, v: float, source: str = "user") -> Param:
    return Param(name, v, "mm", source, "")


def go(ws, decide, **kw):
    return run_mutation(ws, decide if isinstance(decide, FakeRun) else FakeRun(decide), timeout_s=60, secret_names=(), **kw)


def test_perturbations_for_zero_and_small_counts():
    assert perturbations(Param("gap", 0, "mm", "user")) == [1.0]
    assert perturbations(Param("n", 1, "1", "user")) == [2.0]
    assert perturbations(Param("n", 4, "1", "user")) == [5.0, 3.0]
    assert perturbations(Param("l", 30, "mm", "user")) == [36.0, 24.0]
    assert perturbations(Param("k", 2.5, "1", "user")) == [3.0, 2.0]
    assert perturbations(Param("n", 0, "1", "user")) == [1.0]
    for p in (Param("n", 1, "1", "user"), Param("n", 2, "1", "user"), Param("gap", 0, "mm", "user")):
        vals = perturbations(p)
        assert all(v != p.value for v in vals) and all(v >= 1 for v in vals if p.unit == "1")


def test_constrained_when_a_check_fails():
    res, skipped = go(ws_with([mm("a", 30)]), lambda n, v: "fail:w")
    assert res == [MutationResult("a", "constrained", (36.0,), ("w",))] and skipped == []


def test_unconstrained_when_everything_passes():
    fake = FakeRun(lambda n, v: "pass")
    res, _ = go(ws_with([mm("a", 30)]), fake)
    assert res == [MutationResult("a", "unconstrained", (36.0,), ())]
    assert len(fake.calls) == 1   # 只试了第一个数值


def test_unbuildable_after_both_directions_fail():
    res, _ = go(ws_with([mm("a", 30)]), lambda n, v: "error" if v == 36.0 else "timeout")
    assert res == [MutationResult("a", "unbuildable", (36.0, 24.0), ())]


def test_mandatory_failure_counts_as_unbuildable():
    res, _ = go(ws_with([mm("a", 30)]), lambda n, v: "mandatory")
    assert res[0].verdict == "unbuildable" and res[0].tried == (36.0, 24.0)


def test_second_direction_is_tried_after_error():
    res, _ = go(ws_with([mm("a", 30)]), lambda n, v: "error" if v == 36.0 else "fail:fin")
    assert res == [MutationResult("a", "constrained", (36.0, 24.0), ("fin",))]


def test_check_values_are_the_original_values():
    fake = FakeRun(lambda n, v: "fail:w")
    go(ws_with([mm("a", 30), mm("b", 20)]), fake)
    assert len(fake.calls) == 2
    for call in fake.calls:
        assert call["check_values"] == {"a": 30.0, "b": 20.0}
        assert call["mode"] == "build"
        assert call["check_ids"] == ["w", "fin"]   # 用 final_checks：s1 的 here_only 不在里面
    by = {c["changed"][0]: c["values"] for c in fake.calls}
    assert by["a"] == {"a": 36.0, "b": 20.0} and by["b"] == {"a": 30.0, "b": 24.0}


def test_only_user_params_and_limit():
    params = [mm("s", 5, "suggested")] + [mm(f"p{i}", 10 + i) for i in range(15)]
    fake = FakeRun(lambda n, v: "fail:w")
    res, skipped = go(ws_with(params), fake)
    assert LIMIT == 12
    assert [r.param for r in res] == [f"p{i}" for i in range(12)]
    assert skipped == ["p12", "p13", "p14"]
    assert all(c["changed"][0] != "s" for c in fake.calls)


def test_results_keep_brief_order_with_parallel_workers():
    params = [mm(f"p{i}", 10 + i) for i in range(6)]
    res, _ = go(ws_with(params), lambda n, v: "pass" if n == "p3" else "fail:w", workers=3)
    assert [r.param for r in res] == [f"p{i}" for i in range(6)]
    assert [r.verdict for r in res] == ["constrained"] * 3 + ["unconstrained"] + ["constrained"] * 2


def test_integer_count_is_written_as_integer():
    fake = FakeRun(lambda n, v: "fail:w")
    go(ws_with([Param("n", 4, "1", "user")]), fake)
    assert "    n = 5\n" in fake.calls[0]["text"]
    assert fake.calls[0]["values"]["n"] == 5.0


@pytest.mark.parametrize("v", [0, 1])
def test_zero_and_one_count_are_buildable_values(v):
    fake = FakeRun(lambda n, val: "fail:w")
    go(ws_with([Param("n", v, "1", "user")]), fake)
    assert fake.calls[0]["values"]["n"] >= 1
