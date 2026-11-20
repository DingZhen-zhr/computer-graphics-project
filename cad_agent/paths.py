"""数据放在哪（设计文档第 6.3 节；3.0 改名，见 3.0 设计第 11 节）。

Windows：%LOCALAPPDATA%\\Datum；Mac：~/Library/Application Support/Datum；其他系统：~/.datum。
环境变量 DATUM_HOME 可以改。沙盒的工作目录必须是纯英文路径，系统临时目录带中文时改用 work_root()。
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

from cad_agent import brand

HOME_ENV = brand.HOME_ENV
APP_DIR = brand.HOME_DIR


def app_home() -> Path:
    """数据目录：环境变量 DATUM_HOME 优先（空白不算）；否则按系统取默认位置。不在这里创建目录。"""
    custom = os.environ.get(HOME_ENV, "").strip()
    if custom:
        return Path(custom)
    if sys.platform == "win32":
        local = os.environ.get("LOCALAPPDATA", "").strip()
        base = Path(local) if local else Path.home() / "AppData" / "Local"
        return base / APP_DIR
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / APP_DIR
    return Path.home() / f".{APP_DIR.lower()}"


def settings_path() -> Path:
    return app_home() / "settings.toml"


def sessions_dir() -> Path:
    return app_home() / "sessions"


def cases_dir() -> Path:
    return app_home() / "cases"


def logs_dir() -> Path:
    return app_home() / "logs"


def is_ascii_path(p: Path) -> bool:
    """路径里是不是只有英文字符（SCA 在带中文的路径下会出错，见第一版笔记）。"""
    return str(p).isascii()


def _ensure_dir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def work_root() -> Path | None:
    """沙盒临时目录放在哪：系统临时目录是纯英文路径时返回 None（就用它）；
    否则 Windows 返回 C:\\ProgramData\\Datum\\work（不存在就建），其他系统返回 /tmp。"""
    if is_ascii_path(Path(tempfile.gettempdir())):
        return None
    if sys.platform == "win32":
        root = Path("C:/ProgramData") / APP_DIR / "work"
        _ensure_dir(root)
        return root
    return Path("/tmp")
