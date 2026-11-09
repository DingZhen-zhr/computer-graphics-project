"""摸底脚本的公共部分：拼 notebook、运行、读取几何事实。

只给 scripts/ 下的探测脚本用，不属于 cad_agent 包。
"""

from __future__ import annotations

import tempfile
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

HEADER = '''# /// script
# requires-python = ">=3.10"
# dependencies = ["simplecadapi"]
#
# [tool.simplecadapi]
# id = "model"
# ///
import marimo

app = marimo.App()

with app.setup:
    import simplecadapi as scad
    from simplecadapi import ql
    import math

'''


def say(tag: str, msg: object) -> None:
    """统一的输出格式：[项目] 结果。"""
    print(f"[{tag}] {msg}", flush=True)


@dataclass
class Cell:
    """一个特征 cell：输入名、代码、输出名都显式给出。"""

    slug: str
    role: str
    inputs: list[str]
    code: str
    outputs: list[str]
    extra: dict[str, Any] = field(default_factory=dict)


def _ret(names: list[str]) -> str:
    if len(names) == 1:
        return f"return ({names[0]},)"
    return "return " + ", ".join(names)


def build_nb(params: list[tuple[str, float, str | None]], cells: list[Cell], product: str | None = None) -> str:
    """拼出 notebook 文本。

    params: (名字, 数值, 单位)；单位为 None 时写成普通常量。
    product: 最后一个 cell 里产品的 body 变量名；不给就取最后一个特征的第一个输出。
    """
    out = [HEADER]
    lines = ["# ---- params ----"]
    names: list[str] = []
    for name, value, unit in params:
        names.append(name)
        if unit is None:
            lines.append(f"{name} = {value!r}")
        else:
            lines.append(f'{name} = scad.var("{name}", {value!r}, unit="{unit}")')
    body = "\n".join("    " + ln for ln in lines)
    out.append(f"\n@app.cell\ndef _():\n{body}\n    {_ret(sorted(names))}\n\n")
    for c in cells:
        code = "\n".join(("    " + ln) if ln.strip() else "" for ln in c.code.strip("\n").splitlines())
        sig = ", ".join(sorted(c.inputs))
        out.append(
            f"\n@app.cell\ndef _({sig}):\n"
            f"    # ---- feature: {c.slug} ({c.role}) ----\n{code}\n    {_ret(c.outputs)}\n\n"
        )
    last = product or cells[-1].outputs[0]
    out.append(
        f'\n@app.cell\ndef _({last}):\n    model = scad.Part(part_id="model", body={last})\n    return (model,)\n'
    )
    return "".join(out)


def new_tmp(prefix: str = "cad-probe-") -> Path:
    """英文临时目录（Windows 用户目录是英文名，所以这里天然是英文路径）。"""
    return Path(tempfile.mkdtemp(prefix=prefix))


def run_nb(text: str, workdir: Path | None = None, name: str = "model.py", timeout: float = 60):
    """运行 notebook 文本，返回 NotebookRun。"""
    from simplecadapi.runtime import run_notebook

    d = workdir or new_tmp()
    p = d / name
    p.write_text(text, encoding="utf-8")
    return run_notebook(p, cache=False, timeout=timeout)


def facts(solid) -> dict[str, Any]:
    """用 inspect_shape_rbrepinspection 取整体事实（包围盒、体积、有效性、个数）。"""
    from simplecadapi.inspect import brep

    i = brep.inspect_shape_rbrepinspection(solid.wrapped)
    return {
        "valid": i.valid,
        "bbox": [round(v, 6) for v in i.bounding_box],
        "volume": round(i.volume, 4),
        "solids": i.counts.get("solid"),
        "faces": i.counts.get("unique_faces"),
        "edges": i.counts.get("unique_edges"),
        "surface_types": dict(i.surface_type_counts),
    }


def try_run(tag: str, fn) -> Any:
    """跑一小段探测，出错就把异常类型和信息原文打印出来，不让脚本中断。"""
    try:
        return fn()
    except Exception as e:  # noqa: BLE001 - 探测脚本需要记录任何异常
        msg = str(e).replace("\n", " | ")
        say(tag, f"异常 {type(e).__name__}: {msg[:600]}")
        return None


def tb_frames(exc: BaseException) -> list[tuple[str, int, str]]:
    """异常的 traceback 帧：(文件名, 行号, 函数名)。"""
    return [(f.filename, f.lineno, f.name) for f in traceback.extract_tb(exc.__traceback__)]
