"""测试共用的小工具：假的 run_job、常用的需求单和检查项。"""

from __future__ import annotations

from cad_agent.brief import Brief, Param
from cad_agent.checks.spec import CheckResult
from cad_agent.sandbox.execute import RunResult

BOX = "base = scad.make_box_rsolid(width=phone_w, height=40, depth=8, bottom_face_center=(0, 0, 0))"
PHONE_W = {"id": "width", "type": "bbox", "axis": "x", "expected": "phone_w"}
TILT = {
    "id": "tilt", "type": "angle", "expected": "tilt_deg",
    "a": [["geom.type", "==", "PLANE"], ["geom.normal.z", ">=", 0.99]],
    "b": [["geom.type", "==", "PLANE"], ["geom.normal.z", "<=", -0.99]],
}
USER_PARAMS = [
    {"name": "phone_w", "value": 78, "unit": "mm", "source": "user", "note": "手机宽度"},
    {"name": "tilt_deg", "value": 65, "unit": "deg", "source": "user", "note": "支撑角度"},
]


def make_brief(confirmed: bool = False) -> Brief:
    return Brief(
        part_name="手机支架", purpose="放桌上看视频",
        params=[Param(p["name"], p["value"], p["unit"], p["source"], p["note"]) for p in USER_PARAMS],
        features=["底座"], confirmed=confirmed,
    )


def good_result(**over) -> RunResult:
    checks = [CheckResult(i, i, True, None, None, None, "几何体有效") for i in ("valid", "single_solid", "positive_volume")]
    checks.append(CheckResult("width", "bbox", True, 78.0, 78.0, 0.1, "x 向尺寸 78.0000，期望 78.0000"))
    base = dict(ok=True, error=None, values={"phone_w": 78.0, "tilt_deg": 65.0}, checks=checks,
                facts={"bbox": [0, 0, 0, 78, 40, 8], "size": [78.0, 40.0, 8.0], "volume": 24960.0, "n_faces": 6, "n_edges": 12},
                duration_s=0.5)
    base.update(over)
    return RunResult(**base)


def bad_result(message: str, cell: str | None = "base", type_: str = "NameError") -> RunResult:
    return RunResult(ok=False, error={"cell": cell, "type": type_, "message": message})


class Runner:
    """代替 run_job。

    build 调用依次返回 results（用完后重复最后一个）；带 export_step 的调用（交付时的导出）
    会真的写出文件，并返回一个成功的结果。
    """

    def __init__(self, *results: RunResult) -> None:
        self.results = list(results) or [good_result()]
        self.calls: list[dict] = []

    def __call__(self, rendered, checks_raw, param_names, **kw):
        self.calls.append({"checks_raw": checks_raw, "param_names": param_names, **kw})
        if kw.get("export_step") is not None:
            step, png = kw["export_step"], kw["render_png"]
            step.parent.mkdir(parents=True, exist_ok=True)
            step.write_bytes(b"STEP")
            png.write_bytes(b"PNG")
            return good_result(step_path=step, png_path=png)
        return self.results.pop(0) if len(self.results) > 1 else self.results[0]
