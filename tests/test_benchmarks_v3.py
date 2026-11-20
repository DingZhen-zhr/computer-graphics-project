"""3.0 计划 4 Task 2：任务分组、四张结果表和覆盖情况表。"""

from __future__ import annotations

from benchmarks.report import max_dimension_deviation
from benchmarks.report_v3 import coverage, render_v3_md
from benchmarks.run import TASK_SETS, V3_DEV, V3_HOLDOUT


def test_v3_sets():
    assert V3_DEV == ["phone_stand", "flange", "l_bracket", "enclosure", "bearing_block", "spur_gear", "heatsink", "tee_fitting",
                      "toolbox", "drawer_cabinet"]
    assert V3_HOLDOUT == ["stepped_shaft", "battery_box", "bracket_arm", "gear_pair"]
    assert TASK_SETS["v3dev"] == V3_DEV and TASK_SETS["v3holdout"] == V3_HOLDOUT and TASK_SETS["v3all"] == V3_DEV + V3_HOLDOUT
    assert TASK_SETS["v2"][:3] == ["phone_stand", "flange", "l_bracket"] and len(TASK_SETS["v2"]) == 11   # 原有集合不变


def _r(task, success=True, questions=1, repairs=0, mod=True, **kw):
    stages = [{"stage": "after_initial", "delivered": True, "acceptance": [{"type": "bbox", "deviation": 0.2}]}]
    if mod:
        stages.append({"stage": "after_mod_1", "delivered": True, "acceptance": [{"type": "bbox", "deviation": -0.4}]})
    return {"task": task, "success": success, "stages": stages, "questions": questions, "repairs": repairs, "duration_s": 100.0,
            "llm_calls": 9, "cost": 0.3, "sim_cost": 0.05, **kw}


def test_four_tables():
    md = render_v3_md([_r("flange"), _r("toolbox", success=False), _r("stepped_shaft"), _r("gear_pair")])
    for title in ("### 开发 · 单零件（1/1 成功）", "### 开发 · 多零件（0/1 成功）", "### 留出 · 单零件（1/1 成功）", "### 留出 · 多零件（1/1 成功）"):
        assert title in md, title
    assert "| flange | 成功 | 0.4 | 100 | 0 | 9 | 0.35 |" in md
    skipped = render_v3_md([{"task": "flange", "skipped_for_cap": True}])
    assert "| flange | 到了花费上限，没跑 |" in skipped


def test_coverage_table():
    only_ask = _r("flange", questions=2, repairs=0, mod=False)
    only_fix = _r("l_bracket", questions=0, repairs=2, mod=False)
    all3 = _r("heatsink", questions=1, repairs=1, mod=True)
    assert coverage(only_ask) == {"clarify": True, "modify": False, "repair": False}
    assert coverage(only_fix) == {"clarify": False, "modify": False, "repair": True}
    assert coverage(all3) == {"clarify": True, "modify": True, "repair": True}
    md = render_v3_md([only_ask, only_fix, all3])
    assert "| flange | ✓ | — | — |" in md and "| heatsink | ✓ | ✓ | ✓ |" in md
    assert "三项都覆盖到的任务：1 个（heatsink）。" in md


def test_multipart_deviation_only_lengths():
    r = {"stages": [{"acceptance": [{"type": "bbox", "deviation": 0.3}, {"type": "joint", "deviation": 15.0},
                                    {"type": "at_pose", "deviation": None}, {"type": "point_inside", "deviation": None}]}]}
    assert max_dimension_deviation(r) == 0.3
