"""把会话日志折叠成桌面端的对话记录（第二版计划 3 Task 4）。

每一项是三种之一：
- {"role": "user", "text"}
- {"role": "assistant", "kind", "text", …}：一轮的结局（问题、确认、交付、失败、停止、出错、普通回复）
- {"role": "work", "stages": [{"id", "title", "passed", "tools": [...]}], "loose": [...]}：一轮里的工具调用树

工具归到哪个阶段：看日志里工具记录的 stage_at（工作台在工具开始时记下当时的当前阶段）；没有这一项的（旧日志）放进 loose。
"""

from __future__ import annotations

from typing import Callable

from cad_agent.agent.automation import has_error
from cad_agent.desk.labels import tool_label, tool_summary
from cad_agent.desk.events import _assistant_entry

END_KINDS = ("reply", "question", "confirm", "delivered", "failed", "stopped", "error")


def _stage_node(work: dict, sid: str, titles: dict[str, str]) -> dict:
    for node in work["stages"]:
        if node["id"] == sid:
            return node
    node = {"id": sid, "title": titles.get(sid, ""), "passed": False, "tools": []}
    work["stages"].append(node)
    return node


def _titles_from_plan(args: object) -> dict[str, str]:
    stages = args.get("stages") if isinstance(args, dict) else None
    if not isinstance(stages, list):
        return {}
    return {f"s{i}": str(s.get("title", "")) for i, s in enumerate(stages, 1) if isinstance(s, dict)}


def assistant_entry(kind: str, row: dict, version_extra: Callable[[str], dict] | None = None) -> dict:
    """一轮结局 → 对话里的一项。交付时带上这个版本的终检和看图审查（version_extra 按版本名取）。"""
    entry = _assistant_entry(kind, row)
    if kind == "delivered":
        entry["gate"] = entry["review"] = None
        if entry.get("version") and version_extra is not None:
            entry.update(version_extra(entry["version"]))
    return entry


def build_transcript(rows: list[dict], version_extra: Callable[[str], dict] | None = None) -> list[dict]:
    out: list[dict] = []
    work: dict | None = None
    titles: dict[str, str] = {}
    auto_reason: str | None = None

    def ensure_work() -> dict:
        nonlocal work
        if work is None:
            work = {"role": "work", "stages": [], "loose": []}
            out.append(work)
        return work

    for row in rows:
        kind = row.get("kind")
        if kind == "user":
            out.append({"role": "user", "text": str(row.get("text", ""))})
            work, auto_reason = None, None
        elif kind == "auto" and row.get("action") == "build":
            auto_reason = str(row.get("reason") or "")
        elif kind == "tool":
            name = str(row.get("name", ""))
            ok, summary = tool_summary(name, row.get("content"), skipped=bool(row.get("skipped")))
            reason = auto_reason if row.get("auto") else None
            node = {"name": name, "label": tool_label(name, row.get("args"), reason), "ok": ok, "summary": summary}
            auto_reason = None if row.get("auto") else auto_reason
            w = ensure_work()
            sid = row.get("stage_at")
            if isinstance(sid, str) and sid:
                _stage_node(w, sid, titles)["tools"].append(node)
            else:
                w["loose"].append(node)
            if name == "set_plan" and not has_error(str(row.get("content", ""))):
                titles.update(_titles_from_plan(row.get("args")))
        elif kind == "stage":
            sid = str(row.get("id", ""))
            titles[sid] = str(row.get("title") or titles.get(sid, ""))
            node = _stage_node(ensure_work(), sid, titles)
            node["passed"], node["title"] = True, titles[sid]
            if isinstance(row.get("checks"), int):
                node["checks"] = row["checks"]
        elif kind in END_KINDS:
            out.append(assistant_entry(kind, row, version_extra))
            work, auto_reason = None, None
    return out


def turn_totals(rows: list[dict]) -> tuple[dict, float | None]:
    """本会话累计的六项用量和费用（只算已经结束的轮；有一轮费用不知道就是 None）。"""
    keys = ("llm_calls", "tokens", "prompt_tokens", "completion_tokens", "cached_tokens", "reasoning_tokens")
    usage = dict.fromkeys(keys, 0)
    cost, known = 0.0, True
    for row in rows:
        if row.get("kind") not in END_KINDS or row.get("kind") == "error":
            continue
        for k in keys:
            usage[k] += int(row.get(k) or 0)
        if row.get("cost") is None:
            known = known and not int(row.get("llm_calls") or 0)
        else:
            cost += float(row["cost"])
    return usage, (cost if known and usage["llm_calls"] else None)
