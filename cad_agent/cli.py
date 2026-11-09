"""命令行界面：普通输入就是和智能体对话，以 / 开头的是命令。"""

from __future__ import annotations

import argparse
import json
import platform
import shutil
import subprocess
import sys
from importlib.metadata import version
from pathlib import Path
from typing import Callable

from cad_agent import __version__
from cad_agent.agent.loop import Agent
from cad_agent.brief import Brief
from cad_agent.config import Config, ConfigError, load_config
from cad_agent.llm.factory import make_llm
from cad_agent.notebook import FeatureList
from cad_agent.session import Session
from cad_agent.tools import ToolBox, Workspace

CONFIRM_HINT = "回复「确认」开始建模，或直接说要改什么"
HELP = """可用命令：
  /view      用 sca edit 在浏览器里打开当前会话的模型
  /diff      对比最近两个版本（参数变化 + 两张截图的路径）
  /versions  列出所有已交付的版本
  /quit      退出
其他输入都会发给建模助手。"""


def build_agent(config: Config) -> tuple[Agent, Session]:
    """按配置组装智能体。没有设置 API key 时抛 ConfigError（此时还不会创建会话目录）。"""
    key = config.api_key()
    llm = make_llm(config, "base", key)
    toolbox = ToolBox(Workspace(Brief(), FeatureList(), []), timeout_s=config.run_timeout_s, secret_names=(config.api_key_env,))
    session = Session(config.sessions_dir)
    return Agent(llm, toolbox, session, config), session


def find_sca() -> str | None:
    """虚拟环境里的 sca 不在 PATH 上，所以先找和当前 python 同目录的（见 docs/sca-api-notes.md 第 11 节）。"""
    local = Path(sys.executable).parent / ("sca.exe" if sys.platform == "win32" else "sca")
    return str(local) if local.exists() else shutil.which("sca")


def diff_briefs(old: Brief, new: Brief) -> list[str]:
    """两份需求单的参数差异（中文变化行）。"""
    new_by_name = {p.name: p for p in new.params}
    old_names = {p.name for p in old.params}
    lines: list[str] = []
    for p in old.params:
        q = new_by_name.get(p.name)
        if q is None:
            lines.append(f"{p.name}: 已删除")
        elif (p.value, p.unit) != (q.value, q.unit):
            same_unit = p.unit == q.unit
            lines.append(f"{p.name}: {p.value:g} → {q.value:g} ({q.unit})" if same_unit else f"{p.name}: {p.value:g} {p.unit} → {q.value:g} {q.unit}")
    lines += [f"{q.name}: 新增 {q.value:g} {q.unit}" for q in new.params if q.name not in old_names]
    return lines


def _load_brief(version_dir: Path) -> Brief:
    return Brief.from_dict(json.loads((version_dir / "brief.json").read_text(encoding="utf-8")))


def _banner(config: Config, session: Session) -> tuple[str, dict]:
    info = {
        "python": platform.python_version(), "simplecadapi": version("simplecadapi"), "cad_agent": __version__,
        "model": config.model, "base_url": config.base_url,
    }
    text = (f"Python {info['python']} | simplecadapi {info['simplecadapi']} | cad-agent {info['cad_agent']} | "
            f"模型 {config.model}（{config.base_url}）\n会话目录：{session.dir}\n"
            "直接说出你想做的零件，例如：做一个放在桌上看视频的小支架。输入 /help 查看命令。")
    return text, info


def main(argv: list[str] | None = None, input_fn: Callable[[str], str] = input, print_fn: Callable[..., None] = print) -> int:
    parser = argparse.ArgumentParser(prog="python -m cad_agent", description="CAD 建模智能体")
    parser.add_argument("--config", default="config.toml", help="配置文件路径，默认 config.toml")
    args = parser.parse_args(argv)

    try:
        config = load_config(Path(args.config))
        agent, session = build_agent(config)
    except ConfigError as e:
        print_fn(str(e))
        return 1

    banner, info = _banner(config, session)
    print_fn(banner)
    session.log("startup", **info)  # 作业要求记录软件和模型版本

    editors: list[subprocess.Popen] = []

    def cmd_view() -> None:
        if any(p.poll() is None for p in editors):
            print_fn("编辑器已经在运行了，请在浏览器里查看。")
            return
        sca = find_sca()
        if sca is None:
            print_fn("找不到 sca 命令。请确认已安装 simplecadapi[editor]：.venv\\Scripts\\python -m pip install -e \".[dev]\"")
            return
        editors.append(subprocess.Popen([sca, "edit", str(session.dir)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))
        print_fn("已启动编辑器，浏览器会自动打开；退出本程序时会一并关闭它。")

    def cmd_versions() -> None:
        versions = session.versions()
        if not versions:
            print_fn("还没有交付过版本。")
        for v in versions:
            print_fn(f"{v.name}  {v}")
            for line in (v / "changes.md").read_text(encoding="utf-8").splitlines():
                if line.startswith("- "):
                    print_fn(f"    {line}")

    def cmd_diff() -> None:
        versions = session.versions()
        if len(versions) < 2:
            print_fn("还没有可对比的两个版本。")
            return
        old, new = versions[-2:]
        changes = diff_briefs(_load_brief(old), _load_brief(new))
        print_fn(f"对比 {old.name} → {new.name}")
        print_fn("参数变化：")
        for line in changes or ["（参数没有变化）"]:
            print_fn(f"  {line}")
        print_fn("截图：")
        print_fn(f"  {old.name}: {old / 'view.png'}")
        print_fn(f"  {new.name}: {new / 'view.png'}")

    commands = {"/view": cmd_view, "/versions": cmd_versions, "/diff": cmd_diff, "/help": lambda: print_fn(HELP)}
    try:
        while True:
            try:
                line = input_fn("你> ").strip()
            except EOFError:
                break
            if not line:
                continue
            if line == "/quit":
                break
            if line.startswith("/"):
                handler = commands.get(line.split()[0])
                if handler is None:
                    print_fn(f"不认识的命令 {line.split()[0]}。输入 /help 查看可用命令。")
                else:
                    handler()
                continue
            turn = agent.handle_user(line)
            print_fn(f"\n{turn.text}")
            if turn.kind == "confirm":
                print_fn(f"\n{CONFIRM_HINT}")
            if turn.llm_calls:
                print_fn(f"（本轮模型调用 {turn.llm_calls} 次，约 {turn.tokens} token）")
    except KeyboardInterrupt:
        print_fn("\n已退出。")
    finally:
        for p in editors:
            if p.poll() is None:
                p.terminate()
    return 0
