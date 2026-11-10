"""分阶段流程的快照和阶段小结（第二版计划 1 Task 10）。"""

import json

from cad_agent.agent.state import SNAPSHOT_TITLE, render_snapshot
from cad_agent.sandbox.execute import RunResult
from cad_agent.staged.build import Advance, StageRun
from cad_agent.staged.summary import stage_summary
from helpers_staged import BASE, WALL, passing, two_stage_ws


def test_snapshot_legacy_unchanged():
    ws = two_stage_ws()
    assert render_snapshot(ws) == render_snapshot(ws, False)
    legacy = render_snapshot(ws)
    assert "计划：" not in legacy and "--- base（build）---" in legacy
    assert legacy.splitlines()[1] == "阶段：可以建模（需求单已确认）"


def test_snapshot_phases():
    ws = two_stage_ws()
    ws.brief.confirmed = False
    lines = render_snapshot(ws, True).splitlines()
    assert lines[:3] == [SNAPSHOT_TITLE, "阶段：澄清中（需求单未确认）", "需求单："]
    assert "计划：" not in lines and "特征（按顺序）：" not in lines
    ws.brief.confirmed = True
    plan, ws.plan = ws.plan, None
    text = render_snapshot(ws, True)
    assert text.splitlines()[1] == "阶段：规划中（还没有计划，先调用 set_plan）"
    assert "计划：\n无\n特征（按顺序）：" in text
    ws.plan = plan
    assert render_snapshot(ws, True).splitlines()[1] == "阶段：建模中（当前阶段 s1）"
    ws.plan.mark_passed("s1")
    assert render_snapshot(ws, True).splitlines()[1] == "阶段：建模中（当前阶段 s2）"
    ws.plan.mark_passed("s2")
    assert render_snapshot(ws, True).splitlines()[1] == "阶段：全部阶段已通过"


def test_snapshot_layout():
    ws = two_stage_ws()
    ws.last_build_content = '{"passed": false}'
    lines = render_snapshot(ws, True).splitlines()
    brief_json = json.dumps(ws.brief.to_dict(), ensure_ascii=False, indent=1).splitlines()
    assert lines[2:3 + len(brief_json)] == ["需求单：", *brief_json]
    rest = lines[3 + len(brief_json):]
    assert rest[0] == "计划：" and rest[3] == "特征（按顺序）："
    assert "检查项：" in rest and rest[rest.index("上次 build：") + 1] == '{"passed": false}'
    ws.last_build_content = None
    assert render_snapshot(ws, True).endswith("上次 build：\n未运行")


def test_snapshot_plan_lines():
    ws = two_stage_ws()
    ws.plan.mark_passed("s1")
    lines = render_snapshot(ws, True).splitlines()
    i = lines.index("计划：")
    assert lines[i + 1:i + 3] == ["s1 底板：有一块底板 —— 已通过", "s2 立板：左端有立板 —— 当前"]
    ws.plan.invalidate_all()
    lines = render_snapshot(ws, True).splitlines()
    assert lines[i + 1:i + 3] == ["s1 底板：有一块底板 —— 当前", "s2 立板：左端有立板 —— 未开始"]


def test_snapshot_feature_header_has_stage():
    text = render_snapshot(two_stage_ws(), True)
    assert f"特征（按顺序）：\n--- base（build，s1）---\n{BASE}\n\n--- wall（add，s2）---\n{WALL}\n检查项：" in text
    empty = two_stage_ws()
    empty.features = type(empty.features)()
    assert "特征（按顺序）：\n无\n检查项：" in render_snapshot(empty, True)


def run_with(size, volume, n_checks) -> RunResult:
    r = passing(*[f"c{i}" for i in range(n_checks - 3)])
    r.facts = {"size": size, "volume": volume}
    return r


def test_stage_summary_format():
    ws = two_stage_ws()
    ws.plan.mark_passed("s1")
    adv = Advance([StageRun("s1", run_with([78.0, 40.0, 8.0], 24960.0, 5))], ["s1"], "s2", "not_ready")
    assert stage_summary(ws, adv).splitlines() == [
        "【阶段已通过（程序生成）】s1 底板",
        "特征：",
        "--- base（build，s1）---",
        BASE,
        "检查：5 条，全部通过。",
        "外形：78 × 40 × 8，体积 24960",
        "",
        "现在是 s2：立板。做完的标志：左端有立板",
    ]
    ws.plan.mark_passed("s2")
    adv2 = Advance([StageRun("s1", run_with([78.0, 40.0, 8.0], 24960.0, 5)),
                    StageRun("s2", run_with([78.12345, 40.0, 60.00004], 43123.456789, 6))], ["s1", "s2"], None, "complete")
    assert stage_summary(ws, adv2).splitlines() == [
        "【阶段已通过（程序生成）】s1 底板", "特征：", "--- base（build，s1）---", BASE, "检查：5 条，全部通过。", "外形：78 × 40 × 8，体积 24960",
        "",
        "【阶段已通过（程序生成）】s2 立板", "特征：", "--- wall（add，s2）---", WALL, "检查：6 条，全部通过。",
        "外形：78.1235 × 40 × 60，体积 43123.4568",
    ]
    adv3 = Advance([StageRun("s2", run_with([78.0, 40.0, 60.0], 1.5, 4))], ["s2"], None, "complete")
    assert stage_summary(ws, adv3).splitlines()[0] == "【阶段已通过（程序生成）】s2 立板"
    assert stage_summary(ws, adv3).splitlines()[-1] == "外形：78 × 40 × 60，体积 1.5"
