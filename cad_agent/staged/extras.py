"""probe（试一小段代码）和 read_reference（读官方建模文档）两个工具（设计文档第 3.4 节）。

两个都不改动模型：不计失败、不改 unbuilt_edits、不改上次 build 的结果。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from cad_agent.notebook import NotebookError, render_notebook
from cad_agent.references import RefError, read_reference
from cad_agent.sandbox.guard import check_code
from cad_agent.staged import messages as msg
from cad_agent.staged.select import features_upto
from cad_agent.tool_common import ToolOutcome, _err, _error_for_model, _json

if TYPE_CHECKING:
    from cad_agent.tools import ToolBox

PROBE_LIMIT = 10  # 每个阶段最多用这么多次；阶段通过时清零


def probe_tool(box: "ToolBox", args: dict) -> ToolOutcome:
    ws = box.ws
    code = args["code"]
    if not isinstance(code, str):
        return _err("code 必须是文字")
    if ws.probes_used >= PROBE_LIMIT:
        return _err(msg.PROBE_LIMIT_REACHED)
    problems = check_code(code)
    if problems:
        return _err("probe 代码没有通过检查：" + "；".join(problems))
    cur = ws.plan.current()
    stage_id = cur.id if cur is not None else ws.plan.ids()[-1]
    try:
        rendered = render_notebook(ws.brief.params, features_upto(ws, stage_id), probe=code)
    except NotebookError as e:
        return _err(str(e))
    run = box.run_job(rendered, [], set(ws.brief.param_values()), mode="probe",
                      timeout_s=box.timeout_s, secret_names=box.secret_names)
    ws.probes_used += 1
    return ToolOutcome(_json({
        "output": run.probe_output or "",
        "error": _error_for_model(run.error) if run.error else None,
        "probes_left": max(0, PROBE_LIMIT - ws.probes_used),
    }))


def read_reference_tool(box: "ToolBox", args: dict) -> ToolOutcome:
    name, section = args["name"], args.get("section")
    if not isinstance(name, str) or not (section is None or isinstance(section, str)):
        return _err("name 和 section 都必须是文字")
    try:
        return ToolOutcome(_json(read_reference(name, section)))
    except RefError as e:
        return _err(str(e))
