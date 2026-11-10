"""旧流程（1.2 版，单阶段）的建模工具：从 tools.py 原样移过来，行为不变。

ToolBox 继承这个类；分阶段流程的工具在 cad_agent/staged/ 里。
"""

from __future__ import annotations

import copy
from typing import Any

from cad_agent.checks.spec import CheckSpecError, missing_coverage, parse_checks, parse_where
from cad_agent.notebook import Feature, NotebookError, render_notebook
from cad_agent.sandbox.execute import RunResult
from cad_agent.sandbox.guard import check_code
from cad_agent.tool_common import INSPECT_LIMIT, ToolOutcome, _err, _error_for_model, _hint, _json


class LegacyTools:
    """旧流程的 upsert_feature、remove_feature、set_checks、build、inspect。用到 ToolBox 的 ws、run_job 等成员。"""

    # ---- 建模阶段 ----
    def _feature_names(self) -> list[str]:
        return [f"{f.slug}({f.role})" for f in self.ws.features.items]

    def _upsert_feature(self, args: dict) -> ToolOutcome:
        slug, role, code, before = args["slug"], args["role"], args["code"], args.get("before")
        if not all(isinstance(v, str) for v in (slug, role, code)) or not (before is None or isinstance(before, str)):
            return _err("slug、role、code、before 都必须是文字")
        problems = check_code(code)
        if problems:
            return _err(f"特征 {slug} 的代码没有通过检查，没有改动：" + "；".join(problems))
        try:
            self.ws.features.upsert(Feature(slug, role, code), before)
        except NotebookError as e:
            return _err(str(e))
        self.unbuilt_edits = True
        return ToolOutcome(_json({"ok": True, "features": self._feature_names()}))

    def _remove_feature(self, args: dict) -> ToolOutcome:
        try:
            self.ws.features.remove(args["slug"])
        except NotebookError as e:
            return _err(str(e))
        self.unbuilt_edits = True
        return ToolOutcome(_json({"ok": True, "features": self._feature_names()}))

    def _set_checks(self, args: dict) -> ToolOutcome:
        raw = args["checks"]
        try:
            checks = parse_checks(raw, set(self.ws.brief.param_values()))
        except CheckSpecError as e:
            return _err(f"检查项没有通过校验，原有检查项保持不变：{e}")
        self.ws.checks_raw = copy.deepcopy(raw)
        self.unbuilt_edits = True
        missing = sorted(missing_coverage(checks, self.ws.brief.user_param_names()))
        return ToolOutcome(_json({"ok": True, "count": len(raw), "missing_coverage": missing}))

    def _build(self, args: dict) -> ToolOutcome:
        ws = self.ws
        self.unbuilt_edits = False  # 一运行就算 build 过了，不管通没通过
        names = set(ws.brief.param_values())
        try:
            rendered = render_notebook(ws.brief.params, ws.features.items)
            checks = parse_checks(ws.checks_raw, names)
        except NotebookError as e:
            return self._build_without_run({"cell": e.feature, "type": "NotebookError", "message": str(e)})
        except CheckSpecError as e:
            return self._build_without_run({"cell": None, "type": "CheckSpecError", "message": str(e)})
        run = self.run_job(rendered, ws.checks_raw, names, mode="build", timeout_s=self.timeout_s, secret_names=self.secret_names)
        ws.last_run = run
        missing = sorted(missing_coverage(checks, ws.brief.user_param_names()))
        deliverable = run.ok and not missing
        if not run.ok:  # C4：几何没出错、检查都通过、只是缺检查，不算失败（hint 里提醒补检查）
            self.build_failures += 1
        error = _error_for_model(run.error) if run.error else None
        failed = [
            {"id": c.id, "type": c.type, "expected": c.expected, "measured": c.measured, "tol": c.tol, "detail": c.detail}
            for c in run.checks if not c.passed
        ]
        body: dict[str, Any] = {
            "passed": deliverable,
            "error": error,
            "failed_checks": failed,
            "passed_checks": sum(1 for c in run.checks if c.passed),
            "missing_coverage": missing,
            "facts": {"size": run.facts["size"], "volume": run.facts["volume"]} if run.facts else None,
            "failures_left": max(0, self.max_build_failures - self.build_failures),
            "hint": _hint(error, run.timed_out, failed, missing),
        }
        if missing:  # 计划的测试要求出现“缺少检查”；提示词文档的 hint 原文写的是“还没有检查”，所以多放一个字段
            body["coverage_note"] = f"缺少检查的用户参数：{'、'.join(missing)}"
        ws.last_build_content = _json(body)
        return ToolOutcome(ws.last_build_content, build=run, deliverable=deliverable)

    def _build_without_run(self, err: dict) -> ToolOutcome:
        """渲染 notebook 或解析检查项时就出错了：没有运行，但仍然计一次失败。"""
        run = RunResult(ok=False, error=err)
        self.unbuilt_edits = False
        self.ws.last_run = run
        self.build_failures += 1
        error = _error_for_model(err)
        body = {
            "passed": False, "error": error, "failed_checks": [], "passed_checks": 0, "missing_coverage": [], "facts": None,
            "failures_left": max(0, self.max_build_failures - self.build_failures),
            "hint": _hint(error, False, [], []),
        }
        self.ws.last_build_content = _json(body)
        return ToolOutcome(self.ws.last_build_content, build=run)

    def _inspect(self, args: dict) -> ToolOutcome:
        kind = args["kind"]
        if kind not in ("faces", "edges"):
            return _err(f"kind 只能是 faces 或 edges，收到 {kind!r}")
        names = set(self.ws.brief.param_values())
        try:
            where = parse_where(args.get("where", []), names)
            rendered = render_notebook(self.ws.brief.params, self.ws.features.items)
        except (CheckSpecError, NotebookError) as e:
            return _err(str(e))
        run = self.run_job(rendered, [], names, mode="inspect", query_spec={"kind": kind, "where": where},
                           timeout_s=self.timeout_s, secret_names=self.secret_names)
        if run.error:
            return ToolOutcome(_json({"error": _error_for_model(run.error)}))
        items = run.query or []
        return ToolOutcome(_json({
            "items": items[:INSPECT_LIMIT], "total": len(items), "truncated": len(items) > INSPECT_LIMIT, "facts": run.facts,
        }))
