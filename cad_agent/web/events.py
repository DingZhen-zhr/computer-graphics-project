"""把会话日志（log.jsonl 的每一行）折叠成网页要显示的内容：对话记录、实时进度、用量、当前阶段。

实时界面和回放用的是同一个函数，所以两种模式看到的东西一模一样。
新日志在每轮结束的记录里带着结构化内容（问题列表、需求单、检查通过数）；
旧日志没有这些字段，就从给用户看的文字里解析出来。
"""

from __future__ import annotations

import re
from typing import Any, Iterable

from cad_agent.agent.automation import has_error

END_KINDS = ("reply", "question", "confirm", "delivered", "failed", "error")
STAGES = ("clarify", "confirm", "modeling", "checking", "delivered")
_NUMBERED = re.compile(r"^\s*\d+[.、]\s*(.+)$")
_TOTAL = re.compile(r"共\s*(\d+)\s*项")
CHANGE_PREFIX = "本版变化："
BRIEF_MARK = "【需求单】"


# ---------------------------------------------------------------- 一条日志 → 一句进度


def _short(value: Any, limit: int = 40) -> str:
    text = " ".join(str(value).split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def describe_event(kind: str, data: dict) -> str | None:
    """把一条日志变成一句给人看的进度；不需要显示的返回 None。"""
    if kind == "tool":
        return _describe_tool(data)
    if kind == "build":
        if data.get("passed"):
            return f"运行通过，检查 {data.get('passed_checks', 0)}/{data.get('total_checks', 0)}"
        error = data.get("error")
        if error:
            where = f"特征 {error.get('feature')}" if error.get("feature") else "特征之间的引用"
            return f"运行出错（{where}），模型正在修"
        if data.get("failed_checks"):
            return "检查没通过：" + _short("、".join(data["failed_checks"]))
        if data.get("missing_coverage"):
            return "还缺检查：" + _short("、".join(data["missing_coverage"]))
        return "运行没通过"
    if kind == "auto":
        if data.get("action") == "request_confirmation":
            return "需求单整理好了，请你确认"
        if data.get("reason") == "turn_end":
            return "程序补跑一次检查"
        return "只改了参数，程序自动重新运行"
    if kind == "stl_error":
        return "STL 导出失败，3D 预览改用截图"
    return None


def _describe_tool(data: dict) -> str | None:
    name, args = data.get("name"), data.get("args") or {}
    if data.get("skipped"):
        return "前面的调用出错，这次运行跳过了"
    if name in ("build", "ask_user", "request_confirmation"):
        return None  # build 由 build 记录负责；提问和确认会结束本轮，直接显示在对话里
    if has_error(str(data.get("content", ""))):
        return f"{_TOOL_LABEL.get(name, name)}出错，模型正在改"
    if name == "upsert_feature":
        return f"写特征 {args.get('slug', '')}".rstrip()
    if name == "remove_feature":
        return f"删除特征 {args.get('slug', '')}".rstrip()
    if name == "set_checks":
        checks = args.get("checks")
        return f"写检查项（{len(checks)} 条）" if isinstance(checks, list) else "写检查项"
    if name == "api_help":
        return f"查函数用法 {args.get('name', '')}".rstrip()
    return _TOOL_LABEL.get(name)


_TOOL_LABEL = {"update_brief": "更新需求单", "upsert_feature": "写特征", "remove_feature": "删除特征", "set_checks": "写检查项",
               "inspect": "查看几何", "api_help": "查函数用法"}


# ---------------------------------------------------------------- 一轮结束 → 一条助手消息


def _assistant_entry(kind: str, data: dict) -> dict:
    text = str(data.get("text", ""))
    entry: dict = {
        "role": "assistant", "kind": kind, "text": text, "lead": "", "questions": None, "brief": None,
        "version": data.get("version"), "passed": None, "total": None, "changes": [],
        "repairs": int(data.get("repairs") or 0), "llm_calls": int(data.get("llm_calls") or 0), "cost": data.get("cost"),
        "prompt_tokens": int(data.get("prompt_tokens") or 0), "cached_tokens": int(data.get("cached_tokens") or 0),
    }
    lines = text.splitlines()
    if kind == "question":
        if isinstance(data.get("questions"), list):
            entry["questions"] = [str(q) for q in data["questions"]]
            entry["lead"] = str(data.get("lead", ""))
        else:
            numbered = [i for i, line in enumerate(lines) if _NUMBERED.match(line)]
            entry["questions"] = [_NUMBERED.match(lines[i]).group(1) for i in numbered]  # type: ignore[union-attr]
            entry["lead"] = "\n".join(lines[: numbered[0]]).strip() if numbered else text
    elif kind == "confirm":
        entry["brief"] = data.get("brief") if isinstance(data.get("brief"), dict) else None
        entry["lead"] = str(data["lead"]) if "lead" in data else text.split(BRIEF_MARK)[0].strip()
    elif kind == "delivered":
        if isinstance(data.get("total"), int):
            entry["passed"], entry["total"] = int(data.get("passed") or 0), data["total"]
        elif (m := _TOTAL.search(text)) is not None:
            entry["passed"] = entry["total"] = int(m.group(1))  # 旧日志：交付时检查一定全部通过
        if isinstance(data.get("changes"), list):
            entry["changes"] = [str(c) for c in data["changes"]]
        else:
            line = next((x for x in lines if x.startswith(CHANGE_PREFIX)), "")
            entry["changes"] = [c for c in line[len(CHANGE_PREFIX):].split("；") if c]
    return entry


# ---------------------------------------------------------------- 整份日志 → 网页内容


def fold(events: Iterable[tuple[str, dict]], *, confirmed: bool, busy: bool) -> dict:
    """返回 transcript、activity、stats、stage、last_version。

    confirmed：需求单现在是否已确认；busy：是否正在处理一条消息（回放时为假）。
    """
    transcript: list[dict] = []
    activity: list[str] = []
    in_turn = turn_built = False
    turn_prompt = turn_cached = turn_calls = 0
    turn_cost: float | None = 0.0
    total = {"cost": 0.0, "cost_known": True, "prompt_tokens": 0, "cached_tokens": 0, "llm_calls": 0, "turns": 0}
    last_version: str | None = None

    for kind, data in events:
        if kind == "user":
            transcript.append({"role": "user", "text": str(data.get("text", ""))})
            activity, in_turn, turn_built = [], True, False
            turn_prompt = turn_cached = turn_calls = 0
            turn_cost = 0.0
        elif kind in END_KINDS:
            entry = _assistant_entry(kind, data)
            transcript.append(entry)
            activity, in_turn = [], False
            total["turns"] += 1
            total["prompt_tokens"] += entry["prompt_tokens"]
            total["cached_tokens"] += entry["cached_tokens"]
            total["llm_calls"] += entry["llm_calls"]
            if entry["cost"] is None:
                total["cost_known"] = total["cost_known"] and entry["llm_calls"] == 0
            else:
                total["cost"] += float(entry["cost"])
            if kind == "delivered" and entry["version"]:
                last_version = entry["version"]
        else:
            if kind == "assistant":
                usage = data.get("usage") or {}
                turn_calls += 1
                turn_prompt += int(usage.get("prompt_tokens", 0) or 0)
                turn_cached += int(usage.get("cached_tokens", 0) or 0)
                turn_cost = None if turn_cost is None or data.get("cost") is None else turn_cost + float(data["cost"])
            if kind == "build" or (kind == "auto" and data.get("action") == "build"):
                turn_built = True
            line = describe_event(kind, data)
            if line is not None:
                activity.append(line)

    stats = {"prompt_tokens": total["prompt_tokens"], "cached_tokens": total["cached_tokens"],
             "llm_calls": total["llm_calls"], "turns": total["turns"]}
    cost_known = total["cost_known"]
    cost = total["cost"]
    if in_turn and turn_calls:
        stats["prompt_tokens"] += turn_prompt
        stats["cached_tokens"] += turn_cached
        stats["llm_calls"] += turn_calls
        if turn_cost is None:
            cost_known = False
        else:
            cost += turn_cost
    stats["cost"] = cost if cost_known and stats["llm_calls"] else None
    stats["cache_ratio"] = stats["cached_tokens"] / stats["prompt_tokens"] if stats["prompt_tokens"] else None

    return {"transcript": transcript, "activity": activity if in_turn else [], "stats": stats,
            "stage": _stage(transcript, confirmed, busy or in_turn, turn_built), "last_version": last_version}


def _stage(transcript: list[dict], confirmed: bool, working: bool, built: bool) -> str:
    """五步流程里现在走到哪一步：澄清 → 确认 → 建模 → 检查 → 交付。"""
    if working:
        if built:
            return "checking"
        return "modeling" if confirmed else "clarify"
    last = next((t["kind"] for t in reversed(transcript) if t["role"] == "assistant"), None)
    if last == "confirm":
        return "confirm"
    if last == "delivered":
        return "delivered"
    return "modeling" if confirmed else "clarify"
