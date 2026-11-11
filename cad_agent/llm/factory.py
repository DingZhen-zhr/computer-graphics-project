"""按阶段造模型客户端：模型名、温度、额外参数、价目表都从配置里取，代码里不认识任何厂商专用的参数。

接口类型（OpenAI 兼容 / Claude 官方接口）和地址按阶段取：只有看图审查（review）可以换一家服务。
"""

from __future__ import annotations

from dataclasses import replace

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


def secret_env_names(config: Config) -> tuple[str, ...]:
    """沙盒子进程里要去掉的 key 变量名：基础的，加上审查另用的（如果不同）。"""
    review_env = config.endpoint("review")[2]
    return (config.api_key_env,) + ((review_env,) if review_env != config.api_key_env else ())


def make_review_llm(config: Config, base_key: str) -> LLM | None:
    """看图审查用的模型：分阶段、开关 visual_review 打开、审查用的模型能识图时才造，否则是 None（不审查）。

    审查另用一家服务时，key 从那家的环境变量取；没设时抛 ConfigError（中文）。
    """
    if not (config.gates.staged and config.gates.visual_review and config.vision):
        return None
    review_env = config.endpoint("review")[2]
    key = base_key if review_env == config.api_key_env else replace(config, api_key_env=review_env).api_key()
    return make_llm(config, "review", key)
