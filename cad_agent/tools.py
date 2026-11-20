"""工具定义与实现：模型能调用的全部工具都在这里，程序在这里把关。

工具的 description 和参数格式在 tool_specs.py（逐字取自提示词文档）；
build 的返回格式和 hint 取自提示词文档第 4 节。
"""

from __future__ import annotations

import copy
import difflib
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Iterable

from cad_agent.agent.api_docs import api_names, lookup_api, normalize_api_name
from cad_agent.brief import Brief, BriefError
from cad_agent.gates import Gates
from cad_agent.notebook import FeatureList
from cad_agent.plan import Plan
from cad_agent.sandbox import execute
from cad_agent.sandbox.execute import RunResult
from cad_agent.tool_common import INSPECT_LIMIT, ToolOutcome, _err, _error_for_model, _hint, _json  # noqa: F401 - 其他模块从这里导入
from cad_agent.tool_specs import PRE_CONFIRM_TOOLS, TOOL_NAMES, TOOL_SPECS
from cad_agent.tools_legacy import LegacyTools

if TYPE_CHECKING:
    from cad_agent.product.model import Assembly
    from cad_agent.product.workspace import PartState
    from cad_agent.sandbox.runner_assembly import AssemblyRun
    from cad_agent.staged.build import Advance
    from cad_agent.staged.final_gate import GateResult

MAX_QUESTIONS = 5
PRODUCT_TOOL_NAMES = ("select_part", "set_connectors", "set_assembly", "set_assembly_checks", "build_assembly")


@dataclass
class Workspace:
    brief: Brief
    features: FeatureList
    checks_raw: list[dict]
    last_run: RunResult | None = None
    awaiting_confirmation: bool = False
    last_build_content: str | None = None   # 上次 build 返回给模型的 JSON 原文；_build 和 _build_without_run 都要设
    plan: Plan | None = None                 # 分阶段计划；旧流程一直是 None
    probes_used: int = 0                     # 当前阶段已经用了几次 probe
    # 多零件（3.0）：单零件时都保持默认。parts 里存各零件的状态，上面几个字段是当前零件（active）的
    parts: dict[str, "PartState"] = field(default_factory=dict)
    active: str | None = None
    assembly: "Assembly | None" = None
    assembly_checks_raw: list[dict] = field(default_factory=list)
    assembly_passed: bool = False
    last_assembly: "AssemblyRun | None" = None


class ToolBox(LegacyTools):
    def __init__(
        self,
        ws: Workspace,
        run_job: Callable[..., RunResult] = execute.run_job,
        timeout_s: float = 60,
        secret_names: Iterable[str] = (),
        gates: Gates | None = None,
    ) -> None:
        self.ws = ws
        self.gates = gates or Gates.legacy()   # 不传 gates 就是 1.2 版的流程
        self.stage_dir: Path | None = None     # 分阶段时各阶段 STL 放哪里（主循环设成会话目录下的 stages）
        self.last_advance: Advance | None = None   # 上次分阶段 build 的推进结果
        self.last_gate: GateResult | None = None   # 上次终检的结果
        self.should_stop: Callable[[], bool] | None = None   # 主循环设；不为 None 时每次 run_job 都带上它
        self.run_job = run_job
        self.timeout_s = timeout_s
        self.secret_names = tuple(secret_names)
        self.max_build_failures = 3  # 由主循环按配置设置
        self.run_assembly = execute.run_assembly   # 多零件的装配运行（测试里换成假的）
        self.motion_samples = 24                   # 每个关节取几个位置，由主循环按配置设置
        self.build_failures = 0      # 本轮用户消息内 build 没通过的次数
        self.unbuilt_edits = False   # 有没有 build 的改动：update_brief、upsert_feature、remove_feature、set_checks 成功后为真，build 一运行就清掉
        self._handlers: dict[str, Callable[[dict], ToolOutcome]] = {
            "update_brief": self._update_brief, "ask_user": self._ask_user, "request_confirmation": self._request_confirmation,
            "upsert_feature": self._upsert_feature, "remove_feature": self._remove_feature, "set_checks": self._set_checks,
            "build": self._build, "inspect": self._inspect, "api_help": self._api_help,
        }
        self._specs, self._names, self._pre_confirm = TOOL_SPECS, list(TOOL_NAMES), list(PRE_CONFIRM_TOOLS)
        if self.gates.staged:  # 分阶段：工具表和建模类工具换成 staged/ 里的（导入放这里，避免循环导入）
            from cad_agent.staged.specs import PRE_CONFIRM_TOOLS_V2, TOOL_NAMES_V2, TOOL_SPECS_V2
            from cad_agent.staged.tools import StagedTools

            ws.brief.require_relations = True
            self._specs, self._names, self._pre_confirm = TOOL_SPECS_V2, list(TOOL_NAMES_V2), list(PRE_CONFIRM_TOOLS_V2)
            self._handlers = StagedTools(self).handlers()
            from cad_agent.product.tools import ProductTools

            self._handlers.update(ProductTools(self).handlers())

    # ---- 运行沙盒 ----
    @property
    def run_job(self) -> Callable[..., RunResult]:
        """沙盒运行函数。设了 should_stop 时自动带上它（分阶段和旧流程所有调用 run_job 的地方都经过这里）；
        没设时就是原来的函数本身，调用方式和以前逐字相同。"""
        raw, stop = self._run_job, self.should_stop
        if stop is None:
            return raw

        def with_stop(*args: Any, **kwargs: Any) -> RunResult:
            kwargs.setdefault("should_stop", stop)
            return raw(*args, **kwargs)

        return with_stop

    @run_job.setter
    def run_job(self, fn: Callable[..., RunResult]) -> None:
        self._run_job = fn

    # ---- 对外接口 ----
    def begin_turn(self) -> None:
        """每收到一条新的用户消息时由主循环调用：建模失败计数清零。"""
        self.build_failures = 0

    def available(self) -> list[str]:
        ok, _ = self.ws.brief.can_build()
        names = list(self._names) if ok else list(self._pre_confirm)
        if not self.ws.brief.is_multipart():   # 只有一个零件时，多零件的工具不出现
            names = [n for n in names if n not in PRODUCT_TOOL_NAMES]
        return names

    def schemas(self) -> list[dict]:
        names = set(self.available())
        return [copy.deepcopy(s) for s in self._specs if s["function"]["name"] in names]

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
        if name in PRODUCT_TOOL_NAMES and not self.ws.brief.is_multipart():
            return _err("这个需求只有一个零件，用不到这个工具。")
        if name not in self.available():
            ok, why = self.ws.brief.can_build()
            return _err(f"需求单现在不能建模：{why}。建模工具要等需求单确认后才能用。现在可用的工具：{'、'.join(self.available())}")
        spec = next(s for s in self._specs if s["function"]["name"] == name)["function"]
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
        if changes:  # 什么都没改的 update_brief 不算改动
            self.unbuilt_edits = True
            if self.gates.staged and self.ws.plan is not None:  # 需求单变了：全部阶段都要重新验证
                self.ws.plan.invalidate_all()
        body: dict[str, Any] = {"changes": changes, "can_build": ok}
        if not ok:
            body["why_not"] = why
        missing = self.ws.brief.missing_relations()
        if missing:
            body["relations_missing"] = missing
            if self.ws.brief.is_multipart():   # 多零件时，没写怎么相接的是零件
                body["parts_missing_relations"] = missing
        return ToolOutcome(_json(body))

    def _ask_user(self, args: dict) -> ToolOutcome:
        qs = args["questions"]
        if not isinstance(qs, list) or not 1 <= len(qs) <= MAX_QUESTIONS or not all(isinstance(q, str) and q.strip() for q in qs):
            return _err(f"questions 必须是 1 到 {MAX_QUESTIONS} 个非空问题组成的数组")
        return ToolOutcome(_json({"questions": qs, "status": "已向用户提问，等用户回答"}), end_turn=True, kind="question")

    def _request_confirmation(self, args: dict) -> ToolOutcome:
        if self.ws.brief.open_questions:
            return _err("还有待确认的问题，不能请用户确认需求单：" + "；".join(self.ws.brief.open_questions) + "。先用 ask_user 问清楚")
        missing = self.ws.brief.missing_relations()
        if missing:
            return _err(f"这些部分还没有写明怎么相接：{'、'.join(missing)}。在 relations 里各写一句，要原样写出它的名字")
        self.ws.awaiting_confirmation = True
        return ToolOutcome(
            _json({"status": "需求单已展示给用户，等用户确认", "brief_text": self.ws.brief.render_text()}),
            end_turn=True, kind="confirm",
        )

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
