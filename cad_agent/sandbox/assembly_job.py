"""父进程这边的装配任务：写零件 notebook 和 job.json，读回 result.json 整理成 AssemblyRun。"""

from __future__ import annotations

import copy
import json
import shutil
from pathlib import Path
from typing import TYPE_CHECKING

from cad_agent.sandbox.execute import STOPPED_ERROR
from cad_agent.sandbox.runner_assembly import AssemblyRun

if TYPE_CHECKING:
    from cad_agent.tools import Workspace


def _with_values(ws: "Workspace", values: dict[str, float] | None) -> "Workspace":
    """values 给了时，换成一份参数值改过的工作区副本（特征、零件状态共用，只换需求单）。"""
    if not values:
        return ws
    out = copy.copy(ws)
    out.brief = copy.deepcopy(ws.brief)
    for p in out.brief.params:
        if p.name in values:
            p.value = float(values[p.name])
    return out


def prepare(ws: "Workspace", workdir: Path, *, mode: str, samples: int, timeout_s: float,
            values: dict[str, float] | None) -> Path:
    from cad_agent.product.render import render_part_notebook
    from cad_agent.product.workspace import part_param_names, select_part

    if ws.active is not None:   # 让 parts 里的当前零件和工作区字段一致
        select_part(ws, ws.active)
    wv = _with_values(ws, values)
    parts = []
    for p in wv.brief.parts:
        nb = render_part_notebook(wv, p.id)
        d = workdir / "parts" / p.id
        d.mkdir(parents=True, exist_ok=True)
        (d / "model.py").write_text(nb.text, encoding="utf-8")
        parts.append({"id": p.id, "param_names": part_param_names(wv, p.id),
                      "cell_lines": {k: list(v) for k, v in nb.cell_lines.items()}})
    job = {
        "workdir": str(workdir), "mode": "assembly", "export": mode == "export", "timeout_s": timeout_s,
        "samples": int(samples), "parts": parts, "values": wv.brief.param_values(),
        "params": [{"name": p.name, "value": p.value, "unit": p.unit, "source": p.source, "note": p.note, "part": p.part}
                   for p in wv.brief.params],
        "connectors": {pid: [c.to_dict() for c in st.connectors] for pid, st in wv.parts.items()},
        "assembly": wv.assembly.to_dict() if wv.assembly is not None else None,
        "checks": list(wv.assembly_checks_raw),
    }
    path = workdir / "job.json"
    path.write_text(json.dumps(job, ensure_ascii=False), encoding="utf-8")
    return path


def collect(workdir: Path, outcome: str, stderr: str, returncode: int | None, duration_s: float, limit_s: float,
            out_dir: Path | None) -> AssemblyRun:
    if outcome == "stopped":
        return AssemblyRun(ok=False, error=dict(STOPPED_ERROR), duration_s=duration_s)
    if outcome == "timeout":
        return AssemblyRun(ok=False, timed_out=True, duration_s=duration_s,
                           error={"cell": None, "type": "TimeoutError", "message": f"装配检查超过 {limit_s:g} 秒被终止"})
    path = workdir / "result.json"
    if not path.exists():
        tail = (stderr or "").strip()[-500:]
        return AssemblyRun(ok=False, duration_s=duration_s,
                           error={"cell": None, "type": "SandboxCrash", "message": f"运行进程异常退出（返回码 {returncode}）：{tail}"})
    res = json.loads(path.read_text(encoding="utf-8"))
    files: dict[str, Path] = {}
    if out_dir is not None:
        for name in res.get("files") or []:
            dst = Path(out_dir) / name
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(workdir / name, dst)
            files[name] = dst
    connectors = res.get("connectors") or {}
    samples = res.get("samples") or {}
    ok = (res.get("error") is None and not any("error" in c for c in connectors.values())
          and not any(row.get("error") for rows in samples.values() for row in rows))
    return AssemblyRun(ok=ok, error=res.get("error"), connectors=connectors, rest=res.get("rest") or {},
                       overlaps=res.get("overlaps") or [], measures=res.get("measures") or {}, samples=samples,
                       files=files, duration_s=duration_s, timed_out=bool(res.get("timed_out")))
