"""3.0 计划 2 Task 14：三个多零件评测任务能加载、任务集、验收条目的格式。"""

from __future__ import annotations

from pathlib import Path

import pytest

from benchmarks.assembly_accept import AcceptSpecError, validate_entries
from benchmarks.run import MULTI_TASKS, TASK_SETS, load_task

ROOT = Path(__file__).resolve().parents[1]


def test_multi_tasks_load():
    for name in ("toolbox", "drawer_cabinet", "gear_pair"):
        t = load_task(name)
        assert list(t["acceptance"]) == ["after_initial", "after_mod_1"]
        types = {c["type"] for c in t["acceptance"]["after_initial"]}
        assert {"joint", "at_pose"} <= types


def test_task_sets():
    assert MULTI_TASKS == ["toolbox", "drawer_cabinet", "gear_pair"]
    assert TASK_SETS["multi"] == MULTI_TASKS
    assert TASK_SETS["v3"] == TASK_SETS["v2"] + MULTI_TASKS and len(TASK_SETS["v3"]) == 14
    assert TASK_SETS["v2"] == ["phone_stand", "flange", "l_bracket", "enclosure", "stepped_shaft", "bearing_block", "battery_box",
                               "spur_gear", "heatsink", "tee_fitting", "bracket_arm"]


@pytest.mark.parametrize("bad", [
    [{"id": "j", "type": "joint", "kind": "revolute", "through": [0, 0, 0], "pos_tol": 1, "lo": 0, "hi": 90}],   # 缺 axis
    [{"id": "j", "type": "joint", "kind": "hinge", "axis": [1, 0, 0], "lo": 0, "hi": 90}],
    [{"id": "j", "type": "joint", "kind": "revolute", "axis": [1, 0, 0], "lo": 0, "hi": 90}],                    # 转动缺 through
    [{"id": "p", "type": "at_pose", "joint": "nope", "value": 1, "checks": [{"id": "a", "type": "point_inside", "point": [0, 0, 0]}]}],
    [{"id": "j", "type": "joint", "kind": "prismatic", "axis": [1, 0, 0], "lo": 0, "hi": 9},
     {"id": "p", "type": "at_pose", "joint": "j", "value": 1, "checks": []}],
])
def test_acceptance_entries_validated(bad):
    with pytest.raises(AcceptSpecError):
        validate_entries(bad)


def test_accept_does_not_import_kernel_kinematics():
    src = (ROOT / "benchmarks" / "assembly_accept.py").read_text(encoding="utf-8")
    assert "cad_agent.product.kinematics" not in src and "motion.json\")" not in src
    assert "import cad_agent" not in src and "from cad_agent" not in src
