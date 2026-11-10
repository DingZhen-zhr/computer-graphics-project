"""案例库：读取、检索、渲染、保存（第二版计划 1 Task 11）。"""

import copy
import re
from pathlib import Path

import pytest
import yaml

from cad_agent import cases as cases_mod
from cad_agent.brief import Brief
from cad_agent.cases import (MAX_CASE_CHARS, TAG_BONUS, THRESHOLD, Case, CaseError, case_workspace, load_case, load_cases,
                             pick_cases, render_cases, save_case, score)
from helpers_staged import BASE, CHECK_S1, CHECK_S2, TILT, WALL, two_stage_ws

TAIL = "…（后面的内容省略）"
HEAD = "【参考案例（程序生成，只供参考；尺寸和结构以需求单为准）】"


def case_dict(title="法兰盖", tags=("法兰", "螺栓孔"), request="做一个带一圈螺栓孔的法兰盖", features_brief=("圆盘", "螺栓孔")) -> dict:
    return {
        "title": title, "tags": list(tags), "request": request,
        "brief": {"part": {"name": title, "purpose": "测试"},
                  "params": [{"name": "phone_w", "value": 78, "unit": "mm", "source": "user", "note": "宽"},
                             {"name": "tilt_deg", "value": 65, "unit": "deg", "source": "user", "note": "角"}],
                  "features": list(features_brief), "relations": ["螺栓孔在圆盘上"], "open_questions": [], "confirmed": True},
        "plan": [{"title": "底板", "done_when": "有一块底板"}, {"title": "立板", "done_when": "左端有立板"}],
        "features": [{"slug": "base", "role": "build", "stage": "s1", "code": BASE},
                     {"slug": "wall", "role": "add", "stage": "s2", "code": WALL}],
        "checks": copy.deepcopy([CHECK_S1, TILT, CHECK_S2]),   # 复制：有的测试会改它
    }


def write_case(root: Path, cid: str, data: dict) -> Path:
    d = root / cid
    d.mkdir(parents=True)
    (d / "case.yaml").write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return d


def make_case(cid="flange-cap", builtin=True, **over) -> Case:
    d = case_dict(**over)
    return Case(cid, d["title"], tuple(d["tags"]), d["request"], d["brief"], d["plan"], d["features"], d["checks"], builtin)


def test_load_case_round_trip(tmp_path):
    d = write_case(tmp_path, "flange-cap", case_dict())
    c = load_case(d, builtin=True)
    assert c == make_case()
    assert c.id == "flange-cap" and c.tags == ("法兰", "螺栓孔") and c.builtin
    assert load_case(d, builtin=False).builtin is False


@pytest.mark.parametrize("breaker,hint", [
    (lambda d: d.pop("title"), "title"),
    (lambda d: d.pop("checks"), "checks"),
    (lambda d: d.update(plan=[]), "plan"),
    (lambda d: d["features"][1].update(stage="s9"), "s9"),
    (lambda d: d.update(tags="法兰"), "tags"),
    (lambda d: d["checks"][0].pop("stage"), "stage"),
])
def test_load_case_errors(tmp_path, breaker, hint):
    data = case_dict()
    breaker(data)
    d = write_case(tmp_path, "bad", data)
    with pytest.raises(CaseError) as e:
        load_case(d, builtin=False)
    assert str(d / "case.yaml") in str(e.value) and hint in str(e.value)


def test_load_case_bad_yaml_and_missing_file(tmp_path):
    d = tmp_path / "broken"
    d.mkdir()
    with pytest.raises(CaseError):
        load_case(d, builtin=False)
    (d / "case.yaml").write_text("title: [没关上", encoding="utf-8")
    with pytest.raises(CaseError):
        load_case(d, builtin=False)


def test_load_cases_skips_bad_ones_and_reports(tmp_path, monkeypatch):
    builtin = tmp_path / "builtin"
    write_case(builtin, "zz-builtin", case_dict(title="自带的"))
    monkeypatch.setattr(cases_mod, "BUILTIN_DIR", builtin)
    user = tmp_path / "user"
    write_case(user, "user-1", case_dict(title="用户的"))
    bad = case_dict()
    bad.pop("plan")
    write_case(user, "user-2", bad)
    (user / "stray.txt").write_text("不是目录", encoding="utf-8")
    found, problems = load_cases(user)
    assert [(c.id, c.builtin) for c in found] == [("zz-builtin", True), ("user-1", False)]
    assert len(problems) == 1 and "user-2" in problems[0]
    assert load_cases(None)[0][0].id == "zz-builtin"
    assert load_cases(tmp_path / "nope")[1] == []


def flange_brief() -> Brief:
    return Brief(part_name="法兰盘", purpose="管道连接", features=["圆盘", "一圈螺栓孔"])


def test_score_orders_similar_first():
    brief = flange_brief()
    query = cases_mod.query_text(brief)
    near = make_case("flange-cap")
    far = make_case("phone", title="手机支架", tags=("支架",), request="做一个放手机的支架", features_brief=("底座", "靠背"))
    other = make_case("hook", title="挂钩", tags=("挂钩",), request="墙上的挂钩", features_brief=("钩子",))
    assert score(query, near) > score(query, far)
    assert score(query, far) < THRESHOLD and score(query, other) < THRESHOLD
    assert score(query, near) >= THRESHOLD


def test_score_tag_bonus():
    q = cases_mod.query_text(flange_brief())
    one = make_case(tags=("法兰", "不相干"))
    two = make_case(tags=("法兰", "螺栓孔"))
    assert score(q, two) - score(q, one) == pytest.approx(TAG_BONUS) and TAG_BONUS == 0.15


def test_score_ignores_spaces_and_punctuation():
    a = make_case(title="法兰 盖", request="做一个，带一圈螺栓孔的 法兰盖！")
    b = make_case(title="法兰盖", request="做一个带一圈螺栓孔的法兰盖")
    q = cases_mod.query_text(flange_brief())
    assert score(q, a) == pytest.approx(score(q, b))


def test_pick_cases_limit_and_threshold():
    brief = flange_brief()
    cands = [make_case("user-x", builtin=False), make_case("b-flange"), make_case("a-flange"),
             make_case("phone", title="手机支架", tags=("支架",), request="放手机", features_brief=("底座",))]
    picked = pick_cases(brief, cands)
    assert [c.id for c in picked] == ["a-flange", "b-flange"]   # 分数相同：自带的在前，再按 id
    assert [c.id for c in pick_cases(brief, cands, k=3)] == ["a-flange", "b-flange", "user-x"]
    assert pick_cases(brief, [cands[-1]]) == [] and pick_cases(brief, []) == []


def test_render_cases_format_and_truncation():
    assert render_cases([]) == ""
    c = make_case()
    lines = render_cases([c]).splitlines()
    assert lines[:7] == [HEAD, "== 法兰盖 ==", "需求：做一个带一圈螺栓孔的法兰盖", "计划：", "s1 底板：有一块底板", "s2 立板：左端有立板", "特征："]
    assert lines[7:] == ["--- base（build，s1）---", BASE, "", "--- wall（add，s2）---", WALL]
    two = render_cases([c, make_case("x", title="法兰盖二")])
    assert two.count(HEAD) == 1 and "\n\n== 法兰盖二 ==\n" in two
    long = make_case(title="长案例")
    long = Case(long.id, long.title, long.tags, long.request, long.brief, long.plan,
                [{"slug": "base", "role": "build", "stage": "s1", "code": "base = 1  # " + "很长" * 3000}], long.checks, True)
    text = render_cases([long, c])
    first = text[len(HEAD) + 1:].split("\n\n== 法兰盖 ==")[0]
    assert len(first) <= MAX_CASE_CHARS == 3000 and first.endswith("\n" + TAIL)
    assert text.endswith(WALL)


def test_save_case_and_reload(tmp_path):
    ws = two_stage_ws()
    for s in ws.plan.stages:
        ws.plan.mark_passed(s.id)
    d = save_case(tmp_path / "cases", "我的 L 形支架", ["支架", "L 形"], ws)
    assert re.fullmatch(r"user-\d{8}-\d{6}", d.name) and d.parent == tmp_path / "cases"
    c = load_case(d, builtin=False)
    assert c.title == "我的 L 形支架" and c.tags == ("支架", "L 形") and c.brief == ws.brief.to_dict()
    assert c.plan == [{"title": "底板", "done_when": "有一块底板"}, {"title": "立板", "done_when": "左端有立板"}]
    assert [f["stage"] for f in c.features] == ["s1", "s2"] and c.checks == ws.checks_raw
    d2 = save_case(tmp_path / "cases", "再存一个", ["支架"], ws)
    assert d2 != d and d2.name.startswith("user-") and d2.parent == d.parent


def test_save_case_requires_finished_plan(tmp_path):
    ws = two_stage_ws()
    with pytest.raises(CaseError):
        save_case(tmp_path, "没做完", ["x"], ws)
    for s in ws.plan.stages:
        ws.plan.mark_passed(s.id)
    with pytest.raises(CaseError):
        save_case(tmp_path, "  ", ["x"], ws)
    ws.plan = None
    with pytest.raises(CaseError):
        save_case(tmp_path, "没计划", ["x"], ws)
    assert not any(tmp_path.iterdir())


def test_case_workspace():
    ws = case_workspace(make_case())
    assert ws.brief.can_build()[0] and ws.brief.relations == ["螺栓孔在圆盘上"]
    assert ws.plan.ids() == ["s1", "s2"] and not any(s.passed for s in ws.plan.stages)
    assert [(f.slug, f.stage) for f in ws.features.items] == [("base", "s1"), ("wall", "s2")]
    assert ws.checks_raw == [CHECK_S1, TILT, CHECK_S2] and ws.checks_raw[0] is not CHECK_S1
