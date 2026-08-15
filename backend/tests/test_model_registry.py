"""Unit tests for the #5 model reliability registry."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core import model_registry


class TestRegistry:
    def setup_method(self):
        model_registry.reset()

    def test_record_success_clears_cooldown(self):
        model_registry.record("m1", False)
        model_registry.record("m1", False)
        assert model_registry.is_on_cooldown("m1") is False  # below threshold
        model_registry.record("m1", False)
        assert model_registry.is_on_cooldown("m1") is True
        model_registry.record("m1", True)
        assert model_registry.is_on_cooldown("m1") is False

    def test_stats_accumulate(self):
        model_registry.record("m1", True)
        model_registry.record("m1", True)
        model_registry.record("m1", False, "boom")
        stats = model_registry.stats("m1")
        assert stats["calls"] == 3
        assert stats["successes"] == 2
        assert stats["failures"] == 1
        assert stats["consecutive_failures"] == 1
        assert stats["last_error"] == "boom"
        assert stats["last_used_at"] is not None

    def test_unknown_model_stats_start_empty(self):
        stats = model_registry.stats("never-seen")
        assert stats["calls"] == 0
        assert stats["consecutive_failures"] == 0

    def test_order_chain_preserves_healthy_order(self):
        assert model_registry.order_chain(["a", "b", "c"]) == ["a", "b", "c"]

    def test_order_chain_moves_cooling_to_end(self):
        for _ in range(model_registry.COOLDOWN_AFTER):
            model_registry.record("b", False, "x")
        assert model_registry.order_chain(["a", "b", "c"]) == ["a", "c", "b"]

    def test_order_chain_never_drops_models(self):
        for _ in range(model_registry.COOLDOWN_AFTER):
            model_registry.record("a", False, "x")
            model_registry.record("c", False, "y")
        result = model_registry.order_chain(["a", "b", "c"])
        assert set(result) == {"a", "b", "c"}
        assert result == ["b", "a", "c"]

    def test_reset_clears_everything(self):
        model_registry.record("m1", True)
        model_registry.reset()
        assert model_registry.stats("m1")["calls"] == 0
