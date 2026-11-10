"""终检（第二版计划 1 Task 8，假 run_job）。"""

from cad_agent.brief import Param
from cad_agent.gates import Gates
from cad_agent.staged.final_gate import GateResult, run_final_gate
from cad_agent.staged.mutation import MutationResult
from test_mutation import FakeRun, mm, ws_with


def gate(ws, decide, gates=Gates()):
    fake = FakeRun(decide)
    return run_final_gate(ws, fake, gates, timeout_s=60, secret_names=()), fake


def test_coverage_gap_skips_mutation():
    ws = ws_with([mm("a", 30), mm("b", 20), mm("c", 5)])
    g, fake = gate(ws, lambda n, v: "fail:w")
    assert not g.passed and g.missing_coverage == ["c"] and g.mutation == [] and fake.calls == []


def test_coverage_counts_only_from_here_checks():
    ws = ws_with([mm("a", 30), mm("b", 20)])
    ws.checks_raw = [c for c in ws.checks_raw if c["id"] != "w"]   # 只剩 here_only 的 pre 用到 a
    g, fake = gate(ws, lambda n, v: "fail:fin")
    assert g.missing_coverage == ["a"] and not g.passed


def test_mutation_off():
    g, fake = gate(ws_with([mm("a", 30), mm("b", 20)]), lambda n, v: "pass", Gates(mutation_check=False))
    assert g.passed and g.mutation == [] and fake.calls == []


def test_passed_when_all_constrained():
    g, _ = gate(ws_with([mm("a", 30), mm("b", 20)]), lambda n, v: "fail:w" if n == "a" else "fail:fin")
    assert g.passed and g.unconstrained == [] and [m.verdict for m in g.mutation] == ["constrained", "constrained"]


def test_unconstrained_blocks():
    g, _ = gate(ws_with([mm("a", 30), mm("b", 20)]), lambda n, v: "fail:w" if n == "a" else "pass")
    assert not g.passed and g.unconstrained == ["b"]


def test_unbuildable_does_not_block():
    g, _ = gate(ws_with([mm("a", 30), mm("b", 20)]), lambda n, v: "fail:w" if n == "a" else "error")
    assert g.passed and g.unbuildable == ["b"] and g.unconstrained == []


def test_to_dict_keys():
    params = [mm("a", 30), mm("b", 20)] + [mm(f"z{i}", 1 + i, "user") for i in range(11)]
    ws = ws_with(params)
    ws.checks_raw.append({"id": "all", "type": "volume", "stage": "s1",
                          "expected": " + ".join(p.name for p in params) + " + 0"})
    g, _ = gate(ws, lambda n, v: "error" if n == "b" else "fail:all")
    d = g.to_dict()
    assert list(d) == ["missing_coverage", "unconstrained", "unbuildable", "skipped", "mutation"]
    assert d["missing_coverage"] == [] and d["unconstrained"] == [] and d["unbuildable"] == ["b"]
    assert d["skipped"] == ["z10"]
    assert d["mutation"][0] == {"param": "a", "verdict": "constrained", "tried": [36.0], "caught_by": ["all"]}
    assert d["mutation"][1] == {"param": "b", "verdict": "unbuildable", "tried": [24.0, 16.0], "caught_by": []}
    assert isinstance(g, GateResult) and isinstance(g.mutation[0], MutationResult)
