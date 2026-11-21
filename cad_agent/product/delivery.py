"""多零件的交付：导出一个版本目录、写 motion.json、交付给用户看的文字（设计文档第 5.8、7.7 节）。

版本目录：brief.json、assembly.json、assembly.py、product.step、view.png、motion.json、checks.json、gate.json、changes.md、
parts/<编号>/model.py|model.step|model.stl|checks.json。
"""

from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ..checks.expr import eval_expr
from ..checks.spec import CheckResult
from .checks import evaluate, mandatory_checks, real_hits
from .kinematics import explode_directions, frame_from_geometry
from .materials import MATERIALS
from .render import render_part_notebook

if TYPE_CHECKING:
    from ..session import Session
    from ..tools import Workspace

UNIT_KEY = {"revolute": "deg", "prismatic": "mm"}
UNIT_TEXT = {"revolute": "°", "prismatic": " 毫米"}


def _num(v: Any, values: dict[str, float]) -> float:
    return float(v) if isinstance(v, (int, float)) else eval_expr(v, values)


def _g(v: float) -> str:
    return f"{round(float(v), 3):g}"


def motion_data(ws: "Workspace", run: Any) -> dict:
    """motion.json 的内容：界面播放的运动和碰撞检查用的是同一份姿态（run 里的取样）。"""
    values = ws.brief.param_values()
    parts = {}
    for p in ws.brief.parts:
        m = MATERIALS[p.material]
        parts[p.id] = {"name": p.name, "material": p.material, "color": p.color or m.color, "finish": m.finish,
                       "stl": f"parts/{p.id}/model.stl"}
    frames = {k: frame_from_geometry(v.get("type", ""), v["center"], v["direction"], 0, False)
              for k, v in run.connectors.items() if "center" in v}
    explode = explode_directions(ws.assembly, frames, run.rest) if frames and run.rest else {}
    joints = []
    for j in ws.assembly.joints:
        joints.append({"id": j.id, "label": j.label, "type": j.type, "unit": UNIT_KEY[j.type],
                       "lo": _num(j.lo, values), "hi": _num(j.hi, values),
                       "samples": [{"value": r["value"], "poses": r["poses"], "hits": real_hits(ws.assembly, r["hits"])} for r in run.samples.get(j.id, [])]})
    return {"parts": parts, "rest": run.rest, "explode": {k: list(v) for k, v in explode.items()}, "joints": joints}


def _write(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1, default=str), encoding="utf-8")


def write_product_version(session: "Session", ws: "Workspace", run: Any, files_dir: Path, *, assembly_results: list[CheckResult],
                          gate: dict | None, changes: list[str]) -> Path:
    v = session.reserve_version()
    for name in ("assembly.py", "product.step", "view.png"):
        shutil.copyfile(files_dir / name, v / name)
    checks: list[dict] = []
    for p in ws.brief.parts:
        d = v / "parts" / p.id
        d.mkdir(parents=True, exist_ok=True)
        (d / "model.py").write_text(render_part_notebook(ws, p.id).text, encoding="utf-8")
        for name in ("model.step", "model.stl"):
            shutil.copyfile(files_dir / "parts" / p.id / name, d / name)
        _write(d / "connectors.json", [c.to_dict() for c in ws.parts[p.id].connectors])   # 验收要用（不读 motion.json）
        own = [{**r, "part": p.id} for r in ws.parts[p.id].results]
        _write(d / "checks.json", own)
        checks += own
    checks += [{**r.to_dict(), "part": "assembly"} for r in assembly_results]
    _write(v / "checks.json", checks)
    _write(v / "brief.json", ws.brief.to_dict())
    _write(v / "assembly.json", ws.assembly.to_dict())
    _write(v / "motion.json", motion_data(ws, run))
    _write(v / "gate.json", gate or {})
    lines = [f"# {v.name} 变更说明", ""] + ([f"- {c}" for c in changes] if changes else ["- （需求单参数没有变化）"])
    (v / "changes.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return v


def export_product_version(agent: Any, changes: list[str]) -> Path | str:
    """导出产品并存成新版本。成功返回版本目录，失败返回给用户看的文字。"""
    box, ws = agent.toolbox, agent.ws
    with tempfile.TemporaryDirectory(prefix="cad-agent-out-") as tmp:
        out = Path(tmp)
        run = box.run_assembly(ws, mode="export", samples=box.motion_samples, timeout_s=box.timeout_s,
                               secret_names=box.secret_names, out_dir=out, should_stop=box.should_stop)
        results = evaluate(run, mandatory_checks(ws.assembly, list(ws.parts)) + ws.assembly_checks_raw, ws.assembly,
                           ws.brief.param_values())
        needed = ["assembly.py", "product.step", "view.png"] + [f"parts/{p.id}/{n}" for p in ws.brief.parts for n in ("model.step", "model.stl")]
        if not run.ok or not all(r.passed for r in results) or any(not (out / n).is_file() for n in needed):
            why = run.error["message"] if run.error else "检查没有全部通过或没有生成导出文件"
            return f"检查已经通过，但交付时导出出了问题：{why}"
        ws.last_assembly = run
        gate = box.last_gate.to_dict() if box.last_gate is not None else None
        return write_product_version(agent.session, ws, run, out, assembly_results=results, gate=gate, changes=changes)


def product_delivery_text(ws: "Workspace", version: Path, changes: list[str], gate_line: str | None) -> str:
    checks = json.loads((version / "checks.json").read_text(encoding="utf-8"))
    motion = json.loads((version / "motion.json").read_text(encoding="utf-8"))
    k = int(version.name.lstrip("v"))
    lines = [f"做好了，{len(ws.brief.parts)} 个零件，存成第 {k} 版。"]
    names = {p.id: p.name for p in ws.brief.parts} | {"assembly": "装配"}
    for pid in [p.id for p in ws.brief.parts] + ["assembly"]:
        rows = [c for c in checks if c["part"] == pid]
        if not rows:
            continue
        lines.append(f"{names[pid]}（{len(rows)} 项，全部通过）：")
        lines += ["| 检查 | 结果 | 实测 | 期望 |", "|---|---|---|---|"]
        lines += [f"| {c['id']} | {'通过' if c['passed'] else '没通过'} | {'-' if c['measured'] is None else _g(c['measured'])} | "
                  f"{'-' if c['expected'] is None else _g(c['expected'])} |" for c in rows]
    for j in motion["joints"]:
        unit = UNIT_TEXT["revolute" if j["unit"] == "deg" else "prismatic"]
        lines.append(f"{j['label']}：从 {_g(j['lo'])} 到 {_g(j['hi'])}{unit}，取了 {len(j['samples'])} 个位置，都没有碰到别的零件。")
    if gate_line:
        lines.append(gate_line)
    if changes:
        lines.append("本版变化：" + "；".join(changes))
    lines += [f"截图：{version / 'view.png'}", f"STEP：{version / 'product.step'}"]
    return "\n".join(lines)
