from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ProviderConfig:
    name: str
    base_url: str
    api_key_env: str
    default_model: str
    model_prefixes: tuple[str, ...] = ()
    model_names: tuple[str, ...] = ()
    extra_body_by_model: dict[str, dict[str, Any]] = field(default_factory=dict)

    @property
    def api_key(self) -> str:
        return os.getenv(self.api_key_env, "")


PROVIDERS: dict[str, ProviderConfig] = {
    "deepseek": ProviderConfig(
        name="deepseek",
        base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1"),
        api_key_env="DEEPSEEK_API_KEY",
        default_model="deepseek-chat",
        model_names=("deepseek-chat", "deepseek-reasoner"),
    ),
    "aliyun": ProviderConfig(
        name="aliyun",
        base_url=os.getenv("ALIYUN_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1"),
        api_key_env="ALIYUN_API_KEY",
        default_model="qwen-plus",
        model_prefixes=("qwen-",),
    ),
    "siliconflow": ProviderConfig(
        name="siliconflow",
        base_url=os.getenv("SILICONFLOW_BASE_URL", "https://api.siliconflow.cn/v1"),
        api_key_env="SILICONFLOW_API_KEY",
        default_model="deepseek-ai/DeepSeek-R1",
        model_prefixes=(
            "deepseek-ai/",
            "Pro/deepseek-ai/",
            "Qwen/",
            "zai-org/",
            "moonshotai/",
        ),
        model_names=("Ring-1T", "step3"),
    ),
    "nvidia": ProviderConfig(
        name="nvidia",
        base_url=os.getenv("NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1"),
        api_key_env="NVIDIA_API_KEY",
        default_model="deepseek-ai/deepseek-v3.1-terminus",
        model_prefixes=(
            "meta/",
            "minimaxai/",
            "z-ai/",
            "qwen/",
            "moonshotai/",
            "nvidia/",
            "mistralai/",
        ),
        model_names=(
            "deepseek-ai/deepseek-v3.1-terminus",
            "deepseek-ai/deepseek-v4-flash",
            "deepseek-ai/deepseek-v4-pro",
            "minimaxai/minimax-m2.7",
            "minimaxai/minimax-m3",
            "moonshotai/kimi-k2.5",
            "moonshotai/kimi-k2.6",
            "moonshotai/kimi-k2-instruct",
            "moonshotai/kimi-k2-thinking",
        ),
        extra_body_by_model={
            "z-ai/glm5": {"chat_template_kwargs": {"enable_thinking": True, "clear_thinking": False}},
            "qwen/qwen3.5-397b-a17b": {"chat_template_kwargs": {"enable_thinking": True}},
            "moonshotai/kimi-k2.5": {"chat_template_kwargs": {"thinking": True}},
            "deepseek-ai/deepseek-v3.1-terminus": {"chat_template_kwargs": {"thinking": True}},
            "deepseek-ai/deepseek-v4-flash": {"chat_template_kwargs": {"thinking": True}},
            "deepseek-ai/deepseek-v4-pro": {"chat_template_kwargs": {"thinking": True}},
            "nvidia/nemotron-3-super-120b-a12b": {
                "chat_template_kwargs": {"enable_thinking": True},
                "reasoning_budget": 16384,
            },
        },
    ),
    "modelscope": ProviderConfig(
        name="modelscope",
        base_url=os.getenv("MODELSCOPE_BASE_URL", "https://api-inference.modelscope.cn/v1"),
        api_key_env="MODELSCOPE_API_KEY",
        default_model="stepfun-ai/Step-3.7-Flash",
        model_prefixes=(
            "stepfun-ai/",
            "Shanghai_AI_Laboratory/",
            "deepseek-ai/",
            "moonshotai/",
            "MiniMax/",
            "ZhipuAI/",
            "inclusionAI/",
        ),
        model_names=(
            "deepseek-ai/DeepSeek-V3.2",
            "deepseek-ai/DeepSeek-V4-Flash",
            "deepseek-ai/DeepSeek-V4-Pro",
            "ZhipuAI/GLM-5.2",
            "inclusionAI/Ring-2.6-1T",
            "Qwen/Qwen3.5-122B-A10B",
            "Qwen/Qwen3.5-27B",
            "Qwen/Qwen3.5-35B-A3B",
            "Qwen/Qwen3.5-397B-A17B",
            "Qwen/Qwen3-Next-80B-A3B-Instruct",
            "Qwen/Qwen3-Next-80B-A3B-Thinking",
            "MiniMax/MiniMax-M2.7",
            "MiniMax/MiniMax-M3",
            "moonshotai/Kimi-K2.5",
            "moonshotai/Kimi-K2.7-Code:Moonshot",
            "meituan-longcat/LongCat-Flash-Lite",
            "nex-agi/Nex-N2-Pro",
            "LLM-Research/Llama-4-Maverick-17B-128E-Instruct",
        ),
    ),
}


def resolve_provider(model: str | None) -> ProviderConfig:
    selected = model or PROVIDERS["deepseek"].default_model
    for provider in PROVIDERS.values():
        if selected in provider.model_names:
            return provider
    for provider in PROVIDERS.values():
        if any(selected.startswith(prefix) for prefix in provider.model_prefixes):
            return provider
    return PROVIDERS["deepseek"]


def configured_model_pool(primary_model: str) -> list[str]:
    """Return primary model plus optional failover models from AI_MODEL_POOL.

    AI_MODEL_POOL accepts comma-separated model names. The primary model stays
    first so user choice remains deterministic; repeated names are ignored.
    """
    raw_pool = os.getenv("AI_MODEL_POOL", "")
    candidates = [primary_model]
    candidates.extend(item.strip() for item in raw_pool.split(",") if item.strip())
    deduped: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        if candidate not in seen:
            deduped.append(candidate)
            seen.add(candidate)
    return deduped


def available_model_options() -> dict[str, str]:
    return {
        "deepseek-chat": "DeepSeek Chat (默认)",
        "deepseek-reasoner": "DeepSeek Reasoner (推理增强)",
        "qwen-plus": "qwen-plus (阿里百炼)",
        "qwen-plus-latest": "qwen-plus-latest (阿里百炼)",
        "qwen-flash": "qwen-flash (阿里百炼)",
        "qwen-turbo": "qwen-turbo (阿里百炼)",
        "qwen3-max": "qwen-max (阿里百炼)",
        "qwen-long": "qwen-long (阿里百炼)",
        "deepseek-ai/DeepSeek-R1-0528-Qwen3-8B": "DeepSeek-R1 免费(硅基流动)",
        "Qwen/Qwen2.5-7B-Instruct": "Qwen 免费(硅基流动)",
        "Pro/deepseek-ai/DeepSeek-V3.1-Terminus": "DeepSeek-V3.1-Terminus (硅基流动)",
        "deepseek-ai/DeepSeek-R1": "DeepSeek-R1 (硅基流动)",
        "Qwen/Qwen3-235B-A22B-Thinking-2507": "Qwen3-235B (硅基流动)",
        "zai-org/GLM-4.6": "智谱(硅基流动)",
        "moonshotai/Kimi-K2-Instruct-0905": "Kimi (硅基流动)",
        "Ring-1T": "蚂蚁百灵 (硅基流动)",
        "step3": "阶跃星辰(硅基流动)",
        "meta/llama-4-maverick-17b-128e-instruct": "Llama 4 Maverick (NVIDIA)",
        "minimaxai/minimax-m2.5": "MiniMax M2.5 (NVIDIA)",
        "minimaxai/minimax-m2.7": "MiniMax M2.7 (NVIDIA)",
        "minimaxai/minimax-m3": "MiniMax M3 (NVIDIA)",
        "z-ai/glm5": "GLM5 Thinking (NVIDIA)",
        "qwen/qwen3.5-397b-a17b": "Qwen3.5 397B Thinking (NVIDIA)",
        "moonshotai/kimi-k2.5": "Kimi K2.5 Thinking (NVIDIA)",
        "deepseek-ai/deepseek-v3.1-terminus": "DeepSeek V3.1 Terminus (NVIDIA)",
        "deepseek-ai/deepseek-v4-flash": "DeepSeek V4 Flash (NVIDIA)",
        "deepseek-ai/deepseek-v4-pro": "DeepSeek V4 Pro (NVIDIA)",
        "nvidia/nemotron-3-super-120b-a12b": "Nemotron 3 Super 120B (NVIDIA)",
        "mistralai/mistral-small-4-119b-2603": "Mistral Small 4 119B (NVIDIA)",
        "mistralai/ministral-14b-instruct-2512": "Ministral 14B 2512 (NVIDIA)",
        "mistralai/mistral-large-3-675b-instruct-2512": "Mistral Large 3 675B 2512 (NVIDIA)",
        "mistralai/mistral-medium-3.5-128b": "Mistral Medium 3.5 128B (NVIDIA)",
        "nvidia/llama-3.3-nemotron-super-49b-v1.5": "Nemotron Super 49B v1.5 (NVIDIA)",
        "moonshotai/kimi-k2.6": "Kimi K2.6 (NVIDIA)",
        "moonshotai/kimi-k2-instruct": "Kimi K2 Instruct (NVIDIA)",
        "moonshotai/kimi-k2-thinking": "Kimi K2 Thinking (NVIDIA)",
        "stepfun-ai/Step-3.5-Flash": "Step 3.5 Flash (ModelScope)",
        "Shanghai_AI_Laboratory/Intern-S1-Pro": "Intern-S1-Pro (ModelScope)",
        "deepseek-ai/DeepSeek-V3.2": "DeepSeek V3.2 (ModelScope)",
        "deepseek-ai/DeepSeek-V4-Flash": "DeepSeek V4 Flash (ModelScope)",
        "deepseek-ai/DeepSeek-V4-Pro": "DeepSeek V4 Pro (ModelScope)",
        "stepfun-ai/Step-3.7-Flash": "Step 3.7 Flash (ModelScope)",
        "ZhipuAI/GLM-5.2": "GLM 5.2 (ModelScope)",
        "inclusionAI/Ring-2.6-1T": "Ring 2.6 1T (ModelScope)",
        "Qwen/Qwen3.5-122B-A10B": "Qwen3.5 122B (ModelScope)",
        "Qwen/Qwen3-Next-80B-A3B-Instruct": "Qwen3 Next 80B Instruct (ModelScope)",
        "Qwen/Qwen3-Next-80B-A3B-Thinking": "Qwen3 Next 80B Thinking (ModelScope)",
        "moonshotai/Kimi-K2.5": "Kimi K2.5 (ModelScope)",
        "moonshotai/Kimi-K2.7-Code:Moonshot": "Kimi K2.7 Code (ModelScope)",
        "MiniMax/MiniMax-M3": "MiniMax M3 (ModelScope)",
    }
