"""第二版的分阶段工具在多零件时作用于当前零件：它能用哪些参数、notebook 怎么拼。

单零件（ws.active 为 None）时和以前完全一样：全部参数，render_notebook 原样调用。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..brief import Param
from ..notebook import RenderedNotebook, _analyse, render_notebook

if TYPE_CHECKING:
    from ..tools import Workspace


def scoped_params(ws: "Workspace") -> list[Param]:
    """当前零件能用的参数：产品参数 + 它自己的参数。"""
    if ws.active is None:
        return ws.brief.params
    return [p for p in ws.brief.params if p.part is None or p.part == ws.active]


def gate_params(ws: "Workspace") -> list[Param]:
    """终检要管住的参数：单零件是全部；多零件时是这个零件自己的参数，加上它的特征里用到的产品参数。"""
    if ws.active is None:
        return ws.brief.params
    used: set[str] = set()
    for f in ws.features.items:
        try:
            used |= _analyse(f).reads
        except Exception:  # noqa: BLE001 - 语法错误的特征在 build 时会报，这里只是少算它用到的名字
            continue
    return [p for p in scoped_params(ws) if p.part == ws.active or p.name in used]


def render_scoped(ws: "Workspace", params: list[Param], features: list, probe: str | None = None) -> RenderedNotebook:
    """拼当前零件的 notebook。多零件时带上零件编号和材料。"""
    if ws.active is None:
        return render_notebook(params, features, probe)
    from .materials import MATERIALS

    info = next(p for p in ws.brief.parts if p.id == ws.active)
    return render_notebook(params, features, probe, notebook_id=ws.active, material=MATERIALS[info.material], color=info.color)
