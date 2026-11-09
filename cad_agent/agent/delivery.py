"""交付与失败的文字，以及交付时的导出（从 loop.py 拆出来，行为不变）。"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from cad_agent.checks.spec import CheckResult
from cad_agent.notebook import render_notebook
from cad_agent.session import Session
from cad_agent.tools import ToolBox, ToolOutcome


def _fmt(v: float | None) -> str:
    return "-" if v is None else f"{v:.4f}".rstrip("0").rstrip(".")


def failure_text(toolbox: ToolBox, outcome: ToolOutcome) -> str:
    run = outcome.build
    lines = [f"建模已经连续没通过 {toolbox.build_failures} 次，我先停下来，免得越改越乱。最后一次的问题："]
    if run.error:
        where = f"特征 {run.error['cell']}" if run.error.get("cell") else "不在某个具体特征里"
        lines.append(f"- {where}（{run.error['type']}）：{run.error['message']}")
    failed = [r for r in run.checks if not r.passed]
    lines += [f"- 检查 {r.id} 没通过：{r.detail}" for r in failed[:3]]
    missing = json.loads(outcome.content)["missing_coverage"]
    if missing:
        lines.append(f"- 这些你给的参数还没有对应的检查：{'、'.join(missing)}")
    lines.append("你可以告诉我怎么调整（比如换个做法、放宽某个要求），或者说「继续」让我再试。")
    return "\n".join(lines)


def delivery_text(version: Path, checks: list[CheckResult], changes: list[str], repairs: int) -> str:
    head = f"已交付 {version.name}" + (f"（建模中自动修复了 {repairs} 次）" if repairs else "") + "。"
    rows = ["| 检查 | 结果 | 实测 | 期望 |", "|---|---|---|---|"]
    rows += [f"| {r.id} | {'通过' if r.passed else '没通过'} | {_fmt(r.measured)} | {_fmt(r.expected)} |" for r in checks]
    lines = [head, f"检查结果（共 {len(checks)} 项，全部通过）：", *rows]
    if changes:
        lines.append("本版变化：" + "；".join(changes))
    lines += [f"截图：{version / 'view.png'}", f"STEP：{version / 'model.step'}"]
    return "\n".join(lines)


def export_version(toolbox: ToolBox, session: Session, changes: list[str]) -> tuple[Path, list[CheckResult]] | str:
    """再跑一次导出 STEP 和截图，存成新版本。成功返回 (版本目录, 检查结果)，失败返回给用户看的文字。"""
    ws = toolbox.ws
    rendered = render_notebook(ws.brief.params, ws.features.items)
    with tempfile.TemporaryDirectory(prefix="cad-agent-out-") as tmp:
        out = Path(tmp)
        result = toolbox.run_job(
            rendered, ws.checks_raw, set(ws.brief.param_values()), mode="build",
            export_step=out / "model.step", render_png=out / "view.png",
            timeout_s=toolbox.timeout_s, secret_names=toolbox.secret_names,
        )
        if not result.ok or result.step_path is None or result.png_path is None:
            why = result.error["message"] if result.error else "检查没有全部通过或没有生成导出文件"
            return f"检查已经通过，但交付时导出出了问题：{why}"
        version = session.new_version(
            notebook_text=rendered.text, brief=ws.brief, check_results=result.checks, changes=changes,
            step_src=result.step_path, png_src=result.png_path,
        )
    return version, result.checks
