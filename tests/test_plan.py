"""计划与阶段（第二版计划 1 Task 4）。"""

import pytest

from cad_agent.plan import MAX_STAGES, Plan, PlanError, Stage, revise

LOCKED = "阶段 {} 已经通过，不能在 set_plan 里改它。要改它的内容，直接修改这个阶段的特征或检查。"
HAS_FEATURES = "阶段 {} 里还有特征（{}），不能删掉这个阶段。先删掉或改写这些特征。"


def raw(n: int) -> list[dict]:
    return [{"title": f"第{i}步", "done_when": f"多了第{i}块"} for i in range(1, n + 1)]


def three(passed: int = 0) -> Plan:
    p = revise(None, raw(3), {})
    for s in p.stages[:passed]:
        p.mark_passed(s.id)
    return p


def test_current_and_complete():
    p = three()
    assert p.current().id == "s1" and not p.complete()
    p.mark_passed("s1")
    assert p.current().id == "s2"
    p.mark_passed("s2")
    p.mark_passed("s3")
    assert p.current() is None and p.complete()
    assert p.ids() == ["s1", "s2", "s3"] and p.index("s2") == 1 and p.get("s3").title == "第3步"
    with pytest.raises(PlanError):
        p.index("s9")
    with pytest.raises(PlanError):
        p.get("s0")


def test_invalidate_from():
    p = three(passed=3)
    p.invalidate_from("s2")
    assert [s.passed for s in p.stages] == [True, False, False]
    assert p.current().id == "s2"
    p.invalidate_all()
    assert [s.passed for s in p.stages] == [False, False, False]


def test_round_trip():
    p = three(passed=1)
    lst = p.to_list()
    assert lst[0] == {"id": "s1", "title": "第1步", "done_when": "多了第1块", "passed": True}
    assert Plan.from_list(lst) == p
    assert Plan.from_list(lst).to_list() == lst


def test_revise_first_plan_numbers_stages():
    p = revise(None, raw(4), {})
    assert p.ids() == ["s1", "s2", "s3", "s4"]
    assert all(isinstance(s, Stage) and not s.passed for s in p.stages)
    assert p.stages[2].title == "第3步" and p.stages[2].done_when == "多了第3块"


@pytest.mark.parametrize("bad", [
    [],
    raw(MAX_STAGES + 1),
    [{"done_when": "多了一块"}],
    [{"title": "底板"}],
    [{"title": "  ", "done_when": "多了一块"}],
    [{"title": "底板", "done_when": ""}],
    [{"title": 1, "done_when": "多了一块"}],
    ["底板"],
    "底板",
    None,
])
def test_revise_limits(bad):
    with pytest.raises(PlanError) as e:
        revise(None, bad, {})
    assert str(e.value)  # 都有一句中文原因
    assert MAX_STAGES == 12
    assert len(revise(None, raw(12), {}).stages) == 12


def test_revise_keeps_passed_prefix():
    old = three(passed=2)
    new = revise(old, raw(2) + [{"title": "改过的第3步", "done_when": "不一样了"}, {"title": "第4步", "done_when": "新加的"}], {})
    assert new.ids() == ["s1", "s2", "s3", "s4"]
    assert [s.passed for s in new.stages] == [True, True, False, False]
    assert new.stages[2].title == "改过的第3步"
    assert [s.passed for s in old.stages] == [True, True, False]   # 原计划不变


def test_revise_rejects_changing_passed_stage():
    old = three(passed=2)
    changed = raw(3)
    changed[1]["done_when"] = "换了个说法"
    with pytest.raises(PlanError) as e:
        revise(old, changed, {})
    assert str(e.value) == LOCKED.format("s2")
    with pytest.raises(PlanError) as e:
        revise(old, raw(1), {})   # 去掉了已通过的 s2
    assert str(e.value) == LOCKED.format("s2")
    swapped = [raw(3)[1], raw(3)[0], raw(3)[2]]
    with pytest.raises(PlanError) as e:
        revise(old, swapped, {})
    assert str(e.value) == LOCKED.format("s1")


def test_revise_rejects_dropping_stage_with_features():
    old = three()
    with pytest.raises(PlanError) as e:
        revise(old, raw(1), {"s1": ["base"], "s3": ["fillet", "chamfer"]})
    assert str(e.value) == HAS_FEATURES.format("s3", "fillet、chamfer")
    new = revise(old, raw(2), {"s1": ["base"], "s3": []})   # 去掉的 s3 没有特征：可以
    assert new.ids() == ["s1", "s2"]


def test_revise_can_append_after_all_passed():
    old = three(passed=3)
    new = revise(old, raw(3) + [{"title": "加一个孔", "done_when": "多了一个孔"}], {"s1": ["base"]})
    assert new.ids() == ["s1", "s2", "s3", "s4"]
    assert [s.passed for s in new.stages] == [True, True, True, False]
    assert new.current().id == "s4"
