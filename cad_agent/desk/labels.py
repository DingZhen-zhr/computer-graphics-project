"""工具调用在界面上的说明：开始时的一句"在做什么"（label），结束时的一句"结果怎样"（summary）。"""

from __future__ import annotations

import json
from typing import Any

AUTO_LABELS = {"param_change": "只改了参数，程序自动重新运行", "turn_end": "程序补跑一次检查"}
SUMMARY_LIMIT = 60


def _short(text: Any, limit: int = SUMMARY_LIMIT) -> str:
    s = " ".join(str(text).split())
    return s if len(s) <= limit else s[: limit - 1] + "…"


def _count(value: Any) -> int | None:
    return len(value) if isinstance(value, list) else None


def tool_label(name: str, args: Any, auto_reason: str | None = None) -> str:
    """工具开始执行时显示的一句中文。auto_reason 不为空时是程序代模型运行的 build。"""
    if auto_reason is not None:
        return AUTO_LABELS.get(auto_reason, "程序自动运行一次检查")
    a = args if isinstance(args, dict) else {}
    if name == "set_plan":
        n = _count(a.get("stages"))
        return f"制定计划（{n} 个阶段）" if n else "制定计划"
    if name == "upsert_feature":
        return f"写特征 {a.get('slug', '')}".rstrip()
    if name == "remove_feature":
        return f"删除特征 {a.get('slug', '')}".rstrip()
    if name == "set_checks":
        n = _count(a.get("checks"))
        parts = [p for p in (str(a.get("stage") or ""), f"{n} 条" if n is not None else "") if p]
        return "写检查" + (f"（{'，'.join(parts)}）" if parts else "")
    if name == "api_help":
        return f"查函数用法 {a.get('name', '')}".rstrip()
    if name == "read_reference":
        return f"查阅文档 {a.get('name', '')}".rstrip()
    return {"update_brief": "更新需求单", "ask_user": "提问", "request_confirmation": "请你确认需求单", "build": "运行并检查",
            "inspect": "查看几何", "probe": "试验代码"}.get(name, name)


def _build_summary(body: dict) -> str:
    if body.get("passed"):
        stages = body.get("stages_passed") or []
        head = f"阶段 {'、'.join(stages)} 通过" if stages else "通过"
        total = int(body.get("passed_checks") or 0) + len(body.get("failed_checks") or [])
        return f"{head}，检查 {body.get('passed_checks', 0)}/{total}"
    err = body.get("error")
    if isinstance(err, dict):
        where = f"特征 {err.get('feature')}" if err.get("feature") else "特征之间的引用"
        return f"运行出错（{where}）"
    failed = [f.get("id", "") for f in body.get("failed_checks") or [] if isinstance(f, dict)]
    if failed:
        return "检查没通过：" + _short("、".join(failed), 40)
    if body.get("missing_coverage"):
        return "还缺检查：" + _short("、".join(body["missing_coverage"]), 40)
    gate = body.get("final_gate") or {}
    if gate.get("unconstrained"):
        return "终检没通过：参数没被约束（" + _short("、".join(gate["unconstrained"]), 30) + "）"
    stages = body.get("stages_passed") or []
    if stages:
        return f"阶段 {'、'.join(stages)} 通过，下一个阶段还没写"
    return "没通过"


def tool_summary(name: str, content: Any, skipped: bool = False) -> tuple[bool, str]:
    """工具执行完：(是否成功, 一句结果)。content 是返回给模型的文字（通常是 JSON）。"""
    if skipped:
        return False, "前面的调用出错，这次没有运行"
    try:
        body = json.loads(content) if isinstance(content, str) else content
    except (TypeError, ValueError):
        body = None
    if not isinstance(body, dict):
        return True, "完成"
    if "error" in body and name != "build":
        return False, "出错：" + _short(body["error"])
    if name == "build":   # 阶段通过、只是下一个阶段还没写，也算顺利
        gate = body.get("final_gate") or {}
        clean = not (body.get("error") or body.get("failed_checks") or body.get("missing_coverage") or gate.get("unconstrained"))
        return bool(body.get("passed")) or (clean and bool(body.get("stages_passed"))), _build_summary(body)
    if name == "set_checks":
        n = body.get("count")
        return True, f"记下 {n} 条检查" if isinstance(n, int) else "已记下"
    if name == "update_brief":
        changes = body.get("changes") or []
        return True, _short("；".join(changes)) if changes else "需求单没有变化"
    if name == "set_plan":
        return True, "计划已记下"
    return True, "完成"
