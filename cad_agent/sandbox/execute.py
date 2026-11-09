"""父进程：启动运行模型的子进程，处理超时，整理结果。

协议：在英文临时目录写 model.py 和 job.json → 子进程写 result.json → 复制导出的文件 → 删除临时目录。
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Literal

from cad_agent.checks.spec import CheckResult
from cad_agent.notebook import RenderedNotebook
from cad_agent.sandbox.guard import clean_env

GRACE_S = 30  # 子进程里除了运行模型，还要跑检查、导出、截图，所以外层超时比 timeout_s 多留一点


@dataclass
class RunResult:
    ok: bool
    error: dict | None
    values: dict[str, float] = field(default_factory=dict)
    checks: list[CheckResult] = field(default_factory=list)
    facts: dict = field(default_factory=dict)
    query: list[dict] | None = None
    step_path: Path | None = None
    png_path: Path | None = None
    duration_s: float = 0.0
    timed_out: bool = False


def _kill_tree(proc: subprocess.Popen) -> None:
    """结束子进程以及它启动的子进程（比如截图用的渲染进程）。"""
    if sys.platform == "win32":
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)], capture_output=True, check=False)
    else:
        proc.kill()


def _copy_out(src: Path, dst: Path) -> Path:
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src, dst)
    return dst


def run_job(
    rendered: RenderedNotebook,
    checks_raw: list[dict],
    param_names: set[str],
    *,
    mode: Literal["build", "inspect"] = "build",
    query_spec: dict | None = None,
    export_step: Path | None = None,
    render_png: Path | None = None,
    timeout_s: float = 60,
    secret_names: Iterable[str] = (),
) -> RunResult:
    """在独立子进程里运行 notebook 并测量。exports 的文件会复制到调用方给的路径。"""
    started = time.monotonic()
    workdir = Path(tempfile.mkdtemp(prefix="cad-agent-"))
    try:
        (workdir / "model.py").write_text(rendered.text, encoding="utf-8")
        job = {
            "workdir": str(workdir),
            "notebook": str(workdir / "model.py"),
            "cell_lines": {k: list(v) for k, v in rendered.cell_lines.items()},
            "checks_raw": checks_raw,
            "param_names": sorted(param_names),
            "mode": mode,
            "query_spec": query_spec,
            "export_step": export_step is not None,
            "render_png": render_png is not None,
            "timeout_s": timeout_s,
        }
        job_path = workdir / "job.json"
        job_path.write_text(json.dumps(job, ensure_ascii=False), encoding="utf-8")

        env = clean_env(os.environ, secret_names)
        env["PYTHONUTF8"] = "1"
        # -I 会忽略 PYTHONUTF8，所以再用 -X utf8 明确打开
        cmd = [sys.executable, "-I", "-X", "utf8", "-m", "cad_agent.sandbox.runner", str(job_path)]
        flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        proc = subprocess.Popen(
            cmd, cwd=workdir, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, encoding="utf-8", errors="replace", creationflags=flags,
        )
        try:
            _, stderr = proc.communicate(timeout=timeout_s + GRACE_S)
        except subprocess.TimeoutExpired:
            _kill_tree(proc)
            proc.communicate()
            return RunResult(
                ok=False, timed_out=True, duration_s=time.monotonic() - started,
                error={"cell": None, "type": "TimeoutError", "message": f"运行超过 {timeout_s:g} 秒被终止"},
            )

        result_path = workdir / "result.json"
        if not result_path.exists():
            tail = (stderr or "").strip()[-500:]
            return RunResult(
                ok=False, duration_s=time.monotonic() - started,
                error={"cell": None, "type": "SandboxCrash", "message": f"运行进程异常退出（返回码 {proc.returncode}）：{tail}"},
            )
        res = json.loads(result_path.read_text(encoding="utf-8"))
        checks = [CheckResult.from_dict(d) for d in res["checks"]]
        step_path = _copy_out(workdir / "model.step", export_step) if export_step is not None and res["step"] else None
        png_path = _copy_out(workdir / "view.png", render_png) if render_png is not None and res["png"] else None
        return RunResult(
            ok=res["error"] is None and all(c.passed for c in checks),
            error=res["error"], values=res["values"], checks=checks, facts=res["facts"], query=res["query"],
            step_path=step_path, png_path=png_path, duration_s=time.monotonic() - started, timed_out=bool(res["timed_out"]),
        )
    finally:
        shutil.rmtree(workdir, ignore_errors=True)  # 只是清理临时目录，删不掉（比如被占用）不应让整次运行失败
