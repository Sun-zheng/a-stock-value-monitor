from tools.validate_ai_providers import _validate_model


def test_validate_model_skips_missing_key(monkeypatch):
    monkeypatch.delenv("NVIDIA_API_KEY", raising=False)

    result = _validate_model("deepseek-ai/deepseek-v3.1-terminus", "ping", 1)

    assert result["status"] == "skipped"
    assert result["provider"] == "nvidia"
