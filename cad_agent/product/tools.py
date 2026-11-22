"""多零件的五个工具：select_part、set_connectors、set_assembly、set_assembly_checks、build_assembly。

需求单只有一个零件时，这五个工具不出现在工具表里，调用也只返回一句说明。
关卡报错一律返回 {"error": 原文}，不计失败次数。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Callable

from ..staged.messages import hint_unconstrained
from ..tool_common import ToolOutcome, _err, _json
from .checks import evaluate, mandatory_checks, parse_assembly_checks
from .model import ProductError
from .spec import parse_assembly, parse_connectors
from .workspace import ensure_parts, part_param_names, select_part

if TYPE_CHECKING:
    from ..tools import ToolBox

Handler = Callable[[dict], ToolOutcome]
NAMES = ("select_part", "set_connectors", "set_assembly", "set_assembly_checks", "build_assembly")
SINGLE_PART = "这个需求只有一个零件，用不到这个工具。"
NO_ASSEMBLY = "还没有装配关系。先用 set_connectors 和 set_assembly 写好。"
PARTS_LEFT = "还有零件没做完：{ids}。全部零件做完才能装配。"
HINT_ERROR = "出错位置不在某个特征里，多半是参数或特征之间的引用有问题。先检查参数名和变量名是否一致。"
HINT_ANCHOR = "有连接点没有挂在真实的几何上。看 connectors 里每个连接点选中了什么，改 set_connectors 的 where。"
HINT_OVERLAP = ("装好后零件 {a} 和 {b} 重叠了 {v} 立方毫米。看是哪边的尺寸或位置不对：尺寸不对就用 select_part 回去改那个零件；"
                "位置不对就改 set_connectors 或 set_assembly。")
HINT_HIT = ("{label} 动到 {value}{unit} 时，零件 {a} 和 {b} 碰到了，重叠 {v} 立方毫米。给它们留出动的空间：加大间隙、缩短会碰到的部分，"
            "或者改动的范围（改范围要先问用户）。")
HINT_WRONG_WAY = ("刚离开装好的位置就碰到，多半是动的方向反了：先在 set_assembly 里把这个关节的范围反过来（比如 [0, 110] 改成 [-110, 0]），"
                  "或者把连接点的方向反过来，再 build_assembly 试一次；方向对了还碰，再改零件。")
HINT_FAILED = "先看每条 detail 里选中了哪些几何：选错了就改检查条件，选对了但数值不对就改模型。"
HINT_DONE = "全部通过，程序会自动交付。"
UNIT = {"revolute": "°", "prismatic": " 毫米"}


def _g(v: float) -> str:
    return f"{round(float(v), 3):g}"


def hint_hit(label: str, value: float, unit: str, a: str, b: str, volume: float, span: float) -> str:
    """动起来碰到时的提示。碰的位置离装好的位置（0）不到取样范围的十分之一，多加一句先查方向（3.0 修改清单第 5 条）。"""
    text = HINT_HIT.format(label=label, value=_g(value), unit=unit, a=a, b=b, v=_g(volume))
    return text + HINT_WRONG_WAY if span > 0 and abs(value) <= 0.1 * span else text


def invalidate_assembly(ws: Any) -> None:
    ws.assembly_passed = False
    ws.last_assembly = None


class ProductTools:
    def __init__(self, box: "ToolBox") -> None:
        self.box = box

    @property
    def ws(self):  # noqa: ANN201 - Workspace，避免循环导入不写类型
        return self.box.ws

    def handlers(self) -> dict[str, Handler]:
        return {"select_part": self.select_part, "set_connectors": self.set_connectors, "set_assembly": self.set_assembly,
                "set_assembly_checks": self.set_assembly_checks, "build_assembly": self.build_assembly}

    def _sync(self) -> None:
        if set(self.ws.parts) != {p.id for p in self.ws.brief.parts}:
            ensure_parts(self.ws)

    def _names(self) -> set[str]:
        return {p.name for p in self.ws.brief.params}

    def _part(self, args: dict) -> str | ToolOutcome:
        pid = args.get("part")
        if pid not in self.ws.parts:
            return _err(f"没有零件 {pid!r}。现在的零件：{'、'.join(self.ws.parts)}")
        return pid

    # ---- select_part ----
    def select_part(self, args: dict) -> ToolOutcome:
        self._sync()
        pid = self._part(args)
        if isinstance(pid, ToolOutcome):
            return pid
        select_part(self.ws, pid)
        ws = self.ws
        cur = ws.plan.current() if ws.plan is not None else None
        info = next(p for p in ws.brief.parts if p.id == pid)
        return ToolOutcome(_json({
            "ok": True, "part": pid, "name": info.name, "done": ws.parts[pid].done,
            "plan": [{"id": s.id, "title": s.title, "passed": s.passed} for s in ws.plan.stages] if ws.plan else None,
            "current": cur.id if cur else None, "features": [f.slug for f in ws.features.items],
            "params": part_param_names(ws, pid),
        }))

    # ---- set_connectors ----
    def set_connectors(self, args: dict) -> ToolOutcome:
        self._sync()
        pid = self._part(args)
        if isinstance(pid, ToolOutcome):
            return pid
        try:
            cons = parse_connectors(pid, args["connectors"], set(part_param_names(self.ws, pid)))
        except ProductError as e:
            return _err(str(e))
        self.ws.parts[pid].connectors = cons
        invalidate_assembly(self.ws)
        body: dict[str, Any] = {"ok": True, "part": pid, "connectors": [c.name for c in cons]}
        if self.ws.assembly is not None:   # 装配关系里用到的连接点没了：装配关系作废，要重写
            try:
                self._parse(self.ws.assembly.to_dict())
            except ProductError as e:
                self.ws.assembly = None
                body["note"] = f"原来的装配关系用到了改掉的连接点，已经作废，要重新 set_assembly：{e}"
        return ToolOutcome(_json(body))

    # ---- set_assembly ----
    def _parse(self, raw: dict):  # noqa: ANN202
        cons = {pid: st.connectors for pid, st in self.ws.parts.items()}
        return parse_assembly(raw, list(self.ws.parts), cons, self._names())

    def set_assembly(self, args: dict) -> ToolOutcome:
        self._sync()
        try:
            asm = self._parse(args)
        except ProductError as e:
            return _err(str(e))
        ws = self.ws
        ws.assembly = asm
        invalidate_assembly(ws)
        body: dict[str, Any] = {"ok": True, "ground": asm.ground, "mates": [m.id for m in asm.mates],
                                "joints": [{"id": j.id, "label": j.label, "type": j.type, "range": [j.lo, j.hi]} for j in asm.joints],
                                "notes": list(asm.notes)}
        if ws.assembly_checks_raw:
            try:
                parse_assembly_checks(ws.assembly_checks_raw, asm, list(ws.parts), self._names())
            except ProductError as e:
                ws.assembly_checks_raw = []
                body["notes"].append(f"原来的装配检查和新的装配关系对不上，已经清空，要重新 set_assembly_checks：{e}")
        return ToolOutcome(_json(body))

    # ---- set_assembly_checks ----
    def set_assembly_checks(self, args: dict) -> ToolOutcome:
        ws = self.ws
        if ws.assembly is None:
            return _err(NO_ASSEMBLY)
        try:
            checks = parse_assembly_checks(args["checks"], ws.assembly, list(ws.parts), self._names())
        except ProductError as e:
            return _err(f"装配检查没有通过校验，原有的保持不变：{e}")
        ws.assembly_checks_raw = checks
        invalidate_assembly(ws)
        auto = [c["id"] for c in mandatory_checks(ws.assembly, list(ws.parts))]
        return ToolOutcome(_json({"ok": True, "count": len(checks), "auto_checks": auto}))

    # ---- build_assembly ----
    def build_assembly(self, args: dict) -> ToolOutcome:
        self._sync()
        ws, box = self.ws, self.box
        left = [pid for pid, st in ws.parts.items() if not st.done]
        if left:
            return _err(PARTS_LEFT.format(ids="、".join(left)))
        if ws.assembly is None:
            return _err(NO_ASSEMBLY)
        run = box.run_assembly(ws, mode="check", samples=box.motion_samples, timeout_s=box.timeout_s,
                               secret_names=box.secret_names, should_stop=box.should_stop)
        ws.last_assembly = run
        values = ws.brief.param_values()
        results = evaluate(run, mandatory_checks(ws.assembly, list(ws.parts)) + ws.assembly_checks_raw, ws.assembly, values)
        failed = [r for r in results if not r.passed]
        gate = None
        if run.error is None and not failed:
            from .flow import run_product_gate   # flow 要用到这里，放在这里导入

            gate = run_product_gate(box)
            box.last_gate = gate
        passed = gate is not None and gate.passed
        if not passed:
            box.build_failures += 1
        ws.assembly_passed = passed
        body = {
            "passed": passed,
            "error": {"part": run.error.get("part"), "feature": run.error.get("cell"), "type": run.error["type"],
                      "message": run.error["message"]} if run.error else None,
            "connectors": run.connectors,
            "failed_checks": [{"id": r.id, "type": r.type, "measured": r.measured, "expected": r.expected, "detail": r.detail}
                              for r in failed],
            "passed_checks": len(results) - len(failed),
            "hits": self._first_hits(run),
            "final_gate": None if gate is None else {k: gate.to_dict()[k] for k in ("missing_coverage", "unconstrained", "unbuildable")},
            "failures_left": max(0, box.max_build_failures - box.build_failures),
            "hint": self._hint(run, results, gate),
        }
        ws.last_build_content = _json(body)
        return ToolOutcome(ws.last_build_content, deliverable=passed)

    def _first_hits(self, run: Any) -> list[dict]:
        out = []
        for j in self.ws.assembly.joints:
            for row in run.samples.get(j.id) or []:
                if row["hits"]:
                    h = max(row["hits"], key=lambda x: x["volume"])
                    out.append({"joint": j.id, "label": j.label, "value": row["value"], "a": h["a"], "b": h["b"], "volume": h["volume"]})
                    break
        return out

    def _hint(self, run: Any, results: list, gate: Any) -> str:
        bad = {r.id for r in results if not r.passed}
        if run.error is not None:
            return HINT_ERROR
        if "connectors_anchored" in bad:
            return HINT_ANCHOR
        if "no_overlap_at_rest" in bad and run.overlaps:
            o = max(run.overlaps, key=lambda x: x["volume"])
            return HINT_OVERLAP.format(a=o["a"], b=o["b"], v=_g(o["volume"]))
        for j in self.ws.assembly.joints:
            if f"motion_clear_{j.id}" in bad:
                hit = next((h for h in self._first_hits(run) if h["joint"] == j.id), None)
                if hit is not None:
                    span = max((abs(r["value"]) for r in run.samples.get(j.id) or []), default=0.0)
                    return hint_hit(j.label, hit["value"], UNIT[j.type], hit["a"], hit["b"], hit["volume"], span)
        if bad:
            return HINT_FAILED
        if gate is not None and gate.unconstrained:
            return hint_unconstrained(gate.unconstrained)
        return HINT_DONE
