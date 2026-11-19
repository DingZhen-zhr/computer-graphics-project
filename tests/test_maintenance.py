"""版本号、更新和卸载（第二版计划 4 Task 2）。

文件操作都在临时目录里；钥匙串用内存里的假后端；运行外部命令的 run 都是假函数，什么都不会真的执行。
"""

from __future__ import annotations

import subprocess
import tomllib
from pathlib import Path

import keyring
import pytest

from cad_agent import __version__, app, maintenance
from cad_agent.llm.providers import load_providers
from cad_agent.maintenance import INSTALL_PS1, INSTALL_SH, REPO, run_uninstall, run_update, shortcut_paths, update_command
from test_keystore import MemoryKeyring

ROOT = Path(__file__).resolve().parent.parent
FAKE = "fake-uninstall-key-0000-WXYZ"
QUESTION = "要把会话、案例和设置也一起删掉吗？输入 yes 确认删除，直接回车保留："


@pytest.fixture
def box(monkeypatch, tmp_path):
    """假的用户目录：数据目录、开始菜单、桌面、~/Applications 都在 tmp_path 里；钥匙串在内存里，放好两条假 key。"""
    home = tmp_path / "home"
    data = home / "AppData" / "Local" / "Caliper"
    (data / "sessions" / "s1").mkdir(parents=True)
    (data / "settings.toml").write_text('provider = "deepseek"\n', encoding="utf-8")
    monkeypatch.setenv("CALIPER_HOME", str(data))
    monkeypatch.setattr(maintenance, "_home", lambda: home)
    monkeypatch.setattr(maintenance, "_programs_dir", lambda: home / "Start Menu" / "Programs")
    monkeypatch.setattr(maintenance, "_desktop_dir", lambda: home / "Desktop")
    monkeypatch.setattr(maintenance, "_system", lambda: "win32")
    monkeypatch.setattr(maintenance, "_interactive", lambda: False)
    monkeypatch.setattr(maintenance, "_uv", lambda: "uv")
    previous = keyring.get_keyring()
    backend = MemoryKeyring()
    keyring.set_keyring(backend)
    backend.set_password("caliper", "deepseek", FAKE)
    backend.set_password("caliper", "glm", FAKE)
    backend.set_password("other-app", "deepseek", "not-ours")
    for p in shortcut_paths():
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"lnk")
    yield {"home": home, "data": data, "keyring": backend}
    keyring.set_keyring(previous)


class Recorder:
    def __init__(self, fail: bool = False) -> None:
        self.calls: list[list[str]] = []
        self.kwargs: list[dict] = []
        self.fail = fail

    def __call__(self, cmd, **kwargs):
        self.calls.append(list(cmd))
        self.kwargs.append(kwargs)
        if self.fail:
            raise OSError("开不了进程")
        return 0


def test_version_string(capsys):
    assert __version__ == "2.0.0"
    with pytest.raises(SystemExit) as e:
        app.main(["--version"])
    assert e.value.code == 0
    assert capsys.readouterr().out.strip() == "卡尺 Caliper 2.0.0"


def test_pyproject_name_and_version():
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert data["project"]["name"] == "caliper-cad"
    assert data["project"]["version"] == "2.0.0" == __version__
    assert "卡尺" in data["project"]["description"]


def test_install_urls():
    assert REPO == "DingZhen-zhr/computer-graphics-project"
    assert INSTALL_PS1 == "https://raw.githubusercontent.com/DingZhen-zhr/computer-graphics-project/master/install.ps1"
    assert INSTALL_SH == "https://raw.githubusercontent.com/DingZhen-zhr/computer-graphics-project/master/install.sh"


@pytest.mark.parametrize("system", ["win32", "darwin"])
def test_update_runs_install_script_command(monkeypatch, system):
    monkeypatch.setattr(maintenance, "_system", lambda: system)
    cmd = update_command()
    run = Recorder()
    assert run_update(run=run, say=lambda *_: None) == 0
    assert run.calls == [cmd]
    text = " ".join(cmd)
    if system == "win32":
        assert cmd[0].lower().startswith("powershell") and INSTALL_PS1 in text and "iex" in text
    else:
        assert cmd[0] == "sh" and INSTALL_SH in text and "curl" in text and "| sh" in text
        assert "--connect-timeout" in text


def test_update_prints_before_running(monkeypatch):
    monkeypatch.setattr(maintenance, "_system", lambda: "darwin")
    order: list[str] = []

    def run(cmd, **_):
        order.append("run")
        return 0

    run_update(run=run, say=lambda text="": order.append(f"say:{text}"))
    assert order[-1] == "run"
    assert any(x.startswith("say:") and INSTALL_SH in x for x in order[:-1])


def test_update_reports_a_failed_command(monkeypatch):
    monkeypatch.setattr(maintenance, "_system", lambda: "darwin")
    said: list[str] = []
    assert run_update(run=lambda cmd, **_: 3, say=said.append) == 3
    assert any("没有成功" in s for s in said)
    assert run_update(run=Recorder(fail=True), say=said.append) == 1


def test_shortcut_paths_per_platform(monkeypatch, tmp_path):
    monkeypatch.setattr(maintenance, "_home", lambda: tmp_path)
    monkeypatch.setattr(maintenance, "_programs_dir", lambda: tmp_path / "P")
    monkeypatch.setattr(maintenance, "_desktop_dir", lambda: tmp_path / "D")
    monkeypatch.setattr(maintenance, "_system", lambda: "win32")
    assert shortcut_paths() == [tmp_path / "P" / "卡尺 Caliper.lnk", tmp_path / "D" / "卡尺 Caliper.lnk"]
    monkeypatch.setattr(maintenance, "_system", lambda: "darwin")
    assert shortcut_paths() == [tmp_path / "Applications" / "Caliper.app"]


def test_uninstall_removes_shortcuts_and_keys(box):
    said: list[str] = []
    run = Recorder()
    assert run_uninstall(delete_data=False, say=said.append, run=run) == 0
    assert all(not p.exists() for p in shortcut_paths())
    assert ("caliper", "deepseek") not in box["keyring"].store and ("caliper", "glm") not in box["keyring"].store
    assert box["keyring"].store == {("other-app", "deepseek"): "not-ours"}   # 别人的钥匙串项不动
    text = "\n".join(said)
    assert all(str(p) in text for p in shortcut_paths())
    assert FAKE not in text and FAKE[-4:] not in text


def test_uninstall_mac_app_bundle(box, monkeypatch):
    monkeypatch.setattr(maintenance, "_system", lambda: "darwin")
    app_dir = box["home"] / "Applications" / "Caliper.app"
    (app_dir / "Contents" / "MacOS").mkdir(parents=True)
    (app_dir / "Contents" / "Info.plist").write_text("<plist/>", encoding="utf-8")
    run_uninstall(delete_data=False, say=lambda *_: None, run=Recorder())
    assert not app_dir.exists() and (box["home"] / "Applications").exists()


def test_uninstall_skips_missing_shortcuts(box):
    for p in shortcut_paths():
        p.unlink()
    said: list[str] = []
    assert run_uninstall(delete_data=False, say=said.append, run=Recorder()) == 0
    assert any("跳过" in s for s in said)


def test_uninstall_delete_data_flag(box):
    asked: list[str] = []
    run_uninstall(delete_data=True, ask=lambda q: asked.append(q) or "", say=lambda *_: None, run=Recorder())
    assert not box["data"].exists() and asked == []
    assert box["home"].exists()


def test_uninstall_keep_data_flag(box, monkeypatch):
    monkeypatch.setattr(maintenance, "_interactive", lambda: True)
    asked: list[str] = []
    run_uninstall(delete_data=False, ask=lambda q: asked.append(q) or "yes", say=lambda *_: None, run=Recorder())
    assert (box["data"] / "settings.toml").exists() and (box["data"] / "sessions" / "s1").exists() and asked == []


@pytest.mark.parametrize("answer, deleted", [("", False), ("y", False), ("no", False), ("是", False), ("yes", True), (" yes\n", True)])
def test_uninstall_asks_and_only_yes_deletes(box, monkeypatch, answer, deleted):
    monkeypatch.setattr(maintenance, "_interactive", lambda: True)
    asked: list[str] = []
    run_uninstall(delete_data=None, ask=lambda q: asked.append(q) or answer, say=lambda *_: None, run=Recorder())
    assert asked == [QUESTION]
    assert box["data"].exists() is not deleted


def test_uninstall_keeps_data_by_default_when_not_interactive(box):
    asked: list[str] = []
    said: list[str] = []
    run_uninstall(delete_data=None, ask=lambda q: asked.append(q) or "yes", say=said.append, run=Recorder())
    assert asked == []
    assert (box["data"] / "settings.toml").exists()
    assert any("保留" in s and str(box["data"]) in s for s in said)


def test_uninstall_ask_eof_keeps_data(box, monkeypatch):
    monkeypatch.setattr(maintenance, "_interactive", lambda: True)

    def eof(_q: str) -> str:
        raise EOFError

    run_uninstall(delete_data=None, ask=eof, say=lambda *_: None, run=Recorder())
    assert box["data"].exists()


def test_uninstall_spawns_detached_uv_uninstall(box):
    run = Recorder()
    said: list[str] = []
    assert run_uninstall(delete_data=False, say=said.append, run=run) == 0
    assert len(run.calls) == 1
    cmd = " ".join(run.calls[0])
    assert "uv" in cmd and "tool uninstall caliper-cad" in cmd
    kw = run.kwargs[0]
    if hasattr(subprocess, "DETACHED_PROCESS"):   # Windows：不依附当前的控制台
        assert kw["creationflags"] & subprocess.DETACHED_PROCESS
    else:                                         # Mac：新的会话，当前进程退出也不受影响
        assert kw["start_new_session"] is True
    assert any("uv tool uninstall caliper-cad" in s for s in said)


def test_uninstall_prints_command_when_spawn_fails(box):
    said: list[str] = []
    code = run_uninstall(delete_data=False, say=said.append, run=Recorder(fail=True))
    assert code == 1
    assert any("uv tool uninstall caliper-cad" in s and "自己运行" in s for s in said)


def test_uninstall_steps_are_printed_in_order(box):
    said: list[str] = []
    run_uninstall(delete_data=False, say=said.append, run=Recorder())
    marks = [next(i for i, s in enumerate(said) if s.startswith(f"[{n}/4]")) for n in range(1, 5)]
    assert marks == sorted(marks)


def test_uninstall_never_touches_paths_outside_home(box, monkeypatch, tmp_path):
    elsewhere = tmp_path / "important" / "data"
    elsewhere.mkdir(parents=True)
    (elsewhere / "keep.txt").write_text("别删我", encoding="utf-8")
    monkeypatch.setenv("CALIPER_HOME", str(elsewhere))
    said: list[str] = []
    code = run_uninstall(delete_data=True, say=said.append, run=Recorder())
    assert (elsewhere / "keep.txt").exists()
    assert code == 1
    assert any("不删" in s and str(elsewhere) in s for s in said)
    # 用户主目录本身，或它的上级，也不删
    for target in (box["home"], box["home"].parent):
        monkeypatch.setenv("CALIPER_HOME", str(target))
        assert run_uninstall(delete_data=True, say=lambda *_: None, run=Recorder()) == 1
        assert target.exists()


def test_uninstall_command_line(box, monkeypatch, capsys):
    run = Recorder()
    monkeypatch.setattr(maintenance, "_spawn", run)
    assert app.main(["uninstall", "--keep-data"]) == 0
    assert box["data"].exists() and len(run.calls) == 1
    assert app.main(["uninstall", "--delete-data"]) == 0
    assert not box["data"].exists()
    with pytest.raises(SystemExit):
        app.main(["uninstall", "--keep-data", "--delete-data"])


def test_update_command_line(monkeypatch, capsys):
    run = Recorder()
    monkeypatch.setattr(maintenance, "_call", run)
    monkeypatch.setattr(maintenance, "_system", lambda: "win32")
    assert app.main(["update"]) == 0
    assert run.calls == [update_command()]
    assert INSTALL_PS1 in capsys.readouterr().out


def test_every_provider_key_is_removed(box):
    for p in load_providers():
        box["keyring"].set_password("caliper", p.id, FAKE)
    run_uninstall(delete_data=False, say=lambda *_: None, run=Recorder())
    assert not any(service == "caliper" for service, _ in box["keyring"].store)
