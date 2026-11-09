"""启动网页界面。

    python -m cad_agent.web --config config.toml [--port 8765] [--no-browser]
    python -m cad_agent.web --replay <会话目录> [--port 8765] [--no-browser]
    python -m cad_agent.web --config config.toml --public [--budget 5]

第二种是只读回放：不需要 API key，不花钱，用来预览界面，演示时断网也能当后备。
第三种给公网测试用（配合 start_public.bat 的临时隧道）：访问密码从环境变量 CAD_WEB_PASSWORD 读，
所有访问者共用一个会话；累计花费到 --budget（元）后不再接新消息。
"""

from __future__ import annotations

import argparse
import os
import sys
import webbrowser
from http.server import ThreadingHTTPServer
from pathlib import Path
from typing import Callable

from cad_agent import cli
from cad_agent.agent.loop import Agent
from cad_agent.brief import Brief
from cad_agent.config import Config, ConfigError, load_config
from cad_agent.llm.factory import make_llm
from cad_agent.notebook import FeatureList
from cad_agent.tools import ToolBox, Workspace
from cad_agent.web.app import LiveApp, LiveSession, ReplayApp
from cad_agent.web.server import make_server

PORT_TRIES = 10  # 端口被占用时，往后最多再试这么多个
PASSWORD_ENV = "CAD_WEB_PASSWORD"
MIN_PASSWORD = 6


def build_live_agent(config: Config) -> tuple[Agent, LiveSession]:
    """和 cli.build_agent 的组装方式一样，只是会话换成 LiveSession（有人在听）。没有 API key 时抛 ConfigError。"""
    key = config.api_key()
    toolbox = ToolBox(Workspace(Brief(), FeatureList(), []), timeout_s=config.run_timeout_s, secret_names=(config.api_key_env,))
    session = LiveSession(config.sessions_dir)
    agent = Agent(make_llm(config, "clarify", key), toolbox, session, config, modeling_llm=make_llm(config, "modeling", key))
    _, info = cli._banner(config, session)
    session.log("startup", **info)  # 作业要求记录软件和模型版本
    return agent, session


def bind_server(state: LiveApp | ReplayApp, host: str, port: int, password: str | None = None) -> ThreadingHTTPServer:
    """从 port 开始找能用的端口，最多试 PORT_TRIES 个。"""
    last: OSError | None = None
    for candidate in range(port, port + PORT_TRIES):
        try:
            return make_server(state, host, candidate, password=password)
        except OSError as e:
            last = e
    raise OSError(f"端口 {port}～{port + PORT_TRIES - 1} 都被占用了，可以用 --port 换一个起点") from last


def main(argv: list[str] | None = None, print_fn: Callable[..., None] = print) -> int:
    parser = argparse.ArgumentParser(prog="python -m cad_agent.web", description="CAD 建模智能体的网页界面")
    parser.add_argument("--config", default="config.toml", help="配置文件路径，默认 config.toml")
    parser.add_argument("--replay", metavar="会话目录", help="只读回放一个已保存的会话，不需要 API key")
    parser.add_argument("--port", type=int, default=8765, help="端口，默认 8765；被占用时自动换下一个")
    parser.add_argument("--no-browser", action="store_true", help="不自动打开浏览器")
    parser.add_argument("--public", action="store_true", help=f"公网测试：要求访问密码（环境变量 {PASSWORD_ENV}），并限制花费")
    parser.add_argument("--budget", type=float, default=5.0, help="公网测试时的花费上限（元），默认 5")
    args = parser.parse_args(argv)
    password = None

    try:
        if args.replay:
            state: LiveApp | ReplayApp = ReplayApp(Path(args.replay))
        else:
            config = load_config(Path(args.config))
            budget = None
            if args.public:
                password = os.environ.get(PASSWORD_ENV, "").strip()
                if len(password) < MIN_PASSWORD:
                    raise ConfigError(f"公网测试要先设置访问密码：环境变量 {PASSWORD_ENV}，至少 {MIN_PASSWORD} 个字符")
                if config.llm_settings("base").pricing is None:
                    raise ConfigError("公网测试要限制花费，请先在 config.toml 里填好 [llm.pricing]")
                budget = args.budget
            state = LiveApp(lambda: build_live_agent(config), config.model, budget=budget)
        server = bind_server(state, "127.0.0.1", args.port, password=password)
    except (ConfigError, OSError) as e:
        print_fn(str(e))
        return 1

    url = f"http://127.0.0.1:{server.server_address[1]}/"
    mode = "回放模式（只读）" if args.replay else (f"公网测试模式（要密码，花费上限 ¥{args.budget:g}）" if password else "实时模式")
    print_fn(f"网页界面已启动（{mode}）：{url}　按 Ctrl+C 退出")
    if not args.no_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print_fn("\n已退出。")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
