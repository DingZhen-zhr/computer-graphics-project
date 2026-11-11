"""按阶段造模型客户端：模型名、温度、额外参数、价目表都从配置里取，代码里不认识任何厂商专用的参数。

接口类型（OpenAI 兼容 / Claude 官方接口）和地址按阶段取：只有看图审查（review）可以换一家服务。
"""

from __future__ import annotations

from cad_agent.config import Config, Phase
from cad_agent.llm.client import LLM, OpenAICompatLLM


def make_llm(config: Config, phase: Phase, api_key: str) -> LLM:
    settings = config.llm_settings(phase)
    kind, base_url, _ = config.endpoint(phase)
    if kind == "anthropic":
        from cad_agent.llm.anthropic_client import AnthropicLLM  # 只有用到时才导入 anthropic SDK

        return AnthropicLLM(base_url=base_url, api_key=api_key, model=settings.model, temperature=settings.temperature,
                            extra_body=settings.extra_body, pricing=settings.pricing)
    return OpenAICompatLLM(
        base_url, settings.model, api_key,
        temperature=settings.temperature, extra_body=settings.extra_body, pricing=settings.pricing,
    )

