"""Unit tests for deterministic chart detection (task 2.4).

Covers: bar, line (time series), pie (percentage/share), chart skip for
>15 categories, chart skip for unsuitable shapes, and graceful None on
empty/exception-prone input.
"""
import sys
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from app.core.agent_loop import (
    _build_chart_data,
    _is_numeric_column,
    _is_date_column,
    _is_share_column,
    MAX_CHART_CATEGORIES,
)


def _rows(cols: list[str], data: list[tuple]) -> list[dict]:
    return [dict(zip(cols, row)) for row in data]


class TestHelpers:
    def test_is_numeric_column_ints_and_floats(self):
        rows = _rows(["a", "b"], [(1, 2.5), (3, 4.0), (5, 6.5)])
        assert _is_numeric_column(rows, "a") is True
        assert _is_numeric_column(rows, "b") is True

    def test_is_numeric_column_numeric_strings(self):
        rows = _rows(["a"], [("10",), ("20",), ("30",)])
        assert _is_numeric_column(rows, "a") is True

    def test_is_numeric_column_mixed_non_numeric(self):
        rows = _rows(["a"], [("cat",), ("dog",), ("10",)])
        assert _is_numeric_column(rows, "a") is False

    def test_is_numeric_column_mostly_null(self):
        rows = _rows(["a"], [(None,), (None,), (5,)])
        assert _is_numeric_column(rows, "a") is True

    def test_is_date_column_by_name(self):
        rows = _rows(["created_at", "v"], [(datetime(2026, 1, 1), 1)])
        assert _is_date_column(rows, "created_at") is True

    def test_is_date_column_by_value(self):
        rows = _rows(["day", "v"], [("2026-01-01", 1), ("2026-01-02", 2)])
        assert _is_date_column(rows, "day") is True

    def test_is_date_column_false_for_categories(self):
        rows = _rows(["name", "v"], [("alice", 1), ("bob", 2)])
        assert _is_date_column(rows, "name") is False

    def test_is_share_column_by_name(self):
        rows = _rows(["segment", "pct"], [("a", 40), ("b", 60)])
        assert _is_share_column(rows, "pct") is True

    def test_is_share_column_by_value_on_unit_interval(self):
        rows = _rows(["segment", "ratio"], [("a", 0.4), ("b", 0.6)])
        assert _is_share_column(rows, "ratio") is True

    def test_is_share_column_false_for_counts(self):
        rows = _rows(["segment", "count"], [("a", 40), ("b", 60)])
        assert _is_share_column(rows, "count") is False


class TestBuildChartData:
    def test_bar_chart_two_columns_categorical_numeric(self):
        rows = _rows(
            ["category", "total"],
            [(f"cat{i}", i * 10) for i in range(5)],
        )
        spec = _build_chart_data(rows)
        assert spec is not None
        assert spec["type"] == "bar"
        assert spec["x_key"] == "category"
        assert "total" in spec["y_keys"]

    def test_line_chart_datetime_x_axis(self):
        rows = _rows(
            ["created_at", "revenue"],
            [(datetime(2026, 1, d), d * 100) for d in range(1, 8)],
        )
        spec = _build_chart_data(rows)
        assert spec is not None
        assert spec["type"] == "line"
        assert spec["x_key"] == "created_at"
        assert "revenue" in spec["y_keys"]

    def test_pie_chart_percentage_data(self):
        rows = _rows(
            ["region", "pct_share"],
            [("north", 30), ("south", 20), ("east", 50)],
        )
        spec = _build_chart_data(rows)
        assert spec is not None
        assert spec["type"] == "pie"
        assert spec["x_key"] == "region"
        assert spec["y_keys"] == ["pct_share"]

    def test_pie_chart_unit_interval_share(self):
        rows = _rows(
            ["region", "share"],
            [("north", 0.3), ("south", 0.2), ("east", 0.5)],
        )
        spec = _build_chart_data(rows)
        assert spec is not None
        assert spec["type"] == "pie"

    def test_skip_when_more_than_max_categories(self):
        rows = _rows(
            ["category", "total"],
            [(f"cat{i}", i) for i in range(MAX_CHART_CATEGORIES + 1)],
        )
        assert _build_chart_data(rows) is None

    def test_skip_when_single_column(self):
        rows = _rows(["only"], [(1,), (2,), (3,)])
        assert _build_chart_data(rows) is None

    def test_skip_when_no_numeric_column(self):
        rows = _rows(["name", "city"], [("a", "x"), ("b", "y"), ("c", "z")])
        assert _build_chart_data(rows) is None

    def test_skip_when_id_like_columns_only(self):
        rows = _rows(["id", "user_id"], [(1, 1), (2, 2), (3, 3)])
        assert _build_chart_data(rows) is None

    def test_empty_results_returns_none(self):
        assert _build_chart_data([]) is None

    def test_none_results_returns_none(self):
        assert _build_chart_data(None) is None

    def test_bar_chart_keeps_all_data_ordered(self):
        rows = _rows(["category", "total"], [("a", 1), ("b", 2), ("c", 3)])
        spec = _build_chart_data(rows)
        assert spec["data"] == rows

    def test_skip_non_id_related_single_numeric(self):
        # one categorical + one numeric -> still a valid bar chart
        rows = _rows(["name", "score"], [("a", 10), ("b", 20), ("c", 30)])
        spec = _build_chart_data(rows)
        assert spec is not None
        assert spec["type"] == "bar"

    def test_three_numeric_series_bar_chart(self):
        rows = _rows(
            ["category", "a", "b", "c"],
            [(f"cat{i}", i, i * 2, i * 3) for i in range(3)],
        )
        spec = _build_chart_data(rows)
        assert spec is not None
        assert spec["type"] == "bar"
        assert set(spec["y_keys"]) == {"a", "b", "c"}


class TestScatterDetection:
    def test_two_numerics_no_categorical_is_scatter(self):
        rows = _rows(
            ["distance_km", "final_cost"],
            [(10.0, 50.0), (25.0, 120.0), (40.0, 210.0)],
        )
        spec = _build_chart_data(rows)
        assert spec is not None
        assert spec["type"] == "scatter"
        assert spec["x_key"] == "distance_km"
        assert spec["y_keys"] == ["final_cost"]
        assert "z_key" not in spec

    def test_id_column_ignored_in_scatter(self):
        rows = _rows(
            ["id", "distance_km", "final_cost"],
            [(1, 10.0, 50.0), (2, 25.0, 120.0)],
        )
        spec = _build_chart_data(rows)
        assert spec is not None
        assert spec["type"] == "scatter"
        assert spec["x_key"] == "distance_km"
        assert spec["y_keys"] == ["final_cost"]

    def test_three_numerics_adds_bubble_z_key(self):
        rows = _rows(
            ["distance_km", "final_cost", "seats"],
            [(10.0, 50.0, 3), (25.0, 120.0, 5)],
        )
        spec = _build_chart_data(rows)
        assert spec is not None
        assert spec["type"] == "scatter"
        assert spec["z_key"] == "seats"

    def test_single_numeric_still_not_scatter(self):
        rows = _rows(["value"], [(10.0,), (20.0,), (30.0,)])
        assert _build_chart_data(rows) is None

    def test_scatter_intent_with_categorical(self):
        rows = _rows(
            ["city", "distance_km", "final_cost"],
            [("hyd", 10.0, 50.0), ("blr", 25.0, 120.0), ("hyd", 40.0, 210.0)],
        )
        spec = _build_chart_data(rows, question="show the correlation between distance and cost")
        assert spec is not None
        assert spec["type"] == "scatter"
        assert spec["x_key"] == "distance_km"
        assert spec["y_keys"] == ["final_cost"]

    def test_no_scatter_intent_keeps_bar(self):
        rows = _rows(
            ["city", "distance_km", "final_cost"],
            [("hyd", 10.0, 50.0), ("blr", 25.0, 120.0)],
        )
        spec = _build_chart_data(rows, question="total cost per city")
        assert spec is not None
        assert spec["type"] == "bar"


class TestFunnelDetection:
    def test_funnel_intent_single_status_column(self):
        rows = _rows(
            ["status", "count"],
            [("accepted", 12), ("completed", 8), ("cancelled", 4), ("requested", 20)],
        )
        spec = _build_chart_data(rows, question="show the conversion funnel for ride requests")
        assert spec is not None
        assert spec["type"] == "funnel"
        assert spec["x_key"] == "status"
        assert spec["y_keys"] == ["count"]
        # sorted largest-first for the drop-off visual
        assert [r["status"] for r in spec["data"]] == ["requested", "accepted", "completed", "cancelled"]

    def test_ranking_question_without_intent_stays_bar(self):
        rows = _rows(
            ["status", "count"],
            [("accepted", 12), ("completed", 8), ("cancelled", 4), ("requested", 20)],
        )
        spec = _build_chart_data(rows, question="how many rides in each status")
        assert spec is not None
        assert spec["type"] == "bar"

    def test_funnel_requires_3_8_categories(self):
        rows = _rows(
            ["status", "count"],
            [("on", 10), ("off", 5)],
        )
        spec = _build_chart_data(rows, question="conversion funnel")
        assert spec is not None
        assert spec["type"] == "bar"  # too few stages to be a funnel

    def test_funnel_ignores_date_column(self):
        rows = _rows(
            ["created_at", "status", "count"],
            [("2026-01-01", "a", 10), ("2026-01-02", "b", 5)],
        )
        spec = _build_chart_data(rows, question="conversion funnel")
        assert spec is not None
        assert spec["type"] == "line"  # time series wins


class TestTreemapDetection:
    def test_treemap_intent_two_categoricals(self):
        rows = _rows(
            ["city", "status", "count"],
            [
                ("hyd", "completed", 8),
                ("hyd", "cancelled", 2),
                ("blr", "completed", 5),
                ("blr", "cancelled", 4),
                ("chn", "completed", 3),
            ],
        )
        spec = _build_chart_data(rows, question="break down rides by city then status as a treemap")
        assert spec is not None
        assert spec["type"] == "treemap"
        assert spec["value_key"] == "count"
        # parent sorted by total descending: hyd(10) > blr(9) > chn(3)
        assert [p["name"] for p in spec["data"]] == ["hyd", "blr", "chn"]
        # children sorted by value descending
        assert [c["name"] for c in spec["data"][0]["children"]] == ["completed", "cancelled"]
        assert spec["data"][0]["children"][0]["value"] == 8

    def test_no_treemap_intent_keeps_bar(self):
        rows = _rows(
            ["city", "status", "count"],
            [("hyd", "completed", 8), ("blr", "cancelled", 4)],
        )
        spec = _build_chart_data(rows, question="list counts")
        assert spec is not None
        assert spec["type"] == "bar"
