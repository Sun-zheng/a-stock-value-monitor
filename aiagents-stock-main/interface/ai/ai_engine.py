from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from interface.ai.deepseek_client import DeepSeekClient
from interface.ai.provider_config import available_model_options, configured_model_pool, resolve_provider


@dataclass
class AIEngineResponse:
    ok: bool
    content: str
    model: str
    provider: str
    error: str = ""
    health: dict[str, Any] = field(default_factory=dict)


class AIEngine:
    """统一AI调用入口。

    旧代码仍可使用 DeepSeekClient；新功能应优先使用 AIEngine，避免在业务代码中
    直接处理供应商、模型池、密钥和失败切换。
    """

    def __init__(self, default_model: str = "stepfun-ai/Step-3.7-Flash"):
        self.default_model = default_model
        self._clients: dict[str, DeepSeekClient] = {}

    @staticmethod
    def model_options() -> dict[str, str]:
        return available_model_options()

    @staticmethod
    def provider_name(model: str) -> str:
        return resolve_provider(model).name

    @staticmethod
    def model_pool(primary_model: str, use_pool: bool = True) -> list[str]:
        return configured_model_pool(primary_model) if use_pool else [primary_model]

    def chat(
        self,
        messages: list[dict[str, Any]],
        model: str | None = None,
        temperature: float = 0.3,
        max_tokens: int = 2000,
        allowed_providers: set[str] | None = None,
        use_pool: bool = True,
    ) -> AIEngineResponse:
        selected_model = model or self.default_model
        candidates = self.model_pool(selected_model, use_pool=use_pool)
        last_error = ""
        for candidate in candidates:
            provider = resolve_provider(candidate)
            if allowed_providers and provider.name not in allowed_providers:
                last_error = f"{candidate}: provider {provider.name} not allowed"
                continue
            client = self._clients.setdefault(candidate, DeepSeekClient(model=candidate))
            content = client.call_api(
                messages=messages,
                model=candidate,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            if not content.startswith("API调用失败"):
                return AIEngineResponse(
                    ok=True,
                    content=content,
                    model=candidate,
                    provider=provider.name,
                    health=client.provider_health,
                )
            last_error = content
        return AIEngineResponse(
            ok=False,
            content="",
            model=selected_model,
            provider=resolve_provider(selected_model).name,
            error=last_error or "没有可用AI模型",
        )
