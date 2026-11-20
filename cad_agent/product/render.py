"""零件 notebook 和装配 notebook（笔记第 23、25 节）。

零件 notebook 和单零件的一样，只是文件头和零件的编号换成零件编号、产品带上材料。
装配 notebook 用 scad.use 引用 parts/<编号>/model.py，把参数 cell 里的全部参数都传过去（只传一部分会报错），
再按每个零件的 4×4 矩阵摆好。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..notebook import FOOTER, HEADER, RenderedNotebook, _literal, render_notebook
from .materials import MATERIALS
from .workspace import part_param_names

if TYPE_CHECKING:
    from ..brief import Param
    from ..tools import Workspace

PRODUCT_ID = "product"


def part_notebook_path(part_id: str) -> str:
    """装配 notebook 引用零件 notebook 的相对路径；会话目录、版本目录、沙盒临时目录都按这个放。"""
    return f"parts/{part_id}/model.py"


def _features(ws: "Workspace", part_id: str) -> list:
    if part_id == ws.active:
        return ws.features.items
    return ws.parts[part_id].features.items


def render_part_notebook(ws: "Workspace", part_id: str, probe: str | None = None) -> RenderedNotebook:
    info = next(p for p in ws.brief.parts if p.id == part_id)
    names = set(part_param_names(ws, part_id))
    params = [p for p in ws.brief.params if p.name in names]
    return render_notebook(params, _features(ws, part_id), probe, notebook_id=part_id,
                           material=MATERIALS[info.material], color=info.color)


def _fmt(v: float) -> str:
    return f"{round(float(v), 9):g}"


def _placement(m: list[float]) -> str:
    """16 个数（按行）→ make_placement_rplacement 的原点、x 轴、y 轴（矩阵的第 4、1、2 列，笔记第 25 节）。"""
    origin = ", ".join(_fmt(m[i]) for i in (3, 7, 11))
    x_axis = ", ".join(_fmt(m[i]) for i in (0, 4, 8))
    y_axis = ", ".join(_fmt(m[i]) for i in (1, 5, 9))
    return f"scad.make_placement_rplacement(({origin}), x_axis=({x_axis}), y_axis=({y_axis}))"


def render_assembly_notebook(ws: "Workspace", placements: dict[str, list[float]]) -> str:
    parts = [(p.id, part_param_names(ws, p.id)) for p in ws.brief.parts]
    return assembly_notebook_text(ws.brief.params, parts, placements)


def assembly_notebook_text(params: list["Param"], parts: list[tuple[str, list[str]]], placements: dict[str, list[float]]) -> str:
    """装配 notebook 的文本。parts 是 (零件编号, 它的参数名)；沙盒子进程里没有工作区，直接用这个。"""
    lines = HEADER.replace('id = "model"', f'id = "{PRODUCT_ID}"').splitlines()

    def add_cell(sig: list[str], body: list[str]) -> None:
        lines.extend(["", "", "@app.cell", f"def _({', '.join(sig)}):"])
        lines.extend("    " + ln for ln in body)

    names = [p.name for p in params]
    if params:
        body = ["# ---- params ----"]
        for p in params:
            if p.unit == "1":
                body.append(f"{p.name} = {_literal(p.value)}")
            else:
                body.append(f'{p.name} = scad.var("{p.name}", {_literal(p.value)}, unit="{p.unit}")')
        body.append(f"return ({names[0]},)" if len(names) == 1 else "return " + ", ".join(names))
        add_cell([], body)
    body = ["# ---- assembly ----", f'_a = scad.make_assembly_rassembly("{PRODUCT_ID}")']
    for pid, own in parts:
        overrides = "".join(f", {n}={n}" for n in own)
        body.append(f'_{pid} = scad.use("{part_notebook_path(pid)}"{overrides})')
        body.append(f'_a = scad.add_component_rassembly(_a, _{pid}, "{pid}", {_placement(placements[pid])})')
    body += ["product = _a", "return (product,)"]
    add_cell(sorted(names), body)
    return "\n".join(lines) + "\n" + FOOTER
