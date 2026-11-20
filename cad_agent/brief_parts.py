"""需求单里的多零件部分：零件列表、会动的地方，以及它们的校验和显示。"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from .product.materials import MATERIALS

PART_ID_RE = re.compile(r"^[a-z][a-z0-9_]*$")
COLOR_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")


@dataclass
class PartInfo:
    id: str
    name: str
    material: str
    color: str | None = None
    features: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"id": self.id, "name": self.name, "material": self.material, "color": self.color,
                "features": list(self.features)}

    @classmethod
    def from_dict(cls, d: dict) -> "PartInfo":
        return cls(d["id"], d["name"], d["material"], d.get("color"), list(d.get("features", [])))


def parse_parts(raw: Any, error: type[Exception]) -> list[PartInfo]:
    """校验 parts 并转成 PartInfo；出错抛 error（中文信息）。"""
    if not isinstance(raw, list):
        raise error("parts 必须是数组")
    if len(raw) == 1:
        raise error("只有一个零件时不写 parts，用 features 写组成部分就行")
    out: list[PartInfo] = []
    for item in raw:
        if not isinstance(item, dict):
            raise error("parts 里的每一项都必须是对象，含 id、name、material、features")
        pid, name, mat = item.get("id"), item.get("name"), item.get("material")
        if not isinstance(pid, str) or not PART_ID_RE.match(pid):
            raise error(f"零件编号 {pid!r} 不合法：要用小写英文开头，只含小写字母、数字、下划线，如 lid")
        if any(p.id == pid for p in out):
            raise error(f"零件编号 {pid} 重复了")
        if not isinstance(name, str) or not name.strip():
            raise error(f"零件 {pid} 要写名字")
        if mat not in MATERIALS:
            raise error(f"零件 {pid} 的材料 {mat!r} 不认识，只能是：{'、'.join(MATERIALS)}")
        color = item.get("color")
        if color is not None and (not isinstance(color, str) or not COLOR_RE.match(color)):
            raise error(f"零件 {pid} 的颜色要写成 # 加 6 位十六进制，如 #4767E8，收到 {color!r}")
        feats = item.get("features", [])
        if not isinstance(feats, list) or not all(isinstance(x, str) and x.strip() for x in feats):
            raise error(f"零件 {pid} 的 features 必须是非空文字组成的数组")
        out.append(PartInfo(pid, name.strip(), mat, color, [x.strip() for x in feats]))
    return out


def render_parts(parts: list[PartInfo], motions: list[str]) -> list[str]:
    """需求单文字里"零件"和"会动的地方"两段。"""
    out = ["零件："]
    for p in parts:
        out.append(f"  - {p.id} {p.name}（{MATERIALS[p.material].name}）：{'；'.join(p.features) or '（还没写）'}")
    out.append("会动的地方：")
    out.extend(f"  - {m}" for m in motions) if motions else out.append("  （没有）")
    return out
