"""修改前后对比的数据（3.0 计划 3 Task 8）：两个版本之间变了的参数和检查，以及各有哪些文件。只列有变化的项。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from cad_agent.brief import feature_name


def _read(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _params(vdir: Path) -> dict[str, dict]:
    raw = _read(vdir / "brief.json")
    return {p["name"]: p for p in (raw or {}).get("params", []) if isinstance(p, dict) and "name" in p}


def _checks(vdir: Path) -> dict[tuple[str, str], bool]:
    raw = _read(vdir / "checks.json")
    return {(str(c.get("part", "main")), str(c["id"])): bool(c.get("passed")) for c in raw or [] if isinstance(c, dict) and "id" in c}


def _files(vdir: Path) -> dict[str, bool]:
    return {"stl": (vdir / "model.stl").is_file() or (vdir / "parts").is_dir(), "png": (vdir / "view.png").is_file(),
            "motion": (vdir / "motion.json").is_file()}


def compare_versions(va: Path, vb: Path) -> dict:
    pa, pb = _params(va), _params(vb)
    params = []
    for name in [*pa, *[n for n in pb if n not in pa]]:
        a, b = pa.get(name), pb.get(name)
        av, bv = (a or {}).get("value"), (b or {}).get("value")
        if av == bv:
            continue
        p = b or a
        params.append({"name": name, "label": feature_name(str(p.get("note") or "")) or name, "unit": p.get("unit", ""), "a": av, "b": bv})
    ca, cb = _checks(va), _checks(vb)
    checks = [{"id": cid, "part": part, "a": ca.get((part, cid)), "b": cb.get((part, cid))}
              for part, cid in [*ca, *[k for k in cb if k not in ca]] if ca.get((part, cid)) != cb.get((part, cid))]
    return {"params": params, "checks": checks, "files": {"a": _files(va), "b": _files(vb)}}
