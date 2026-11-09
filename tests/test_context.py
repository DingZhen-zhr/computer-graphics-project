import json

from cad_agent.agent.context import CONFIRM_COMPACT, USER_HEADER, Context, compact_text, with_warning

SNAPSHOT = "【当前状态（程序生成，不是用户说的话）】\n阶段：澄清中（需求单未确认）"


def test_messages_layout_first_turn():
    ctx = Context("系统提示词")
    ctx.start_turn("做一个支架", SNAPSHOT)
    msgs = ctx.messages()
    assert [m["role"] for m in msgs] == ["system", "user"]
    assert msgs[0]["content"] == "系统提示词"
    assert msgs[1]["content"] == SNAPSHOT + "\n\n【用户说】\n" + "做一个支架" and USER_HEADER == "【用户说】"


def test_append_only_within_turn():
    ctx = Context("s")
    ctx.start_turn("你好", SNAPSHOT)
    before = ctx.messages()
    ctx.append({"role": "assistant", "content": "好", "tool_calls": [{"id": "c1"}]})
    ctx.append({"role": "tool", "tool_call_id": "c1", "content": "{}"})
    after = ctx.messages()
    assert after[: len(before)] == before and len(after) == len(before) + 2
    assert ctx.messages() is not ctx.messages()  # 每次返回新列表


def test_end_turn_compacts():
    ctx = Context("s")
    ctx.start_turn("做一个支架", SNAPSHOT)
    ctx.append({"role": "assistant", "content": "", "tool_calls": [{"id": "c1"}]})
    ctx.append({"role": "tool", "tool_call_id": "c1", "content": "{}"})
    ctx.end_turn("question", "1. 手机多厚？")
    ctx.start_turn("12 mm", "【新快照】")
    msgs = ctx.messages()
    assert [m["role"] for m in msgs] == ["system", "user", "assistant", "user"]
    assert msgs[1] == {"role": "user", "content": "做一个支架"}   # 旧轮只有原话，没有快照
    assert msgs[2] == {"role": "assistant", "content": "1. 手机多厚？"}
    assert msgs[3]["content"] == "【新快照】\n\n【用户说】\n12 mm"
    assert not any(m["role"] == "tool" for m in msgs) and SNAPSHOT not in json.dumps(msgs, ensure_ascii=False)


def test_messages_without_open_turn():
    ctx = Context("s")
    ctx.start_turn("你好", SNAPSHOT)
    ctx.end_turn("reply", "你好呀")
    assert [m["role"] for m in ctx.messages()] == ["system", "user", "assistant"]


def test_compact_text_rules():
    for kind in ("question", "reply", "failed"):
        assert compact_text(kind, "第一行\n第二行") == "第一行\n第二行"
    assert compact_text("confirm", "【需求单】\n零件：手机支架") == CONFIRM_COMPACT == "（已把需求单发给用户确认）"
    delivered = ("已交付 v2。\n检查结果（共 4 项，全部通过）：\n| 检查 | 结果 |\n|---|---|\n| width | 通过 |\n"
                 "本版变化：tilt_deg: 65 → 70\n截图：x\nSTEP：y")
    assert compact_text("delivered", delivered) == "已交付 v2。\n本版变化：tilt_deg: 65 → 70"
    assert compact_text("delivered", "已交付 v1。\n检查结果：\n截图：x") == "已交付 v1。"


def test_with_warning():
    content = json.dumps({"ok": True, "note": "中文"}, ensure_ascii=False)
    assert with_warning(content, 6) == content
    warned = with_warning(content, 5)
    assert json.loads(warned) == {"ok": True, "note": "中文", "warning": "本轮工具调用只剩 5 次"}
    assert "中文" in warned and "\\u" not in warned   # 中文不转义
    assert json.loads(with_warning(content, 0))["warning"] == "本轮工具调用只剩 0 次"
    for plain in ("不是 JSON", "[1, 2]", "42"):
        assert with_warning(plain, 1) == plain
