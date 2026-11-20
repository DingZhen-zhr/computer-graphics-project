"""一轮结束时把工作区存进会话目录（从 loop.py 拆出来）。多零件时各零件的 notebook 也存一份。"""

from __future__ import annotations

from typing import Callable

from cad_agent.notebook import NotebookError, RenderedNotebook, render_notebook
from cad_agent.product.render import render_part_notebook
from cad_agent.product.workspace import product_state
from cad_agent.session import Session
from cad_agent.tools import Workspace


def _text(make: Callable[[], RenderedNotebook]) -> str:
    try:
        return make().text
    except NotebookError as e:
        return f"# 当前的特征还不能拼成 notebook：{e}\n"


def save_state(session: Session, ws: Workspace) -> None:
    text = _text(lambda: render_notebook(ws.brief.params, ws.features.items))
    product = product_state(ws)
    notebooks = {pid: _text(lambda pid=pid: render_part_notebook(ws, pid)) for pid in ws.parts} if product else None
    session.save_state(ws.brief, ws.features.to_list(), ws.checks_raw, text,
                       plan=ws.plan.to_list() if ws.plan is not None else None, product=product, part_notebooks=notebooks)
