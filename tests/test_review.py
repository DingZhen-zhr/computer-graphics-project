"""看图审查：提示词和工具说明逐字比对、消息组装、结论解析、四视图渲染（标记 sca 的用真实沙盒）。"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from cad_agent.agent.state import PROMPT_DIR
from cad_agent.brief import Brief, Param
from cad_agent.llm.client import LLMReply, ToolCall
from cad_agent.llm.vision import tiny_test_image
from cad_agent.review import (MAX_REVIEW_ROUNDS, SUBMIT_REVIEW_SPEC, VIEWS, ReviewItem, ReviewResult, objection_note,
                              parse_review, review_line, review_messages, review_targets, run_review)

PLAN2 = Path(__file__).resolve().parent.parent / "docs" / "superpowers" / "plans" / "2026-11-10-caliper-2-llm.md"


def verbatim(letter: str) -> str:
    """计划 2"原文照抄"一节里 `### <字母>.` 小节的内容。"""
    doc = PLAN2.read_text(encoding="utf-8")
    start = doc.index(f"\n### {letter}. ")
    m = re.search(r"\n### [A-Z]\. ", doc[start + 5:])
    return doc[start:] if m is None else doc[start: start + 5 + m.start()]


def blocks(section: str, lang: str = "text") -> list[str]:
    return re.findall(rf"```{lang}\n(.*?)\n```", section, flags=re.S)


def brief(purpose: str = "放在桌上", relations: list[str] | None = None) -> Brief:
    return Brief(part_name="L 形支架", purpose=purpose, params=[Param("w", 60, "mm", "user", "宽")],
                 features=["底板", "立板"], relations=["立板的下端和底板的一端重叠"] if relations is None else relations,
                 confirmed=True)


def views(tmp_path: Path, missing: tuple[str, ...] = ()) -> dict[str, Path]:
    out = {}
    for name in VIEWS:
        if name in missing:
            continue
        p = tmp_path / f"{name}.png"
        p.write_bytes(tiny_test_image() + name.encode("ascii"))
        out[name] = p
    return out


def review_call(items: list[dict], overall: str = "看起来是一个 L 形支架") -> LLMReply:
    return LLMReply("", [ToolCall("r1", "submit_review", {"items": items, "overall": overall})], {"prompt_tokens": 50, "completion_tokens": 9, "total_tokens": 59})


TARGETS = ["底板", "立板", "立板的下端和底板的一端重叠"]


def test_constants():
    assert VIEWS == ("iso", "front", "top", "right") and MAX_REVIEW_ROUNDS == 2


def test_reviewer_prompt_is_verbatim():
    # 3.0 计划 2 Task 11（要改的旧测试）：原文后面接一句"整体做工"
    [expected] = blocks(verbatim("A"))
    plan3 = PLAN2.parent / "2026-11-20-datum-2-multipart.md"
    sentence = re.search(r"原文照抄：`(另外，在清单最后加一项.*?)`", plan3.read_text(encoding="utf-8")).group(1)
    assert (PROMPT_DIR / "reviewer.md").read_text(encoding="utf-8").rstrip("\n") == expected + "\n" + sentence


def test_submit_review_spec_is_verbatim():
    [expected] = blocks(verbatim("C"), "json")
    assert SUBMIT_REVIEW_SPEC == {"type": "function", "function": json.loads(expected)}


def test_user_text_is_verbatim(tmp_path):
    template, labels = blocks(verbatim("B"))
    msgs = review_messages(brief(), views(tmp_path))
    text = msgs[1]["content"][0]["text"]
    t = template.splitlines()
    assert text.splitlines() == [
        t[0].replace("<零件名>", "L 形支架").replace("<用途>", "放在桌上"), t[1], t[2], "- 底板", "- 立板", t[4],
        "- 立板的下端和底板的一端重叠"]
    no_purpose = review_messages(brief(purpose="", relations=[]), views(tmp_path))[1]["content"][0]["text"].splitlines()
    assert no_purpose[0] == "零件：L 形支架" and no_purpose[-1] == "- （没有）" and no_purpose[-2] == "位置关系："
    labels_sent = [p["text"] for p in msgs[1]["content"][1:] if p["type"] == "text"]
    assert labels_sent == labels.splitlines()


def test_missing_view_label(tmp_path):
    msgs = review_messages(brief(), views(tmp_path, missing=("top",)))
    parts = msgs[1]["content"]
    texts = [p["text"] for p in parts if p["type"] == "text"]
    assert "俯视图（这张图没有渲染出来）" in texts and "俯视图：" not in texts
    assert sum(1 for p in parts if p["type"] == "image_url") == 3
    i = texts.index("俯视图（这张图没有渲染出来）")
    assert texts[i + 1] == "右视图："   # 后面不接图片，直接是下一张的标题


def test_review_targets():
    # 3.0 计划 2 Task 11（要改的旧测试）：期望的末尾多"整体做工"
    assert review_targets(brief()) == TARGETS + ["整体做工"]
    assert review_targets(brief(relations=[])) == ["底板", "立板", "整体做工"]


def test_review_messages_have_no_modeling_context(tmp_path):
    msgs = review_messages(brief(), views(tmp_path))
    assert [m["role"] for m in msgs] == ["system", "user"]
    assert msgs[0]["content"] == (PROMPT_DIR / "reviewer.md").read_text(encoding="utf-8")
    parts = msgs[1]["content"]
    assert sum(1 for p in parts if p["type"] == "image_url") == 4
    order = [p["type"] for p in parts]
    assert order == ["text", "text", "image_url", "text", "image_url", "text", "image_url", "text", "image_url"]
    dump = json.dumps(msgs, ensure_ascii=False)
    assert "scad." not in dump and "make_box" not in dump and "feature" not in dump


def test_run_review_sends_only_submit_review(tmp_path):
    from cad_agent.llm.fake import ScriptedLLM

    llm = ScriptedLLM([review_call([{"target": t, "verdict": "match", "reason": "看得见"} for t in TARGETS])])
    result, reply = run_review(llm, brief(), views(tmp_path))
    assert result.passed and reply.usage["total_tokens"] == 59
    assert llm.tool_lists == [[SUBMIT_REVIEW_SPEC]] and len(llm.calls[0]) == 2


def test_parse_all_match():
    r = parse_review(review_call([{"target": t, "verdict": "match", "reason": f"在等轴测图上看到{t}"} for t in TARGETS]), TARGETS)
    assert r.passed and r.objections == [] and [i.target for i in r.items] == TARGETS
    assert r.overall == "看起来是一个 L 形支架"
    assert r.to_dict() == {"items": [{"target": t, "verdict": "match", "reason": f"在等轴测图上看到{t}"} for t in TARGETS],
                           "overall": "看起来是一个 L 形支架"}


def test_parse_mismatch():
    items = [{"target": "底板", "verdict": "match", "reason": "有"},
             {"target": "立板", "verdict": "mismatch", "reason": "正视图上立板叠在底板上面"},
             {"target": TARGETS[2], "verdict": "unreviewable", "reason": "看不清"}]
    r = parse_review(review_call(items), TARGETS)
    assert not r.passed and r.objections == [ReviewItem("立板", "mismatch", "正视图上立板叠在底板上面")]


def test_review_reply_without_tool_call():
    for reply in (LLMReply("我觉得都符合", [], {}),
                  LLMReply("", [ToolCall("x", "other_tool", {})], {}),
                  LLMReply("", [ToolCall("x", "submit_review", {"__raw__": "{bad"})], {}),
                  LLMReply("", [ToolCall("x", "submit_review", {"items": "全部符合", "overall": "好"})], {})):
        r = parse_review(reply, TARGETS)
        assert [i.verdict for i in r.items] == ["unreviewable"] * 3 and [i.target for i in r.items] == TARGETS
        assert r.overall == "审查没有给出有效的结论" and r.passed   # 没有异议，但也不是"全部符合"
        assert not any(i.verdict == "match" for i in r.items)


def test_missing_items_are_unreviewable():
    r = parse_review(review_call([{"target": "底板", "verdict": "match", "reason": "有"}]), TARGETS)
    assert [(i.target, i.verdict) for i in r.items] == [("底板", "match"), ("立板", "unreviewable"), (TARGETS[2], "unreviewable")]
    assert r.items[1].reason and r.passed


def test_unknown_verdict_and_extra_targets():
    items = [{"target": "底板", "verdict": "yes", "reason": "有"},
             {"target": "立板", "verdict": "mismatch", "reason": "缺了"},
             {"target": "不存在的部分", "verdict": "mismatch", "reason": "多出来的"},
             "不是对象", {"target": TARGETS[2], "verdict": "match"}]
    r = parse_review(review_call(items), TARGETS)
    assert [(i.target, i.verdict) for i in r.items] == [("底板", "unreviewable"), ("立板", "mismatch"), (TARGETS[2], "match")]
    assert [i.target for i in r.objections] == ["立板"]


def test_objection_note_format():
    [expected] = blocks(verbatim("D"))
    r = ReviewResult([ReviewItem("底板", "match", "有"), ReviewItem("立板", "mismatch", "叠在上面"),
                      ReviewItem("孔", "mismatch", "俯视图上没有孔")], "大体对")
    lines = expected.splitlines()
    assert objection_note(r).splitlines() == [lines[0], lines[1], "- 立板：叠在上面", "- 孔：俯视图上没有孔", lines[3]]


def test_review_lines_are_verbatim():
    section = verbatim("E")
    passed, objected, skipped = blocks(section)
    r = ReviewResult([ReviewItem("a", "match", ""), ReviewItem("b", "match", ""), ReviewItem("c", "unreviewable", "")], "")
    assert review_line(r, None) == passed.replace("<n>", "2").replace("<m>", "1")
    bad = ReviewResult([ReviewItem("a", "mismatch", "缺了"), ReviewItem("b", "mismatch", "反了")], "")
    head, item = objected.splitlines()
    assert review_line(bad, None).splitlines() == [head, "  - a：缺了", "  - b：反了"]
    assert item.startswith("  - ")
    assert review_line(None, "模型不能识图") == skipped.replace("<原因>", "模型不能识图")
    assert review_line(None, None) is None


@pytest.mark.sca
def test_render_views_real(tmp_path):
    from cad_agent.notebook import Feature, render_notebook
    from cad_agent.sandbox.execute import run_job

    params = [Param("w", 60, "mm", "user")]
    feats = [Feature("plate", "build", "plate = scad.make_box_rsolid(width=w, height=30, depth=8, bottom_face_center=(0, 0, 0))"),
             Feature("post", "add", "post = scad.union_rsolid(plate, scad.make_box_rsolid(width=8, height=8, depth=30, "
                                    "bottom_face_center=(20, 8, 0)))")]
    out = tmp_path / "看图" / "round-1"
    r = run_job(render_notebook(params, feats), [{"id": "x", "type": "bbox", "axis": "x", "expected": "w"}], {"w"},
                render_views=out, timeout_s=120)
    assert r.ok and set(r.view_paths) == set(VIEWS)
    data = {}
    for name, p in r.view_paths.items():
        assert p == out / f"{name}.png" and p.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
        data[name] = p.read_bytes()
    assert len(set(data.values())) == 4   # 四张互不相同
    plain = run_job(render_notebook(params, feats), [], {"w"}, timeout_s=120)
    assert plain.view_paths == {}
