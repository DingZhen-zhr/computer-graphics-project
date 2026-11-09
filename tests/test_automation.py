import json

import pytest

from cad_agent.agent.automation import (AUTO_BUILD_NOTE, AUTO_BUILD_PREFIX, SKIPPED_BUILD_MESSAGE, BriefShape, brief_shape, has_error,
                                        should_auto_build, should_auto_confirm, should_build_before_reply)
from cad_agent.brief import Brief
from cad_agent.notebook import Feature, FeatureList
from cad_agent.tools import Workspace
from helpers import PHONE_W, TILT, make_brief

UPDATE_OK = ("update_brief", True)


def test_constants():
    assert AUTO_BUILD_PREFIX == "auto-build-" and AUTO_BUILD_NOTE == "【程序自动运行了 build，结果如下】"
    assert json.loads(SKIPPED_BUILD_MESSAGE) == {"error": "同一次回复里前面的调用出错了，这次 build 没有运行，也不算失败。先改好出错的调用，再调用 build。"}
    assert "\\u" not in SKIPPED_BUILD_MESSAGE   # 中文不转义


def test_has_error():
    assert has_error('{"error": null}') is False
    assert has_error('{"error": "x"}') is True
    assert has_error('{"passed": false, "error": {"feature": "a"}}') is True
    assert has_error("不是 JSON") is False
    assert has_error("[1]") is False


def ws_with(confirmed: bool = False, with_params: bool = True, open_questions: bool = False, built: bool = True) -> Workspace:
    brief = make_brief(confirmed) if with_params else Brief(part_name="空", confirmed=confirmed)
    if open_questions:
        brief.open_questions = ["手机多厚？"]
    ws = Workspace(brief, FeatureList(), [])
    if built:
        ws.features.upsert(Feature("base", "build", "base = 1"))
        ws.checks_raw = [PHONE_W, TILT]
    return ws


@pytest.mark.parametrize("name,ws,calls,expected", [
    ("全部成立", ws_with(), [UPDATE_OK], True),
    ("同一次回复里还有别的成功调用", ws_with(), [UPDATE_OK, ("api_help", True)], True),
    ("需求单已经确认", ws_with(confirmed=True), [UPDATE_OK], False),
    ("没有 update_brief", ws_with(), [("api_help", True)], False),
    ("没有任何调用", ws_with(), [], False),
    ("update_brief 失败了", ws_with(), [("update_brief", False)], False),
    ("同一次回复里有 ask_user", ws_with(), [UPDATE_OK, ("ask_user", True)], False),
    ("同一次回复里有 request_confirmation", ws_with(), [UPDATE_OK, ("request_confirmation", True)], False),
    ("需求单里没有参数", ws_with(with_params=False), [UPDATE_OK], False),
    ("还有待问问题", ws_with(open_questions=True), [UPDATE_OK], False),
    ("update_brief 之后 build 被挡住", ws_with(), [UPDATE_OK, ("build", False)], True),
])
def test_should_auto_confirm_cases(name, ws, calls, expected):
    assert should_auto_confirm(ws, calls) is expected, name


@pytest.mark.parametrize("name,ws,unbuilt,used,expected", [
    ("全部成立", ws_with(confirmed=True), True, False, True),
    ("没有没 build 的改动", ws_with(confirmed=True), False, False, False),
    ("这一轮已经兜底过一次", ws_with(confirmed=True), True, True, False),
    ("需求单没确认", ws_with(confirmed=False), True, False, False),
    ("还有待问问题", ws_with(confirmed=True, open_questions=True), True, False, False),
    ("还没有特征", ws_with(confirmed=True, built=False), True, False, False),
])
def test_should_build_before_reply_cases(name, ws, unbuilt, used, expected):
    assert should_build_before_reply(ws, unbuilt, used) is expected, name


def test_should_build_before_reply_needs_checks():
    ws = ws_with(confirmed=True)
    ws.checks_raw = []
    assert should_build_before_reply(ws, True, False) is False


def test_brief_shape():
    brief = make_brief(confirmed=True)
    shape = brief_shape(brief)
    assert shape == BriefShape(True, frozenset({"phone_w", "tilt_deg"}), ("底座",), (("phone_w", 78.0), ("tilt_deg", 65.0)))
    brief.apply_patch({"set_params": [{"name": "tilt_deg", "value": 70, "unit": "deg", "source": "user", "note": "支撑角度"}]})
    assert brief_shape(brief).values == (("phone_w", 78.0), ("tilt_deg", 70.0))


def change(ws: Workspace, **patch) -> None:
    ws.brief.apply_patch(patch)


TILT_70 = {"name": "tilt_deg", "value": 70, "unit": "deg", "source": "user", "note": "支撑角度"}
NEW_PARAM = {"name": "wall", "value": 3, "unit": "mm", "source": "user", "note": "壁厚"}


def test_should_auto_build_cases():
    # 只改了数值 → 真
    ws = ws_with(confirmed=True)
    before = brief_shape(ws.brief)
    change(ws, set_params=[TILT_70])
    assert should_auto_build(ws, [UPDATE_OK], before) is True
    assert should_auto_build(ws, [UPDATE_OK, UPDATE_OK], before) is True

    # 新增参数 → 假
    ws = ws_with(confirmed=True)
    before = brief_shape(ws.brief)
    change(ws, set_params=[NEW_PARAM])
    assert should_auto_build(ws, [UPDATE_OK], before) is False

    # 删除参数 → 假
    ws = ws_with(confirmed=True)
    before = brief_shape(ws.brief)
    change(ws, remove_params=["tilt_deg"])
    assert should_auto_build(ws, [UPDATE_OK], before) is False

    # 改了组成部分 → 假
    ws = ws_with(confirmed=True)
    before = brief_shape(ws.brief)
    change(ws, set_params=[TILT_70], features=["底座", "托唇"])
    assert should_auto_build(ws, [UPDATE_OK], before) is False

    # 什么都没变 → 假
    ws = ws_with(confirmed=True)
    before = brief_shape(ws.brief)
    change(ws, set_params=[{"name": "tilt_deg", "value": 65, "unit": "deg", "source": "user", "note": "支撑角度"}])
    assert should_auto_build(ws, [UPDATE_OK], before) is False

    # 改之前就没确认 → 假
    ws = ws_with(confirmed=False)
    before = brief_shape(ws.brief)
    change(ws, set_params=[TILT_70])
    assert should_auto_build(ws, [UPDATE_OK], before) is False

    # 改完之后不再是已确认的（改了建议值）→ 假
    ws = ws_with(confirmed=True)
    before = brief_shape(ws.brief)
    change(ws, set_params=[{"name": "lip_h", "value": 20, "unit": "mm", "source": "suggested", "note": "托唇"}])
    assert ws.brief.confirmed is False and should_auto_build(ws, [UPDATE_OK], before) is False

    # 有待问问题 → 假
    ws = ws_with(confirmed=True)
    before = brief_shape(ws.brief)
    change(ws, set_params=[TILT_70], open_questions=["还有疑问"])
    assert should_auto_build(ws, [UPDATE_OK], before) is False

    # 还没有特征或检查项 → 假
    for kwargs in ({"built": False},):
        ws = ws_with(confirmed=True, **kwargs)
        before = brief_shape(ws.brief)
        change(ws, set_params=[TILT_70])
        assert should_auto_build(ws, [UPDATE_OK], before) is False
    ws = ws_with(confirmed=True)
    ws.checks_raw = []
    before = brief_shape(ws.brief)
    change(ws, set_params=[TILT_70])
    assert should_auto_build(ws, [UPDATE_OK], before) is False

    # calls 为空、有别的工具、update_brief 失败 → 假
    ws = ws_with(confirmed=True)
    before = brief_shape(ws.brief)
    change(ws, set_params=[TILT_70])
    assert should_auto_build(ws, [], before) is False
    assert should_auto_build(ws, [UPDATE_OK, ("api_help", True)], before) is False
    assert should_auto_build(ws, [UPDATE_OK, ("build", True)], before) is False
    assert should_auto_build(ws, [("update_brief", False)], before) is False
    assert should_auto_build(ws, [UPDATE_OK, ("update_brief", False)], before) is False
