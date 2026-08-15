"""
Test which configured LLM models (Gemini / Groq) actually respond right now.
Tests each model individually (no fallback chain) and reports latency + errors.

Provider is resolved automatically from the model slug via settings.endpoint_for():
    gemini-*  -> Google's OpenAI-compatible endpoint
    everything else -> Groq's OpenAI-compatible endpoint

Usage:
    python scripts/test_models.py [model1,model2,...]
    # with no args, tests PRIMARY_LLM_MODEL + FALLBACK_LLM_MODELS from .env
"""
import asyncio
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx

from app.config import settings


async def test_one(client: httpx.AsyncClient, model: str) -> tuple[str, bool, str, float]:
    base_url, api_key = settings.endpoint_for(model)
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    start = time.monotonic()
    try:
        resp = await client.post(
            f"{base_url.rstrip('/')}/chat/completions",
            headers=headers,
            json={
                "model": model,
                "messages": [{"role": "user", "content": "Reply with exactly: OK"}],
                "temperature": 0.0,
                # 16 tokens is too small for reasoning models (gemini-3.x, gpt-oss):
                # thinking alone consumes it, leaving empty content. 256 fits both.
                "max_tokens": 256,
                "stream": False,
            },
        )
        elapsed = round((time.monotonic() - start) * 1000)
        if resp.status_code != 200:
            detail = resp.text[:200]
            return model, False, f"HTTP {resp.status_code}: {detail}", elapsed
        data = resp.json()
        content = (data["choices"][0]["message"].get("content") or "").strip()
        if not content:
            return model, False, "Empty content in response", elapsed
        return model, True, f"OK ({content!r})", elapsed
    except Exception as exc:
        return model, False, str(exc)[:200], round((time.monotonic() - start) * 1000)


async def main():
    models = sys.argv[1:] if len(sys.argv) > 1 else (
        [settings.primary_llm_model] + settings.fallback_models_list
    )
    print(f"Testing {len(models)} models (providers: gemini/groq)")
    async with httpx.AsyncClient(timeout=45) as client:
        for model in models:
            slug, ok, detail, ms = await test_one(client, model)
            status = "PASS" if ok else "FAIL"
            print(f"[{status}] {slug} ({ms}ms) -> {detail}")


if __name__ == "__main__":
    asyncio.run(main())
