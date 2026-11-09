import pytest

from cad_agent.brief import Brief, BriefError, Param


def confirmed_brief(tilt_deg: float = 65) -> Brief:
    """测试用的辅助函数：一个已确认的需求单，含一个用户给的角度参数。"""
    return Brief(
        part_name="手机支架",
        purpose="放桌上看视频",
        params=[
            Param("phone_w", 78, "mm", "user", "带壳手机宽度"),
            Param("tilt_deg", tilt_deg, "deg", "user", "支撑角度"),
        ],
        features=["底座", "倾斜支撑面"],
        confirmed=True,
    )


def test_new_brief_cannot_build():
    ok, why = Brief().can_build()
    assert not ok and "未确认" in why


def test_open_questions_block_build():
    b = Brief(confirmed=True, open_questions=["手机多厚？"])
    ok, why = b.can_build()
    assert not ok and "待确认问题" in why


def test_confirmed_without_questions_can_build():
    ok, why = confirmed_brief().can_build()
    assert ok and why == ""


def test_patch_user_param_keeps_confirmation():
    b = confirmed_brief(tilt_deg=65)
    lines = b.apply_patch({"set_params": [{"name": "tilt_deg", "value": 70, "unit": "deg", "source": "user"}]})
    assert b.confirmed and any("65 → 70" in line for line in lines)


def test_patch_suggested_param_resets_confirmation():
    b = confirmed_brief(tilt_deg=65)
    b.apply_patch({"set_params": [{"name": "lip_h", "value": 15, "unit": "mm", "source": "suggested"}]})
    assert not b.confirmed


def test_patch_unchanged_suggested_param_keeps_confirmation():
    b = confirmed_brief()
    b.apply_patch({"set_params": [{"name": "lip_h", "value": 15, "unit": "mm", "source": "suggested", "note": "托唇"}]})
    b.confirmed = True
    b.apply_patch({"set_params": [{"name": "lip_h", "value": 15, "unit": "mm", "source": "suggested", "note": "托唇"}]})
    assert b.confirmed


def test_patch_new_open_question_resets_confirmation():
    b = confirmed_brief()
    b.apply_patch({"open_questions": ["手机多厚？"]})
    assert not b.confirmed and b.open_questions == ["手机多厚？"]


def test_patch_rejects_unknown_unit():
    with pytest.raises(BriefError, match="mm"):
        Brief().apply_patch({"set_params": [{"name": "w", "value": 7.8, "unit": "cm", "source": "user"}]})


@pytest.mark.parametrize("bad", ["1w", "phone w", "Phone", "", "w-1", "if", "model", "scad"])
def test_patch_rejects_bad_name(bad):
    with pytest.raises(BriefError):
        Brief().apply_patch({"set_params": [{"name": bad, "value": 1, "unit": "mm", "source": "user"}]})


def test_patch_rejects_bad_source_and_value():
    with pytest.raises(BriefError, match="source"):
        Brief().apply_patch({"set_params": [{"name": "w", "value": 1, "unit": "mm", "source": "me"}]})
    with pytest.raises(BriefError, match="数"):
        Brief().apply_patch({"set_params": [{"name": "w", "value": "很大", "unit": "mm", "source": "user"}]})


def test_patch_rejects_unknown_key_and_lists_valid_ones():
    with pytest.raises(BriefError, match="set_params"):
        Brief().apply_patch({"params": []})


def test_failed_patch_changes_nothing():
    b = confirmed_brief()
    before = b.to_dict()
    with pytest.raises(BriefError):
        b.apply_patch({
            "part": {"name": "别的名字"},
            "set_params": [{"name": "ok_w", "value": 1, "unit": "mm", "source": "user"},
                           {"name": "Bad", "value": 1, "unit": "mm", "source": "user"}],
        })
    assert b.to_dict() == before


def test_remove_param():
    b = confirmed_brief()
    lines = b.apply_patch({"remove_params": ["phone_w"]})
    assert [p.name for p in b.params] == ["tilt_deg"] and any("phone_w" in line for line in lines)
    with pytest.raises(BriefError, match="phone_w"):
        b.apply_patch({"remove_params": ["phone_w"]})


def test_patch_part_features_and_questions():
    b = Brief()
    lines = b.apply_patch({"part": {"name": "法兰盘", "purpose": "连接管道"}, "features": ["底盘", "凸台"]})
    assert b.part_name == "法兰盘" and b.purpose == "连接管道" and b.features == ["底盘", "凸台"]
    assert lines  # 每次改动都有中文变化行


def test_user_param_names_and_values():
    b = confirmed_brief()
    b.apply_patch({"set_params": [{"name": "lip_h", "value": 15, "unit": "mm", "source": "suggested"}]})
    assert b.user_param_names() == {"phone_w", "tilt_deg"}
    assert b.param_values() == {"phone_w": 78.0, "tilt_deg": 65.0, "lip_h": 15.0}


def test_round_trip():
    b = confirmed_brief()
    b.apply_patch({"open_questions": ["手机多厚？"]})
    assert Brief.from_dict(b.to_dict()) == b


def test_to_dict_matches_design_format():
    d = confirmed_brief().to_dict()
    assert d["part"] == {"name": "手机支架", "purpose": "放桌上看视频"}
    assert d["params"][0] == {"name": "phone_w", "value": 78, "unit": "mm", "source": "user", "note": "带壳手机宽度"}
    assert set(d) == {"part", "params", "features", "open_questions", "confirmed"}


def test_render_text_marks_source():
    b = confirmed_brief()
    b.apply_patch({"set_params": [{"name": "lip_h", "value": 15, "unit": "mm", "source": "suggested", "note": "托唇高度"}]})
    text = b.render_text()
    assert "建议" in text and "用户" in text
    assert "phone_w" in text and "托唇高度" in text and "底座" in text
