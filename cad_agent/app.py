"""caliper 命令（第二版计划 3 Task 13）：起本机服务，开 pywebview 窗口加载页面；窗口开不了就改用浏览器。

    caliper                  打开桌面窗口
    caliper --browser        改用默认浏览器打开，终端里按 Ctrl+C 退出
    caliper --cli [--config 文件]   终端对话模式
    caliper --demo-script 剧本.json  开发用：模型换成假模型剧本，沙盒是真的，不需要密钥

没有密钥也能启动（界面会进引导页）；智能体第一次要调用模型时才需要密钥，没有就让这一轮以 failed 结束，提示去设置里填。
密钥只从环境变量或系统钥匙串取，不打印、不写日志。
"""

from __future__ import annotations

import argparse
import logging
import os
import threading
import time
import webbrowser
from pathlib import Path

from cad_agent import cli, paths
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
TITLE = "卡尺 Caliper"
WINDOW_SIZE = (1360, 860)
MIN_SIZE = (1100, 700)
NO_KEY_TEXT = '还没有可用的密钥。到右上角的"设置"里填好密钥，再发一次。'
WINDOW_FAIL = "桌面窗口打不开（{reason}），改用浏览器打开。Windows 上通常是缺少 WebView2 运行时，可以运行 caliper doctor 查看。"
logger = logging.getLogger("caliper")


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
        if script is not None:
            llm: LLM = ScriptedLLM(load_script(script))
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
    print(f"卡尺已经在浏览器里打开：{url}\n关掉终端或按 Ctrl+C 退出。")
    open_browser(url)
    wait_for_exit()


def _setup_logging() -> None:
    root = logging.getLogger("caliper")
    if root.handlers:
        return
    try:
        paths.logs_dir().mkdir(parents=True, exist_ok=True)
        handler = logging.FileHandler(paths.logs_dir() / "caliper.log", encoding="utf-8")
    except OSError:
        return   # 日志写不了不影响使用
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    root.addHandler(handler)
    root.setLevel(logging.INFO)


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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="caliper", description="卡尺 Caliper：用平常话做 CAD 零件，每一步都由程序实测。",
                                     epilog="--demo-script <剧本文件>：开发用，模型换成假模型剧本，不需要密钥。")
    parser.add_argument("--browser", action="store_true", help="不开桌面窗口，改用默认浏览器打开")
    parser.add_argument("--cli", action="store_true", help="终端对话模式")
    parser.add_argument("--config", metavar="文件", help="终端对话模式用的配置文件；不给就用设置和钥匙串里的密钥")
    parser.add_argument("--demo-script", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    _setup_logging()
    if args.cli:
        return _run_cli(args.config)
    try:
        settings = load_settings()
    except ConfigError as e:
        print(f"{e}\n先用默认设置启动，可以在设置页里改。")
        settings = Settings()
    hub = build_hub(settings, script=args.demo_script)
    server, token = make_desk_server(hub, make_settings_routes(hub, make_llm_for=make_llm_for))
    threading.Thread(target=server.serve_forever, daemon=True, name="caliper-server").start()
    url = f"http://127.0.0.1:{server.server_address[1]}/?t={token}"
    try:
        if args.browser or not _window(url):
            _browser(url)
    finally:
        server.shutdown()
        server.server_close()
        hub.close()
    return 0


def gui_main() -> None:
    """caliper-app：不带黑窗口的入口。"""
    main([])
