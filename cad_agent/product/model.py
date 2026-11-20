"""多零件产品声明的数据结构：连接点、配合、关节、联动、装配。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


class ProductError(ValueError):
    """装配声明写得不对；信息是中文，直接返回给模型。"""


@dataclass(frozen=True)
class Connector:
    part: str
    name: str
    kind: Literal["faces", "edges"]
    where: list[list]
    offset: str | float = 0
    flip: bool = False

    def to_dict(self) -> dict:
        return {"name": self.name, "kind": self.kind, "where": self.where, "offset": self.offset, "flip": self.flip}


@dataclass(frozen=True)
class Mate:
    id: str
    fixed: str      # "零件.连接点"
    moving: str
    align: Literal["same", "opposite"]
    gap: str | float = 0
    angle: str | float = 0


@dataclass(frozen=True)
class Joint:
    id: str
    mate: str
    type: Literal["revolute", "prismatic"]
    lo: str | float
    hi: str | float
    direction: tuple[float, float, float] | None
    label: str


@dataclass(frozen=True)
class Coupling:
    driver: str
    driven: str
    ratio: str | float
    kind: Literal["gear", "belt"]


@dataclass
class Assembly:
    ground: str
    mates: list[Mate]
    joints: list[Joint]
    couplings: list[Coupling]
    notes: list[str] = field(default_factory=list)   # 给模型的说明，比如"范围写反了，已经按从小到大处理"

    def mate(self, mate_id: str) -> Mate:
        return next(m for m in self.mates if m.id == mate_id)

    def joint(self, joint_id: str) -> Joint:
        return next(j for j in self.joints if j.id == joint_id)

    def to_dict(self) -> dict:
        return {
            "ground": self.ground,
            "mates": [{"id": m.id, "fixed": m.fixed, "moving": m.moving, "align": m.align, "gap": m.gap, "angle": m.angle}
                      for m in self.mates],
            "joints": [{"id": j.id, "mate": j.mate, "type": j.type, "range": [j.lo, j.hi],
                        **({"direction": list(j.direction)} if j.direction else {}), "label": j.label} for j in self.joints],
            "couplings": [{"driver": c.driver, "driven": c.driven, "ratio": c.ratio, "kind": c.kind} for c in self.couplings],
        }


def part_of(ref: str) -> str:
    return ref.split(".", 1)[0]
