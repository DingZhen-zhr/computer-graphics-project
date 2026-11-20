"""多零件的流程：零件做完、换下一个零件、装配、产品终检（设计文档第 5 节）。"""

from __future__ import annotations

from .gate import run_product_gate

__all__ = ["run_product_gate"]
