from __future__ import annotations

import argparse
import getpass
import json
import os
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ENV_PATH = Path(
    os.getenv("AIAGENTS_ENV_FILE", ROOT / ".env")
)

SECRET_KEYS = {
    "deepseek": ["DEEPSEEK_API_KEY", "DEEPSEEK_BASE_URL"],
    "aliyun": ["ALIYUN_API_KEY", "ALIYUN_BASE_URL"],
    "siliconflow": ["SILICONFLOW_API_KEY", "SILICONFLOW_BASE_URL"],
    "nvidia": ["NVIDIA_API_KEY", "NVIDIA_BASE_URL"],
    "modelscope": ["MODELSCOPE_API_KEY", "MODELSCOPE_BASE_URL"],
    "pool": ["AI_MODEL_POOL"],
}

DEFAULT_BASE_URLS = {
    "DEEPSEEK_BASE_URL": "https://api.deepseek.com/v1",
    "ALIYUN_BASE_URL": "https://dashscope.aliyuncs.com/compatible-mode/v1",
    "SILICONFLOW_BASE_URL": "https://api.siliconflow.cn/v1",
    "NVIDIA_BASE_URL": "https://integrate.api.nvidia.com/v1",
    "MODELSCOPE_BASE_URL": "https://api-inference.modelscope.cn/v1",
}


def read_env(path: Path = DEFAULT_ENV_PATH) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        value = value.strip()
        if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
            value = value[1:-1]
        values[key.strip()] = value
    return values


def write_env(values: dict[str, str], path: Path = DEFAULT_ENV_PATH) -> None:
    existing_order = []
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if stripped and not stripped.startswith("#") and "=" in stripped:
                key = stripped.split("=", 1)[0].strip()
                if key not in existing_order:
                    existing_order.append(key)
    for keys in SECRET_KEYS.values():
        for key in keys:
            if key not in existing_order and key in values:
                existing_order.append(key)
    lines = ["# AI股票分析系统环境配置", "# 密钥只保存在本机 .env，不提交到代码仓库", ""]
    for key in existing_order:
        value = values.get(key, "")
        lines.append(f'{key}="{value}"')
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    path.chmod(0o600)


def masked(value: str) -> str:
    if not value:
        return ""
    if len(value) <= 10:
        return "***"
    return value[:4] + "*" * max(len(value) - 8, 3) + value[-4:]


def configure_provider(provider: str, values: dict[str, str]) -> dict[str, str]:
    for key in SECRET_KEYS[provider]:
        default = values.get(key) or DEFAULT_BASE_URLS.get(key, "")
        if key.endswith("_API_KEY"):
            prompt = f"{key}: "
            new_value = getpass.getpass(prompt)
            if new_value:
                values[key] = new_value.strip()
        else:
            prompt = f"{key} [{default}]: "
            new_value = input(prompt).strip()
            values[key] = new_value or default
    return values


def main() -> int:
    parser = argparse.ArgumentParser(description="Configure AI provider secrets in local .env.")
    parser.add_argument("provider", choices=sorted(SECRET_KEYS), nargs="?", help="Provider to configure.")
    parser.add_argument("--list", action="store_true", help="List configured keys without revealing values.")
    parser.add_argument("--env-file", default=str(DEFAULT_ENV_PATH), help="Target env file.")
    args = parser.parse_args()

    env_path = Path(args.env_file)
    values = read_env(env_path)
    if args.list:
        configured = {
            key: masked(values.get(key, ""))
            for keys in SECRET_KEYS.values()
            for key in keys
            if values.get(key)
        }
        print(json.dumps(configured, ensure_ascii=False, indent=2))
        return 0
    if not args.provider:
        parser.error("provider is required unless --list is used")
    values = configure_provider(args.provider, values)
    write_env(values, env_path)
    print(f"{args.provider} 配置已保存到 {env_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
