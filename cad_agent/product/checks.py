"""装配和运动的检查：解析模型写的检查、程序必做的检查，以及按沙盒量到的结果判断（设计文档第 5.6 节）。

"接触"豁免只给程序从转动关节和齿轮联动推出来的配对（contact_pairs），其余照常算穿模。
"""

from __future__ import annotations

from typing import Any

from ..checks.expr import CheckSpecError, eval_expr, expr_names
from ..checks.spec import ID_RE, CheckResult, parse_where
from .model import Assembly, ProductError
from .spec import contact_pairs

ASSEMBLY_TYPES = ("interference", "clearance", "coaxial", "flush", "motion_clear", "reach", "ratio")
MANDATORY_IDS = ("connectors_anchored", "no_overlap_at_rest")
CONTACT_TOL_MM3 = 0.5      # 笔记"三个常量"一节
OVERLAP_TOL_MM3 = 0.01
DIST_TOL = 0.05
ANGLE_TOL = 0.2
REACH_TOL = {"revolute": 0.5, "prismatic": 0.05}
UNIT = {"revolute": "°", "prismatic": " 毫米"}


def _expr(v: Any, what: str, params: set[str]) -> str | float:
    try:
        unknown = expr_names(v) - params
    except CheckSpecError as e:
        raise ProductError(f"{what}：{e}") from e
    if unknown:
        raise ProductError(f"{what} 用到了不存在的参数 {'、'.join(sorted(unknown))}")
    return v.strip() if isinstance(v, str) else float(v)


def _target(raw: Any, what: str, part_ids: list[str], params: set[str]) -> dict:
    if not isinstance(raw, dict) or raw.get("part") not in part_ids:
        raise ProductError(f"{what} 要写成 {{\"part\": 零件编号, \"kind\": \"faces\", \"where\": [...]}}，零件编号只能是：{'、'.join(part_ids)}")
    try:
        where = parse_where(raw.get("where"), params)
    except CheckSpecError as e:
        raise ProductError(f"{what}：{e}") from e
    return {"part": raw["part"], "kind": raw.get("kind", "faces"), "where": where}


def parse_assembly_checks(raw: object, asm: Assembly, part_ids: list[str], param_names: set[str]) -> list[dict]:
    if not isinstance(raw, list):
        raise ProductError("checks 必须是数组")
    params, joints = set(param_names), {j.id for j in asm.joints}
    out: list[dict] = []
    for item in raw:
        if not isinstance(item, dict):
            raise ProductError("checks 里的每一项都必须是对象，含 id、type")
        cid, t = item.get("id"), item.get("type")
        if not isinstance(cid, str) or not ID_RE.match(cid) or cid in MANDATORY_IDS or cid.startswith("motion_clear_"):
            raise ProductError(f"检查编号 {cid!r} 不合法（小写英文开头；不能用 {'、'.join(MANDATORY_IDS)}、motion_clear_ 开头这些程序用的名字）")
        if any(c["id"] == cid for c in out):
            raise ProductError(f"检查编号 {cid} 重复了")
        if t not in ASSEMBLY_TYPES:
            raise ProductError(f"检查 {cid} 的 type 只能是 {'、'.join(ASSEMBLY_TYPES)}")
        c: dict[str, Any] = {"id": cid, "type": t}
        if t in ("interference", "clearance") or (t == "motion_clear" and ("a" in item or "b" in item)):
            for side in ("a", "b"):
                if item.get(side) not in part_ids:
                    raise ProductError(f"检查 {cid} 的 {side} 要写零件编号，只能是：{'、'.join(part_ids)}")
                c[side] = item[side]
        if t in ("coaxial", "flush"):
            c["a"] = _target(item.get("a"), f"检查 {cid} 的 a", part_ids, params)
            c["b"] = _target(item.get("b"), f"检查 {cid} 的 b", part_ids, params)
        if t in ("motion_clear", "reach"):
            if item.get("joint") not in joints:
                raise ProductError(f"检查 {cid} 的 joint 写的关节 {item.get('joint')!r} 不存在")
            c["joint"] = item["joint"]
        if t == "reach":
            c["value"] = _expr(item.get("value"), f"检查 {cid} 的 value", params)
        if t == "ratio":
            for key in ("driver", "driven"):
                if item.get(key) not in joints:
                    raise ProductError(f"检查 {cid} 的 {key} 写的关节 {item.get(key)!r} 不存在")
                c[key] = item[key]
        if t in ("clearance", "ratio") and "expected" not in item:
            raise ProductError(f"检查 {cid} 要写 expected")
        if "expected" in item or t in ("coaxial", "flush"):
            c["expected"] = _expr(item.get("expected", 0), f"检查 {cid} 的 expected", params)
        c["op"] = item.get("op", ">=" if t == "clearance" else "==")
        if c["op"] not in ("==", ">=", "<="):
            raise ProductError(f"检查 {cid} 的 op 只能是 ==、>=、<=")
        tol = item.get("tol")
        if tol is not None and (isinstance(tol, bool) or not isinstance(tol, (int, float)) or tol < 0):
            raise ProductError(f"检查 {cid} 的 tol 要写不小于 0 的数")
        c["tol"] = float(tol) if tol is not None else (OVERLAP_TOL_MM3 if t == "interference" else 0.01 if t == "ratio" else DIST_TOL)
        out.append(c)
    return out


def mandatory_checks(asm: Assembly, part_ids: list[str]) -> list[dict]:
    return ([{"id": "connectors_anchored", "type": "connectors_anchored"}, {"id": "no_overlap_at_rest", "type": "no_overlap_at_rest"}]
            + [{"id": f"motion_clear_{j.id}", "type": "motion_clear", "joint": j.id} for j in asm.joints])


def _res(c: dict, passed: bool, detail: str, measured: float | None = None, expected: float | None = None) -> CheckResult:
    return CheckResult(c["id"], c["type"], passed, measured, expected, c.get("tol"), detail)


def _cmp(measured: float, expected: float, op: str, tol: float) -> bool:
    return {"==": abs(measured - expected) <= tol, ">=": measured >= expected - tol, "<=": measured <= expected + tol}[op]


def _fmt(v: float) -> str:
    return f"{round(v, 3):g}"


class _Eval:
    def __init__(self, run: Any, asm: Assembly, values: dict[str, float]) -> None:
        self.run, self.asm, self.values = run, asm, values
        self.contact = contact_pairs(asm)

    def tol_for(self, a: str, b: str) -> float:
        return CONTACT_TOL_MM3 if frozenset((a, b)) in self.contact else OVERLAP_TOL_MM3

    def num(self, v: Any) -> float:
        return float(v) if isinstance(v, (int, float)) else eval_expr(v, self.values)

    def connectors_anchored(self, c: dict) -> CheckResult:
        bad = [i["error"] for i in self.run.connectors.values() if "error" in i]
        if bad or not self.run.connectors:
            return _res(c, False, "；".join(bad) or "没有量到连接点（零件没有运行成功）")
        return _res(c, True, f"{len(self.run.connectors)} 个连接点都挂在了真实的几何上")

    def no_overlap_at_rest(self, c: dict) -> CheckResult:
        if not self.run.rest:
            return _res(c, False, "没有装起来，量不了穿模")
        bad = [o for o in self.run.overlaps if o["volume"] > self.tol_for(o["a"], o["b"])]
        if bad:
            o = max(bad, key=lambda x: x["volume"])
            return _res(c, False, f"装好后零件 {o['a']} 和 {o['b']} 重叠了 {_fmt(o['volume'])} 立方毫米", o["volume"], 0.0)
        return _res(c, True, "装好后任意两个零件都不穿模", 0.0, 0.0)

    def motion_clear(self, c: dict) -> CheckResult:
        j = self.asm.joint(c["joint"])
        rows = self.run.samples.get(j.id)
        if not rows:
            return _res(c, False, f"{j.label} 没有取样，量不了碰撞")
        pair = frozenset((c["a"], c["b"])) if "a" in c else None
        for row in rows:
            at = f"{_fmt(row['value'])}{UNIT[j.type]}"
            if row.get("error"):
                return _res(c, False, f"{j.label} 在 {at} 时没量成：{row['error']}")
            for h in row["hits"]:
                if (pair is None or frozenset((h["a"], h["b"])) == pair) and h["volume"] > self.tol_for(h["a"], h["b"]):
                    return _res(c, False, f"{j.label} 动到 {at} 时，零件 {h['a']} 和 {h['b']} 碰到了，重叠 {_fmt(h['volume'])} 立方毫米",
                                h["volume"], 0.0)
        return _res(c, True, f"{j.label} 取了 {len(rows)} 个位置，都没有碰到")

    def reach(self, c: dict) -> CheckResult:
        j = self.asm.joint(c["joint"])
        want = self.num(c["value"])
        rows = self.run.samples.get(j.id) or []
        hit = next((r for r in rows if abs(r["value"] - want) <= REACH_TOL[j.type] and not r.get("error")), None)
        if hit is None:
            return _res(c, False, f"{j.label} 没有动到 {_fmt(want)}{UNIT[j.type]}", None, want)
        return _res(c, True, f"{j.label} 能动到 {_fmt(want)}{UNIT[j.type]}", hit["value"], want)

    def ratio(self, c: dict) -> CheckResult:
        rows = [r for r in self.run.samples.get(c["driver"]) or [] if not r.get("error") and r.get("joints")]
        expected = self.num(c["expected"])
        if len(rows) < 2:
            return _res(c, False, f"关节 {c['driver']} 的取样不够，量不了比例", None, expected)
        d_in = rows[-1]["joints"][c["driver"]] - rows[0]["joints"][c["driver"]]
        d_out = rows[-1]["joints"][c["driven"]] - rows[0]["joints"][c["driven"]]
        measured = d_out / d_in if abs(d_in) > 1e-12 else float("nan")
        ok = _cmp(measured, expected, c["op"], c["tol"])
        return _res(c, ok, f"关节 {c['driven']} 动的量 / 关节 {c['driver']} 动的量 = {_fmt(measured)}，要 {_fmt(expected)}", measured, expected)

    def geometric(self, c: dict) -> CheckResult:
        m = self.run.measures.get(c["id"])
        if m is None:
            return _res(c, False, "没有量到（装配没有运行到这一步）")
        if "error" in m:
            return _res(c, False, f"没量成：{m['error']}")
        t = c["type"]
        if t == "interference":
            v = m["volume"]
            return _res(c, v <= c["tol"], f"零件 {c['a']} 和 {c['b']} 重叠 {_fmt(v)} 立方毫米，最多 {_fmt(c['tol'])}", v, 0.0)
        if t == "clearance":
            d, e = m["distance"], self.num(c["expected"])
            return _res(c, _cmp(d, e, c["op"], c["tol"]), f"零件 {c['a']} 和 {c['b']} 最近 {_fmt(d)} 毫米，要 {c['op']} {_fmt(e)}", d, e)
        what = "圆柱面" if t == "coaxial" else "平面"
        for side in ("a", "b"):
            n = m.get(f"selected_{side}", 0)
            if n != 1:
                return _res(c, False, f"{side}（零件 {c[side]['part']}）选中了 {n} 个{what}，要恰好 1 个")
        d, ang, e = m["distance"], m["angle"], self.num(c["expected"])
        ok = abs(d - e) <= c["tol"] and ang <= ANGLE_TOL
        name = "两条轴线" if t == "coaxial" else "两个平面"
        return _res(c, ok, f"{name}相距 {_fmt(d)} 毫米、夹角 {_fmt(ang)}°，要相距 {_fmt(e)}、夹角不超过 {ANGLE_TOL:g}°", d, e)


def evaluate(run: Any, checks: list[dict], asm: Assembly, values: dict[str, float]) -> list[CheckResult]:
    ev = _Eval(run, asm, values)
    out = []
    for c in checks:
        t = c["type"]
        fn = getattr(ev, t) if t in ("connectors_anchored", "no_overlap_at_rest", "motion_clear", "reach", "ratio") else ev.geometric
        out.append(fn(c))
    return out
