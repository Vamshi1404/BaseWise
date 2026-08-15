"""
#5: Model reliability registry.

Tracks which model actually served each LLM call and how it is performing, so
the fallback chain can prefer healthy models. Free-tier providers (Groq/Gemini)
flap — a model can sit inside a rate-limit or outage window while its peers
stay healthy, and blindly trying the primary first burns latency and quota on
every request during that window.

The registry keeps a small in-memory score per model slug (calls, successes,
failures, consecutive failures, last error, last used). `order_chain` simply
moves models that are on a consecutive-failure cooldown to the END of the
attempt order; everything else keeps its configured order. It never removes or
hard-blocks a model — only reorders attempts, and a successful call clears the
cooldown instantly.

In-memory only: a process restart rebuilds it from scratch, which is correct
behaviour for a health signal — stale observations should not outlive a restart.
"""
import time
from typing import Optional

COOLDOWN_AFTER = 3  # consecutive failures before a model is deprioritized

_registry: dict[str, dict] = {}


def reset() -> None:
    """Clear all observations (used by tests and on demand)."""
    _registry.clear()


def _entry(slug: str) -> dict:
    return _registry.setdefault(
        slug,
        {
            "calls": 0,
            "successes": 0,
            "failures": 0,
            "consecutive_failures": 0,
            "last_error": None,
            "last_used_at": None,
        },
    )


def record(slug: str, success: bool, error: Optional[str] = None) -> None:
    """Record one attempt outcome for a model slug."""
    entry = _entry(slug)
    entry["calls"] += 1
    entry["last_used_at"] = time.time()
    if success:
        entry["successes"] += 1
        entry["consecutive_failures"] = 0
    else:
        entry["failures"] += 1
        entry["consecutive_failures"] += 1
        entry["last_error"] = error


def stats(slug: str) -> dict:
    """Snapshot of a model's recorded observations."""
    return dict(_entry(slug))


def is_on_cooldown(slug: str) -> bool:
    return _entry(slug)["consecutive_failures"] >= COOLDOWN_AFTER


def order_chain(models: list[str]) -> list[str]:
    """Preserve the configured order but move cooldown models to the end.

    The returned list contains exactly the same slugs as the input, never
    drops a model, and keeps relative order within each group.
    """
    healthy = [m for m in models if not is_on_cooldown(m)]
    cooling = [m for m in models if is_on_cooldown(m)]
    return healthy + cooling
