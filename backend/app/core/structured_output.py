"""
Structured-output parsing with self-healing (project.md Section 4.2).

LLM responses — especially from reasoning models — routinely wrap JSON in
markdown fences, prefix it with thinking text, or append trailing prose.
`extract_json` recovers the value robustly (direct parse, fence-aware, then a
balanced-brace/bracket scan that ignores non-JSON surroundings).

When parsing still fails, `parse_llm_json` makes ONE corrective follow-up call
that feeds the previous output and the exact parser error back to the model so
it fixes its own formatting, before the caller degrades to regex/heuristic
extraction. This turns a wasted, corrupted call into a corrected one instead of
silently shipping garbage SQL.
"""
import json
import logging
import re
from typing import Any, Callable, Optional

from app.core import llm_client

logger = logging.getLogger(__name__)

# Cap on how much of a failed response is echoed into the corrective call.
MAX_REPAIR_CONTEXT_CHARS = 12000

_FENCE_RE = re.compile(r"```(?:json)?(.*?)```", re.DOTALL)


def _balanced_scan(text: str, start: int) -> Optional[str]:
    """Extract a balanced JSON value (object or array) beginning at `start`.

    Tracks nesting depth and skips string literals (with escape handling) so
    prose before/after the value, or braces/quotes inside string data, cannot
    derail it. Returns None when the value is unterminated or mismatched.
    """
    open_ch = text[start]
    stack: list[str] = [open_ch]
    i = start + 1
    in_string = False
    escaped = False
    while i < len(text):
        ch = text[i]
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
        else:
            if ch == '"':
                in_string = True
            elif ch in "{[":
                stack.append(ch)
            elif ch == "}" and stack and stack[-1] == "{":
                stack.pop()
                if not stack:
                    return text[start : i + 1]
            elif ch == "]" and stack and stack[-1] == "[":
                stack.pop()
                if not stack:
                    return text[start : i + 1]
            elif ch in "}]":
                # Mismatched close bracket — the value is malformed.
                return None
        i += 1
    return None


def extract_json(raw: Any) -> tuple[Optional[Any], str]:
    """Robustly extract a JSON value from an LLM response string.

    Tries, in order: a direct parse of the full text, any code-fence contents,
    then a balanced-brace/bracket scan of the first top-level value. This
    recovers the JSON even when it is wrapped in fences, prefixed with thinking
    text, or followed by trailing prose.

    Returns:
        (value, "") on success, or (None, error_message) on failure where
        error_message is human-readable (including the underlying
        json.JSONDecodeError when available).
    """
    if raw is None:
        return None, "empty response (None)"
    text = str(raw).strip()
    if not text:
        return None, "empty response"

    candidates: list[str] = []
    fence = _FENCE_RE.search(text)
    if fence and fence.group(1).strip():
        candidates.append(fence.group(1).strip())

    for i, ch in enumerate(text):
        if ch in "{[":
            segment = _balanced_scan(text, i)
            if segment:
                candidates.append(segment)
            break

    candidates.append(text)

    last_error = "not valid JSON"
    for candidate in candidates:
        try:
            return json.loads(candidate), ""
        except (json.JSONDecodeError, ValueError, TypeError) as exc:
            last_error = str(exc)
    return None, last_error


def _correction_messages(
    previous: str, parse_error: str, expected_shape: str
) -> list[dict]:
    """Build the corrective follow-up prompt for a failed JSON parse."""
    return [
        {
            "role": "system",
            "content": (
                "Your previous response was not valid JSON. Rewrite it as a single "
                f"valid JSON value ({expected_shape}) with the exact same content and "
                "meaning. Fix ONLY the formatting — keep the underlying data identical. "
                "Respond with ONLY the JSON value: no markdown fences, no code blocks, "
                "no prose before or after."
            ),
        },
        {
            "role": "user",
            "content": (
                "Your previous output (which failed to parse):\n"
                f"<PREVIOUS_OUTPUT>\n{previous}\n</PREVIOUS_OUTPUT>\n\n"
                f"Parser error: {parse_error}\n\n"
                "Return the corrected JSON now."
            ),
        },
    ]


async def parse_llm_json(
    raw: str,
    *,
    expected_shape: str = "a JSON value",
    validate: Optional[Callable[[Any], bool]] = None,
    model: Optional[str] = None,
    temperature: float = 0.0,
    max_tokens: int = 4096,
) -> tuple[Optional[Any], str]:
    """Parse `raw` as JSON, self-healing with one corrective LLM call.

    On a parse failure — or on valid JSON with the wrong shape — the previous
    output and the exact error are fed back to the model, which is asked to
    re-emit the same content as valid JSON of the expected shape. The corrected
    output is parsed once more; if it still fails, the caller receives the
    original error so it can fall back to its regex/heuristic path.

    The corrective call goes through llm_client.complete, inheriting the
    existing provider fallback/retry behavior.

    Returns:
        (value, "") on success or (None, error_message) on failure.
    """
    value, error = extract_json(raw)
    if value is not None and (validate is None or validate(value)):
        return value, ""

    if value is not None:
        error = f"expected {expected_shape}, got {type(value).__name__}"

    repair_context = str(raw)[:MAX_REPAIR_CONTEXT_CHARS]
    try:
        corrected = await llm_client.complete(
            _correction_messages(repair_context, error, expected_shape),
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
        )
    except Exception as exc:
        logger.warning(f"JSON repair call failed: {exc}")
        return None, error

    if not corrected or not corrected.strip():
        return None, error

    repaired, repaired_error = extract_json(corrected)
    if repaired is None or (validate is not None and not validate(repaired)):
        logger.warning(
            f"JSON repair still failed ({repaired_error}); falling back. "
            f"Original error: {error}"
        )
        return None, error
    return repaired, ""
