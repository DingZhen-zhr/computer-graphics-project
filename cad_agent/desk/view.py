"""把会话目录和日志变成界面要的完整状态（第二版计划 3 Task 4）。

ws 是智能体的工作区；示例会话没有智能体，ws 为 None，需求单和计划从文件读。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from cad_agent.brief import Brief
from cad_agent.desk.product_view import multipart_checks, params_view, product_view
from cad_agent.desk.stl_info import stl_facts
from cad_agent.desk.transcript import build_transcript, turn_totals
from cad_agent.session import Session
from cad_agent.tools import Workspace
from cad_agent.desk.replay import version_summary

NEW_TITLE = "新会话"


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def session_title(session: Session, brief: dict | None) -> str:
    """标题：meta.json 里有就用它；没有用需求单的零件名；都没有是"新会话"。"""
    title = str(session.meta().get("title") or "").strip()
    if title:
        return title
    name = str(((brief or {}).get("part") or {}).get("name") or "").strip()
    return name or NEW_TITLE


def _version_extra(vdir: Path) -> dict:
    gate, review = _read_json(vdir / "gate.json"), _read_json(vdir / "review.json")
    return {"gate": gate if isinstance(gate, dict) else None, "review": review if isinstance(review, dict) else None}


def version_entry(vdir: Path) -> dict:
    s = version_summary(vdir)
    size, volume = stl_facts(vdir / "model.stl")
    stages_dir = vdir / "stages"
    stages = sorted((p.stem for p in stages_dir.glob("*.stl")), key=lambda x: (len(x), x)) if stages_dir.is_dir() else []
    return {"name": vdir.name, "changes": s["changes"], "size": size, "volume": volume, "has_stl": s["has_stl"],
            "has_png": s["has_png"], "passed": s["passed"], "total": s["total"], "stages": stages,
            "created": _mtime(vdir), **_version_extra(vdir)}


def _mtime(p: Path) -> str | None:
    import datetime

    try:
        return datetime.datetime.fromtimestamp(p.stat().st_mtime).isoformat(timespec="seconds")
    except OSError:
        return None


def _checks(ws: Workspace | None, versions: list[Path]) -> list[dict]:
    """最近一次验证的每条检查结果，带上它属于哪个阶段（从检查项里查）、哪个零件（单零件是 main）。"""
    if ws is not None and ws.parts:
        return multipart_checks(ws)
    if ws is not None and ws.last_run is not None:
        results = [c.to_dict() for c in ws.last_run.checks]
    else:
        raw = _read_json(versions[-1] / "checks.json") if versions else None
        results = [c for c in raw if isinstance(c, dict)] if isinstance(raw, list) else []
    stage_of = {c.get("id"): c.get("stage") for c in (ws.checks_raw if ws is not None else []) if isinstance(c, dict)}
    return [{**c, "stage": c.get("stage") or stage_of.get(c.get("id")), "part": c.get("part", "main"), "selected": None}
            for c in results]


def _last_row(rows: list[dict], kind: str) -> dict | None:
    row = next((r for r in reversed(rows) if r.get("kind") == kind), None)
    if row is None:
        return None
    return {k: v for k, v in row.items() if k not in ("ts", "kind", "usage", "cost")}


def _phase(ws: Workspace | None, brief: dict, transcript: list[dict], has_versions: bool) -> str:
    last = next((t.get("kind") for t in reversed(transcript) if t["role"] == "assistant"), None)
    if ws is None:   # 示例会话：只看对话记录
        if last in ("delivered", "confirm"):
            return last
        return "modeling" if brief.get("confirmed") else "clarify"
    if ws.awaiting_confirmation:
        return "confirm"
    if not ws.brief.can_build()[0]:
        return "clarify"
    if ws.plan is None:
        if ws.brief.require_relations:   # 分阶段：还没有计划
            return "planning"
        return "delivered" if last == "delivered" else "modeling"   # 关掉分阶段时的老流程没有计划
    if ws.plan.complete() and has_versions:
        return "delivered"
    return "modeling"


def build_state(session: Session, ws: Workspace | None, *, busy: bool, demo: bool) -> dict:
    rows = session.read_log()
    vdirs = session.versions()
    if ws is not None:
        brief = ws.brief.to_dict()
    else:
        raw = _read_json(session.part_dir() / "brief.json")
        brief = raw if isinstance(raw, dict) else Brief().to_dict()
    transcript = build_transcript(rows, lambda name: _version_extra(session.part_dir() / "versions" / name))
    plan_obj = ws.plan if ws is not None else None
    plan = None
    if plan_obj is not None:
        cur = plan_obj.current()
        plan = {"stages": plan_obj.to_list(), "current": cur.id if cur is not None else None}
    elif ws is None:
        raw_plan = _read_json(session.part_dir() / "plan.json")
        if isinstance(raw_plan, list) and raw_plan:
            plan = {"stages": raw_plan, "current": next((s["id"] for s in raw_plan if not s.get("passed")), None)}
    versions = [version_entry(v) for v in vdirs]
    stage_dir = session.dir / "stages"
    passed = {s["id"] for s in (plan or {}).get("stages", []) if s.get("passed")}
    stage_files = sorted((p.stem for p in stage_dir.glob("*.stl") if p.stem in passed), key=lambda x: (len(x), x)) \
        if stage_dir.is_dir() else []
    gate = _last_row(rows, "gate") or (versions[-1]["gate"] if versions else None)
    review = (versions[-1]["review"] if versions else None) or _last_row(rows, "review")
    usage, cost = turn_totals(rows)
    return {
        "session": {"id": session.dir.name, "title": session_title(session, brief), "demo": demo},
        "busy": busy,
        "phase": _phase(ws, brief, transcript, bool(vdirs)),
        "transcript": transcript,
        "brief": brief,
        "plan": plan,
        "checks": _checks(ws, vdirs),
        "product": product_view(session.dir.name, ws, brief, vdirs),
        "params_view": params_view(ws.brief if ws is not None else Brief.from_dict(brief)),
        "gate": gate,
        "review": review,
        "versions": versions,
        "stage_files": stage_files,
        "usage": usage,
        "cost": cost,
        "last_seq": 0,
    }
