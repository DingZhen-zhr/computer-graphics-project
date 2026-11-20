"""一行安装脚本 install.ps1 / install.sh 和图标（第二版计划 4 Task 3）。

脚本都只在演示模式（CALIPER_DRY_RUN=1）下运行，或者在第一步就因为平台不支持而退出；
PATH 最前面放一个假的 uv，它一旦被调用就留下记号，用来确认没有真的调用 uv。
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from PIL import Image

from cad_agent import __version__
from cad_agent.maintenance import REPO

ROOT = Path(__file__).resolve().parent.parent
PS1 = ROOT / "install.ps1"
SH = ROOT / "install.sh"
STATIC = ROOT / "cad_agent" / "desk" / "static"
UV_INSTALLERS = {"https://astral.sh/uv/install.ps1", "https://astral.sh/uv/install.sh"}
MIRRORS = {"https://pypi.tuna.tsinghua.edu.cn/simple", "https://registry.npmmirror.com/-/binary/python-build-standalone"}
URL = re.compile(r"https?://[^\s'\"`)<>]+")
POWERSHELL = shutil.which("powershell")
SH_EXE = shutil.which("sh")
windows_only = pytest.mark.skipif(sys.platform != "win32" or POWERSHELL is None, reason="只在 Windows 上跑")
needs_sh = pytest.mark.skipif(SH_EXE is None, reason="这台机器上没有 sh")
# PowerShell 往管道里写的是控制台代码页（中文 Windows 是 936，英文是 437），不是 UTF-8；脚本的步骤标记和命令都是英文，读得出来
PS_ENCODING = "oem" if sys.platform == "win32" else "utf-8"


def _text(p: Path) -> str:
    return p.read_text(encoding="utf-8-sig")


def _env(tmp_path: Path, **extra: str) -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if not k.startswith("CALIPER_")}
    env.update({"PYTHONUTF8": "1", "HOME": str(tmp_path / "home"), "USERPROFILE": str(tmp_path / "home"), **extra})
    (tmp_path / "home").mkdir(exist_ok=True)
    return env


def _fake_bin(tmp_path: Path) -> tuple[Path, Path]:
    """假的 uv（被调用就写下记号文件）。返回 (目录, 记号文件)。"""
    bin_dir = tmp_path / "fakebin"
    bin_dir.mkdir(exist_ok=True)
    marker = tmp_path / "uv-was-called"
    (bin_dir / "uv").write_text(f'#!/bin/sh\necho called > "{marker.as_posix()}"\n', encoding="utf-8", newline="\n")
    (bin_dir / "uv.cmd").write_text(f'@echo called > "{marker}"\r\n', encoding="utf-8")
    os.chmod(bin_dir / "uv", 0o755)
    return bin_dir, marker


def _fake(bin_dir: Path, name: str, output: str) -> None:
    (bin_dir / name).write_text(f"#!/bin/sh\necho {output}\n", encoding="utf-8", newline="\n")
    os.chmod(bin_dir / name, 0o755)


def _fake_uname(bin_dir: Path, machine: str, system: str) -> None:
    """假的 uname：-m 打印 machine，其他打印 system。必须加可执行权限：Mac 上 PATH 里没有可执行权限的文件会被跳过，
    用的就成了真的 uname（持续集成第三次运行实测；Windows 的 Git sh 不看这个权限，本机测不出来）。"""
    (bin_dir / "uname").write_text(f'#!/bin/sh\nif [ "$1" = "-m" ]; then echo {machine}; else echo {system}; fi\n',
                                   encoding="utf-8", newline="\n")
    os.chmod(bin_dir / "uname", 0o755)


def _steps_in_order(out: str) -> None:
    positions = [out.find(f"[{n}/5]") for n in range(1, 6)]
    assert all(p >= 0 for p in positions), out
    assert positions == sorted(positions), out


# ---------------------------------------------------------------- 语法


@windows_only
def test_ps1_parses():
    # 按 UTF-8 读进来再交给解析器（和用户的 irm | iex 一样；5.1 的 ParseFile 会按系统编码读没有 BOM 的文件）
    script = ("$errs = $null; $tokens = $null; "
              f"$text = Get-Content -Raw -Encoding UTF8 -LiteralPath '{PS1}'; "
              "[void][System.Management.Automation.Language.Parser]::ParseInput($text, [ref]$tokens, [ref]$errs); "
              "if ($errs.Count -gt 0) { $errs | ForEach-Object { $_.Message }; exit 1 } else { 'parsed' }")
    r = subprocess.run([POWERSHELL, "-NoProfile", "-Command", script], capture_output=True, text=True, encoding="utf-8", errors="replace")
    assert r.returncode == 0 and "parsed" in r.stdout, r.stdout + r.stderr


@needs_sh
def test_sh_parses():
    r = subprocess.run([SH_EXE, "-n", str(SH)], capture_output=True, text=True, encoding="utf-8", errors="replace")
    assert r.returncode == 0, r.stderr


def test_ps1_is_utf8_without_bom_and_sh_has_lf_endings():
    """irm | iex 会把 BOM 当成第一个命令名报错，所以 install.ps1 是不带 BOM 的 UTF-8（偏离 D17）；sh 脚本只能是 LF 换行。"""
    raw_ps1 = PS1.read_bytes()
    assert not raw_ps1.startswith(b"\xef\xbb\xbf")
    raw_ps1.decode("utf-8")
    raw = SH.read_bytes()
    assert b"\r\n" not in raw and raw.startswith(b"#!/bin/sh")


# ---------------------------------------------------------------- 演示模式


@windows_only
def test_ps1_dry_run_prints_five_steps(tmp_path):
    bin_dir, marker = _fake_bin(tmp_path)
    env = _env(tmp_path, CALIPER_DRY_RUN="1", PATH=f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    command = f"Get-Content -Raw -Encoding UTF8 -LiteralPath '{PS1}' | Invoke-Expression; exit $LASTEXITCODE"
    r = subprocess.run([POWERSHELL, "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command],
                       capture_output=True, text=True, encoding=PS_ENCODING, errors="replace", env=env, timeout=120)
    out = r.stdout + r.stderr
    assert r.returncode == 0, out
    _steps_in_order(out)
    assert not marker.exists(), "演示模式不该真的调用 uv"
    assert "uv tool install --python 3.12 --force" in out
    assert not (tmp_path / "home" / "Desktop").exists() or not list((tmp_path / "home" / "Desktop").iterdir())


@windows_only
def test_ps1_dry_run_through_iex_keeps_the_shell(tmp_path):
    """用户的用法是 irm … | iex：脚本是在用户自己的 PowerShell 里执行的，出错或结束时不能把这个窗口关掉。"""
    bin_dir, marker = _fake_bin(tmp_path)
    env = _env(tmp_path, CALIPER_DRY_RUN="1", PATH=f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    command = f"Get-Content -Raw -Encoding UTF8 '{PS1}' | Invoke-Expression; 'still-here'"
    r = subprocess.run([POWERSHELL, "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command],
                       capture_output=True, text=True, encoding=PS_ENCODING, errors="replace", env=env, timeout=120)
    out = r.stdout + r.stderr
    _steps_in_order(out)
    assert "still-here" in out and not marker.exists()
    assert r.stderr.strip() == "", r.stderr   # 开头没有"不认识的命令"之类的红字


@needs_sh
def test_sh_dry_run_prints_five_steps(tmp_path):
    bin_dir, marker = _fake_bin(tmp_path)
    _fake_uname(bin_dir, "arm64", "Darwin")
    _fake(bin_dir, "sw_vers", "14.5")
    env = _env(tmp_path, CALIPER_DRY_RUN="1", PATH=f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    r = subprocess.run([SH_EXE, str(SH)], capture_output=True, text=True, encoding="utf-8", errors="replace", env=env, timeout=120)
    out = r.stdout + r.stderr
    assert r.returncode == 0, out
    _steps_in_order(out)
    assert not marker.exists(), "演示模式不该真的调用 uv"
    assert "uv tool install --python 3.12 --force" in out
    assert not (tmp_path / "home" / "Applications").exists()


@needs_sh
@pytest.mark.parametrize("arch, version, reason", [("x86_64", "14.5", "Apple 芯片"), ("arm64", "13.6", "14")])
def test_install_sh_platform_gate(tmp_path, arch, version, reason):
    bin_dir, marker = _fake_bin(tmp_path)
    _fake_uname(bin_dir, arch, "Darwin")
    _fake(bin_dir, "sw_vers", version)
    env = _env(tmp_path, PATH=f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    r = subprocess.run([SH_EXE, str(SH)], capture_output=True, text=True, encoding="utf-8", errors="replace", env=env, timeout=60)
    out = r.stdout + r.stderr
    assert r.returncode == 2, out
    assert "[1/5]" in out and "[2/5]" not in out
    assert reason in out and "macOS 14" in out
    assert not marker.exists()
    assert not (tmp_path / "home" / "Applications").exists() and not (tmp_path / "home" / ".local").exists()


@needs_sh
def test_install_sh_refuses_linux(tmp_path):
    bin_dir, marker = _fake_bin(tmp_path)
    _fake_uname(bin_dir, "x86_64", "Linux")
    env = _env(tmp_path, PATH=f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    r = subprocess.run([SH_EXE, str(SH)], capture_output=True, text=True, encoding="utf-8", errors="replace", env=env, timeout=60)
    assert r.returncode == 2 and not marker.exists() and "[2/5]" not in r.stdout


# ---------------------------------------------------------------- 内容


def test_default_source_is_the_release_tag():
    for p in (PS1, SH):
        m = re.search(r"(git\+https://github\.com/[^\s'\"]+)", _text(p))
        assert m, p.name
        assert m.group(1) == f"git+https://github.com/{REPO}@v{__version__}", p.name
        assert m.group(1).endswith(f"@v{__version__}")


def test_only_one_external_script_is_executed():
    for p, installer in ((PS1, "https://astral.sh/uv/install.ps1"), (SH, "https://astral.sh/uv/install.sh")):
        urls = {u.rstrip(".,;/") for u in URL.findall(_text(p))}
        ours = {u for u in urls if u.startswith((f"https://github.com/{REPO}", f"https://raw.githubusercontent.com/{REPO}"))}
        others = urls - ours - {m.rstrip("/") for m in MIRRORS}
        assert others == {installer}, (p.name, sorted(others))
        assert not (urls & (UV_INSTALLERS - {installer}))


def test_install_script_mentions_mirror_and_offline_path():
    ps1, sh = _text(PS1), _text(SH)
    for text in (ps1, sh):
        assert "CALIPER_MIRROR" in text and "装不上怎么办" in text
        assert "UV_HTTP_CONNECT_TIMEOUT" in text   # uv 自己下载时也有连接超时
    # 每一个下载命令都带超时
    downloads = [line for line in ps1.splitlines() if re.search(r"\b(Invoke-RestMethod|Invoke-WebRequest|irm|iwr)\b", line)
                 and not line.strip().startswith("#")]
    assert downloads and all("-TimeoutSec" in line for line in downloads), downloads
    curls = [line for line in sh.splitlines() if re.search(r"\b(curl|wget)\b", line) and not line.strip().startswith("#")]
    assert curls and all("--connect-timeout" in line for line in curls), curls


def test_scripts_have_no_admin_or_system_changes():
    ps1, sh = _text(PS1), _text(SH)
    for word in ("RunAs", "HKLM", "Set-ExecutionPolicy"):
        assert word not in ps1, word
    assert "sudo" not in sh


def test_env_options_are_documented_in_both_scripts():
    for p in (PS1, SH):
        text = _text(p)
        for name in ("CALIPER_SOURCE", "CALIPER_MIRROR", "CALIPER_NO_SHORTCUT", "CALIPER_DRY_RUN"):
            assert name in text, (p.name, name)


def test_icons_exist_and_are_valid():
    with Image.open(STATIC / "icon.png") as im:
        assert im.size == (256, 256)
    with Image.open(STATIC / "icon.ico") as im:
        assert im.format == "ICO"
        assert {(16, 16), (32, 32), (48, 48), (256, 256)} <= set(im.info.get("sizes", set()))
    with Image.open(STATIC / "icon.icns") as im:
        assert im.format == "ICNS"


def _glob_regex(pattern: str) -> re.Pattern:
    """setuptools package-data 的写法：** 跨目录，* 不跨目录。"""
    out = ""
    i = 0
    while i < len(pattern):
        if pattern.startswith("**/", i):
            out, i = out + "(?:.*/)?", i + 3
        elif pattern.startswith("**", i):
            out, i = out + ".*", i + 2
        elif pattern[i] == "*":
            out, i = out + "[^/]*", i + 1
        else:
            out, i = out + re.escape(pattern[i]), i + 1
    return re.compile(out + r"\Z")


def test_package_ships_everything_the_page_loads():
    """装好的程序里要有页面用到的全部静态文件，包括 three.js（只从源码运行时看不出来缺了它，Task 3 实测装上后页面是空的）。"""
    import tomllib

    from cad_agent.desk import server

    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    patterns = [_glob_regex(p) for p in data["tool"]["setuptools"]["package-data"]["cad_agent"]]
    pkg = ROOT / "cad_agent"
    needed = [p for p in Path(server.VENDOR_DIR).rglob("*") if p.is_file()] + \
             [p for p in Path(server.STATIC_DIR).rglob("*") if p.is_file() and "tests" not in p.relative_to(server.STATIC_DIR).parts]
    assert any(p.name == "three.module.js" for p in needed)
    missing = [p.relative_to(pkg).as_posix() for p in needed if not any(r.match(p.relative_to(pkg).as_posix()) for r in patterns)]
    assert missing == [], missing


def test_ps1_stops_when_caliper_is_running():
    """Windows 上卡尺开着时 uv 换不掉正在运行的文件（Task 3 实测"拒绝访问"）：安装前先查，查到就请用户关掉，不给网络方面的提示。"""
    text = _text(PS1)
    check = text.find("Windows 不让替换正在运行的程序文件")
    install = text.find("$installArgs = @('tool', 'install'")
    assert 0 <= check < install
    block = text[check:install]
    assert "Get-Process" in block and "caliper-cad" in block and "关掉" in block and "-WithHelp" not in block


def test_sh_variables_are_braced():
    """Mac 自带的 /bin/sh（bash 3.2）会把紧跟在变量名后面的中文字节当成变量名的一部分（持续集成实测：
    "$MAC_VERSION，" 报 "MAC_VERSION?: unbound variable"），所以 install.sh 里的变量一律写成 ${名字}。"""
    bare = [line.strip() for line in _text(SH).splitlines()
            if not line.lstrip().startswith("#") and re.search(r"\$[A-Za-z_][A-Za-z0-9_]*", line.replace("\\$", ""))]
    assert bare == [], bare[:5]


# 快捷方式函数在 install.ps1 里夹在这两行注释之间，测试把它单独取出来运行
SHORTCUT_BEGIN, SHORTCUT_END = "# >>> 建快捷方式", "# <<< 建快捷方式"


@windows_only
def test_ps1_shortcut_handles_characters_outside_the_code_page(tmp_path):
    """持续集成第三次运行：英文 Windows 上 WScript.Shell 存不了"卡尺 Caliper.lnk"（文件名被换成"?? Caliper.lnk"，安装停在第 4 步）。
    本机复现：系统编码表示不了的字（这里用泰文）不论在文件名、目标路径还是说明里，WScript.Shell 都会出错。
    所以安装脚本改用 Unicode 的 IShellLinkW 建快捷方式；这里名字、目标、工作目录、说明、图标全用泰文，建好后用 Shell.Application 读回来核对。"""
    text = _text(PS1)
    begin, end = text.find(SHORTCUT_BEGIN), text.find(SHORTCUT_END)
    assert 0 <= begin < end, "install.ps1 里找不到建快捷方式的函数"
    function = text[begin:end]
    assert "-ComObject WScript.Shell" not in text   # 注释里会提到它，但代码里不能再用

    thai = "ทดสอบ"
    target_dir = tmp_path / thai
    target_dir.mkdir()
    target = target_dir / "app.exe"
    target.write_bytes(b"x")
    icon = target_dir / "icon.ico"
    shutil.copyfile(STATIC / "icon.ico", icon)
    lnk = tmp_path / f"{thai} Caliper.lnk"
    result = tmp_path / "result.txt"
    script = tmp_path / "probe.ps1"
    script.write_text(
        function
        + f"\nNew-CaliperShortcut -Path '{lnk}' -Target '{target}' -WorkingDirectory '{target_dir}' -Description '说明 {thai}' -Icon '{icon}'\n"
        + f"$link = (New-Object -ComObject Shell.Application).NameSpace('{tmp_path}').ParseName('{lnk.name}').GetLink\n"
        + "$icon = ''; $null = $link.GetIconLocation([ref]$icon)\n"
        + f"Set-Content -LiteralPath '{result}' -Encoding UTF8 -Value @($link.Path, $link.WorkingDirectory, $link.Description, $icon)\n",
        encoding="utf-8-sig")   # 带 BOM，Windows PowerShell 5.1 才会按 UTF-8 读 -File 的脚本
    r = subprocess.run([POWERSHELL, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script)],
                       capture_output=True, text=True, encoding=PS_ENCODING, errors="replace", timeout=120)
    assert r.returncode == 0 and r.stderr.strip() == "", r.stdout + r.stderr
    assert lnk.is_file()
    assert result.read_text(encoding="utf-8-sig").splitlines() == [str(target), str(target_dir), f"说明 {thai}", str(icon)]
