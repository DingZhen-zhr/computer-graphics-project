"""八个自带案例（第二版计划 1 Task 14，真实 SCA）。"""

import pytest

from cad_agent.cases import load_cases
from cad_agent.gates import Gates
from cad_agent.sandbox.execute import run_job
from cad_agent.staged.build import advance
from cad_agent.staged.final_gate import run_final_gate

pytestmark = pytest.mark.sca

# gear-rack 换成 ring-gear：齿条在 SCA 2.2.7 里实体无效（偏离 D13）
IDS = {"mounting-plate", "pulley", "tray", "motor-mount", "cam-plate", "ring-gear", "pull-handle", "knob"}
BENCHMARK_IDS = ["phone_stand", "flange", "l_bracket", "enclosure", "stepped_shaft", "bearing_block", "battery_box", "spur_gear",
                 "heatsink", "tee_fitting", "bracket_arm"]
BENCHMARK_PARTS = ["手机支架", "法兰盘", "L 形", "电路板", "阶梯轴", "轴承座", "电池盒", "直齿轮", "散热器", "三通", "支架臂"]
CASES, PROBLEMS = load_cases(None)
BY_ID = {c.id: c for c in CASES}


def test_there_are_eight_builtin_cases():
    assert PROBLEMS == []
    assert {c.id for c in CASES} == IDS and all(c.builtin for c in CASES)


@pytest.mark.parametrize("cid", sorted(IDS))
def test_case_shape(cid):
    c = BY_ID[cid]
    params = c.brief["params"]
    assert 3 <= len(params) <= 6 and all(p["source"] == "user" for p in params)
    assert 2 <= len(c.plan) <= 4
    for i in range(1, len(c.plan) + 1):
        assert sum(1 for k in c.checks if k["stage"] == f"s{i}") >= 2, f"s{i}"
    assert 3 <= len(c.tags) <= 5
    assert c.request.strip() and c.title.strip()
    if len(c.brief["features"]) >= 2:
        assert c.brief.get("relations"), "有两个以上组成部分的要写 relations"
    assert {f["stage"] for f in c.features} == {f"s{i}" for i in range(1, len(c.plan) + 1)}


@pytest.mark.parametrize("cid", sorted(IDS))
def test_case_builds_and_passes_gates(cid):
    from cad_agent.cases import case_workspace

    ws = case_workspace(BY_ID[cid])
    adv = advance(ws, run_job, timeout_s=120, secret_names=())
    detail = adv.runs[-1].run if adv.runs else None
    assert adv.reason == "complete", (adv.stopped, detail.error if detail else None,
                                      [(k.id, k.detail) for k in (detail.checks if detail else []) if not k.passed])
    gate = run_final_gate(ws, run_job, Gates(), timeout_s=120, secret_names=())
    assert gate.passed, gate.to_dict()
    assert gate.skipped == [] and gate.unbuildable == []


def test_builtin_cases_are_not_benchmark_tasks():
    for c in CASES:
        for word in BENCHMARK_IDS + BENCHMARK_PARTS:
            assert word not in c.id and word not in c.title, (c.id, word)
