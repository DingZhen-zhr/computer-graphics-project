"""需求单：参数的唯一来源，也是用户确认的对象。"""

from __future__ import annotations

import copy
import keyword
import math
import re
from dataclasses import dataclass, field
from typing import Any, Literal

from .brief_parts import PartInfo, parse_parts, render_parts

UNITS = ("mm", "deg", "1")
SOURCES = ("user", "suggested")
PATCH_KEYS = ("part", "set_params", "remove_params", "features", "open_questions", "parts", "motions", "relations")
NAME_STOPS = "，,；;：:（("  # 组成部分的名字到这些符号为止
NAME_RE = re.compile(r"^[a-z][a-z0-9_]*$")
# 这些名字会和 notebook 里已有的名字或检查表达式里的函数冲突，不能当参数名
RESERVED_NAMES = frozenset({
    "scad", "ql", "math", "model", "marimo", "app",
    "sin", "cos", "tan", "asin", "acos", "atan", "radians", "degrees", "sqrt", "abs", "min", "max", "pi",
})
SOURCE_LABEL = {"user": "用户给的", "suggested": "智能体建议"}


class BriefError(ValueError):
    """需求单修改不合法；信息是中文，直接返回给模型看。"""


@dataclass
class Param:
    name: str
    value: float
    unit: str
    source: Literal["user", "suggested"]
    note: str = ""
    part: str | None = None   # 只属于某一个零件时是零件编号；产品参数（几个零件共用）是 None


def _num(v: float) -> float | int:
    """整数值按整数输出，给模型和用户看更自然（78 而不是 78.0）。"""
    return int(v) if float(v).is_integer() else v


def _fmt(v: float) -> str:
    return f"{v:g}"


def _parse_param(raw: Any) -> Param:
    if not isinstance(raw, dict):
        raise BriefError("set_params 里的每一项都必须是对象，含 name、value、unit、source、note")
    name = raw.get("name")
    if not isinstance(name, str) or not NAME_RE.match(name) or keyword.iskeyword(name) or name in RESERVED_NAMES:
        raise BriefError(
            f"参数名 {name!r} 不合法：必须是小写字母开头、只含小写字母数字下划线的英文名，"
            "且不能是 Python 关键字，也不能叫 scad、ql、math、model、sin、pi 这类保留名"
        )
    value = raw.get("value")
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise BriefError(f"参数 {name} 的 value 必须是有限的数，收到 {value!r}")
    unit = raw.get("unit")
    if unit not in UNITS:
        raise BriefError(f"参数 {name} 的单位只能是 mm、deg、1（个数等无量纲量），收到 {unit!r}。请先换算成 mm 再写入，并在 note 里写下原话")
    source = raw.get("source")
    if source not in SOURCES:
        raise BriefError(f"参数 {name} 的 source 只能是 user 或 suggested，收到 {source!r}")
    note = raw.get("note", "")
    if not isinstance(note, str):
        raise BriefError(f"参数 {name} 的 note 必须是文字")
    part = raw.get("part")
    if part is not None and not isinstance(part, str):
        raise BriefError(f"参数 {name} 的 part 必须是零件编号")
    return Param(name, float(value), unit, source, note, part or None)


def _param_line(p: Param) -> str:
    note = f"　{p.note}" if p.note else ""
    return f"  - {p.name} = {_fmt(p.value)} {p.unit}　［{SOURCE_LABEL[p.source]}］{note}"


def feature_name(text: str) -> str:
    """组成部分的名字：取 NAME_STOPS 里最早出现的那个符号之前的部分，去掉首尾空白。"""
    cut = min((i for i in (text.find(ch) for ch in NAME_STOPS) if i >= 0), default=len(text))
    return text[:cut].strip()


def _str_list(raw: Any, key: str) -> list[str]:
    if not isinstance(raw, list) or not all(isinstance(x, str) and x.strip() for x in raw):
        raise BriefError(f"{key} 必须是非空文字组成的数组")
    return [x.strip() for x in raw]


@dataclass
class Brief:
    part_name: str = ""
    purpose: str = ""
    params: list[Param] = field(default_factory=list)
    features: list[str] = field(default_factory=list)
    open_questions: list[str] = field(default_factory=list)
    confirmed: bool = False
    relations: list[str] = field(default_factory=list)       # 各部分怎么相接，每条一句话
    require_relations: bool = field(default=False, compare=False)  # 分阶段时由 ToolBox 打开；不写进 to_dict
    parts: list[PartInfo] = field(default_factory=list)       # 多零件时每个零件一项；单零件为空
    motions: list[str] = field(default_factory=list)          # 每个会动的地方一句话

    # ---- 查询 ----
    def can_build(self) -> tuple[bool, str]:
        if self.open_questions:
            return False, "还有待确认问题：" + "；".join(self.open_questions)
        if not self.confirmed:
            return False, "需求单还未确认，请先用 request_confirmation 请用户确认"
        return True, ""

    def is_multipart(self) -> bool:
        return len(self.parts) >= 2

    def params_of(self, part_id: str | None) -> list[Param]:
        """part_id 为 None 时是产品参数；否则是这个零件自己的参数。"""
        return [p for p in self.params if p.part == part_id]

    def missing_relations(self) -> list[str]:
        """除第一个部分（多零件时是第一个零件）外，名字没有在任何一条 relations 里出现的；不要求位置关系时总是空表。"""
        if not self.require_relations:
            return []
        if self.is_multipart():
            names = [p.name for p in self.parts[1:]]
        elif len(self.features) >= 2:
            names = [feature_name(f) for f in self.features[1:]]
        else:
            return []
        return [n for n in names if not any(n in r for r in self.relations)]

    def user_param_names(self) -> set[str]:
        return {p.name for p in self.params if p.source == "user"}

    def param_values(self) -> dict[str, float]:
        return {p.name: p.value for p in self.params}

    # ---- 修改 ----
    def apply_patch(self, patch: dict) -> list[str]:
        """应用一次修改，返回中文变化行。出错时抛 BriefError，且需求单保持原样。"""
        if not isinstance(patch, dict):
            raise BriefError("patch 必须是对象")
        unknown = [k for k in patch if k not in PATCH_KEYS]
        if unknown:
            raise BriefError(f"未知字段：{'、'.join(map(str, unknown))}。可用字段：{'、'.join(PATCH_KEYS)}")
        work = copy.deepcopy(self)
        lines: list[str] = []
        reset = False

        part = patch.get("part")
        if part is not None:
            if not isinstance(part, dict):
                raise BriefError("part 必须是对象，含 name、purpose")
            for key, attr, label in (("name", "part_name", "零件名称"), ("purpose", "purpose", "用途")):
                if key in part:
                    if not isinstance(part[key], str):
                        raise BriefError(f"part.{key} 必须是文字")
                    old, new = getattr(work, attr), part[key].strip()
                    if old != new:
                        setattr(work, attr, new)
                        lines.append(f"{label}: {old or '（空）'} → {new}")

        removes = patch.get("remove_params")
        if removes is not None:
            for name in _str_list(removes, "remove_params"):
                hit = next((p for p in work.params if p.name == name), None)
                if hit is None:
                    raise BriefError(f"没有参数 {name}，无法删除")
                work.params.remove(hit)
                lines.append(f"{name}: 已删除（原值 {_fmt(hit.value)} {hit.unit}）")

        sets = patch.get("set_params")
        if sets is not None:
            if not isinstance(sets, list):
                raise BriefError("set_params 必须是数组")
            for raw in sets:
                new = _parse_param(raw)
                old = next((p for p in work.params if p.name == new.name), None)
                if old is None:
                    work.params.append(new)
                    lines.append(f"{new.name}: 新增 {_fmt(new.value)} {new.unit}（{SOURCE_LABEL[new.source]}）")
                    changed = True
                elif old != new:
                    if old.value != new.value or old.unit != new.unit:
                        lines.append(f"{new.name}: {_fmt(old.value)} → {_fmt(new.value)} ({new.unit})")
                    else:
                        lines.append(f"{new.name}: 说明或来源有改动（{SOURCE_LABEL[new.source]}）")
                    work.params[work.params.index(old)] = new
                    changed = True
                else:
                    changed = False
                if changed and new.source == "suggested":
                    reset = True

        if "features" in patch:
            new_features = _str_list(patch["features"], "features")
            if new_features != work.features:
                work.features = new_features
                lines.append("组成部分: " + "；".join(new_features))

        if "relations" in patch:
            new_relations = _str_list(patch["relations"], "relations")
            if new_relations != work.relations:
                work.relations = new_relations
                work.confirmed = False  # 确认之后改了相接方式，要重新确认
                lines.append("位置关系有改动")

        if "parts" in patch:
            new_parts = parse_parts(patch["parts"], BriefError)
            if new_parts != work.parts:
                work.parts = new_parts
                work.confirmed = False
                lines.append("零件: " + ("；".join(f"{p.id} {p.name}" for p in new_parts) if new_parts else "（已清空）"))

        if "motions" in patch:
            new_motions = _str_list(patch["motions"], "motions") if patch["motions"] else []
            if new_motions != work.motions:
                work.motions = new_motions
                work.confirmed = False
                lines.append("会动的地方: " + ("；".join(new_motions) if new_motions else "（没有）"))

        ids = {p.id for p in work.parts}
        stray = [f"{p.name}（{p.part}）" for p in work.params if p.part is not None and p.part not in ids]
        if stray:
            raise BriefError(f"这些参数写的零件不存在：{'、'.join(stray)}。part 要写 parts 里已有的零件编号")

        if "open_questions" in patch:
            new_questions = _str_list(patch["open_questions"], "open_questions")
            if new_questions != work.open_questions:
                work.open_questions = new_questions
                lines.append("待确认问题: " + ("；".join(new_questions) if new_questions else "（已清空）"))

        if work.open_questions or reset:
            work.confirmed = False

        # 全部检查通过，才改动自己
        self.__dict__.update(work.__dict__)
        return lines

    # ---- 序列化 ----
    def to_dict(self) -> dict:
        return {
            "part": {"name": self.part_name, "purpose": self.purpose},
            "params": [
                {"name": p.name, "value": _num(p.value), "unit": p.unit, "source": p.source, "note": p.note,
                 **({"part": p.part} if p.part is not None else {})}
                for p in self.params
            ],
            "features": list(self.features),
            **({"relations": list(self.relations)} if self.relations else {}),
            **({"parts": [p.to_dict() for p in self.parts]} if self.parts else {}),
            **({"motions": list(self.motions)} if self.motions else {}),
            "open_questions": list(self.open_questions),
            "confirmed": self.confirmed,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Brief":
        part = d.get("part", {})
        return cls(
            part_name=part.get("name", ""),
            purpose=part.get("purpose", ""),
            params=[Param(p["name"], float(p["value"]), p["unit"], p["source"], p.get("note", ""), p.get("part")) for p in d.get("params", [])],
            features=list(d.get("features", [])),
            open_questions=list(d.get("open_questions", [])),
            confirmed=bool(d.get("confirmed", False)),
            relations=list(d.get("relations", [])),
            parts=[PartInfo.from_dict(x) for x in d.get("parts", [])],
            motions=list(d.get("motions", [])),
        )

    def render_text(self) -> str:
        """给用户看的中文需求单，标出每个参数是用户给的还是智能体建议的。"""
        out = ["【需求单】", f"零件：{self.part_name or '（未命名）'}" + (f"（{self.purpose}）" if self.purpose else "")]
        out.append("参数：")
        if self.params and self.is_multipart():
            groups = [("产品参数", self.params_of(None))] + [(f"{p.name}的参数", self.params_of(p.id)) for p in self.parts]
            for title, items in groups:
                if items:
                    out.append(f"  {title}：")
                    out.extend("  " + _param_line(p) for p in items)
        elif self.params:
            out.extend(_param_line(p) for p in self.params)
        else:
            out.append("  （还没有）")
        if self.is_multipart():
            out.extend(render_parts(self.parts, self.motions))
        else:
            out.append("组成部分：")
            out.extend([f"  {i}. {f}" for i, f in enumerate(self.features, 1)] or ["  （还没有）"])
        if self.relations:
            out.append("位置关系：")
            out.extend(f"  - {r}" for r in self.relations)
        if self.open_questions:
            out.append("待确认问题：")
            out.extend(f"  - {q}" for q in self.open_questions)
        return "\n".join(out)
