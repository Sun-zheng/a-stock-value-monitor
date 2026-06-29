from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from interface.ai.provider_config import PROVIDERS, resolve_provider  # noqa: E402


DEFAULT_TEST_MODELS = [
    "stepfun-ai/Step-3.5-Flash",
    "Qwen/Qwen3-Next-80B-A3B-Instruct",
    "moonshotai/Kimi-K2.5",
]


def _validate_model(model: str, prompt: str, timeout: int) -> dict:
    provider = resolve_provider(model)
    if not provider.api_key:
        return {
            "model": model,
            "provider": provider.name,
            "status": "skipped",
            "reason": f"{provider.api_key_env} not configured",
        }
    started = time.perf_counter()
    try:
        client = OpenAI(api_key=provider.api_key, base_url=provider.base_url, timeout=timeout, max_retries=0)
        kwargs = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0,
            "max_tokens": 24,
        }
        extra_body = provider.extra_body_by_model.get(model)
        if extra_body:
            kwargs["extra_body"] = extra_body
        response = client.chat.completions.create(**kwargs)
        content = response.choices[0].message.content or ""
        return {
            "model": model,
            "provider": provider.name,
            "status": "ok",
            "latency_ms": round((time.perf_counter() - started) * 1000),
            "sample_chars": len(content),
        }
    except Exception as exc:
        return {
            "model": model,
            "provider": provider.name,
            "status": "failed",
            "latency_ms": round((time.perf_counter() - started) * 1000),
            "error": str(exc)[-500:],
        }


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate configured OpenAI-compatible AI providers.")
    parser.add_argument("--models", help="Comma-separated model names. Defaults to one representative model per provider.")
    parser.add_argument("--prompt", default="只回复 OK", help="Minimal validation prompt.")
    parser.add_argument("--timeout", type=int, default=45)
    args = parser.parse_args()

    load_dotenv(os.getenv("AIAGENTS_ENV_FILE", str(ROOT / ".env")), override=True)
    models = [item.strip() for item in (args.models or ",".join(DEFAULT_TEST_MODELS)).split(",") if item.strip()]
    results = [_validate_model(model, args.prompt, args.timeout) for model in models]
    summary = {
        "configured_providers": [
            name for name, provider in PROVIDERS.items() if os.getenv(provider.api_key_env)
        ],
        "results": results,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if all(item["status"] in {"ok", "skipped"} for item in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
