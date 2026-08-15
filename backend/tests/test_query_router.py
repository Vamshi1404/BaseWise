"""Tests for the pre-pipeline intent router (#3).

classify_route is deterministic and never calls the LLM; route_request adds one
optional escalation call only for the genuinely ambiguous band.
"""
import asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core import query_router
from app.core.query_router import (
    ROUTE_CONVERSATIONAL,
    ROUTE_FULL,
    ROUTE_SIMPLE,
    classify_route,
    route_request,
)

SCHEMA = {
    "dialect": "postgres",
    "tables": [
        {
            "name": "users",
            "columns": [
                {"name": "id", "type": "INTEGER", "nullable": False, "primary_key": True},
                {"name": "email", "type": "VARCHAR", "nullable": True, "primary_key": False},
            ],
            "primary_keys": ["id"],
            "foreign_keys": [],
            "row_count": 100,
        },
        {
            "name": "orders",
            "columns": [
                {"name": "id", "type": "INTEGER", "nullable": False, "primary_key": True},
                {"name": "user_id", "type": "INTEGER", "nullable": True, "primary_key": False},
                {"name": "total_amount", "type": "NUMERIC", "nullable": True, "primary_key": False},
            ],
            "primary_keys": ["id"],
            "foreign_keys": [{"column": "user_id", "references_table": "users", "references_column": "id"}],
            "row_count": 50,
        },
    ],
}


class TestConversationalRouting:
    def test_greeting(self):
        d = classify_route("hi there!", SCHEMA)
        assert d.route == ROUTE_CONVERSATIONAL
        assert not d.needs_escalation

    def test_thanks(self):
        d = classify_route("thanks a lot, that helps", SCHEMA)
        assert d.route == ROUTE_CONVERSATIONAL

    def test_ack_exact_word(self):
        d = classify_route("ok", SCHEMA)
        assert d.route == ROUTE_CONVERSATIONAL

    def test_ack_with_query_is_not_conversational(self):
        d = classify_route("ok show me the orders", SCHEMA)
        assert d.route != ROUTE_CONVERSATIONAL

    def test_smalltalk(self):
        d = classify_route("how are you?", SCHEMA)
        assert d.route == ROUTE_CONVERSATIONAL

    def test_capability(self):
        d = classify_route("what can you do?", SCHEMA)
        assert d.route == ROUTE_CONVERSATIONAL

    def test_empty_message(self):
        d = classify_route("   ", SCHEMA)
        assert d.route == ROUTE_CONVERSATIONAL

    def test_greeting_with_schema_ref_is_a_query(self):
        # "hi" + a real data ask must NOT be short-circuited.
        d = classify_route("hi, can you show me the users", SCHEMA)
        assert d.route != ROUTE_CONVERSATIONAL


class TestQueryRouting:
    def test_clean_single_table_is_simple(self):
        d = classify_route("show me users", SCHEMA)
        assert d.route == ROUTE_SIMPLE
        assert not d.needs_escalation

    def test_singular_question_matches_plural_table(self):
        d = classify_route("list each user", SCHEMA)
        assert d.route == ROUTE_SIMPLE

    def test_aggregation_is_full(self):
        d = classify_route("total sales by region", SCHEMA)
        assert d.route == ROUTE_FULL

    def test_join_across_tables_is_full(self):
        d = classify_route("show me users and their orders", SCHEMA)
        assert d.route == ROUTE_FULL

    def test_history_reference_is_full(self):
        d = classify_route("same thing for last month", SCHEMA)
        assert d.route == ROUTE_FULL

    def test_destructive_intent_is_full(self):
        d = classify_route("delete all inactive users", SCHEMA)
        assert d.route == ROUTE_FULL
        assert not d.needs_escalation

    def test_write_request_is_full(self):
        d = classify_route("add a new user named bob", SCHEMA)
        assert d.route == ROUTE_FULL

    def test_generic_query_words_without_schema_hit_are_full(self):
        d = classify_route("show me the growth", SCHEMA)
        assert d.route == ROUTE_FULL
        assert not d.needs_escalation


class TestEscalationBand:
    def test_ambiguous_offtopic_flags_escalation(self):
        d = classify_route("tell me a joke", SCHEMA)
        assert d.route == ROUTE_FULL
        assert d.needs_escalation

    def test_ambiguous_needs_no_schema(self):
        d = classify_route("what do you think?", SCHEMA)
        assert d.needs_escalation

    def test_neutral_is_never_escalated(self):
        # A data-flavored turn is answered by the pipeline, not an extra call.
        d = classify_route("show me the top products", SCHEMA)
        assert not d.needs_escalation


class TestEscalation:
    def _request(self, question, escalation=True):
        async def scenario():
            with patch(
                "app.core.query_router.settings.query_router_escalation", escalation
            ):
                return await route_request(question, SCHEMA)

        return asyncio.run(scenario())

    def test_escalates_ambiguous_to_conversational(self):
        with patch(
            "app.core.query_router.llm_client.complete",
            new=AsyncMock(
                return_value='{"category": "conversational", "complexity": "simple", "reason": "chit-chat"}'
            ),
        ) as mock:
            d = self._request("tell me a joke")
        assert d.route == ROUTE_CONVERSATIONAL
        assert not d.needs_escalation
        mock.assert_awaited_once()

    def test_escalates_ambiguous_to_simple_query(self):
        with patch(
            "app.core.query_router.llm_client.complete",
            new=AsyncMock(
                return_value='{"category": "query", "complexity": "simple", "reason": "wants data"}'
            ),
        ):
            d = self._request("i need help with my data")
        assert d.route == ROUTE_SIMPLE

    def test_escalates_ambiguous_to_write(self):
        with patch(
            "app.core.query_router.llm_client.complete",
            new=AsyncMock(
                return_value='{"category": "write", "complexity": "complex", "reason": "wants a write"}'
            ),
        ):
            d = self._request("I need to put something in")
        assert d.route == ROUTE_FULL

    def test_escalation_failure_defaults_to_full(self):
        with patch(
            "app.core.query_router.llm_client.complete",
            new=AsyncMock(side_effect=RuntimeError("down")),
        ):
            d = self._request("tell me a joke")
        assert d.route == ROUTE_FULL
        assert not d.needs_escalation

    def test_escalation_disabled_skips_llm_call(self):
        with patch(
            "app.core.query_router.llm_client.complete",
            new=AsyncMock(),
        ) as mock:
            d = self._request("tell me a joke", escalation=False)
        assert d.route == ROUTE_FULL
        mock.assert_not_awaited()

    def test_non_ambiguous_turn_never_calls_llm(self):
        with patch(
            "app.core.query_router.llm_client.complete",
            new=AsyncMock(),
        ) as mock:
            d = self._request("show me users")
        assert d.route == ROUTE_SIMPLE
        mock.assert_not_awaited()


class TestConversationalHelpers:
    def test_canned_reply_known(self):
        assert query_router.canned_reply("greeting")
        assert query_router.canned_reply("thanks")
        assert query_router.canned_reply("ack")

    def test_canned_reply_unknown_is_none(self):
        assert query_router.canned_reply("other") is None
        assert query_router.canned_reply(None) is None

    def test_detect_category(self):
        assert query_router.detect_conversation_category("hello") == "greeting"
        assert query_router.detect_conversation_category("thanks!") == "thanks"
        assert query_router.detect_conversation_category("how are you") == "smalltalk"
        assert query_router.detect_conversation_category("show me users") is None
