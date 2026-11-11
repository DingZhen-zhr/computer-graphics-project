"""看图审查（设计文档第 3.6 节第 (3) 项）：交付前，让一个只看图、没看过建模过程的审查者逐项判断。

审查者拿到的只有：审查者提示词（prompts/reviewer.md）、需求单的零件、组成部分、位置关系，以及四张渲染图。
它必须调用 submit_review 回答；没调用、格式不对、少了条目，一律按"看不出"算，不当成"全部符合"。
文字全部取自计划 2"原文照抄"一节。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from cad_agent.agent.state import PROMPT_DIR
from cad_agent.brief import Brief
from cad_agent.llm.client import LLM, LLMReply
from cad_agent.llm.vision import image_part, text_part

VIEWS = ("iso", "front", "top", "right")
VIEW_NAMES = {"iso": "等轴测图", "front": "正视图", "top": "俯视图", "right": "右视图"}
MAX_REVIEW_ROUNDS = 2
VERDICTS = ("match", "mismatch", "unreviewable")
SUBMIT_REVIEW_SPEC: dict = {"type": "function",
                            "function": json.loads((PROMPT_DIR / "submit_review.json").read_text(encoding="utf-8"))}
INVALID_OVERALL = "审查没有给出有效的结论"
NOT_MENTIONED = "审查没有提到这一项"
SKIP_REASONS = ("模型不能识图", "已关闭", "没有渲染出图片", "审查调用失败")


@dataclass(frozen=True)
class ReviewItem:
    target: str                                    # 组成部分的名字，或位置关系的原文
    verdict: Literal["match", "mismatch", "unreviewable"]
    reason: str


@dataclass
class ReviewResult:
    items: list[ReviewItem]
    overall: str

    @property
    def objections(self) -> list[ReviewItem]:
        return [i for i in self.items if i.verdict == "mismatch"]

    @property
    def passed(self) -> bool:
        return not self.objections

    def to_dict(self) -> dict:
        return {"items": [{"target": i.target, "verdict": i.verdict, "reason": i.reason} for i in self.items],
                "overall": self.overall}


def review_targets(brief: Brief) -> list[str]:
    """清单：各组成部分的原文，后面接各条位置关系的原文。"""
    return [*brief.features, *brief.relations]


def _user_text(brief: Brief) -> str:
    head = f"零件：{brief.part_name}（{brief.purpose}）" if brief.purpose.strip() else f"零件：{brief.part_name}"
    lines = [head, "请逐项审查下面的清单。", "组成部分："]
    lines += [f"- {f}" for f in brief.features]
    lines.append("位置关系：")
    lines += [f"- {r}" for r in brief.relations] if brief.relations else ["- （没有）"]
    return "\n".join(lines)


def review_messages(brief: Brief, views: dict[str, Path]) -> list[dict]:
    """一条 system（审查者提示词全文）和一条 user（清单文字，后面依次接四张图，每张图前面一行视角名）。"""
    parts: list[dict] = [text_part(_user_text(brief))]
    for name in VIEWS:
        label = VIEW_NAMES[name]
        path = views.get(name)
        if path is None:
            parts.append(text_part(f"{label}（这张图没有渲染出来）"))
        else:
            parts += [text_part(f"{label}："), image_part(path)]
    system = (PROMPT_DIR / "reviewer.md").read_text(encoding="utf-8")
    return [{"role": "system", "content": system}, {"role": "user", "content": parts}]


def _invalid(targets: list[str]) -> ReviewResult:
    return ReviewResult([ReviewItem(t, "unreviewable", INVALID_OVERALL) for t in targets], INVALID_OVERALL)


def parse_review(reply: LLMReply, targets: list[str]) -> ReviewResult:
    call = next((tc for tc in reply.tool_calls if tc.name == "submit_review"), None)
    args = call.arguments if call is not None else None
    if not isinstance(args, dict) or "__raw__" in args or not isinstance(args.get("items"), list):
        return _invalid(targets)
    found: dict[str, ReviewItem] = {}
    for raw in args["items"]:
        if not isinstance(raw, dict) or not isinstance(raw.get("target"), str):
            continue
        target = raw["target"].strip()
        if target not in targets or target in found:   # 多出来的、重复的条目丢掉
            continue
        reason = raw.get("reason") if isinstance(raw.get("reason"), str) else ""
        verdict = raw.get("verdict")
        if verdict not in VERDICTS:
            verdict, reason = "unreviewable", f"审查给出的结论不认识（{verdict!r}）" + (f"：{reason}" if reason else "")
        found[target] = ReviewItem(target, verdict, reason)
    items = [found.get(t) or ReviewItem(t, "unreviewable", NOT_MENTIONED) for t in targets]
    overall = args.get("overall") if isinstance(args.get("overall"), str) else ""
    return ReviewResult(items, overall)


def run_review(llm: LLM, brief: Brief, views: dict[str, Path]) -> tuple[ReviewResult, LLMReply]:
    """发起一次独立的审查调用：全新的上下文，只给一个工具 submit_review。模型调用失败时抛 LLMError。"""
    reply = llm.chat(review_messages(brief, views), [SUBMIT_REVIEW_SPEC])
    return parse_review(reply, review_targets(brief)), reply


def objection_note(result: ReviewResult) -> str:
    """退回给建模模型的 user 消息（原文照抄 D）。"""
    lines = ["【看图审查没有通过（程序生成）】", "一位只看渲染图、没看过你的代码的审查者认为下面这些地方和需求单不一致："]
    lines += [f"- {i.target}：{i.reason}" for i in result.objections]
    lines.append("请对照需求单检查这些地方。确实做错了就改对应的特征，然后 build；如果你确认模型是对的，就补一条能证明这一点的检查，然后 build。")
    return "\n".join(lines)


def review_line(review: ReviewResult | None, skipped: str | None) -> str | None:
    """交付文字里审查的那一行（原文照抄 E）；两个都是 None 时没有这一行。"""
    if review is not None:
        if review.passed:
            n = sum(1 for i in review.items if i.verdict == "match")
            m = sum(1 for i in review.items if i.verdict == "unreviewable")
            return f"看图审查：通过（{n} 项符合，{m} 项看不出）。"
        return "\n".join(["看图审查有异议，请你自己看一下模型：", *[f"  - {i.target}：{i.reason}" for i in review.objections]])
    if skipped is not None:
        return f"未做看图审查（{skipped}）。"
    return None
