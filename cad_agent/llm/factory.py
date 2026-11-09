"""按阶段造模型客户端：模型名、温度、额外参数、价目表都从配置里取，代码里不认识任何厂商专用的参数。"""

from __future__ import annotations

from cad_agent.config import Config, Phase
from cad_agent.llm.client import OpenAICompatLLM


def make_llm(config: Config, phase: Phase, api_key: str) -> OpenAICompatLLM:
    settings = config.llm_settings(phase)
    return OpenAICompatLLM(
        config.base_url, settings.model, api_key,
        temperature=settings.temperature, extra_body=settings.extra_body, pricing=settings.pricing,
    )
