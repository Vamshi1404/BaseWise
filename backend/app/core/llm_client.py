"""
Provider-agnostic LLM Client.

Design principle (project.md Section 4.1):
  LLMClient.complete(...) -> str

Primary model: openai/gpt-oss-120b (Groq, free tier — high daily quota)
  Called via OpenAI-compatible REST (api.groq.com).
Fallback chain: gemini-3.6-flash (Google, free tier — ~20 req/day, too low
  to be primary) called via the official `google.genai` SDK (Interactions API /
  native generateContent). The SDK path is required because new AI Studio keys
  (AQ.* format) fail on Google's raw OpenAI-compatible REST endpoint
  (/v1beta/openai/chat/completions → 404).

IMPORTANT: Free-tier model lineup and limits can change without notice.
Model slugs are driven by PRIMARY_LLM_MODEL / FALLBACK_LLM_MODELS env vars —
swap in .env with zero code changes; provider routing follows the slug
(`gemini-*` → SDK, everything else → Groq REST).
"""
import asyncio
import json
import logging
import re
from typing import Optional
import httpx
from google import genai
from google.genai import types
from app.config import settings
from app.core import model_registry

logger = logging.getLogger(__name__)

_gemini_client: Optional[genai.Client] = None


def _get_gemini_client() -> genai.Client:
    """Lazily build the google.genai client (authenticates the AQ.* key format)."""
    global _gemini_client
    if _gemini_client is None:
        _gemini_client = genai.Client(api_key=settings.gemini_api_key)
    return _gemini_client


def _split_gemini_messages(messages: list[dict]) -> tuple[str, list[types.Content]]:
    """Convert OpenAI-style messages to (system_instruction, gemini content list)."""
    system = "".join(m.get("content", "") for m in messages if m.get("role") == "system")
    chat = [
        types.Content(
            role="user" if m.get("role") == "user" else "model",
            parts=[types.Part(text=m.get("content", ""))],
        )
        for m in messages
        if m.get("role") in ("user", "assistant")
    ]
    if not chat:
        chat = [types.Content(role="user", parts=[types.Part(text=system)])]
        system = ""
    return system, chat


def _gemini_config(temperature: float, max_tokens: int) -> types.GenerateContentConfig:
    # gemini-3.x flash models are "thinking" models: reasoning tokens count toward
    # max_output_tokens, so keep a small explicit thinking budget to avoid the
    # visible answer being starved/truncated (budget 0 is rejected by the API).
    return types.GenerateContentConfig(
        system_instruction=None,
        temperature=temperature,
        max_output_tokens=max_tokens,
        thinking_config=types.ThinkingConfig(thinking_budget=16),
    )


def _gemini_complete_sync(
    model_slug: str, messages: list[dict], temperature: float, max_tokens: int
) -> str:
    client = _get_gemini_client()
    system, chat = _split_gemini_messages(messages)
    config = _gemini_config(temperature, max_tokens)
    if system:
        config.system_instruction = system
    response = client.models.generate_content(
        model=model_slug, contents=chat, config=config
    )
    return getattr(response, "text", "") or ""


def _gemini_stream_sync(
    model_slug: str, messages: list[dict], temperature: float, max_tokens: int
):
    client = _get_gemini_client()
    system, chat = _split_gemini_messages(messages)
    config = _gemini_config(temperature, max_tokens)
    if system:
        config.system_instruction = system
    return client.models.generate_content_stream(
        model=model_slug, contents=chat, config=config
    )


def _mask_headers(headers: dict) -> dict:
    masked = dict(headers)
    auth = masked.get("Authorization", "")
    if auth.startswith("Bearer ") and len(auth) > 16:
        token = auth[len("Bearer "):]
        masked["Authorization"] = f"Bearer {token[:6]}...{token[-4:]}"
    return masked


def _log_request(method: str, url: str, headers: dict, body: dict) -> None:
    payload = json.dumps(body)
    print(
        f"[llm] {method} {url}\n"
        f"  headers={_mask_headers(headers)}\n"
        f"  payload {len(payload)} chars ~{len(payload) // 4} tok\n"
        f"  body={payload}",
        flush=True,
    )


def _log_payload(model_slug: str, messages: list[dict]) -> None:
    """Log the size of a Gemini SDK call payload (no REST body to inspect)."""
    text = json.dumps(messages, ensure_ascii=False)
    print(
        f"[llm] gemini {model_slug} | payload {len(text)} chars ~{len(text) // 4} tok",
        flush=True,
    )


def _headers_for(model_slug: str) -> dict:
    _, api_key = settings.endpoint_for(model_slug)
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }


def _chat_completions_url(model_slug: str) -> str:
    base_url, _ = settings.endpoint_for(model_slug)
    return f"{base_url.rstrip('/')}/chat/completions"


def _body_snippet(response: httpx.Response, limit: int = 300) -> str:
    try:
        body = response.text
    except Exception:
        body = ""
    body = body.strip().replace("\n", " ")
    return (body[:limit] + "…") if len(body) > limit else body


def _is_rate_limit(exc: Exception) -> bool:
    """True for HTTP 429 / google.api_core ResourceExhausted."""
    if getattr(exc, "code", None) == 429:
        return True
    return isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code == 429


def _parse_duration(value: str) -> Optional[float]:
    """Parse '2.49s', '28m48s', '1h2m3s' (Groq reset format) or plain seconds."""
    value = value.strip()
    if value.isdigit():
        return float(value)
    m = re.fullmatch(r"(?:(\d+)h)?(?:(\d+)m)?(?:([\d.]+)s)?", value)
    if m and (m.group(1) or m.group(2) or m.group(3)):
        hours = int(m.group(1) or 0)
        mins = int(m.group(2) or 0)
        secs = float(m.group(3) or 0)
        return hours * 3600 + mins * 60 + secs
    return None


def _retry_after_headers(headers: httpx.Headers, default: float = 2.5) -> float:
    """Respect Retry-After / Groq x-ratelimit-reset-requests, capped at 30s."""
    for key in ("Retry-After", "x-ratelimit-reset-requests"):
        value = headers.get(key)
        if value:
            delay = _parse_duration(value)
            if delay is not None:
                return min(delay, 30.0)
    return default


def _retry_delay_from_exc(exc: Exception, default: float = 2.5) -> float:
    """Extract retry delay from SDK exception payloads (e.g. Gemini 429 RetryInfo)."""
    text = str(exc)
    m = re.search(r"retry in ([\d.]+)s", text, re.IGNORECASE)
    if m:
        return min(float(m.group(1)), 30.0)
    m = re.search(r"'retryDelay':\s*'?(\d+)s", text)
    if m:
        return min(int(m.group(1)), 30.0)
    return default


async def _rest_complete_with_retry(
    client: httpx.AsyncClient,
    model_slug: str,
    messages: list[dict],
    temperature: float,
    max_tokens: int,
) -> str:
    """OpenAI-compatible REST chat completion with one 429 retry (short backoff)."""
    url = _chat_completions_url(model_slug)
    headers = _headers_for(model_slug)
    payload = {
        "model": model_slug,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    max_attempts = 2
    for attempt in range(1, max_attempts + 1):
        _log_request("POST", url, headers, payload)
        response = await client.post(url, headers=headers, json=payload)
        if response.status_code == 429:
            if attempt < max_attempts:
                delay = _retry_after_headers(response.headers)
                logger.warning(
                    f"[{model_slug}] HTTP 429 (attempt {attempt}/{max_attempts}), "
                    f"retrying in {delay:.1f}s: {_body_snippet(response)}"
                )
                await asyncio.sleep(delay)
                continue
            raise httpx.HTTPStatusError(
                f"Rate limited (HTTP 429): {_body_snippet(response)}",
                request=response.request,
                response=response,
            )
        response.raise_for_status()
        data = response.json()
        return data["choices"][0]["message"].get("content")
    raise RuntimeError(f"Unreachable: {model_slug}")


async def _gemini_complete_with_retry(
    model_slug: str, messages: list[dict], temperature: float, max_tokens: int
) -> str:
    """google.genai generate_content with one 429 retry (short backoff)."""
    _log_payload(model_slug, messages)
    max_attempts = 2
    for attempt in range(1, max_attempts + 1):
        try:
            return await asyncio.to_thread(
                _gemini_complete_sync, model_slug, messages, temperature, max_tokens
            )
        except Exception as exc:
            if _is_rate_limit(exc) and attempt < max_attempts:
                delay = _retry_delay_from_exc(exc)
                logger.warning(
                    f"[{model_slug}] rate limited (attempt {attempt}/{max_attempts}), "
                    f"retrying in {delay:.1f}s: {str(exc)[:300]}"
                )
                await asyncio.sleep(delay)
                continue
            raise
    raise RuntimeError(f"Unreachable: {model_slug}")


async def complete(
    messages: list[dict],
    model: Optional[str] = None,
    temperature: float = 0.1,   # Low temp for deterministic SQL generation
    max_tokens: int = 4096,
    timeout: float = 60.0,
    report: Optional[dict] = None,
) -> str:
    """
    Send a chat completion request to the configured provider.
    Automatically retries through the fallback model chain on rate-limit or errors.

    Args:
        messages: OpenAI-format message list [{"role": "user"|"assistant"|"system", "content": str}]
        model: Override model slug. Defaults to PRIMARY_LLM_MODEL from config.
        temperature: Sampling temperature.
        max_tokens: Max output tokens.
        timeout: Request timeout in seconds.
        report: Optional dict filled on success with the serving details:
            {"model": slug, "attempts": n, "fallback": bool} — used by callers
            (e.g. the #6 confidence trace) to record which model really answered.
            On total failure the dict is not filled (the exception is raised).

    Returns:
        The assistant's response text.

    Raises:
        RuntimeError: If all models in the fallback chain fail.
    """
    models_to_try = [model or settings.primary_llm_model] + settings.fallback_models_list
    ordered = model_registry.order_chain(models_to_try)
    errors: list[str] = []
    attempts = 0

    async with httpx.AsyncClient(timeout=timeout) as client:
        for model_slug in ordered:
            attempts += 1
            try:
                if model_slug.startswith("gemini-"):
                    content = await _gemini_complete_with_retry(
                        model_slug, messages, temperature, max_tokens
                    )
                else:
                    content = await _rest_complete_with_retry(
                        client, model_slug, messages, temperature, max_tokens
                    )

                if not content:
                    # Some models return empty/null content on truncated runs —
                    # treat as a failed attempt and try the fallback chain.
                    model_registry.record(model_slug, False, "empty content")
                    errors.append(f"{model_slug}: empty content")
                    logger.warning(f"Empty content from {model_slug}, trying fallback...")
                    continue
                model_registry.record(model_slug, True)
                if report is not None:
                    report["model"] = model_slug
                    report["attempts"] = attempts
                    report["fallback"] = attempts > 1
                logger.info(f"LLM response from {model_slug} ({len(content)} chars)")
                return content

            except (httpx.HTTPStatusError, httpx.RequestError, KeyError) as exc:
                model_registry.record(model_slug, False, str(exc))
                errors.append(f"{model_slug}: {exc}")
                logger.warning(f"Model {model_slug} failed: {exc}. Trying fallback...")
                continue
            except Exception as exc:
                # Covers google.api_core.exceptions.* raised by the Gemini SDK.
                model_registry.record(model_slug, False, str(exc))
                errors.append(f"{model_slug}: {exc}")
                logger.warning(f"Model {model_slug} failed: {exc}. Trying fallback...")
                continue

    raise RuntimeError(
        "All LLM models exhausted.\n"
        + "\n".join(f"  - {err}" for err in errors)
        + "\nThe AI service is temporarily at capacity — try again in a moment."
    )


async def complete_stream(
    messages: list[dict],
    model: Optional[str] = None,
    temperature: float = 0.3,
    max_tokens: int = 4096,
    timeout: float = 120.0,
):
    """
    Streaming variant — yields text chunks as they arrive, token-by-token.

    SINGLE MODEL ONLY — no fallback chain (fallback is added separately later).
    Sends `stream: true` and parses the SSE lines from the provider, forwarding
    each `choices[0].delta.content` token. Stops at `data: [DONE]`.

    Raises:
        RuntimeError: on HTTP error or stream failure (caller decides how to recover).
    """
    model_slug = model or settings.primary_llm_model

    if model_slug.startswith("gemini-"):
        # Stream via the official SDK (blocking generator, drained in a thread).
        # Retry once on a rate limit before giving up on this model.
        _log_payload(model_slug, messages)
        stream = None
        first_chunk = None
        max_attempts = 2
        for attempt in range(1, max_attempts + 1):
            try:
                stream = await asyncio.to_thread(
                    _gemini_stream_sync, model_slug, messages, temperature, max_tokens
                )
                first_chunk = await asyncio.to_thread(next, stream)
                break
            except StopIteration:
                first_chunk = None
                break
            except Exception as exc:
                if _is_rate_limit(exc) and attempt < max_attempts:
                    delay = _retry_delay_from_exc(exc)
                    logger.warning(
                        f"[{model_slug}] stream rate limited (attempt {attempt}/{max_attempts}), "
                        f"retrying in {delay:.1f}s"
                    )
                    await asyncio.sleep(delay)
                    continue
                raise
        if first_chunk is not None:
            text = getattr(first_chunk, "text", "") or ""
            if text:
                yield text
        if stream is not None:
            while True:
                try:
                    chunk = await asyncio.to_thread(next, stream)
                except StopIteration:
                    break
                text = getattr(chunk, "text", "") or ""
                if text:
                    yield text
        return

    url = _chat_completions_url(model_slug)
    headers = _headers_for(model_slug)
    payload = {
        "model": model_slug,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": True,
    }

    max_attempts = 2
    async with httpx.AsyncClient(timeout=timeout) as client:
        for attempt in range(1, max_attempts + 1):
            _log_request("POST", url, headers, payload)
            async with client.stream(
                "POST",
                url,
                headers=headers,
                json=payload,
            ) as response:
                if response.status_code == 429:
                    body = (await response.aread()).decode("utf-8", errors="replace")
                    if attempt < max_attempts:
                        delay = _retry_after_headers(response.headers)
                        logger.warning(
                            f"[{model_slug}] stream HTTP 429 (attempt {attempt}/{max_attempts}), "
                            f"retrying in {delay:.1f}s: {body[:300]}"
                        )
                        await asyncio.sleep(delay)
                        break  # retry this model once before falling through
                    raise RuntimeError(
                        f"Stream failed for {model_slug} (HTTP 429): {body[:300]}"
                    )
                if response.status_code != 200:
                    body = (await response.aread()).decode("utf-8", errors="replace")
                    raise RuntimeError(
                        f"Stream failed for {model_slug} (HTTP {response.status_code}): {body[:300]}"
                    )

                async for line in response.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    chunk = line[len("data: "):]
                    if chunk.strip() == "[DONE]":
                        return
                    try:
                        data = json.loads(chunk)
                        delta = data["choices"][0]["delta"].get("content", "")
                        if delta:
                            yield delta
                    except (KeyError, json.JSONDecodeError):
                        continue
                return
