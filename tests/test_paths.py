"""数据目录和纯英文工作目录。"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

from cad_agent import paths


def test_caliper_home_env_wins(monkeypatch, tmp_path):
    home = tmp_path / "卡尺数据"
    monkeypatch.setenv("CALIPER_HOME", str(home))
    assert paths.app_home() == home
    assert paths.settings_path() == home / "settings.toml"
    assert paths.sessions_dir() == home / "sessions"
    assert paths.cases_dir() == home / "cases"
    assert paths.logs_dir() == home / "logs"


def test_default_home_per_platform(monkeypatch, tmp_path):
    monkeypatch.delenv("CALIPER_HOME", raising=False)
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "Local"))
    assert paths.app_home() == tmp_path / "Local" / "Caliper"
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path / "me"))
    monkeypatch.setattr(sys, "platform", "darwin")
    assert paths.app_home() == tmp_path / "me" / "Library" / "Application Support" / "Caliper"
    monkeypatch.setattr(sys, "platform", "linux")
    assert paths.app_home() == tmp_path / "me" / ".caliper"
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.delenv("LOCALAPPDATA", raising=False)   # 没有 LOCALAPPDATA 时退回到用户目录下的 AppData\Local
    assert paths.app_home() == tmp_path / "me" / "AppData" / "Local" / "Caliper"


def test_blank_caliper_home_is_ignored(monkeypatch, tmp_path):
    monkeypatch.setenv("CALIPER_HOME", "   ")
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    assert paths.app_home() == tmp_path / ".caliper"


def test_is_ascii_path():
    assert paths.is_ascii_path(Path("C:/Users/me/AppData/Local/Temp"))
    assert not paths.is_ascii_path(Path("C:/Users/张三/AppData/Local/Temp"))
    assert not paths.is_ascii_path(Path("/tmp/计算机图形学"))


def test_work_root_none_for_ascii_temp(monkeypatch, tmp_path):
    ascii_dir = tmp_path / "plain"
    ascii_dir.mkdir()
    monkeypatch.setattr(tempfile, "gettempdir", lambda: str(ascii_dir))
    if paths.is_ascii_path(ascii_dir):
        assert paths.work_root() is None


def test_work_root_fallback_for_non_ascii_temp(monkeypatch, tmp_path):
    chinese = tmp_path / "临时"
    monkeypatch.setattr(tempfile, "gettempdir", lambda: str(chinese))
    made: list[Path] = []
    monkeypatch.setattr(paths, "_ensure_dir", lambda p: made.append(p))
    monkeypatch.setattr(sys, "platform", "win32")
    root = paths.work_root()
    assert root == Path("C:/ProgramData/Caliper/work") and paths.is_ascii_path(root) and made == [root]
    monkeypatch.setattr(sys, "platform", "darwin")
    assert paths.work_root() == Path("/tmp")
