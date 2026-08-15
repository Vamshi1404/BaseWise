"""Integration tests for #5: llm_client.complete reports serving models and
reorders the fallback chain via the model reliability registry."""
import asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core import llm_client, model_registry

PRIMARY = "openai/test-primary"
FALLBACK = "gemini-test-fallback"


def _run(question: str, **kwargs) -> str:
    async def scenario():
        with patch.object(llm_client.settings, "primary_llm_model", PRIMARY), patch.object(
            llm_client.settings, "fallback_llm_models", FALLBACK
        ):
            return await llm_client.complete(
                [{"role": "user", "content": question}], **kwargs
            )

    return asyncio.run(scenario())


class TestCompleteReport:
    def setup_method(self):
        model_registry.reset()

    def test_primary_success_fills_report(self):
        with patch(
            "app.core.llm_client._rest_complete_with_retry",
            new=AsyncMock(return_value="ok"),
        ):
            report: dict = {}
            text = _run("hi", report=report)
        assert text == "ok"
        assert report == {"model": PRIMARY, "attempts": 1, "fallback": False}

    def test_fallback_used_and_reported(self):
        with patch(
            "app.core.llm_client._rest_complete_with_retry",
            new=AsyncMock(side_effect=RuntimeError("down")),
        ), patch(
            "app.core.llm_client._gemini_complete_with_retry",
            new=AsyncMock(return_value="ok"),
        ):
            report: dict = {}
            text = _run("hi", report=report)
        assert text == "ok"
        assert report["model"] == FALLBACK
        assert report["attempts"] == 2
        assert report["fallback"] is True

    def test_cooled_primary_skipped_on_next_call(self):
        # 3 consecutive failures puts the primary on cooldown; the fallback is
        # then tried FIRST and is not flagged as a fallback anymore.
        for _ in range(model_registry.COOLDOWN_AFTER):
            model_registry.record(PRIMARY, False, "boom")
        with patch(
            "app.core.llm_client._rest_complete_with_retry",
            new=AsyncMock(return_value="primary-ok"),
        ), patch(
            "app.core.llm_client._gemini_complete_with_retry",
            new=AsyncMock(return_value="fallback-ok"),
        ):
            report: dict = {}
            text = _run("hi", report=report)
        assert text == "fallback-ok"
        assert report == {"model": FALLBACK, "attempts": 1, "fallback": False}

    def test_success_clears_cooldown(self):
        for _ in range(model_registry.COOLDOWN_AFTER):
            model_registry.record(PRIMARY, False, "boom")
        assert model_registry.is_on_cooldown(PRIMARY)
        with patch(
            "app.core.llm_client._rest_complete_with_retry",
            new=AsyncMock(return_value="ok"),
        ):
            _run("hi")
        assert not model_registry.is_on_cooldown(PRIMARY)
        assert model_registry.stats(PRIMARY)["successes"] == 1

    def test_all_models_fail_raises_and_records(self):
        with patch(
            "app.core.llm_client._rest_complete_with_retry",
            new=AsyncMock(side_effect=RuntimeError("a")),
        ), patch(
            "app.core.llm_client._gemini_complete_with_retry",
            new=AsyncMock(side_effect=RuntimeError("b")),
        ):
            with pytest.raises(RuntimeError):
                _run("hi")
        assert model_registry.stats(PRIMARY)["consecutive_failures"] == 1
        assert model_registry.stats(FALLBACK)["consecutive_failures"] == 1
