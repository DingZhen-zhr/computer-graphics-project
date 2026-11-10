"""分阶段测试共用的小工具：按"最后一个特征"给结果的假 run_job，和一个两阶段的工作区。"""

from __future__ import annotations

import re
import threading

from cad_agent.brief import Brief, Param
from cad_agent.checks.spec import CheckResult
from cad_agent.notebook import Feature, FeatureList
from cad_agent.plan import revise
from cad_agent.sandbox.execute import RunResult
from cad_agent.tools import Workspace
from helpers import good_result

FEATURE_RE = re.compile(r"# ---- feature: ([a-z][a-z0-9-]*) \(")
STAGES2 = [{"title": "底板", "done_when": "有一块底板"}, {"title": "立板", "done_when": "左端有立板"}]
BASE = "base = scad.make_box_rsolid(width=phone_w, height=40, depth=8, bottom_face_center=(0, 0, 0))"
WALL = "wall = scad.union_rsolid(base, scad.make_box_rsolid(width=8, height=40, depth=60, bottom_face_center=(-35, 0, 0)))"
CHECK_S1 = {"id": "base-w", "type": "bbox", "axis": "x", "expected": "phone_w", "stage": "s1"}
CHECK_S2 = {"id": "wall-h", "type": "bbox", "axis": "z", "expected": 60, "stage": "s2"}
TILT = {
    "id": "tilt", "type": "angle", "expected": "tilt_deg", "stage": "s1",
    "a": [["geom.type", "==", "PLANE"], ["geom.normal.z", ">=", 0.99]],
    "b": [["geom.type", "==", "PLANE"], ["geom.normal.z", "<=", -0.99]],
}


def last_slug(text: str) -> str | None:
    found = FEATURE_RE.findall(text)
    return found[-1] if found else None


def passing(*ids: str, **over) -> RunResult:
    """一个通过的结果；ids 是除必做检查外要带上的检查 id。"""
    r = good_result(**over)
    r.checks = [c for c in r.checks if c.id in ("valid", "single_solid", "positive_volume")]
    r.checks += [CheckResult(i, "bbox", True, 1.0, 1.0, 0.1, "通过") for i in ids]
    return r


def failing(cid: str = "base-w", **over) -> RunResult:
    r = passing(**over)
    r.ok = False
    r.checks.append(CheckResult(cid, "bbox", False, 90.0, 78.0, 0.1, "x 向尺寸 90，期望 78"))
    return r


class StageRunner:
    """代替 run_job：按渲染出的 notebook 里最后一个特征的 slug 取结果。

    results 的值是一个结果，或一串结果（依次取，用完后重复最后一个）。没写到的 slug 用 default（默认是通过）。
    calls 记下每次调用的最后一个特征、检查 id 和全部关键字参数。多个线程可以同时调用。
    """

    def __init__(self, results: dict[str, RunResult | list[RunResult]] | None = None, default: RunResult | None = None) -> None:
        self.results = {k: (list(v) if isinstance(v, list) else [v]) for k, v in (results or {}).items()}
        self.default = default
        self.calls: list[dict] = []
        self.lock = threading.Lock()

    def slugs(self) -> list[str | None]:
        return [c["slug"] for c in self.calls]

    def __call__(self, rendered, checks_raw, param_names, **kw):
        slug = last_slug(rendered.text)
        with self.lock:
            self.calls.append({"slug": slug, "check_ids": [c["id"] for c in checks_raw], "text": rendered.text,
                               "checks_raw": checks_raw, "param_names": param_names, **kw})
            queue = self.results.get(slug)
            if queue:
                result = queue.pop(0) if len(queue) > 1 else queue[0]
            else:
                result = self.default or passing(*[c["id"] for c in checks_raw])
            result = RunResult(**{**result.__dict__})   # 复制一份，避免多次调用共用同一个对象
        if kw.get("export_step") is not None:
            step, png = kw["export_step"], kw["render_png"]
            step.parent.mkdir(parents=True, exist_ok=True)
            step.write_bytes(b"STEP")
            png.write_bytes(b"PNG")
            result.step_path, result.png_path = step, png
        if kw.get("export_stl") is not None and result.ok:
            stl = kw["export_stl"]
            stl.parent.mkdir(parents=True, exist_ok=True)
            stl.write_bytes(b"STL")
            result.stl_path = stl
        return result


def staged_brief() -> Brief:
    return Brief(
        part_name="L 形支架", purpose="测试",
        params=[Param("phone_w", 78, "mm", "user", "宽"), Param("tilt_deg", 65, "deg", "user", "角度")],
        features=["底板", "立板"], relations=["立板的下端和底板的一端重叠"], confirmed=True,
    )


def two_stage_ws(s2_written: bool = True) -> Workspace:
    """已确认的需求单、两个阶段的计划、每个阶段一个特征一条检查（s2_written 为假时 s2 什么都没写）。"""
    feats = [Feature("base", "build", BASE, "s1")]
    checks = [dict(CHECK_S1), dict(TILT)]
    if s2_written:
        feats.append(Feature("wall", "add", WALL, "s2"))
        checks.append(dict(CHECK_S2))
    ws = Workspace(staged_brief(), FeatureList(feats), checks)
    ws.plan = revise(None, STAGES2, {})
    return ws
