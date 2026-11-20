"""datum update 和 datum uninstall（第二版计划 4 Task 2，设计文档第 6.2 节）。

两个命令都会改用户电脑上的东西，所以每一步做之前先打印要做什么。
更新就是重新运行最新的安装脚本，由它覆盖安装；卸载按顺序删快捷方式、钥匙串里的 key、（问过之后）数据目录，
最后新开一个不依附当前进程的进程，让 uv 卸载程序本身。
用到的位置和外部命令都通过模块级的小函数取得，测试里可以换掉。
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Callable

import keyring
import keyring.errors

from cad_agent import brand, paths
from cad_agent.keystore import SERVICE

REPO = "DingZhen-zhr/computer-graphics-project"
INSTALL_PS1 = f"https://raw.githubusercontent.com/{REPO}/master/install.ps1"
INSTALL_SH = f"https://raw.githubusercontent.com/{REPO}/master/install.sh"
DIST_NAME = brand.DIST
WIN_SHORTCUT = f"{brand.DISPLAY}.lnk"
MAC_APP = f"{brand.PRODUCT}.app"
ASK_DELETE = "要把会话、案例和设置也一起删掉吗？输入 yes 确认删除，直接回车保留："
UNINSTALL_WAIT_S = 3   # 后台卸载先等几秒，让当前这个 datum 进程先退出（Windows 上正在运行的程序文件删不掉）
UPDATE_WAIT_S = 3
UPDATE_TITLE = f"{brand.DISPLAY} 更新"

_spawn = subprocess.Popen   # 命令行入口用；测试里换掉
_call = subprocess.call


# ---------------------------------------------------------------- 位置（测试里会换掉）


def _system() -> str:
    return sys.platform


def _home() -> Path:
    return Path.home()


def _interactive() -> bool:
    return sys.stdin is not None and sys.stdin.isatty()


def _windows_folder(csidl: int, fallback: Path) -> Path:
    """Windows 的"开始菜单\\程序""桌面"在哪（桌面可能被挪到别处，所以问系统，和安装脚本的取法一致）。"""
    try:
        import ctypes
        from ctypes import wintypes

        buf = ctypes.create_unicode_buffer(wintypes.MAX_PATH)
        found = ctypes.windll.shell32.SHGetFolderPathW(None, csidl, None, 0, buf) == 0  # type: ignore[attr-defined]
    except (ImportError, AttributeError, OSError):
        return fallback   # 不是 Windows 或接口不可用：用默认位置
    return Path(buf.value) if found and buf.value else fallback


def _programs_dir() -> Path:
    appdata = os.environ.get("APPDATA", "").strip()
    base = Path(appdata) if appdata else _home() / "AppData" / "Roaming"
    return _windows_folder(0x02, base / "Microsoft" / "Windows" / "Start Menu" / "Programs")   # CSIDL_PROGRAMS


def _desktop_dir() -> Path:
    return _windows_folder(0x10, _home() / "Desktop")   # CSIDL_DESKTOPDIRECTORY


def _uv() -> str:
    """uv 在哪：PATH 里有就用它；否则看 uv 官方安装脚本的默认位置 ~/.local/bin；都没有就写 uv。"""
    found = shutil.which("uv")
    if found:
        return found
    exe = "uv.exe" if _system() == "win32" else "uv"
    local = _home() / ".local" / "bin" / exe
    return str(local) if local.exists() else "uv"


# ---------------------------------------------------------------- 更新


def shortcut_paths() -> list[Path]:
    """这个平台上安装脚本会建的快捷方式。"""
    system = _system()
    if system == "win32":
        return [_programs_dir() / WIN_SHORTCUT, _desktop_dir() / WIN_SHORTCUT]
    if system == "darwin":
        return [_home() / "Applications" / MAC_APP]
    return []


def update_command() -> list[str]:
    """这个平台上重新运行安装脚本的命令。

    Windows 不让替换正在运行的程序文件（计划 4 Task 3 实测：程序开着时 uv 报"拒绝访问"），而 datum update 本身就在运行，
    所以用 start 开一个新窗口：先等几秒让这个 datum 退出，再运行安装脚本；窗口留着，装完能看到结果。start 会立刻返回。
    """
    if _system() == "win32":
        script = f"Start-Sleep -Seconds {UPDATE_WAIT_S}; irm {INSTALL_PS1} -TimeoutSec 60 | iex"
        return ["cmd", "/c", "start", UPDATE_TITLE, "powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-NoExit",
                "-Command", script]
    return ["sh", "-c", f"curl -fsSL --connect-timeout 20 {INSTALL_SH} | sh"]


def run_update(run: Callable = subprocess.call, say: Callable = print) -> int:
    cmd = update_command()
    say(f"更新 {brand.PRODUCT}：重新运行最新的安装脚本，由它覆盖安装。会话、案例、设置和钥匙串里的 key 都不受影响。")
    say(f"将要运行：{subprocess.list2cmdline(cmd) if _system() == 'win32' else ' '.join(cmd)}")
    try:
        code = run(cmd)
    except OSError as e:
        say(f"没能运行这条命令（{type(e).__name__}）。可以把上面这条命令复制到终端里自己运行。")
        return 1
    if code == 0 and _system() == "win32":
        say(f"更新会在一个新窗口里进行：等这个 {brand.COMMAND} 退出 {UPDATE_WAIT_S} 秒后开始，结果在那个窗口里看。"
            f"开着的 {brand.PRODUCT} 窗口请先关掉，不然 Windows 不让替换正在运行的程序。")
    if code != 0:
        say(f"更新没有成功（返回码 {code}），原因见上面安装脚本的输出。")
    return int(code)


# ---------------------------------------------------------------- 卸载


def _remove(path: Path) -> None:
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path)
    else:
        path.unlink()


def _remove_shortcuts(say: Callable) -> bool:
    ok = True
    for p in shortcut_paths():
        if not p.exists():
            say(f"  没有 {p}，跳过")
            continue
        say(f"  删除 {p}")
        try:
            _remove(p)
        except OSError as e:
            say(f"  没能删除（{type(e).__name__}），可以自己删掉它")
            ok = False
    return ok


def _remove_keys(say: Callable) -> bool:
    from cad_agent.llm.providers import load_providers

    removed = 0
    for p in load_providers():
        try:
            keyring.delete_password(SERVICE, p.id)
        except keyring.errors.PasswordDeleteError:
            continue   # 钥匙串里没有这一家的 key
        except keyring.errors.NoKeyringError:
            say("  这台电脑上没有可用的系统钥匙串，跳过")
            return True
        except Exception as e:  # noqa: BLE001 - 后端的原始异常可能带着 key，只报类型
            say(f"  没能删除「{p.name}」的 key（{type(e).__name__}），可以在系统的钥匙串或凭据管理器里删掉服务名为 {SERVICE} 的项")
            return False
        removed += 1
        say(f"  已删除「{p.name}」的 key")
    if removed == 0:
        say(f"  钥匙串里没有 {brand.PRODUCT} 存的 key，跳过")
    say(f"  环境变量里的 key 不是 {brand.PRODUCT} 设的，{brand.PRODUCT} 不动它们；不用了可以自己删掉。")
    return True


def _safe_to_delete(data: Path) -> str | None:
    """数据目录能不能删：不能删时返回原因。只删用户主目录里面、名字带 Datum 的目录。"""
    home = _home().resolve()
    target = data.resolve()
    if brand.HOME_DIR.lower() not in target.name.lower():
        return f"这个目录的名字里没有 {brand.HOME_DIR}，可能不是 {brand.PRODUCT} 自己建的"
    if target == home or target in home.parents:
        return "这是用户主目录或它的上级"
    if home not in target.parents:
        return "它不在用户主目录里面"
    return None


def _handle_data(delete_data: bool | None, ask: Callable[[str], str], say: Callable) -> bool:
    data = paths.app_home()
    if delete_data is None:
        if not _interactive():
            say(f"  没有在终端里运行，不问了，按保留处理：{data}")
            return True
        try:
            answer = ask(ASK_DELETE)
        except EOFError:
            answer = ""
        delete_data = answer.strip().lower() == "yes"
    if not delete_data:
        say(f"  保留数据目录：{data}")
        return True
    if not data.exists():
        say(f"  数据目录 {data} 不存在，跳过")
        return True
    why = _safe_to_delete(data)
    if why is not None:
        say(f"  不删 {data}：{why}。需要的话请自己确认后手动删除。")
        return False
    say(f"  删除数据目录：{data}")
    try:
        shutil.rmtree(data)
    except OSError as e:
        say(f"  没能删干净（{type(e).__name__}），剩下的可以自己删掉：{data}")
        return False
    return True


def _uninstall_command() -> tuple[list[str], dict]:
    uv = _uv()
    if _system() == "win32":
        script = f"Start-Sleep -Seconds {UNINSTALL_WAIT_S}; & '{uv}' tool uninstall {DIST_NAME}"
        cmd = ["powershell", "-NoProfile", "-WindowStyle", "Hidden", "-Command", script]
    else:
        cmd = ["sh", "-c", f"sleep {UNINSTALL_WAIT_S}; '{uv}' tool uninstall {DIST_NAME}"]
    if hasattr(subprocess, "DETACHED_PROCESS"):
        flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
        return cmd, {"creationflags": flags, "close_fds": True}
    return cmd, {"start_new_session": True, "close_fds": True}


def run_uninstall(*, delete_data: bool | None, ask: Callable[[str], str] = input, say: Callable = print,
                  run: Callable = subprocess.Popen) -> int:
    """返回 0 表示每一步都做了；有哪一步没做成（或拒绝删除）返回 1，原因已经打印。"""
    ok = True
    say("[1/4] 删除快捷方式")
    ok = _remove_shortcuts(say) and ok
    say(f"[2/4] 删除系统钥匙串里 {brand.PRODUCT} 存的 key（服务名 {SERVICE}）")
    ok = _remove_keys(say) and ok
    say("[3/4] 数据目录（会话、案例、设置、日志）")
    ok = _handle_data(delete_data, ask, say) and ok
    say(f"[4/4] 让 uv 卸载程序本身：uv tool uninstall {DIST_NAME}")
    if _system() == "win32":
        say(f"  开着的 {brand.PRODUCT} 窗口请先关掉：Windows 不让删除正在运行的程序文件。")
    cmd, kwargs = _uninstall_command()
    try:
        run(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, **kwargs)
    except OSError as e:
        say(f"  没能在后台开始卸载（{type(e).__name__}）。请关掉 {brand.PRODUCT} 后自己运行：uv tool uninstall {DIST_NAME}")
        return 1
    say(f"  已在后台开始，几秒后完成。之后可以运行 uv tool list 确认 {DIST_NAME} 不在列表里了。")
    return 0 if ok else 1


# ---------------------------------------------------------------- 命令行


def update_main(argv: list[str]) -> int:
    argparse.ArgumentParser(prog=f"{brand.COMMAND} update", description="更新到最新发布：重新运行安装脚本，覆盖安装。").parse_args(argv)
    return run_update(run=_call)


def uninstall_main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog=f"{brand.COMMAND} uninstall", description=f"卸载 {brand.PRODUCT}：删除快捷方式、钥匙串里的 key 和程序本身。")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--delete-data", action="store_true", help="同时删除会话、案例和设置")
    group.add_argument("--keep-data", action="store_true", help="保留会话、案例和设置")
    args = parser.parse_args(argv)
    choice = True if args.delete_data else False if args.keep_data else None
    return run_uninstall(delete_data=choice, run=_spawn)
