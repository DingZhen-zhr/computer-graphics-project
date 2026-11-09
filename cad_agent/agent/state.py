"""给模型的系统提示词和每次调用前重新生成的状态消息。"""

from __future__ import annotations

import json
from pathlib import Path

from cad_agent.checks.spec import CheckSpecError, missing_coverage, parse_checks
from cad_agent.tools import Workspace

PROMPT_DIR = Path(__file__).parent / "prompts"


def load_system_prompt() -> str:
    """系统提示词全文，末尾接上 SCA 常用写法速查表。"""
    system = (PROMPT_DIR / "system.md").read_text(encoding="utf-8").rstrip("\n")
    sheet = (PROMPT_DIR / "sca_cheatsheet.md").read_text(encoding="utf-8").rstrip("\n")
    return system + "\n\n" + sheet + "\n"


def _last_build(ws: Workspace) -> str:
    run = ws.last_run
    if run is None:
        return "未运行"
    if run.error:
        cell = run.error.get("cell")
        return f"没通过：{cell}" if cell else f"没通过：{run.error['type']}（出错位置不在某个特征里）"
    failed = [c for c in run.checks if not c.passed]
    if failed:
        return f"没通过：{failed[0].id}"
    try:
        checks = parse_checks(ws.checks_raw, set(ws.brief.param_values()))
    except CheckSpecError:
        return "没通过：检查项和需求单对不上"
    missing = sorted(missing_coverage(checks, ws.brief.user_param_names()))
    return "没通过：缺少检查 " + "、".join(missing) if missing else "通过"


def render_state(ws: Workspace, failures_left: int, calls_left: int) -> str:
    """状态消息，格式见提示词文档第 2 节。每次调用模型前重新生成，作为第二条 system 消息。"""
    ok, _ = ws.brief.can_build()
    phase = "可以建模（需求单已确认）" if ok else "澄清中（需求单未确认）"
    features = "、".join(f"{f.slug}({f.role})" for f in ws.features.items) or "无"
    checks = "、".join(str(c.get("id")) for c in ws.checks_raw) or "无"
    brief_json = json.dumps(ws.brief.to_dict(), ensure_ascii=False, indent=1)
    return "\n".join([
        "【当前状态】",
        f"阶段：{phase}",
        "需求单：",
        brief_json,
        f"特征（按顺序）：{features}",
        f"检查项：{checks}",
        f"上次 build：{_last_build(ws)}",
        f"本轮剩余：建模失败还可 {failures_left} 次，工具调用还可 {calls_left} 次",
    ])
