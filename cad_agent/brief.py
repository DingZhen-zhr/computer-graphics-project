"""需求单：参数的唯一来源，也是用户确认的对象。"""

from __future__ import annotations

import copy
import keyword
import math
import re
from dataclasses import dataclass, field
from typing import Any, Literal

UNITS = ("mm", "deg", "1")
SOURCES = ("user", "suggested")
PATCH_KEYS = ("part", "set_params", "remove_params", "features", "open_questions")
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
    return Param(name, float(value), unit, source, note)


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

    # ---- 查询 ----
    def can_build(self) -> tuple[bool, str]:
        if self.open_questions:
            return False, "还有待确认问题：" + "；".join(self.open_questions)
        if not self.confirmed:
            return False, "需求单还未确认，请先用 request_confirmation 请用户确认"
        return True, ""

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
                {"name": p.name, "value": _num(p.value), "unit": p.unit, "source": p.source, "note": p.note}
                for p in self.params
            ],
            "features": list(self.features),
            "open_questions": list(self.open_questions),
            "confirmed": self.confirmed,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Brief":
        part = d.get("part", {})
        return cls(
            part_name=part.get("name", ""),
            purpose=part.get("purpose", ""),
            params=[Param(p["name"], float(p["value"]), p["unit"], p["source"], p.get("note", "")) for p in d.get("params", [])],
            features=list(d.get("features", [])),
            open_questions=list(d.get("open_questions", [])),
            confirmed=bool(d.get("confirmed", False)),
        )

    def render_text(self) -> str:
        """给用户看的中文需求单，标出每个参数是用户给的还是智能体建议的。"""
        out = ["【需求单】", f"零件：{self.part_name or '（未命名）'}" + (f"（{self.purpose}）" if self.purpose else "")]
        out.append("参数：")
        if self.params:
            for p in self.params:
                note = f"　{p.note}" if p.note else ""
                out.append(f"  - {p.name} = {_fmt(p.value)} {p.unit}　［{SOURCE_LABEL[p.source]}］{note}")
        else:
            out.append("  （还没有）")
        out.append("组成部分：")
        if self.features:
            out.extend(f"  {i}. {f}" for i, f in enumerate(self.features, 1))
        else:
            out.append("  （还没有）")
        if self.open_questions:
            out.append("待确认问题：")
            out.extend(f"  - {q}" for q in self.open_questions)
        return "\n".join(out)
