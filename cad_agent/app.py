"""datum 命令（第二版计划 3 Task 13；3.0 改名）：起本机服务，开 pywebview 窗口加载页面；窗口开不了就改用浏览器。

    datum                    打开桌面窗口
    datum --browser          改用默认浏览器打开，终端里按 Ctrl+C 退出
    datum --cli [--config 文件]   终端对话模式
    datum --demo-script 剧本.json  开发用：模型换成假模型剧本，沙盒是真的，不需要密钥
    datum doctor [--offline] [--json]   自检
    datum update             更新到最新发布
    datum uninstall [--delete-data | --keep-data]   卸载
    datum --version          显示版本号
    datum --smoke            持续集成用（不在帮助里）：不开窗口，起服务，请求一次首页和 /api/boot

没有密钥也能启动（界面会进引导页）；智能体第一次要调用模型时才需要密钥，没有就让这一轮以 failed 结束，提示去设置里填。
密钥只从环境变量或系统钥匙串取，不打印、不写日志。
"""

from __future__ import annotations

import argparse
import http.client
import logging
import os
import sys
import threading
import time
import webbrowser
from pathlib import Path

from cad_agent import __version__, brand, cli, doctor, maintenance, migrate, paths
from cad_agent.agent.loop import Agent
from cad_agent.brief import Brief
from cad_agent.cases import load_cases
from cad_agent.config import Config, ConfigError
from cad_agent.desk.hub import Hub
from cad_agent.desk.server import make_desk_server
from cad_agent.desk.settings_api import make_settings_routes
from cad_agent.keystore import get_key
from cad_agent.llm.client import LLM, LLMError
from cad_agent.llm.factory import make_llm, secret_env_names
from cad_agent.llm.fake import ScriptedLLM, load_script
from cad_agent.llm.providers import get_provider
from cad_agent.notebook import FeatureList
from cad_agent.session import Session
from cad_agent.settings import Settings, load_settings, to_config
from cad_agent.tools import ToolBox, Workspace

DEMO_DIR = Path(__file__).parent / "desk" / "demo_data"
TITLE = brand.DISPLAY
WINDOW_SIZE = (1360, 860)
MIN_SIZE = (1100, 700)
NO_KEY_TEXT = '还没有可用的密钥。到右上角的"设置"里填好密钥，再发一次。'
WINDOW_FAIL = "桌面窗口打不开（{reason}），改用浏览器打开。Windows 上通常是缺少 WebView2 运行时，可以运行 " + brand.COMMAND + " doctor 查看。"
logger = logging.getLogger(brand.COMMAND)


class _FailingLLM:
    """还不能调用模型时（没有密钥、设置不完整）顶上的假客户端：一调用就失败，给出原因。"""

    def __init__(self, reason: str) -> None:
        self.reason = reason

    def chat(self, messages: list[dict], tools: list[dict], **_: object) -> object:
        raise LLMError(self.reason)


def _key_for(provider_id: str) -> str | None:
    return get_key(provider_id, get_provider(provider_id).api_key_env)


def make_llm_for(settings: Settings, phase: str) -> LLM:
    """按设置造某个阶段的模型客户端（设置页的测试连接、测试识图用）。没有密钥时抛 ConfigError。"""
    config = to_config(settings)
    provider = settings.review_provider if phase == "review" and settings.review_provider else settings.provider
    key = _key_for(provider)
    if not key:
        raise ConfigError(NO_KEY_TEXT)
    return make_llm(config, phase, key)   # type: ignore[arg-type]


def _review_llm(config: Config, settings: Settings) -> LLM | None:
    if not (config.gates.staged and config.gates.visual_review and config.vision):
        return None
    try:
        return make_llm_for(settings, "review")
    except ConfigError:
        return None   # 审查用的服务没有密钥：不审查（交付卡片上会写没做的原因）


def build_hub(settings: Settings, *, script: Path | None = None) -> Hub:
    def make_agent(session: Session) -> Agent:
        try:
            config = to_config(settings)
            problem = None
        except ConfigError as e:
            config, problem = to_config(Settings()), str(e)
        review = None
        modeling = None
        if script is not None:   # 剧本接着这个会话已经用掉的回复往下走（关掉窗口再打开时不从头再来）
            used = sum(1 for row in session.read_log() if row.get("kind") == "assistant")
            llm: LLM = ScriptedLLM(load_script(script)[used:])
        elif problem is not None:
            llm = _FailingLLM(problem)
        else:
            key = _key_for(settings.provider)
            if key:
                llm, modeling = make_llm(config, "clarify", key), make_llm(config, "modeling", key)
                review = _review_llm(config, settings)
            else:
                llm = _FailingLLM(NO_KEY_TEXT)
        toolbox = ToolBox(Workspace(Brief(), FeatureList(), []), timeout_s=config.run_timeout_s,
                          secret_names=secret_env_names(config), gates=config.gates)
        cases, problems = load_cases(config.cases_dir)
        agent = Agent(llm, toolbox, session, config, modeling_llm=modeling, cases=cases, review_llm=review)
        agent.case_problems = problems
        _, info = cli._banner(config, session)
        session.log("startup", **cli.startup_info(agent, info))   # 作业要求记录软件和模型版本
        return agent

    return Hub(make_agent=make_agent, sessions_dir=paths.sessions_dir(), cases_dir=paths.cases_dir(), demo_dir=DEMO_DIR)


# ---------------------------------------------------------------- 打开页面（测试里会换掉这两个）


def open_browser(url: str) -> None:
    webbrowser.open(url)


def wait_for_exit() -> None:
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n已退出。")


def _window(url: str) -> bool:
    """开 pywebview 窗口，关掉窗口才返回。导入或启动失败返回 False（已经打印了说明）。"""
    try:
        import webview

        webview.create_window(TITLE, url, width=WINDOW_SIZE[0], height=WINDOW_SIZE[1], min_size=MIN_SIZE)
        webview.start()
        return True
    except Exception as e:  # noqa: BLE001 - 缺 WebView2 等各种原因都改用浏览器；原因打印出来
        print(WINDOW_FAIL.format(reason=" ".join(str(e).split())[:80] or type(e).__name__))
        logger.warning("桌面窗口打不开：%s", type(e).__name__)
        return False


def _browser(url: str) -> None:
    print(f"{brand.PRODUCT} 已经在浏览器里打开：{url}\n关掉终端或按 Ctrl+C 退出。")
    open_browser(url)
    wait_for_exit()


def _setup_logging() -> None:
    root = logging.getLogger(brand.COMMAND)
    if root.handlers:
        return
    try:
        paths.logs_dir().mkdir(parents=True, exist_ok=True)
        handler = logging.FileHandler(paths.logs_dir() / f"{brand.COMMAND}.log", encoding="utf-8")
    except OSError:
        return   # 日志写不了不影响使用
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    root.addHandler(handler)
    root.setLevel(logging.INFO)


def _migrate_then_log() -> None:
    """从第二版升级时复制旧数据目录（见 migrate.py），再开程序日志，把结果记进去。
    顺序不能反：开日志会建出新数据目录，迁移就会以为"新目录已存在"而跳过。复制失败不打断启动。"""
    result = migrate.migrate_home()
    _setup_logging()
    failed = result.reason.startswith("复制失败")
    logger.log(logging.WARNING if failed else logging.INFO, "数据目录迁移：%s", result.reason)


def _run_cli(config_file: str | None) -> int:
    if config_file:
        return cli.main(["--config", config_file])
    try:
        settings = load_settings()
        config = to_config(settings)
    except ConfigError as e:
        print(e)
        return 1
    key = _key_for(settings.provider)
    if key:
        os.environ[config.api_key_env] = key   # 只在这个进程里；沙盒子进程会把它去掉
    return cli.main([], config=config)


SUBCOMMANDS = {"doctor": doctor.doctor_main, "update": maintenance.update_main, "uninstall": maintenance.uninstall_main}


def _start(settings: Settings, script: Path | None) -> tuple[Hub, object, str]:
    hub = build_hub(settings, script=script)
    server, token = make_desk_server(hub, make_settings_routes(hub, make_llm_for=make_llm_for))
    threading.Thread(target=server.serve_forever, daemon=True, name=f"{brand.COMMAND}-server").start()
    return hub, server, token


def _smoke(port: int, token: str) -> int:
    """自己请求一次首页和 /api/boot，都是 200 才算通过。令牌不打印。"""
    for path, label, headers in ((f"/?t={token}", "/", {}), ("/api/boot", "/api/boot", {brand.TOKEN_HEADER: token})):
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=60)
        try:
            conn.request("GET", path, headers=headers)
            resp = conn.getresponse()
            resp.read()
        except OSError as e:
            print(f"smoke 失败：请求 {label} 时出错（{type(e).__name__}）")
            return 1
        finally:
            conn.close()
        if resp.status != 200:
            print(f"smoke 失败：{label} 返回 {resp.status}")
            return 1
    print("smoke ok")
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] in SUBCOMMANDS:
        if argv[0] == "doctor":   # 安装脚本装完就运行自检，自检会建出数据目录：迁移要在它前面
            _migrate_then_log()
        return SUBCOMMANDS[argv[0]](argv[1:])
    cmd = brand.COMMAND
    parser = argparse.ArgumentParser(prog=cmd, description=f"{brand.DISPLAY}：用平常话做 CAD 零件，每一步都由程序实测。"
                                     f"另有子命令：{cmd} doctor（自检）、{cmd} update（更新）、{cmd} uninstall（卸载）。",
                                     epilog="--demo-script <剧本文件>：开发用，模型换成假模型剧本，不需要密钥。")
    parser.add_argument("--version", action="version", version=f"{brand.DISPLAY} {__version__}", help="显示版本号")
    parser.add_argument("--browser", action="store_true", help="不开桌面窗口，改用默认浏览器打开")
    parser.add_argument("--cli", action="store_true", help="终端对话模式")
    parser.add_argument("--config", metavar="文件", help="终端对话模式用的配置文件；不给就用设置和钥匙串里的密钥")
    parser.add_argument("--demo-script", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--smoke", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    _migrate_then_log()
    if args.cli:
        return _run_cli(args.config)
    try:
        settings = load_settings()
    except ConfigError as e:
        print(f"{e}\n先用默认设置启动，可以在设置页里改。")
        settings = Settings()
    hub, server, token = _start(settings, args.demo_script)
    url = f"http://127.0.0.1:{server.server_address[1]}/?t={token}"
    try:
        if args.smoke:
            return _smoke(server.server_address[1], token)
        if args.browser or not _window(url):
            _browser(url)
    finally:
        server.shutdown()
        server.server_close()
        hub.close()
    return 0


def gui_main() -> None:
    """datum-app：不带黑窗口的入口。"""
    main([])
