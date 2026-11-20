"""datum doctor：自检（第二版计划 4 Task 1，设计文档第 6.2 节）。

按顺序查十项，每项自己捕获异常：某一项查的过程中出错，这一项记 fail，其余项照常查。
不显示 key 的任何一位，只说它从哪里来；查模型服务只建立一次连接（5 秒超时），不发请求内容。
各项用到的探测函数（_temp_dir、_connect 等）放在 doctor_probes.py，按名字导入到这里，测试里可以换掉。
"""

from __future__ import annotations

import argparse
import json
import secrets
import sys
from dataclasses import asdict, dataclass
from typing import Callable, Literal
from urllib.parse import urlsplit

import keyring

from cad_agent import brand, paths
from cad_agent.doctor_probes import (  # noqa: F401 - 测试按 doctor 里的名字换掉它们
    BOX,
    _connect,
    _fallback_dir,
    _import_webview,
    _platform_info,
    _python_version,
    _sandbox_box,
    _sca_version,
    _system,
    _temp_dir,
    _try_write,
    _webview2_version,
)

Status = Literal["ok", "warn", "fail", "skip"]
Result = tuple[Status, str, str]   # (status, detail, advice)

SCA_VERSION = "2.2.7"
PYTHON_RANGE = ((3, 10), (3, 13))
MAC_MIN = 14
WIN_MIN = 10
PROBE_SERVICE = brand.DOCTOR_SERVICE
CONNECT_TIMEOUT_S = 5
WEBVIEW2_URL = "https://developer.microsoft.com/microsoft-edge/webview2/"
SYMBOLS = {"ok": "✓", "warn": "!", "fail": "✗", "skip": "—"}
SUPPORTED = "支持的系统：Windows 10/11（64 位）；Apple 芯片的 Mac，macOS 14 及以上。"


@dataclass(frozen=True)
class CheckItem:
    id: str
    name: str                                   # 中文名
    status: Literal["ok", "warn", "fail", "skip"]
    detail: str                                 # 一句中文：看到了什么
    advice: str = ""                            # 不是 ok 时：怎么办


# ---------------------------------------------------------------- 各项


def check_platform() -> Result:
    system, machine, release = _platform_info()
    try:
        major = int(release.split(".")[0])
    except ValueError:
        major = 0
    if system == "win32":
        is64 = machine.upper() in ("AMD64", "X86_64")
        if is64 and major >= WIN_MIN:
            return "ok", f"Windows {release}，64 位（{machine}）", ""
        return "fail", f"Windows {release}（{machine}）不在支持范围里", SUPPORTED
    if system == "darwin":
        if machine == "arm64" and major >= MAC_MIN:
            return "ok", f"macOS {release}，Apple 芯片（{machine}）", ""
        why = "Intel 芯片的 Mac 不支持（SCA 没有对应的安装包）" if machine != "arm64" else f"macOS {release} 太旧"
        return "fail", f"macOS {release}（{machine}）：{why}", SUPPORTED
    return "fail", f"{system}（{machine}）不在支持范围里", SUPPORTED


def check_python() -> Result:
    v = _python_version()
    text = ".".join(str(x) for x in v)
    low, high = PYTHON_RANGE
    if low <= tuple(v[:2]) <= high:
        return "ok", text, ""
    return "fail", f"Python {text} 不在 3.10 到 3.13 之间", "重新运行安装命令，它会用 uv 准备 Python 3.12。"


def check_sca() -> Result:
    v = _sca_version()
    if v is None:
        return "fail", "找不到 simplecadapi", f"重新运行安装命令（或 {brand.COMMAND} update）把它装回来。"
    if v != SCA_VERSION:
        return "fail", f"simplecadapi 是 {v}，{brand.PRODUCT} 需要 {SCA_VERSION}", f"重新运行安装命令（或 {brand.COMMAND} update），它会装上对的版本。"
    return "ok", f"simplecadapi {v}", ""


def check_sandbox() -> Result:
    try:
        size = _sandbox_box()
    except RuntimeError as e:
        return "fail", str(e), "先看上面的 SimpleCADAPI 和工作目录两项；都正常还是不行，就重新运行安装命令。"
    shown = " × ".join(f"{v:g}" for v in size)
    if all(abs(a - b) < 1e-3 for a, b in zip(size, BOX)):
        return "ok", f"建了一个方块，量出来 {shown} mm，正确", ""
    want = " × ".join(f"{v:g}" for v in BOX)
    return "fail", f"建了一个方块，量出来 {shown} mm，应该是 {want} mm", "重新运行安装命令；还是不对，请把这份自检结果发给我们。"


def check_workdir() -> Result:
    temp = _temp_dir()
    if paths.is_ascii_path(temp):
        return "ok", f"系统临时目录是纯英文路径：{temp}", ""
    fix = (f"新建文件夹 C:\\ProgramData\\{paths.APP_DIR}\\work 并确认自己能往里写；或者把环境变量 TEMP、TMP 改到一个纯英文路径"
           "（例如 C:\\Temp），重新打开终端再试。")
    try:
        fallback = _fallback_dir()
    except OSError as e:
        return "fail", f"系统临时目录 {temp} 带中文，备用的纯英文工作目录也建不了（{type(e).__name__}）", fix
    if not paths.is_ascii_path(fallback):
        return "fail", f"系统临时目录 {temp} 带中文，备用目录 {fallback} 也带中文", fix
    try:
        _try_write(fallback)
    except OSError as e:
        return "fail", f"系统临时目录 {temp} 带中文，备用目录 {fallback} 写不进去（{type(e).__name__}）", fix
    return ("warn", f"系统临时目录 {temp} 带中文，SCA 在这种路径下会出错；已自动改用纯英文的工作目录 {fallback}",
            "不需要处理：建模时的临时文件会放到这个目录里。")


def check_window() -> Result:
    browser = f"装好之前可以先用 {brand.COMMAND} --browser，在默认浏览器里打开同样的界面。"
    try:
        _import_webview()
    except Exception as e:  # noqa: BLE001 - 导入失败的原因很多（缺包、缺系统组件），都给同一条建议
        return "warn", f"窗口组件 pywebview 导入失败（{type(e).__name__}）", f"重新运行安装命令。{browser}"
    if _system() != "win32":
        return "ok", "窗口组件 pywebview 可以导入", ""
    version = _webview2_version()
    if version is None:
        return ("warn", "没有找到 Microsoft Edge WebView2 运行时，桌面窗口可能打不开",
                f"到 {WEBVIEW2_URL} 下载安装 WebView2 运行时（常青版）。{browser}")
    return "ok", f"pywebview 可以导入，WebView2 运行时 {version}", ""


def check_keyring() -> Result:
    advice = f"可以改用环境变量存 key（变量名见设置页，比如 DEEPSEEK_API_KEY），设好后重新打开 {brand.PRODUCT}。"
    value = secrets.token_hex(8)
    written = False
    try:
        keyring.set_password(PROBE_SERVICE, "probe", value)
        written = True
        back = keyring.get_password(PROBE_SERVICE, "probe")
        keyring.delete_password(PROBE_SERVICE, "probe")
        written = False
        gone = keyring.get_password(PROBE_SERVICE, "probe")
    except Exception as e:  # noqa: BLE001 - 后端各式各样；只报类型，不转述原文
        left = ""
        if written:
            try:
                keyring.delete_password(PROBE_SERVICE, "probe")
            except Exception:  # noqa: BLE001 - 收尾也失败：在结果里写明留下了测试项
                left = f"；测试项（{PROBE_SERVICE}）没能删掉，可以在系统的钥匙串或凭据管理器里手动删除"
        return "warn", f"系统钥匙串用不了（{type(e).__name__}）{left}", advice
    if back != value:
        return "warn", "往系统钥匙串写了一条测试项，读回来不一样", advice
    if gone is not None:
        return "warn", f"系统钥匙串里的测试项（{PROBE_SERVICE}）删不掉", advice
    return "ok", "能写、能读、能删（测试项已删除）", ""


def check_data() -> Result:
    home = paths.app_home()
    try:
        _try_write(home)
    except OSError as e:
        return ("fail", f"数据目录 {home} 建不了或写不进去（{type(e).__name__}）",
                f"确认自己能往这个位置写文件；或者用环境变量 {paths.HOME_ENV} 把数据目录改到别处。")
    return "ok", f"{home}", ""


def _settings_provider() -> tuple[str, str, str, str]:
    """(预设 id, 显示名, 接口地址, key 的环境变量名)；设置文件读不了时按默认设置。"""
    from cad_agent.config import ConfigError
    from cad_agent.llm.providers import get_provider
    from cad_agent.settings import Settings, load_settings

    try:
        s = load_settings()
    except ConfigError:
        s = Settings()
    p = get_provider(s.provider)
    return p.id, p.name, (s.base_url or p.base_url), p.api_key_env


def check_provider(offline: bool) -> Result:
    if offline:
        return "skip", "离线模式，没有连接模型服务", ""
    _, name, url, _ = _settings_provider()
    parts = urlsplit(url)
    if not parts.hostname:
        return "warn", f"「{name}」还没有填接口地址", f"打开 {brand.PRODUCT}，在设置里填上接口地址。"
    port = parts.port or (443 if parts.scheme == "https" else 80)
    try:
        _connect(parts.hostname, port, CONNECT_TIMEOUT_S)
    except OSError as e:
        return ("warn", f"连不上「{name}」的接口 {parts.hostname}:{port}（{type(e).__name__}）",
                "检查网络和代理；确认设置里的接口地址没写错。")
    return "ok", f"能连上「{name}」的接口 {parts.hostname}:{port}（只建立了连接，没有发请求）", ""


def check_key() -> Result:
    from cad_agent.keystore import key_source

    pid, name, _, env = _settings_provider()
    source = key_source(pid, env)
    if source == "env":
        return "ok", f"「{name}」的 key 来自环境变量 {env}", ""
    if source == "keyring":
        return "ok", f"「{name}」的 key 存在系统钥匙串里", ""
    return "warn", f"还没有「{name}」的 key", f"打开 {brand.PRODUCT}，在引导页或设置里填写；也可以设置环境变量 {env}。"


# ---------------------------------------------------------------- 汇总


def _checks(offline: bool) -> list[tuple[str, str, Callable[[], Result]]]:
    """(id, 中文名, 函数)。每次调用时现取模块里的函数，测试换掉的才会生效。"""
    return [
        ("platform", "系统和芯片", check_platform),
        ("python", "Python", check_python),
        ("sca", "SimpleCADAPI", check_sca),
        ("sandbox", "沙盒建模", check_sandbox),
        ("workdir", "工作目录", check_workdir),
        ("window", "桌面窗口", check_window),
        ("keyring", "系统钥匙串", check_keyring),
        ("data", "数据目录", check_data),
        ("provider", "模型服务", lambda: check_provider(offline)),
        ("key", "密钥", check_key),
    ]


def run_doctor(*, offline: bool = False) -> list[CheckItem]:
    items: list[CheckItem] = []
    for cid, name, fn in _checks(offline):
        try:
            status, detail, advice = fn()
        except Exception as e:  # noqa: BLE001 - 一项出错不影响其余各项；原因写进这一项
            status, detail = "fail", f"查的时候出错了：{type(e).__name__}，{' '.join(str(e).split())[:100]}"
            advice = f"这一项没查完。可以重新运行 {brand.COMMAND} doctor；还是这样，请把这份结果发给我们。"
        items.append(CheckItem(cid, name, status, detail, advice if status != "ok" else ""))
    return items


def render_doctor(items: list[CheckItem]) -> str:
    lines: list[str] = []
    for item in items:
        lines.append(f"{SYMBOLS[item.status]} {item.name}：{item.detail}")
        if item.status != "ok" and item.advice:
            lines.append(f"    {item.advice}")
    fails = sum(i.status == "fail" for i in items)
    warns = sum(i.status == "warn" for i in items)
    if fails:
        lines.append(f"有 {fails} 项不能用")
    elif warns:
        lines.append(f"有 {warns} 项需要注意")
    else:
        lines.append("全部正常")
    return "\n".join(lines)


def doctor_exit_code(items: list[CheckItem]) -> int:
    return 1 if any(i.status == "fail" for i in items) else 0


def doctor_main(argv: list[str]) -> int:
    """datum doctor [--offline] [--json]"""
    parser = argparse.ArgumentParser(prog=f"{brand.COMMAND} doctor", description=f"自检：看 {brand.PRODUCT} 在这台电脑上能不能正常用。不显示 key。")
    parser.add_argument("--offline", action="store_true", help="不连接模型服务")
    parser.add_argument("--json", action="store_true", help="输出 JSON")
    args = parser.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")   # 输出被重定向到不支持 ✓ 的编码时不至于崩
    items = run_doctor(offline=args.offline)
    if args.json:
        print(json.dumps([asdict(i) for i in items], ensure_ascii=False, indent=2))
    else:
        print(render_doctor(items))
    return doctor_exit_code(items)
