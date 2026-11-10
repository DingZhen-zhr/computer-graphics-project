"""分阶段流程的工具：set_plan，以及按阶段把关的 upsert_feature、remove_feature、set_checks（设计文档第 3.3、3.4 节）。

关卡报错一律返回 {"error": 原文}，不计失败次数，状态不变。
update_brief、ask_user、request_confirmation、inspect、api_help 沿用 ToolBox 原来的处理函数。
"""

from __future__ import annotations

import copy
from typing import TYPE_CHECKING, Any, Callable

from cad_agent.checks.spec import CheckSpecError, missing_coverage, parse_checks
from cad_agent.notebook import Feature, NotebookError
from cad_agent.plan import PlanError, revise
from cad_agent.sandbox.guard import check_code
from cad_agent.staged import messages as msg
from cad_agent.staged.select import insert_index
from cad_agent.tool_common import ToolOutcome, _err, _json

if TYPE_CHECKING:
    from cad_agent.tools import ToolBox

Handler = Callable[[dict], ToolOutcome]
NOT_READY = "这个工具还没有接上"  # build、probe、read_reference 由后面的任务接上


class StagedTools:
    def __init__(self, box: "ToolBox") -> None:
        self.box = box
        self.build: Handler = lambda args: _err(NOT_READY)
        self.probe: Handler = lambda args: _err(NOT_READY)
        self.read_reference: Handler = lambda args: _err(NOT_READY)

    @property
    def ws(self):  # noqa: ANN201 - Workspace，避免循环导入不写类型
        return self.box.ws

    def handlers(self) -> dict[str, Handler]:
        b = self.box
        return {
            "update_brief": b._update_brief, "ask_user": b._ask_user, "request_confirmation": b._request_confirmation,
            "set_plan": self.set_plan,
            "upsert_feature": self._need_plan(self.upsert_feature),
            "remove_feature": self._need_plan(self.remove_feature),
            "set_checks": self._need_plan(self.set_checks),
            "build": self._need_plan(lambda args: self.build(args)),
            "inspect": b._inspect, "api_help": b._api_help,
            "probe": self._need_plan(lambda args: self.probe(args)),
            "read_reference": lambda args: self.read_reference(args),
        }

    def _need_plan(self, fn: Handler) -> Handler:
        def wrapped(args: dict) -> ToolOutcome:
            if self.ws.plan is None:
                return _err(msg.NO_PLAN)
            return fn(args)
        return wrapped

    def feature_names(self) -> list[str]:
        return [f"{f.slug}({f.role}, {f.stage})" for f in self.ws.features.items]

    def _slugs_by_stage(self) -> dict[str, list[str]]:
        out: dict[str, list[str]] = {}
        for f in self.ws.features.items:
            out.setdefault(f.stage, []).append(f.slug)
        return out

    def _invalidate(self, stage_id: str) -> None:
        """这个阶段原来是已通过的，就把它和后面的阶段都变回未通过。"""
        plan = self.ws.plan
        if stage_id in plan.ids() and plan.get(stage_id).passed:
            plan.invalidate_from(stage_id)

    # ---- set_plan ----
    def set_plan(self, args: dict) -> ToolOutcome:
        try:
            plan = revise(self.ws.plan, args["stages"], self._slugs_by_stage())
        except PlanError as e:
            return _err(str(e))
        self.ws.plan = plan
        self.box.unbuilt_edits = True
        cur = plan.current()
        return ToolOutcome(_json({
            "ok": True, "stages": [{"id": s.id, "title": s.title, "passed": s.passed} for s in plan.stages],
            "current": cur.id if cur else None,
        }))

    # ---- upsert_feature ----
    def upsert_feature(self, args: dict) -> ToolOutcome:
        slug, role, code, before = args["slug"], args["role"], args["code"], args.get("before")
        if not all(isinstance(v, str) for v in (slug, role, code)) or not (before is None or isinstance(before, str)):
            return _err("slug、role、code、before 都必须是文字")
        problems = check_code(code)
        if problems:
            return _err(f"特征 {slug} 的代码没有通过检查，没有改动：" + "；".join(problems))
        ws, plan = self.ws, self.ws.plan
        old = next((f for f in ws.features.items if f.slug == slug), None)
        try:
            if old is not None:  # 替换：位置和所属阶段不变
                ws.features.upsert(Feature(slug, role, code, old.stage))
                self._invalidate(old.stage)
                stage_id = old.stage
            else:
                cur = plan.current()
                if cur is None:
                    return _err(msg.all_passed())
                if not any(c.get("stage") == cur.id for c in ws.checks_raw):
                    return _err(msg.need_checks(cur.id))
                if before is not None:
                    items = ws.features.items
                    pos = next((i for i, f in enumerate(items) if f.slug == before and f.stage == cur.id), None)
                    if pos is None:
                        return _err(msg.before_other_stage(cur.id))
                else:
                    pos = insert_index(ws, cur.id)
                ws.features.insert(Feature(slug, role, code, cur.id), pos)
                stage_id = cur.id
        except NotebookError as e:
            return _err(str(e))
        self.box.unbuilt_edits = True
        return ToolOutcome(_json({"ok": True, "stage": stage_id, "features": self.feature_names()}))

    # ---- remove_feature ----
    def remove_feature(self, args: dict) -> ToolOutcome:
        old = next((f for f in self.ws.features.items if f.slug == args["slug"]), None)
        try:
            self.ws.features.remove(args["slug"])
        except NotebookError as e:
            return _err(str(e))
        if old is not None:
            self._invalidate(old.stage)
        self.box.unbuilt_edits = True
        return ToolOutcome(_json({"ok": True, "features": self.feature_names()}))

    # ---- set_checks ----
    def set_checks(self, args: dict) -> ToolOutcome:
        ws, plan = self.ws, self.ws.plan
        stage = args["stage"]
        if not isinstance(stage, str) or stage not in plan.ids():
            return _err(msg.unknown_stage(str(stage), plan.ids()))
        cur = plan.current()
        if cur is not None and plan.index(stage) > plan.index(cur.id):
            return _err(msg.future_stage(stage, cur.id))
        raw = args["checks"]
        if not isinstance(raw, list):
            return _err("检查项没有通过校验，原有检查项保持不变：checks 必须是数组")
        new = [{**c, "stage": stage} if isinstance(c, dict) else c for c in copy.deepcopy(raw)]
        positions = [i for i, c in enumerate(ws.checks_raw) if c.get("stage") == stage]
        others = [c for c in ws.checks_raw if c.get("stage") != stage]
        at = positions[0] if positions else len(others)  # 放在这个阶段原来的检查所在的位置，原来没有就接在末尾
        combined = others[:at] + new + others[at:]
        try:
            parsed = parse_checks(combined, set(ws.brief.param_values()))
        except CheckSpecError as e:
            return _err(f"检查项没有通过校验，原有检查项保持不变：{e}")
        ws.checks_raw = combined
        self._invalidate(stage)
        self.box.unbuilt_edits = True
        missing = sorted(missing_coverage([c for c in parsed if c.holds == "from_here"], ws.brief.user_param_names()))
        body: dict[str, Any] = {"ok": True, "stage": stage, "count": len(new), "missing_coverage": missing}
        return ToolOutcome(_json(body))
