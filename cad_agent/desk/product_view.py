"""界面状态里多零件和参数面板的部分（3.0 计划 2 Task 13）：product、params_view，以及检查结果属于哪个零件。

单零件时 product 是 None；params_view 和检查的 part 字段单零件也有（part 是 "main"）。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from cad_agent.brief import Brief, feature_name
from cad_agent.product.checks import evaluate, mandatory_checks
from cad_agent.product.materials import MATERIALS
from cad_agent.tools import Workspace

OTHER = "其他"


def _read(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _label(name: str, note: str) -> str:
    """参数在面板上的名字：说明里第一个标点之前的部分（"盖子厚度（建议）"→"盖子厚度"）；没有说明就用参数名。"""
    return feature_name(note) or name


def params_view(brief: Brief) -> list[dict]:
    if brief.is_multipart():
        groups = {p.id: p.name for p in brief.parts}
        names = [p.name for p in brief.parts]
    else:
        groups, names = {}, [feature_name(f) for f in brief.features]
    out = []
    for p in brief.params:
        group = groups.get(p.part) if p.part else next((n for n in names if n and n in p.note), None)
        out.append({"name": p.name, "label": _label(p.name, p.note), "group": group or OTHER, "unit": p.unit,
                    "value": int(p.value) if float(p.value).is_integer() else p.value, "source": p.source, "part": p.part})
    return out


def assembly_status(ws: Workspace) -> str:
    if ws.assembly_passed:
        return "passed"
    return "failed" if ws.last_assembly is not None else "todo"


def _part_checks(ws: Workspace, pid: str) -> list[dict]:
    if pid == ws.active and ws.last_run is not None and not ws.parts[pid].done:
        return [c.to_dict() for c in ws.last_run.checks]
    return list(ws.parts[pid].results)


def product_view(session_id: str, ws: Workspace | None, brief: dict, versions: list[Path]) -> dict | None:
    """多零件的进度、关节和运动数据地址；单零件返回 None。ws 为 None（示例会话）时从文件读。"""
    b = Brief.from_dict(brief)
    if not b.is_multipart():
        return None
    motion = next((v for v in reversed(versions) if (v / "motion.json").is_file()), None)
    parts = []
    for p in b.parts:
        m = MATERIALS[p.material]
        if ws is not None and p.id in ws.parts:
            st = ws.parts[p.id]
            status = "done" if st.done else ("current" if p.id == ws.active else "todo")
            checks = _part_checks(ws, p.id)
        else:
            status = "done" if motion is not None else "todo"
            raw = _read(motion / "parts" / p.id / "checks.json") if motion is not None else None
            checks = raw if isinstance(raw, list) else []
        parts.append({"id": p.id, "name": p.name, "material": p.material, "color": p.color or m.color, "finish": m.finish,
                      "status": status, "checks": {"passed": sum(1 for c in checks if c.get("passed")), "total": len(checks)}})
    joints: list[dict] = []
    if ws is not None and ws.assembly is not None:
        values = ws.brief.param_values()
        from cad_agent.product.delivery import _num

        joints = [{"id": j.id, "label": j.label, "type": j.type, "unit": "deg" if j.type == "revolute" else "mm",
                   "lo": _num(j.lo, values), "hi": _num(j.hi, values)} for j in ws.assembly.joints]
    elif motion is not None:
        data = _read(motion / "motion.json") or {}
        joints = [{k: j[k] for k in ("id", "label", "type", "unit", "lo", "hi")} for j in data.get("joints", [])]
    if ws is not None:
        state = assembly_status(ws)
    else:
        state = "passed" if motion is not None else "todo"
    return {"parts": parts, "joints": joints, "assembly": state,
            "motion": f"/files/{session_id}/{motion.name}/motion.json" if motion is not None else None}


def multipart_checks(ws: Workspace) -> list[dict]:
    """多零件时界面显示的检查：每个零件的结果（带 part），再加最近一次装配检查（part 是 assembly）。"""
    out = []
    for pid in ws.parts:
        out += [{**c, "part": pid, "selected": None} for c in _part_checks(ws, pid)]
    if ws.last_assembly is not None and ws.assembly is not None:
        res = evaluate(ws.last_assembly, mandatory_checks(ws.assembly, list(ws.parts)) + ws.assembly_checks_raw, ws.assembly,
                       ws.brief.param_values())
        out += [{**r.to_dict(), "part": "assembly", "selected": None} for r in res]
    return out
