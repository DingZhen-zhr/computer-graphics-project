"""子进程入口：运行 notebook、跑检查、导出，把结果写成 result.json。

由 execute.py 以 `python -I -X utf8 -m cad_agent.sandbox.runner <job.json>` 启动，工作目录是临时目录。
做法依据 docs/sca-api-notes.md 第 8、9 节。
"""

from __future__ import annotations

import json
import linecache
import os
import re
import sys
import traceback
from pathlib import Path
from typing import Any

FEATURE_RE = re.compile(r"# ---- feature: ([a-z][a-z0-9-]*) \(")
SECTION_RE = re.compile(r"^(Operation|Signature|Documentation|What happened|Measurements|Evidence|Possible causes|How to fix|Technical details|Inventory):\s*(.*)$")
MAX_MESSAGE = 800


# ---------------------------------------------------------------- 报错翻译


def _sections(text: str) -> dict[str, list[str]]:
    """把 SimpleCADError 的多行信息按小节拆开：小节名 → 行列表。"""
    out: dict[str, list[str]] = {}
    current = None
    for line in text.splitlines():
        m = SECTION_RE.match(line)
        if m:
            current = m.group(1)
            out[current] = [m.group(2)] if m.group(2) else []
        elif current is not None and line.strip():
            out[current].append(line.strip())
    return out


def _bullets(lines: list[str], limit: int) -> str:
    return "；".join(ln.removeprefix("- ").strip() for ln in lines[:limit])


def summarize_exception(e: BaseException) -> str:
    """把异常整理成给模型看的精简信息（不含诊断图路径、不含超长的调用参数）。"""
    text = str(e).strip()
    if "What happened:" in text:
        s = _sections(text)
        parts = []
        if s.get("Operation"):
            parts.append(f"操作：{s['Operation'][0]}")
        parts.append("原因：" + " ".join(s.get("What happened", [])))
        if s.get("Measurements"):
            parts.append("数值：" + _bullets(s["Measurements"], 6))
        if s.get("How to fix"):
            parts.append("建议：" + _bullets(s["How to fix"], 2))
        if s.get("Inventory"):
            parts.append("现有几何：" + _bullets(s["Inventory"], 6))
        return "\n".join(parts)[:MAX_MESSAGE]
    if "incompatible function arguments" in text:
        head = text.split("Invoked with:")[0].strip()
        return (head[: MAX_MESSAGE - 20] + "\n（传入的参数已省略）")[:MAX_MESSAGE]
    return text[-MAX_MESSAGE:]


def failed_slug(e: BaseException, nb_path: Path, cell_lines: dict[str, list[int]]) -> str | None:
    """找出出错的特征 slug；出在参数 cell 或产品 cell 里时返回 None。

    marimo 把每个 cell 编译成临时文件 __marimo__cell_*.py，行号是 cell 内部的行号，
    源码可以用 linecache 取到，第一行就是特征注释。traceback 里直接指向 notebook 文件的帧
    （此时行号是文件行号）用 cell_lines 对照，作为兜底。
    """
    slug = None
    nb_norm = os.path.normcase(os.path.abspath(nb_path))
    for f in traceback.extract_tb(e.__traceback__):
        if "__marimo__cell_" in f.filename:
            m = FEATURE_RE.search("".join(linecache.getlines(f.filename)[:3]))
            slug = m.group(1) if m else None
        elif os.path.normcase(os.path.abspath(f.filename)) == nb_norm:
            for name, (start, end) in cell_lines.items():
                if start <= f.lineno <= end:
                    slug = name
    return slug


# ---------------------------------------------------------------- 主流程


def _error(cell: str | None, e: BaseException) -> dict:
    return {"cell": cell, "type": type(e).__name__, "message": summarize_exception(e)}


def _work(job: dict, out: dict[str, Any]) -> None:
    import simplecadapi as scad
    from simplecadapi import exporter
    from simplecadapi.runtime import run_notebook

    workdir = Path(job["workdir"])
    nb_path = Path(job["notebook"])
    timeout_s = job["timeout_s"]
    try:
        run = run_notebook(nb_path, cache=False, timeout=timeout_s)
    except TimeoutError:
        out["timed_out"] = True
        out["error"] = {"cell": None, "type": "TimeoutError", "message": f"运行超过 {timeout_s:g} 秒被终止"}
        return
    except Exception as e:  # noqa: BLE001 - 用户特征代码里的任何异常都要翻译后交回模型
        out["error"] = _error(failed_slug(e, nb_path, job["cell_lines"]), e)
        return

    try:
        from cad_agent.checks.engine import body_facts, query, run_checks
        from cad_agent.checks.spec import parse_checks

        solid = run.product.body
        values = {n: float(run.values[n]) for n in job["param_names"] if n in run.values}
        out["values"] = values
        out["facts"] = body_facts(solid)
        if job["mode"] == "inspect":
            spec = job.get("query_spec") or {}
            out["query"] = query(solid, spec.get("kind", "faces"), spec.get("where", []), values)
        else:
            checks = parse_checks(job["checks_raw"], set(job["param_names"]))
            out["checks"] = [r.to_dict() for r in run_checks(solid, checks, values)]
    except Exception as e:  # noqa: BLE001 - 检查或查询的写法问题，翻译后交回模型
        out["error"] = _error(None, e)
        return

    try:
        if job.get("export_step"):
            cap = scad.capture(run.definition, workdir / "model.scadpkg")
            exporter.export_product_package_to_step(cap.package, workdir / "model.step")
            out["step"] = True
        if job.get("render_png"):
            scad.render_screenshot_rpath(solid, str(workdir / "view.png"), view="iso")
            out["png"] = True
    except Exception as e:  # noqa: BLE001 - 导出失败也要如实报告
        out["error"] = {"cell": None, "type": "ExportError", "message": f"导出失败（{type(e).__name__}）：{summarize_exception(e)}"}


def _json_default(o: Any) -> Any:
    try:
        return float(o)
    except (TypeError, ValueError):
        return str(o)


def main(argv: list[str]) -> int:
    job = json.loads(Path(argv[1]).read_text(encoding="utf-8"))
    out: dict[str, Any] = {
        "error": None, "timed_out": False, "values": {}, "checks": [], "facts": {}, "query": None, "step": False, "png": False,
    }
    try:
        _work(job, out)
    except BaseException as e:  # noqa: BLE001 - 兜底：无论发生什么都要写出结果文件，父进程才能报告原因
        out["error"] = _error(None, e)
    (Path(job["workdir"]) / "result.json").write_text(json.dumps(out, ensure_ascii=False, default=_json_default), encoding="utf-8")
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(0)  # 超时后可能还有跑不完的线程，直接退出，不等它们


if __name__ == "__main__":
    main(sys.argv)
