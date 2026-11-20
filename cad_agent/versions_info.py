"""会话日志里的软件和模型版本（3.0 计划 1 Task 4；作业要求"记录软件及模型版本"）。

命令行和桌面端新建或打开会话时，都往会话日志写一条 {"kind": "startup", **collect_versions(config)}。
不含 key；接口地址只留到路径，账号密码、查询参数、锚点都去掉（那里可能放着 key）。
"""

from __future__ import annotations

import importlib.metadata
import platform
from urllib.parse import urlsplit

from cad_agent import brand
from cad_agent.config import Config

PHASES = ("clarify", "modeling", "review")   # 澄清、建模、审查


def _dist_version(name: str) -> str:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return "没装"


def clean_url(url: str) -> str:
    """只留 协议://主机[:端口]/路径。"""
    try:
        parts = urlsplit(url)
        host = parts.hostname or ""
        port = f":{parts.port}" if parts.port else ""
    except ValueError:
        return ""
    return f"{parts.scheme}://{host}{port}{parts.path}" if parts.scheme else ""


def collect_versions(config: Config) -> dict:
    return {
        "datum": brand.VERSION,
        "python": platform.python_version(),
        "simplecadapi": _dist_version("simplecadapi"),
        "openai": _dist_version("openai"),
        "anthropic": _dist_version("anthropic"),
        "platform": platform.platform(),
        "provider": config.provider,
        "model": config.model,
        "models_by_phase": {phase: config.llm_settings(phase).model for phase in PHASES},   # type: ignore[arg-type]
        "base_url": clean_url(config.base_url),
    }
