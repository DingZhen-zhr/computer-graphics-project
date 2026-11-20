"""材料表：键、中文名、默认颜色、界面渲染用的质感（照抄 3.0 计划 2 提示词文档第 2 节）。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Material:
    key: str
    name: str
    color: str
    finish: str


MATERIALS: dict[str, Material] = {m.key: m for m in (
    Material("abs", "ABS 塑料", "#3A3F47", "matte"),
    Material("aluminum", "铝", "#C9CDD3", "metal"),
    Material("anodized", "阳极氧化铝", "#4767E8", "metal"),
    Material("steel", "不锈钢", "#B8BDC4", "polished"),
    Material("brass", "黄铜", "#C9A24A", "polished"),
    Material("rubber", "橡胶", "#1E1F22", "matte"),
    Material("wood", "木头", "#B98A5A", "matte"),
)}


def rgb01(color: str) -> tuple[float, float, float]:
    """#RRGGBB → SCA 材料要的 0～1 三个浮点数（笔记第 25 节），保留三位小数。"""
    h = color.lstrip("#")
    return tuple(round(int(h[i:i + 2], 16) / 255, 3) for i in (0, 2, 4))  # type: ignore[return-value]
