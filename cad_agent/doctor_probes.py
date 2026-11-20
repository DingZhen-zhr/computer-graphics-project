"""caliper doctor 用到的探测函数（从 doctor.py 拆出来，让它不超过 300 行）。

doctor.py 按名字把这些函数导入进去，各项检查调用的是 doctor 模块里的名字，
所以测试里用 monkeypatch.setattr(doctor, "_connect", ...) 换掉的照样生效。
"""

from __future__ import annotations

import importlib.metadata
import importlib.util
import platform
import secrets
import socket
import sys
import tempfile
from pathlib import Path

from cad_agent import paths

BOX = (10.0, 20.0, 30.0)
WEBVIEW2_GUID = "{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}"   # WebView2 运行时（常青版）在 EdgeUpdate 里的编号


def _platform_info() -> tuple[str, str, str]:
    """(sys.platform, 芯片, 系统版本号)。"""
    if sys.platform == "darwin":
        return sys.platform, platform.machine(), platform.mac_ver()[0]
    return sys.platform, platform.machine(), platform.version()


def _system() -> str:
    return sys.platform


def _python_version() -> tuple[int, int, int]:
    return sys.version_info[:3]


def _sca_version() -> str | None:
    if importlib.util.find_spec("simplecadapi") is None:
        return None
    try:
        return importlib.metadata.version("simplecadapi")
    except importlib.metadata.PackageNotFoundError:
        return None


def _sandbox_box() -> tuple[float, float, float]:
    """用沙盒建一个 10×20×30 的方块，返回量出来的外形尺寸。建不出来抛 RuntimeError（信息是中文）。"""
    from cad_agent.brief import Param
    from cad_agent.notebook import Feature, render_notebook
    from cad_agent.sandbox.execute import run_job

    params = [Param("w", BOX[0], "mm", "user"), Param("h", BOX[1], "mm", "user"), Param("t", BOX[2], "mm", "user")]
    box = Feature("box", "build", "box = scad.make_box_rsolid(width=w, height=h, depth=t, bottom_face_center=(0, 0, 0))")
    result = run_job(render_notebook(params, [box]), [], set(), timeout_s=180)
    if result.timed_out:
        raise RuntimeError("沙盒超时了（3 分钟内没建完）")
    if not result.ok or not result.facts.get("size"):
        err = result.error or {}
        raise RuntimeError(f"沙盒没建出来：{err.get('type', '未知错误')} {str(err.get('message', ''))[:120]}".strip())
    x, y, z = (float(v) for v in result.facts["size"])
    return x, y, z


def _temp_dir() -> Path:
    return Path(tempfile.gettempdir())


def _fallback_dir() -> Path:
    """系统临时目录带中文时沙盒改用的目录（和沙盒用的是同一个函数，不存在就建）。"""
    root = paths.work_root()
    return root if root is not None else _temp_dir()


def _try_write(path: Path) -> None:
    """建目录，写一个小文件再删掉；做不到就抛 OSError。"""
    path.mkdir(parents=True, exist_ok=True)
    probe = path / f".caliper-doctor-{secrets.token_hex(4)}.tmp"
    probe.write_text("ok", encoding="utf-8")
    probe.unlink()


def _import_webview() -> None:
    import webview  # noqa: F401 - 只看能不能导入


def _webview2_version() -> str | None:
    """Windows 上 WebView2 运行时的版本号；没装返回 None。按微软文档查 EdgeUpdate 的注册表项（只读）。"""
    import winreg

    places = [
        (winreg.HKEY_LOCAL_MACHINE, rf"SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{WEBVIEW2_GUID}"),
        (winreg.HKEY_LOCAL_MACHINE, rf"SOFTWARE\Microsoft\EdgeUpdate\Clients\{WEBVIEW2_GUID}"),
        (winreg.HKEY_CURRENT_USER, rf"Software\Microsoft\EdgeUpdate\Clients\{WEBVIEW2_GUID}"),
    ]
    for hive, sub in places:
        try:
            with winreg.OpenKey(hive, sub) as key:
                value, _ = winreg.QueryValueEx(key, "pv")
        except OSError:
            continue
        value = str(value or "").strip()
        if value and value != "0.0.0.0":
            return value
    return None


def _connect(host: str, port: int, timeout: float) -> None:
    """只建立一次 TCP 连接就关掉，不发任何内容。连不上抛 OSError。"""
    socket.create_connection((host, port), timeout=timeout).close()
