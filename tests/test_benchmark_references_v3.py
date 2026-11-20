"""三个多零件评测任务的标准答案（3.0 计划 2 Task 14，真实 SCA）。

确认：标准答案在我们的内核里每个零件都推进到全部步骤通过、零件终检通过，装配的必做检查和产品终检（含参数扰动）通过；
交付出来的版本用独立的验收（benchmarks/assembly_accept.py）初始和修改后两组都全过；
没按修改改的旧版本拿去对修改后的验收，恰好卡在修改相关的条目上。
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from benchmarks.assembly_accept import evaluate as accept
from benchmarks.run import load_task
from cad_agent.gates import Gates
from cad_agent.product.checks import evaluate, mandatory_checks
from cad_agent.product.delivery import export_product_version
from cad_agent.product.gate import run_product_gate
from cad_agent.product.workspace import select_part
from cad_agent.sandbox.execute import run_job
from cad_agent.session import Session
from cad_agent.staged.build import advance
from cad_agent.staged.final_gate import run_final_gate
from cad_agent.tools import ToolBox
from references_v3 import REFERENCES

pytestmark = pytest.mark.sca

TIMEOUT = 120
# 没改的旧版本对修改后的验收，应该恰好不通过的条目（任务文件注释里写了怎么算的）
COUNTER = {
    "toolbox": {"size-z", "in-lid", "in-grip", "out-under-grip", "in-pin", "in-knuckle", "hinge", "open-90"},
    "drawer_cabinet": {"pull"},
    "gear_pair": {"in-shaft", "out-gap", "in-pinion-tooth", "pinion", "gear", "half-tooth"},
}


def _deliver(ws, root: Path, *, gates: bool) -> Path:
    box = ToolBox(ws, run_job=run_job, gates=Gates(visual_review=False, cases=False))
    box.timeout_s, box.motion_samples = TIMEOUT, 12
    for pid in list(ws.parts):
        select_part(ws, pid)
        adv = advance(ws, run_job, timeout_s=TIMEOUT, secret_names=())
        assert adv.reason == "complete", (pid, adv.runs[-1].run.error, [c.detail for c in adv.runs[-1].run.checks if not c.passed])
        if gates:
            gate = run_final_gate(ws, run_job, box.gates, timeout_s=TIMEOUT, secret_names=())
            assert gate.passed, (pid, gate.to_dict())
        ws.parts[pid].done = True
        ws.parts[pid].results = [c.to_dict() for c in adv.runs[-1].run.checks]
    select_part(ws, list(ws.parts)[0])
    run = box.run_assembly(ws, mode="check", samples=12, timeout_s=TIMEOUT, secret_names=())
    res = evaluate(run, mandatory_checks(ws.assembly, list(ws.parts)) + ws.assembly_checks_raw, ws.assembly, ws.brief.param_values())
    assert run.ok and all(r.passed for r in res), [r.detail for r in res if not r.passed]
    if gates:
        gate = run_product_gate(box)
        assert gate.passed, gate.to_dict()
        box.last_gate = gate
    ws.assembly_passed = True
    v = export_product_version(SimpleNamespace(toolbox=box, ws=ws, session=Session(root)), [])
    assert isinstance(v, Path), v
    return v


def _failed(vdir: Path, checks: list[dict]) -> set[str]:
    res = accept(vdir, checks)
    assert res["error"] is None and res["mandatory_ok"], res
    return {e["id"] for e in res["entries"] if not e["passed"]}


@pytest.mark.parametrize("name", list(REFERENCES))
def test_reference_passes_kernel_gates_and_acceptance(name, tmp_path):
    build, mod = REFERENCES[name]
    task = load_task(name)
    v1 = _deliver(build(), tmp_path / "a", gates=True)
    assert _failed(v1, task["acceptance"]["after_initial"]) == set()
    v2 = _deliver(build(**mod), tmp_path / "b", gates=False)
    assert _failed(v2, task["acceptance"]["after_mod_1"]) == set()
    # 反例：没按修改改的旧版本恰好卡在修改相关的条目上
    assert _failed(v1, task["acceptance"]["after_mod_1"]) == COUNTER[name]
