from pathlib import Path

from tools.configure_ai_secrets import masked, read_env, write_env


def test_write_env_masks_and_roundtrips(tmp_path: Path):
    env_path = tmp_path / ".env"

    write_env({"NVIDIA_API_KEY": "nvapi-abcdefghijklmnopqrstuvwxyz", "AI_MODEL_POOL": "a,b"}, env_path)
    values = read_env(env_path)

    assert values["NVIDIA_API_KEY"] == "nvapi-abcdefghijklmnopqrstuvwxyz"
    assert values["AI_MODEL_POOL"] == "a,b"
    assert masked(values["NVIDIA_API_KEY"]).startswith("nvap")
    assert env_path.stat().st_mode & 0o777 == 0o600
