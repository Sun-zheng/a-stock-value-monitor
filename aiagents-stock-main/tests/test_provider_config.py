from interface.ai.provider_config import configured_model_pool, resolve_provider
from interface.ai.deepseek_client import DeepSeekClient


def test_resolve_provider_for_nvidia_model():
    provider = resolve_provider("deepseek-ai/deepseek-v3.1-terminus")

    assert provider.name == "nvidia"
    assert provider.api_key_env == "NVIDIA_API_KEY"


def test_resolve_provider_for_modelscope_model():
    provider = resolve_provider("deepseek-ai/DeepSeek-V4-Pro")

    assert provider.name == "modelscope"
    assert provider.api_key_env == "MODELSCOPE_API_KEY"


def test_resolve_provider_for_new_modelscope_models():
    assert resolve_provider("moonshotai/Kimi-K2.7-Code:Moonshot").name == "modelscope"
    assert resolve_provider("stepfun-ai/Step-3.7-Flash").name == "modelscope"
    assert resolve_provider("MiniMax/MiniMax-M3").name == "modelscope"
    assert resolve_provider("deepseek-ai/DeepSeek-V4-Flash").name == "modelscope"
    assert resolve_provider("ZhipuAI/GLM-5.2").name == "modelscope"
    assert resolve_provider("inclusionAI/Ring-2.6-1T").name == "modelscope"


def test_resolve_provider_defaults_to_deepseek():
    provider = resolve_provider("unknown-model")

    assert provider.name == "deepseek"


def test_resolve_provider_for_siliconflow_deepseek_model():
    provider = resolve_provider("deepseek-ai/DeepSeek-R1")

    assert provider.name == "siliconflow"


def test_configured_model_pool_keeps_primary_first(monkeypatch):
    monkeypatch.setenv("AI_MODEL_POOL", "z-ai/glm5,deepseek-chat,z-ai/glm5")

    assert configured_model_pool("deepseek-chat") == ["deepseek-chat", "z-ai/glm5"]


def test_client_skips_unconfigured_pool_model(monkeypatch):
    monkeypatch.delenv("NVIDIA_API_KEY", raising=False)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.setenv("AI_MODEL_POOL", "deepseek-chat")

    result = DeepSeekClient(model="z-ai/glm5").call_api([{"role": "user", "content": "ping"}])

    assert "API调用失败" in result
    assert "NVIDIA_API_KEY" in result
    assert "DEEPSEEK_API_KEY" in result
