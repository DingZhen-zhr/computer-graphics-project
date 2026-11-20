"""从会话目录恢复智能体（第二版计划 3 Task 3）：打开旧会话时，需求单、计划、特征、检查从文件读回，
对话上下文从日志恢复成折叠后的各轮。

1.2 版留下的旧会话没有 plan.json：有特征时造一个只有一个阶段的计划，全部特征和检查归到 s1，有版本时标成已通过。
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

from cad_agent import brand
from cad_agent.agent.context import compact_text
from cad_agent.brief import Brief
from cad_agent.notebook import FeatureList
from cad_agent.plan import Plan, Stage
from cad_agent.session import Session
from cad_agent.tools import Workspace

if TYPE_CHECKING:
    from cad_agent.agent.loop import Agent

logger = logging.getLogger(f"{brand.COMMAND}.desk")
END_KINDS = ("reply", "question", "confirm", "delivered", "failed", "stopped")   # 一轮的结局（AgentTurn.kind）
LEGACY_TITLE = "整体"
LEGACY_DONE_WHEN = "零件完成"


def _read(path: Path, default: Any) -> Any:
    """读 JSON；文件不存在、或者读不出来（比如以前写到一半断电留下的半个文件）都按没有处理，后者写进程序日志。"""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default
    except (OSError, ValueError):
        logger.warning("会话文件读不出来，按没有处理：%s", path.name)
        return default


def load_workspace(session: Session) -> Workspace:
    """读 brief.json、features.json、checks.json、plan.json；没有的文件按空处理。"""
    d = session.part_dir()
    raw_brief = _read(d / "brief.json", None)
    brief = Brief.from_dict(raw_brief) if isinstance(raw_brief, dict) else Brief()
    features = FeatureList.from_list(_read(d / "features.json", []) or [])
    checks = [c for c in (_read(d / "checks.json", []) or []) if isinstance(c, dict)]
    raw_plan = _read(d / "plan.json", None)
    plan = Plan.from_list(raw_plan) if isinstance(raw_plan, list) and raw_plan else None
    if plan is None and features.items:   # 旧会话：按单阶段处理
        plan = Plan([Stage("s1", LEGACY_TITLE, LEGACY_DONE_WHEN, passed=bool(session.versions()))])
        for f in features.items:
            f.stage = f.stage or "s1"
        checks = [{**c, "stage": c.get("stage") or "s1"} for c in checks]
    ws = Workspace(brief, features, checks)
    ws.plan = plan
    if brief.is_multipart() and (d / "assembly.json").is_file():
        _load_product(session, ws)
    return ws


def _load_product(session: Session, ws: Workspace) -> None:
    """多零件：各零件从 parts/<编号> 读回，装配从 assembly.json、assembly_checks.json 读回。"""
    from cad_agent.product.workspace import restore_product

    meta = _read(session.dir / "assembly.json", {}) or {}
    done = set(meta.get("done") or [])
    parts = {}
    for p in ws.brief.parts:
        pd = session.dir / "parts" / p.id
        parts[p.id] = {"features": _read(pd / "features.json", []) or [], "checks": _read(pd / "checks.json", []) or [],
                       "plan": _read(pd / "plan.json", None), "connectors": _read(pd / "connectors.json", []) or [],
                       "done": p.id in done}
    restore_product(ws, {"active": meta.get("active"), "parts": parts, "assembly": meta.get("assembly"),
                         "assembly_checks": _read(session.dir / "assembly_checks.json", []) or [],
                         "assembly_passed": meta.get("assembly_passed")})


def past_turns(rows: list[dict]) -> list[dict]:
    """日志 → 之前各轮的折叠版（user、assistant 交替）。没有结束记录的最后一轮（上次异常退出）丢掉。"""
    out: list[dict] = []
    user: str | None = None
    for row in rows:
        kind = row.get("kind")
        if kind == "user":
            user = str(row.get("sent_as", row.get("text", "")))
        elif kind in END_KINDS and user is not None:
            out += [{"role": "user", "content": user}, {"role": "assistant", "content": compact_text(kind, str(row.get("text", "")))}]
            user = None
    return out


def _last_end_kind(rows: list[dict]) -> str | None:
    return next((r["kind"] for r in reversed(rows) if r.get("kind") in END_KINDS), None)


def resume_agent(agent: "Agent") -> None:
    """用 agent.session 目录里的内容填好 agent 的工作区和上下文。"""
    session = agent.session
    ws = load_workspace(session)
    if agent.staged:
        ws.brief.require_relations = True   # 和 ToolBox 造分阶段工作区时一样
    rows = session.read_log()
    ws.awaiting_confirmation = _last_end_kind(rows) == "confirm"
    agent.toolbox.ws = ws
    agent.context.restore(past_turns(rows))
    review_dir = session.dir / "review"   # 看图审查的图片目录接着编号，不覆盖以前的
    if review_dir.is_dir():
        agent.review_step._renders = sum(1 for p in review_dir.iterdir() if p.is_dir() and p.name.startswith("round-"))
