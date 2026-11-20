"""装配的子进程：运行每个零件、取连接点、装好、量穿模和对齐、每个关节取样、导出（设计文档第 5 节）。

由 runner.py 在 job 的 mode 是 "assembly" 时调用。AssemblyRun 是父进程整理后的结果（execute.run_assembly）。
连接点选中的不是恰好一个圆柱面、平面或圆形的边时，照实记下，不猜一个用。
某个取样位置出错时，这个位置的 error 写明原因，不跳过。
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

FAIL_SAMPLE_ENV = "DATUM_TEST_FAIL_SAMPLE"   # 只给测试用："<关节 id>:<第几个位置>"，在那个位置故意出错
COUNT_MSG = "零件 {part} 的连接点 {name} 选中了 {n} 个几何，要恰好 1 个。改一下 where 的条件。"
TYPE_MSG = "零件 {part} 的连接点 {name} 选中的是 {type}，只能是圆柱面、平面或圆形的边。"
GEOM_TYPES = ("interference", "clearance", "coaxial", "flush")


@dataclass
class AssemblyRun:
    ok: bool
    error: dict | None
    connectors: dict[str, dict] = field(default_factory=dict)
    rest: dict[str, list[float]] = field(default_factory=dict)
    overlaps: list[dict] = field(default_factory=list)
    measures: dict[str, dict] = field(default_factory=dict)
    samples: dict[str, list[dict]] = field(default_factory=dict)
    files: dict[str, Path] = field(default_factory=dict)
    duration_s: float = 0.0
    timed_out: bool = False


def _r(v: float) -> float:
    return round(float(v), 6) + 0.0


def _mat(m: list[float]) -> list[float]:
    return [_r(v) for v in m]


def _run_parts(job: dict, out: dict) -> tuple[dict, dict] | None:
    from simplecadapi.runtime import run_notebook

    from cad_agent.sandbox.runner import _error, failed_slug

    workdir = Path(job["workdir"])
    solids, runs = {}, {}
    for part in job["parts"]:
        pid = part["id"]
        nb = workdir / "parts" / pid / "model.py"
        try:
            run = run_notebook(nb, cache=False, timeout=job["timeout_s"])
        except TimeoutError:
            out["timed_out"] = True
            out["error"] = {"cell": None, "part": pid, "type": "TimeoutError", "message": f"零件 {pid} 运行超过 {job['timeout_s']:g} 秒被终止"}
            return None
        except Exception as e:  # noqa: BLE001 - 零件代码里的任何异常都要翻译后交回模型
            out["error"] = {**_error(failed_slug(e, nb, part.get("cell_lines") or {}), e), "part": pid}
            return None
        solids[pid], runs[pid] = run.product.body, run
    return solids, runs


def _anchor(job: dict, solids: dict, out: dict) -> dict | None:
    """每个连接点选几何、算坐标系。全部挂上了返回 frames，否则返回 None（原因在 out["connectors"]）。"""
    from cad_agent.checks.engine import _select
    from cad_agent.checks.expr import eval_expr
    from cad_agent.product.kinematics import frame_from_geometry
    from cad_agent.sandbox.assembly_geom import ANCHOR_TYPES, TYPE_CN, anchor_geometry, geom_type

    values = job["values"]
    frames, ok = {}, True
    for pid, items in job["connectors"].items():
        for c in items:
            key = f"{pid}.{c['name']}"
            hits = _select(solids[pid], c["kind"], c["where"], values)
            info: dict[str, Any] = {"selected": len(hits)}
            if len(hits) != 1:
                info["error"] = COUNT_MSG.format(part=pid, name=c["name"], n=len(hits))
            else:
                t = geom_type(hits[0], c["kind"])
                info["type"] = t
                if t not in ANCHOR_TYPES[c["kind"]]:
                    info["error"] = TYPE_MSG.format(part=pid, name=c["name"], type=TYPE_CN.get(t, t))
                else:
                    _, center, direction = anchor_geometry(hits[0], c["kind"])
                    offset = c.get("offset", 0)
                    off = float(offset) if isinstance(offset, (int, float)) else eval_expr(offset, values)
                    f = frame_from_geometry(t, center, direction, off, bool(c.get("flip")))
                    frames[key] = f
                    info.update(center=[_r(v) for v in f.origin], direction=[_r(v) for v in f.z])
            ok = ok and "error" not in info
            out["connectors"][key] = info
    return frames if ok else None


def _measure(job: dict, solids: dict, shapes: dict, rest: dict, out: dict) -> None:
    """装配检查里要量几何的几类：重叠、最短距离、同轴、贴平（同轴和贴平量的是检查自己选中的几何）。"""
    from cad_agent.checks.engine import _select
    from cad_agent.product.kinematics import apply_point, apply_vector
    from cad_agent.sandbox.assembly_geom import (anchor_geometry, geom_type, line_distance_angle, min_distance,
                                                 overlap_volume, plane_distance_angle)
    from cad_agent.sandbox.runner import summarize_exception

    values = job["values"]
    for chk in job["checks"]:
        t = chk.get("type")
        if t not in GEOM_TYPES:
            continue
        try:
            if t == "interference":
                out["measures"][chk["id"]] = {"volume": _r(overlap_volume(shapes[chk["a"]], shapes[chk["b"]]))}
            elif t == "clearance":
                out["measures"][chk["id"]] = {"distance": _r(min_distance(shapes[chk["a"]], shapes[chk["b"]]))}
            else:
                want = "CYLINDER" if t == "coaxial" else "PLANE"
                geo, m = [], {}
                for side in ("a", "b"):
                    tgt = chk[side]
                    hits = [h for h in _select(solids[tgt["part"]], tgt.get("kind", "faces"), tgt["where"], values)
                            if geom_type(h, tgt.get("kind", "faces")) == want]
                    m[f"selected_{side}"] = len(hits)
                    if len(hits) == 1:
                        _, c, d = anchor_geometry(hits[0], "faces")
                        pose = rest[tgt["part"]]
                        geo.append((apply_point(pose, c), apply_vector(pose, d)))
                if len(geo) == 2:
                    fn = line_distance_angle if t == "coaxial" else plane_distance_angle
                    dist, ang = fn(geo[0][0], geo[0][1], geo[1][0], geo[1][1])
                    m.update(distance=_r(dist), angle=_r(ang))
                out["measures"][chk["id"]] = m
        except Exception as e:  # noqa: BLE001 - 量不出来就把原因交给检查，让它不通过
            out["measures"][chk["id"]] = {"error": f"{type(e).__name__}：{summarize_exception(e)}"}


def _relative(a: list[float], b: list[float]) -> list[float]:
    from cad_agent.product.kinematics import inverse, matmul

    return matmul(inverse(a), b)


def _sweep(job: dict, asm: Any, frames: dict, rest: dict, raw_shapes: dict, out: dict) -> None:
    from cad_agent.checks.expr import eval_expr
    from cad_agent.product.kinematics import joint_value_samples, poses_at
    from cad_agent.sandbox.assembly_geom import bbox, overlap_volume, placed
    from cad_agent.sandbox.runner import summarize_exception

    values = job["values"]
    fail = os.environ.get(FAIL_SAMPLE_ENV, "")
    ids = list(raw_shapes)
    for j in asm.joints:
        lo, hi = (float(v) if isinstance(v, (int, float)) else eval_expr(v, values) for v in (j.lo, j.hi))
        rows = []
        for i, v in enumerate(joint_value_samples(lo, hi, job["samples"])):
            row: dict[str, Any] = {"value": _r(v), "poses": {}, "hits": [], "error": None}
            try:
                if fail == f"{j.id}:{i}":
                    raise RuntimeError("测试用：故意在这个位置出错")
                poses = poses_at(asm, frames, rest, {j.id: v}, values)
                row["poses"] = {pid: _mat(m) for pid, m in poses.items()}
                shapes = {pid: placed(raw_shapes[pid], poses[pid]) for pid in ids}
                boxes = {pid: bbox(s) for pid, s in shapes.items()}
                for x in range(len(ids)):
                    for y in range(x + 1, len(ids)):
                        a, b = ids[x], ids[y]
                        if all(abs(p - q) < 1e-9 for p, q in zip(_relative(poses[a], poses[b]), _relative(rest[a], rest[b]))):
                            continue   # 这两个零件之间的相对位置没变，装好时已经查过
                        vol = overlap_volume(shapes[a], shapes[b], boxes[a], boxes[b])
                        if vol > 1e-6:
                            row["hits"].append({"a": a, "b": b, "volume": _r(vol)})
            except Exception as e:  # noqa: BLE001 - 这个位置没量成，照实记下（检查会因此不通过）
                row["error"] = f"{type(e).__name__}：{summarize_exception(e)}"
            rows.append(row)
        out["samples"][j.id] = rows


def _export(job: dict, runs: dict, solids: dict, rest: dict, out: dict) -> None:
    import simplecadapi as scad
    from simplecadapi import exporter
    from simplecadapi.runtime import run_notebook

    from cad_agent.brief import Param
    from cad_agent.product.render import assembly_notebook_text
    from cad_agent.sandbox.assembly_geom import placed_solid

    workdir = Path(job["workdir"])
    for pid, run in runs.items():
        d = workdir / "parts" / pid
        cap = scad.capture(run.definition, d / "model.scadpkg")
        exporter.export_product_package_to_step(cap.package, d / "model.step")
        exporter.export_product_package_to_stl(cap.package, d / "model.stl")
        out["files"] += [f"parts/{pid}/model.step", f"parts/{pid}/model.stl"]
    params = [Param(**p) for p in job["params"]]
    text = assembly_notebook_text(params, [(p["id"], p["param_names"]) for p in job["parts"]], rest)
    (workdir / "assembly.py").write_text(text, encoding="utf-8")
    run = run_notebook(workdir / "assembly.py", cache=False, timeout=job["timeout_s"])
    cap = scad.capture(run.definition, workdir / "product.scadpkg")
    exporter.export_product_package_to_step(cap.package, workdir / "product.step")
    scad.render_screenshot_rpath([placed_solid(solids[pid], rest[pid]) for pid in solids], str(workdir / "view.png"), view="iso")
    out["files"] += ["assembly.py", "product.step", "view.png"]


def work(job: dict, out: dict) -> None:
    from cad_agent.product.kinematics import rest_placements
    from cad_agent.product.spec import parse_assembly, parse_connectors
    from cad_agent.sandbox.assembly_geom import bbox, overlap_volume, placed

    out.update(connectors={}, rest={}, overlaps=[], measures={}, samples={}, files=[])
    started = time.monotonic()
    got = _run_parts(job, out)
    if got is None:
        return
    solids, runs = got
    frames = _anchor(job, solids, out)
    if frames is None:
        return
    names = set(job["values"])
    cons = {pid: parse_connectors(pid, items, names) for pid, items in job["connectors"].items()}
    asm = parse_assembly(job["assembly"], [p["id"] for p in job["parts"]], cons, names)
    rest = rest_placements(asm, frames, job["values"])
    out["rest"] = {pid: _mat(m) for pid, m in rest.items()}
    raw = {pid: s.wrapped for pid, s in solids.items()}
    shapes = {pid: placed(raw[pid], rest[pid]) for pid in raw}
    boxes = {pid: bbox(s) for pid, s in shapes.items()}
    ids = list(shapes)
    for x in range(len(ids)):
        for y in range(x + 1, len(ids)):
            vol = overlap_volume(shapes[ids[x]], shapes[ids[y]], boxes[ids[x]], boxes[ids[y]])
            if vol > 1e-6:
                out["overlaps"].append({"a": ids[x], "b": ids[y], "volume": _r(vol)})
    _measure(job, solids, shapes, rest, out)
    _sweep(job, asm, frames, rest, raw, out)
    if job.get("export"):
        _export(job, runs, solids, rest, out)
    out["duration_child_s"] = time.monotonic() - started
