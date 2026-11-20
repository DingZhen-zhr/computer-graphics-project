"""多零件产品的声明：连接点、配合、关节、联动，以及它们的校验。

只校验格式和结构（零件、连接点存不存在，配合是不是一棵树），不碰几何；几何在沙盒里量（Task 7）。
"""

from __future__ import annotations

import math
import re
from typing import Any

from ..checks.expr import CheckSpecError, expr_names
from ..checks.spec import parse_where
from .model import Assembly, Connector, Coupling, Joint, Mate, ProductError, part_of

__all__ = ["Assembly", "Connector", "Coupling", "Joint", "Mate", "ProductError", "contact_pairs", "mate_tree",
           "moving_parts", "parse_assembly", "parse_connectors", "part_of"]

NAME_RE = re.compile(r"^[a-z][a-z0-9_]*$")
TREE_RULE = "除了 ground，每个零件都要被恰好一个配合连到已经装好的零件上，不能连成一圈。"


def _expr(value: Any, what: str, params: set[str]) -> str | float:
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        raise ProductError(f"{what} 要写数或参数表达式，收到 {value!r}")
    try:
        names = expr_names(value)
    except CheckSpecError as e:
        raise ProductError(f"{what}：{e}") from e
    unknown = sorted(names - params)
    if unknown:
        raise ProductError(f"{what} 用到了不存在的参数 {'、'.join(unknown)}")
    if isinstance(value, str):
        return value.strip()
    if not math.isfinite(value):
        raise ProductError(f"{what} 必须是有限的数")
    return float(value)


def _name(value: Any, what: str) -> str:
    if not isinstance(value, str) or not NAME_RE.match(value):
        raise ProductError(f"{what} {value!r} 不合法：要用小写英文开头，只含小写字母、数字、下划线")
    return value


def parse_connectors(part: str, raw: object, param_names: set[str]) -> list[Connector]:
    if not isinstance(raw, list):
        raise ProductError("connectors 必须是数组")
    out: list[Connector] = []
    for item in raw:
        if not isinstance(item, dict):
            raise ProductError("connectors 里的每一项都必须是对象，含 name、kind、where")
        name = _name(item.get("name"), "连接点名字")
        if any(c.name == name for c in out):
            raise ProductError(f"零件 {part} 的连接点 {name} 重复了")
        kind = item.get("kind")
        if kind not in ("faces", "edges"):
            raise ProductError(f"连接点 {name} 的 kind 只能是 faces 或 edges")
        try:
            where = parse_where(item.get("where"), set(param_names))
        except CheckSpecError as e:
            raise ProductError(f"连接点 {name}：{e}") from e
        flip = item.get("flip", False)
        if not isinstance(flip, bool):
            raise ProductError(f"连接点 {name} 的 flip 只能是 true 或 false")
        offset = _expr(item.get("offset", 0), f"连接点 {name} 的 offset", set(param_names))
        out.append(Connector(part, name, kind, where, offset, flip))
    return out


def _parse_mates(raw: Any, part_ids: list[str], connectors: dict[str, list[Connector]], params: set[str]) -> list[Mate]:
    if not isinstance(raw, list) or not raw:
        raise ProductError("mates 必须是非空数组")
    out: list[Mate] = []
    for item in raw:
        if not isinstance(item, dict):
            raise ProductError("mates 里的每一项都必须是对象，含 id、fixed、moving、align")
        mid = _name(item.get("id"), "配合编号")
        if any(m.id == mid for m in out):
            raise ProductError(f"配合编号 {mid} 重复了")
        ends = []
        for key in ("fixed", "moving"):
            ref = item.get(key)
            if not isinstance(ref, str) or ref.count(".") != 1:
                raise ProductError(f"配合 {mid} 的 {key} 要写成 零件编号.连接点名字，收到 {ref!r}")
            pid, cname = ref.split(".")
            if pid not in part_ids:
                raise ProductError(f"配合 {mid} 的 {key} 写的零件 {pid} 不存在")
            if not any(c.name == cname for c in connectors.get(pid, [])):
                have = "、".join(c.name for c in connectors.get(pid, [])) or "（还没有，先用 set_connectors 写）"
                raise ProductError(f"配合 {mid} 的 {key} 写的连接点 {ref} 不存在；零件 {pid} 的连接点：{have}")
            ends.append(ref)
        if part_of(ends[0]) == part_of(ends[1]):
            raise ProductError(f"配合 {mid} 的两边是同一个零件 {part_of(ends[0])}，要连两个不同的零件")
        align = item.get("align")
        if align not in ("same", "opposite"):
            raise ProductError(f"配合 {mid} 的 align 只能是 same 或 opposite")
        gap = _expr(item.get("gap", 0), f"配合 {mid} 的 gap", params)
        angle = _expr(item.get("angle", 0), f"配合 {mid} 的 angle", params)
        out.append(Mate(mid, ends[0], ends[1], align, gap, angle))
    return out


def _parse_joints(raw: Any, mates: list[Mate], params: set[str], notes: list[str]) -> list[Joint]:
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise ProductError("joints 必须是数组")
    out: list[Joint] = []
    for item in raw:
        if not isinstance(item, dict):
            raise ProductError("joints 里的每一项都必须是对象，含 id、mate、type、range、label")
        jid = _name(item.get("id"), "关节编号")
        if any(j.id == jid for j in out):
            raise ProductError(f"关节编号 {jid} 重复了")
        mate = item.get("mate")
        if not any(m.id == mate for m in mates):
            raise ProductError(f"关节 {jid} 写的配合 {mate!r} 不存在")
        if any(j.mate == mate for j in out):
            raise ProductError(f"配合 {mate} 上已经有一个关节了，一个配合最多一个关节")
        jtype = item.get("type")
        if jtype not in ("revolute", "prismatic"):
            raise ProductError(f"关节 {jid} 的 type 只能是 revolute 或 prismatic")
        rng = item.get("range")
        if not isinstance(rng, list) or len(rng) != 2:
            raise ProductError(f"关节 {jid} 的 range 要写两个数，如 [0, 110]")
        lo, hi = (_expr(v, f"关节 {jid} 的 range", params) for v in rng)
        if lo == hi:
            raise ProductError(f"关节 {jid} 的范围两端相等（{lo}），动不了。要么写出能动的范围，要么不要这个关节")
        if isinstance(lo, float) and isinstance(hi, float) and lo > hi:
            lo, hi = hi, lo
            notes.append(f"关节 {jid} 的范围写反了，已经按从小到大处理")
        direction = None
        if jtype == "prismatic":
            d = item.get("direction")
            if not (isinstance(d, list) and len(d) == 3 and all(isinstance(x, (int, float)) and not isinstance(x, bool) for x in d)):
                raise ProductError(f"关节 {jid} 是滑动的，要写 direction（三个数，装好时滑动的方向）")
            n = math.sqrt(sum(float(x) ** 2 for x in d))
            if n < 1e-9 or not math.isfinite(n):
                raise ProductError(f"关节 {jid} 的 direction 不能是零向量")
            direction = tuple(float(x) / n for x in d)
        label = item.get("label")
        if not isinstance(label, str) or not label.strip():
            raise ProductError(f"关节 {jid} 要写 label（给用户看的名字，如 盖子翻开）")
        out.append(Joint(jid, mate, jtype, lo, hi, direction, label.strip()))
    return out


def _parse_couplings(raw: Any, joints: list[Joint], params: set[str]) -> list[Coupling]:
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise ProductError("couplings 必须是数组")
    ids = {j.id for j in joints}
    out: list[Coupling] = []
    for item in raw:
        if not isinstance(item, dict):
            raise ProductError("couplings 里的每一项都必须是对象，含 driver、driven、ratio、kind")
        driver, driven = item.get("driver"), item.get("driven")
        for key, v in (("driver", driver), ("driven", driven)):
            if v not in ids:
                raise ProductError(f"联动的 {key} 写的关节 {v!r} 不存在")
        if driver == driven:
            raise ProductError(f"联动的 driver 和 driven 是同一个关节 {driver}")
        if any(c.driven == driven for c in out):
            raise ProductError(f"关节 {driven} 被两个联动带动，只能有一个")
        kind = item.get("kind")
        if kind not in ("gear", "belt"):
            raise ProductError("联动的 kind 只能是 gear 或 belt")
        ratio = _expr(item.get("ratio"), f"联动 {driver}→{driven} 的 ratio", params)
        out.append(Coupling(driver, driven, ratio, kind))
    parent = {c.driven: c.driver for c in out}
    for start in parent:
        seen, cur = {start}, parent[start]
        while cur in parent:
            if cur in seen:
                raise ProductError(f"联动连成了一圈（关节 {'、'.join(sorted(seen))}）")
            seen.add(cur)
            cur = parent[cur]
    return out


def mate_tree(asm: Assembly) -> dict[str, tuple[str, str]]:
    """每个非 ground 零件 → (它的父零件, 配合 id)。结构不对时抛 ProductError。"""
    tree: dict[str, tuple[str, str]] = {}
    for m in asm.mates:
        child, par = part_of(m.moving), part_of(m.fixed)
        if child == asm.ground:
            raise ProductError(f"装配关系有问题：配合 {m.id} 把 ground 零件 {child} 当成了被装上去的一边。{TREE_RULE}")
        if child in tree:
            raise ProductError(f"装配关系有问题：零件 {child} 被配合 {tree[child][1]} 和 {m.id} 两次装上去。{TREE_RULE}")
        tree[child] = (par, m.id)
    for start in tree:
        seen, cur = [start], tree[start][0]
        while cur != asm.ground:
            if cur not in tree:
                raise ProductError(f"装配关系有问题：零件 {cur} 没有连上。{TREE_RULE}")
            if cur in seen:
                raise ProductError(f"装配关系有问题：零件 {'、'.join(seen)} 连成了一圈。{TREE_RULE}")
            seen.append(cur)
            cur = tree[cur][0]
    return tree


def parse_assembly(raw: object, part_ids: list[str], connectors: dict[str, list[Connector]],
                   param_names: set[str]) -> Assembly:
    if not isinstance(raw, dict):
        raise ProductError("装配关系必须是对象，含 ground、mates")
    ground = raw.get("ground")
    if ground not in part_ids:
        raise ProductError(f"ground 写的零件 {ground!r} 不存在，只能是：{'、'.join(part_ids)}")
    params = set(param_names)
    mates = _parse_mates(raw.get("mates"), part_ids, connectors, params)
    notes: list[str] = []
    joints = _parse_joints(raw.get("joints"), mates, params, notes)
    couplings = _parse_couplings(raw.get("couplings"), joints, params)
    asm = Assembly(ground, mates, joints, couplings, notes)
    tree = mate_tree(asm)
    missing = [p for p in part_ids if p != ground and p not in tree]
    if missing:
        raise ProductError(f"装配关系有问题：零件 {'、'.join(missing)} 没有连上。{TREE_RULE}")
    return asm


def moving_parts(asm: Assembly, joint_id: str) -> set[str]:
    """这个关节动时一起动的零件：它所在配合的 moving 零件，以及挂在它下面的全部零件。"""
    root = part_of(asm.mate(asm.joint(joint_id).mate).moving)
    tree = mate_tree(asm)
    out = {root}
    changed = True
    while changed:
        changed = False
        for child, (par, _) in tree.items():
            if par in out and child not in out:
                out.add(child)
                changed = True
    return out


def contact_pairs(asm: Assembly) -> set[frozenset[str]]:
    """允许轻微接触的零件配对：只有转动关节的两边和齿轮联动的两个齿轮，其余一概不算。"""
    out: set[frozenset[str]] = set()
    for j in asm.joints:
        if j.type == "revolute":
            m = asm.mate(j.mate)
            out.add(frozenset((part_of(m.fixed), part_of(m.moving))))
    for c in asm.couplings:
        if c.kind == "gear":
            a = part_of(asm.mate(asm.joint(c.driver).mate).moving)
            b = part_of(asm.mate(asm.joint(c.driven).mate).moving)
            out.add(frozenset((a, b)))
    return out
