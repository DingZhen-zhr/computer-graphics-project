"""特征的阶段归属、检查的 stage/holds、某个阶段该用哪些特征和检查（第二版计划 1 Task 4）。"""

import pytest

from cad_agent.checks.spec import HOLDS, CheckSpecError, parse_checks
from cad_agent.notebook import Feature, FeatureList, NotebookError
from cad_agent.plan import revise
from cad_agent.staged.select import checks_for_stage, features_upto, final_checks, insert_index, stage_ready
from cad_agent.tools import Workspace
from helpers import make_brief


def plan3():
    return revise(None, [{"title": t, "done_when": t + "做好了"} for t in ("底板", "立板", "圆角")], {})


def ws_with(features: list[tuple[str, str]], checks: list[dict] | None = None, plan=True) -> Workspace:
    fl = FeatureList([Feature(slug, "build" if i == 0 else "add", f"{slug.replace('-', '_')} = 1", stage) for i, (slug, stage) in enumerate(features)])
    ws = Workspace(make_brief(confirmed=True), fl, checks or [])
    ws.plan = plan3() if plan else None
    return ws


def bbox(cid: str, stage: str | None = None, holds: str | None = None) -> dict:
    c = {"id": cid, "type": "bbox", "axis": "x", "expected": "phone_w"}
    if stage is not None:
        c["stage"] = stage
    if holds is not None:
        c["holds"] = holds
    return c


def test_feature_stage_round_trip_and_default():
    old = [{"slug": "base", "role": "build", "code": "base = 1"}]
    fl = FeatureList.from_list(old)
    assert fl.items[0].stage == "" and fl.to_list() == old     # 旧格式读写不变
    new = [{"slug": "base", "role": "build", "code": "base = 1", "stage": "s1"}]
    assert FeatureList.from_list(new).to_list() == new
    assert Feature("a", "build", "a = 1") == Feature("a", "build", "a = 1", "")


def test_feature_list_in_stage_and_insert():
    fl = FeatureList([Feature("a", "build", "a = 1", "s1"), Feature("b", "add", "b = a", "s2")])
    assert [f.slug for f in fl.in_stage("s1")] == ["a"] and fl.in_stage("s3") == []
    fl.insert(Feature("c", "add", "c = a", "s1"), 1)
    assert [f.slug for f in fl.items] == ["a", "c", "b"]
    with pytest.raises(NotebookError):
        fl.insert(Feature("b", "add", "b = 2", "s1"), 0)
    with pytest.raises(NotebookError):
        fl.insert(Feature("Bad", "add", "x = 1", "s1"), 0)


def test_check_holds_validation():
    assert HOLDS == ("from_here", "here_only")
    with pytest.raises(CheckSpecError):
        parse_checks([bbox("w", "s1", "sometimes")], {"phone_w"})
    with pytest.raises(CheckSpecError):
        parse_checks([{**bbox("w"), "stage": 1}], {"phone_w"})
    checks = parse_checks([bbox("w", "s2", "here_only"), bbox("w2", "s1")], {"phone_w"})
    assert (checks[3].stage, checks[3].holds) == ("s2", "here_only")
    assert (checks[4].stage, checks[4].holds) == ("s1", "from_here")
    plain = parse_checks([bbox("w")], {"phone_w"})[3]
    assert (plain.stage, plain.holds) == (None, "from_here")


def test_checks_for_stage():
    p = plan3()
    raw = [bbox("a", "s1"), bbox("b", "s1", "here_only"), bbox("c", "s2", "from_here"), bbox("d", "s2", "here_only"), bbox("e", "s3")]
    ids = lambda sid: [c["id"] for c in checks_for_stage(raw, p, sid)]  # noqa: E731
    assert ids("s1") == ["a", "b"]
    assert ids("s2") == ["a", "c", "d"]
    assert ids("s3") == ["a", "c", "e"]


def test_final_checks_without_plan_returns_everything():
    raw = [bbox("a", "s1", "here_only"), bbox("b")]
    ws = ws_with([("base", "")], raw, plan=False)
    assert final_checks(ws) == raw
    ws.plan = plan3()
    ws.checks_raw = [bbox("a", "s1", "here_only"), bbox("b", "s1"), bbox("c", "s3", "here_only")]
    assert [c["id"] for c in final_checks(ws)] == ["b", "c"]


def test_features_upto_and_insert_index():
    ws = ws_with([("base", "s1"), ("hole", "s1"), ("wall", "s2")])
    assert [f.slug for f in features_upto(ws, "s1")] == ["base", "hole"]
    assert [f.slug for f in features_upto(ws, "s2")] == ["base", "hole", "wall"]
    assert [f.slug for f in features_upto(ws, "s3")] == ["base", "hole", "wall"]
    assert insert_index(ws, "s1") == 2
    assert insert_index(ws, "s2") == 3
    assert insert_index(ws, "s3") == 3
    empty = ws_with([])
    assert insert_index(empty, "s1") == 0 and insert_index(empty, "s3") == 0
    only_s2 = ws_with([("wall", "s2")])
    assert insert_index(only_s2, "s1") == 0 and insert_index(only_s2, "s3") == 1


def test_stage_ready():
    ws = ws_with([("base", "s1"), ("wall", "s2")], [bbox("a", "s1"), bbox("c", "s3")])
    assert stage_ready(ws, "s1")
    assert not stage_ready(ws, "s2")   # 有特征没检查
    assert not stage_ready(ws, "s3")   # 有检查没特征


def test_workspace_new_fields_default():
    ws = Workspace(make_brief(), FeatureList(), [])
    assert ws.plan is None and ws.probes_used == 0
