"""工具定义与实现：模型能调用的全部工具都在这里，程序在这里把关。

工具的 description 和参数格式在 tool_specs.py（逐字取自提示词文档）；
build 的返回格式和 hint 取自提示词文档第 4 节。
"""

from __future__ import annotations

import copy
import difflib
import json
from dataclasses import dataclass
from typing import Any, Callable, Iterable

from cad_agent.agent.api_docs import api_names, lookup_api, normalize_api_name
from cad_agent.brief import Brief, BriefError
from cad_agent.checks.spec import CheckSpecError, missing_coverage, parse_checks, parse_where
from cad_agent.notebook import Feature, FeatureList, NotebookError, render_notebook
from cad_agent.sandbox import execute
from cad_agent.sandbox.execute import RunResult
from cad_agent.sandbox.guard import check_code
from cad_agent.tool_specs import PRE_CONFIRM_TOOLS, TOOL_NAMES, TOOL_SPECS

INSPECT_LIMIT = 30
MAX_QUESTIONS = 5


@dataclass
class Workspace:
    brief: Brief
    features: FeatureList
    checks_raw: list[dict]
    last_run: RunResult | None = None
    awaiting_confirmation: bool = False
    last_build_content: str | None = None   # 上次 build 返回给模型的 JSON 原文；_build 和 _build_without_run 都要设


@dataclass
class ToolOutcome:
    content: str                    # 给模型看的 JSON 文本
    end_turn: bool = False          # 为真时本轮到此结束，等用户回复
    kind: str | None = None         # "question" 或 "confirm"
    build: RunResult | None = None  # 只有 build 工具会带
    deliverable: bool = False       # 只有 build 全部通过且不缺检查时为真


def _json(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False)


def _err(message: str, **extra: Any) -> ToolOutcome:
    return ToolOutcome(_json({"error": message, **extra}))


def _error_for_model(err: dict) -> dict:
    return {"feature": err.get("cell"), "type": err["type"], "message": err["message"]}


def _hint(error: dict | None, timed_out: bool, failed: list, missing: list[str]) -> str:
    if timed_out:
        return "运行超时了。检查是否写了很慢的操作，比如过多的阵列数量或过细的样条。"
    if error and error["feature"]:
        return f"只修改特征 {error['feature']}。拿不准函数用法时先用 api_help 查。"
    if error:
        return "出错位置不在某个特征里，多半是参数或特征之间的引用有问题。先检查参数名和变量名是否一致。"
    if failed:
        return "先看每条 detail 里选中了哪些几何：选错了就改检查条件，选对了但数值不对就改模型。"
    if missing:
        return f"模型和检查都通过了，但这些用户参数还没有检查：{'、'.join(missing)}。补上检查后再 build。"
    return "全部通过，程序会自动交付。"


class ToolBox:
    def __init__(
        self,
        ws: Workspace,
        run_job: Callable[..., RunResult] = execute.run_job,
        timeout_s: float = 60,
        secret_names: Iterable[str] = (),
    ) -> None:
        self.ws = ws
        self.run_job = run_job
        self.timeout_s = timeout_s
        self.secret_names = tuple(secret_names)
        self.max_build_failures = 3  # 由主循环按配置设置
        self.build_failures = 0      # 本轮用户消息内 build 没通过的次数
        self._handlers: dict[str, Callable[[dict], ToolOutcome]] = {
            "update_brief": self._update_brief, "ask_user": self._ask_user, "request_confirmation": self._request_confirmation,
            "upsert_feature": self._upsert_feature, "remove_feature": self._remove_feature, "set_checks": self._set_checks,
            "build": self._build, "inspect": self._inspect, "api_help": self._api_help,
        }

    # ---- 对外接口 ----
    def begin_turn(self) -> None:
        """每收到一条新的用户消息时由主循环调用：建模失败计数清零。"""
        self.build_failures = 0

    def available(self) -> list[str]:
        ok, _ = self.ws.brief.can_build()
        return list(TOOL_NAMES) if ok else list(PRE_CONFIRM_TOOLS)

    def schemas(self) -> list[dict]:
        names = set(self.available())
        return [copy.deepcopy(s) for s in TOOL_SPECS if s["function"]["name"] in names]

    def call(self, name: str, args: dict) -> ToolOutcome:
        """调用一个工具。任何问题都变成给模型看的中文错误，不抛异常。"""
        try:
            return self._dispatch(name, args)
        except Exception as e:  # noqa: BLE001 - 工具层的约定：不抛异常，原因返回给模型
            return _err(f"工具 {name} 执行时出了内部错误（{type(e).__name__}）：{e}")

    # ---- 分发与把关 ----
    def _dispatch(self, name: str, args: Any) -> ToolOutcome:
        if name not in self._handlers:
            return _err(f"没有叫 {name} 的工具。可用的工具：{'、'.join(self.available())}")
        if not isinstance(args, dict):
            return _err(f"工具 {name} 的参数必须是 JSON 对象")
        if "__raw__" in args:
            return _err(f"工具 {name} 的参数不是合法 JSON，没有执行。收到的原文：{str(args['__raw__'])[:200]}。请按工具说明重新调用")
        if name not in self.available():
            ok, why = self.ws.brief.can_build()
            return _err(f"需求单现在不能建模：{why}。建模工具要等需求单确认后才能用。现在可用的工具：{'、'.join(self.available())}")
        spec = next(s for s in TOOL_SPECS if s["function"]["name"] == name)["function"]
        missing = [k for k in spec["parameters"].get("required", []) if k not in args]
        if missing:
            return _err(f"工具 {name} 缺少参数 {'、'.join(missing)}")
        return self._handlers[name](args)

    # ---- 澄清阶段 ----
    def _update_brief(self, args: dict) -> ToolOutcome:
        try:
            changes = self.ws.brief.apply_patch(args)
        except BriefError as e:
            return _err(str(e))
        ok, why = self.ws.brief.can_build()
        body: dict[str, Any] = {"changes": changes, "can_build": ok}
        if not ok:
            body["why_not"] = why
        return ToolOutcome(_json(body))

    def _ask_user(self, args: dict) -> ToolOutcome:
        qs = args["questions"]
        if not isinstance(qs, list) or not 1 <= len(qs) <= MAX_QUESTIONS or not all(isinstance(q, str) and q.strip() for q in qs):
            return _err(f"questions 必须是 1 到 {MAX_QUESTIONS} 个非空问题组成的数组")
        return ToolOutcome(_json({"questions": qs, "status": "已向用户提问，等用户回答"}), end_turn=True, kind="question")

    def _request_confirmation(self, args: dict) -> ToolOutcome:
        if self.ws.brief.open_questions:
            return _err("还有待确认的问题，不能请用户确认需求单：" + "；".join(self.ws.brief.open_questions) + "。先用 ask_user 问清楚")
        self.ws.awaiting_confirmation = True
        return ToolOutcome(
            _json({"status": "需求单已展示给用户，等用户确认", "brief_text": self.ws.brief.render_text()}),
            end_turn=True, kind="confirm",
        )

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
        return ToolOutcome(_json({"ok": True, "features": self._feature_names()}))

    def _remove_feature(self, args: dict) -> ToolOutcome:
        try:
            self.ws.features.remove(args["slug"])
        except NotebookError as e:
            return _err(str(e))
        return ToolOutcome(_json({"ok": True, "features": self._feature_names()}))

    def _set_checks(self, args: dict) -> ToolOutcome:
        raw = args["checks"]
        try:
            checks = parse_checks(raw, set(self.ws.brief.param_values()))
        except CheckSpecError as e:
            return _err(f"检查项没有通过校验，原有检查项保持不变：{e}")
        self.ws.checks_raw = copy.deepcopy(raw)
        missing = sorted(missing_coverage(checks, self.ws.brief.user_param_names()))
        return ToolOutcome(_json({"ok": True, "count": len(raw), "missing_coverage": missing}))

    def _build(self, args: dict) -> ToolOutcome:
        ws = self.ws
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
        if not deliverable:
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

    # ---- 查文档 ----
    def _api_help(self, args: dict) -> ToolOutcome:
        raw = args["name"]
        if not isinstance(raw, str):
            return _err("name 必须是函数名文字")
        name = normalize_api_name(raw)
        doc = lookup_api(name)
        if doc is not None:
            return ToolOutcome(_json({"name": name, "doc": doc}))
        similar = difflib.get_close_matches(name, api_names(), n=5, cutoff=0.4)
        return _err(f"没有找到叫 {name} 的函数。", similar=similar)
