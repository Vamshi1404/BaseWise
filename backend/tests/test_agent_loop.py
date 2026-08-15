"""Integration tests for the NL→SQL pipeline wiring of #1 and #2.

#1: pass 1/pass 2 structured output self-heals — a malformed (or wrong-shape)
    response triggers one corrective follow-up call instead of regex garbage.
#2: a failed sandbox run triggers one bounded repair call that feeds the error
    back; the corrected SQL re-runs and succeeds.
#3: conversational turns are short-circuited by the pre-pipeline router — zero
    SQL, zero sandbox, zero LLM calls for canned replies.
"""
import asyncio
import json
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.agent_loop import run_nl_to_sql
from app.core.sandbox import SandboxResult

SCHEMA = {
    "dialect": "postgres",
    "tables": [
        {
            "name": "users",
            "columns": [
                {"name": "id", "type": "INTEGER", "nullable": False, "primary_key": True},
                {"name": "name", "type": "VARCHAR", "nullable": True, "primary_key": False},
                {"name": "active", "type": "BOOLEAN", "nullable": True, "primary_key": False},
            ],
            "primary_keys": ["id"],
            "foreign_keys": [],
            "row_count": 100,
            "sample_rows": [],
            "column_stats": {},
        }
    ],
}

# Confidence 0.85 (< the #4 early-exit threshold of 0.9) so these #1/#2 tests
# always run pass 2 and their LLM-call-count assertions stay stable.
PASS1_OK = (
    '{"sql": "SELECT * FROM users", "explanation": "Lists all users.", '
    '"confidence": 0.85, "reasoning": "direct table scan"}'
)

PASS2_OK = (
    '{"approved_sql": "SELECT * FROM users", "issues_found": [], '
    '"confidence": 0.9, "changes_made": "none"}'
)

REPAIR_OK = (
    '{"sql": "SELECT * FROM users WHERE active = TRUE", '
    '"explanation": "column usrs.active does not exist -> users.active"}'
)

MALFORMED_PASS1 = (
    '{"sql": "SELECT * FROM users", "explanation": "Lists all users.", '
    '"confidence": 0.95, "reasoning": "direct table scan",}'
)

WRONG_SHAPE_PASS1 = '["SELECT * FROM users"]'

EXEC_ERROR = "UndefinedColumn: column usrs.active does not exist"

# --- #4 early-exit fixtures: pass-1 confidence 0.95 (>= the 0.9 threshold) ---

PASS1_HIGH = (
    '{"sql": "SELECT name FROM users", "explanation": "Lists user names.", '
    '"confidence": 0.95, "reasoning": "direct table scan"}'
)

PASS1_HIGH_BAD_TABLE = (
    '{"sql": "SELECT * FROM nope", "explanation": "Lists from a fake table.", '
    '"confidence": 0.95, "reasoning": "hallucinated table"}'
)

PASS1_HIGH_WRITE = (
    '{"sql": "INSERT INTO users (name) VALUES (\'bob\')", '
    '"explanation": "Adds a user.", "confidence": 0.95, "reasoning": "write"}'
)

PASS2_WRITE = (
    '{"approved_sql": "INSERT INTO users (name) VALUES (\'bob\')", '
    '"issues_found": [], "confidence": 0.9, "changes_made": "none"}'
)


def _success_result(rows: list[dict] | None = None) -> SandboxResult:
    payload = json.dumps(
        {
            "rows": rows or [{"id": 1, "name": "Alice", "active": True}],
            "row_count": len(rows or [{"id": 1}]),
            "rows_affected": 0,
            "returns_rows": True,
        }
    )
    return SandboxResult(
        stdout=payload,
        stderr="",
        error=None,
        results=[],
        execution_ms=10,
        sandbox_session_id="test-sandbox",
        success=True,
    )


def _fail_result(error: str) -> SandboxResult:
    return SandboxResult(
        stdout="",
        stderr="",
        error=error,
        results=[],
        execution_ms=5,
        sandbox_session_id="test-sandbox",
        success=False,
    )


def _write_success_result() -> SandboxResult:
    payload = json.dumps({"rows": [], "row_count": 0, "rows_affected": 1, "returns_rows": False})
    return SandboxResult(
        stdout=payload,
        stderr="",
        error=None,
        results=[],
        execution_ms=5,
        sandbox_session_id="test-sandbox",
        success=True,
    )


async def _fake_stream(messages, **kwargs):
    yield "Here are your results."


def _run_pipeline(*, complete_side_effect, sandbox_side_effect):
    async def scenario():
        with patch(
            "app.core.llm_client.complete",
            new=AsyncMock(side_effect=complete_side_effect),
        ) as mock, patch(
            "app.core.llm_client.complete_stream", new=_fake_stream
        ), patch(
            "app.core.agent_loop.run_in_sandbox", side_effect=sandbox_side_effect
        ) as sandbox:
            result = await run_nl_to_sql(
                question="List all users",
                schema=SCHEMA,
                db_connection_url="postgresql://u:p@host/db",
            )
        return result, mock, sandbox

    return asyncio.run(scenario())


class TestPass1SelfHealing:
    def test_malformed_pass1_self_heals(self):
        result, mock, sandbox = _run_pipeline(
            complete_side_effect=[MALFORMED_PASS1, PASS1_OK, PASS2_OK],
            sandbox_side_effect=[_success_result()],
        )
        assert result["status"] == "success"
        assert result["sql"] == "SELECT * FROM users"
        # pass1 (malformed) + repair + pass2 = 3 calls, no regex fallback
        assert mock.await_count == 3
        sandbox.assert_called_once()

    def test_wrong_shape_pass1_self_heals(self):
        result, mock, sandbox = _run_pipeline(
            complete_side_effect=[WRONG_SHAPE_PASS1, PASS1_OK, PASS2_OK],
            sandbox_side_effect=[_success_result()],
        )
        assert result["status"] == "success"
        assert result["sql"] == "SELECT * FROM users"
        assert mock.await_count == 3
        sandbox.assert_called_once()

    def test_valid_pass1_uses_no_repair_call(self):
        result, mock, sandbox = _run_pipeline(
            complete_side_effect=[PASS1_OK, PASS2_OK],
            sandbox_side_effect=[_success_result()],
        )
        assert result["status"] == "success"
        assert result["sql"] == "SELECT * FROM users"
        assert mock.await_count == 2
        sandbox.assert_called_once()


class TestExecutionRetry:
    def test_failed_run_repairs_and_retries(self):
        result, mock, sandbox = _run_pipeline(
            complete_side_effect=[PASS1_OK, PASS2_OK, REPAIR_OK],
            sandbox_side_effect=[_fail_result(EXEC_ERROR), _success_result()],
        )
        assert result["status"] == "success"
        assert result["sql"] == "SELECT * FROM users WHERE active = TRUE"
        assert sandbox.call_count == 2

        # The repair call must have received the exact execution error.
        repair_messages = mock.await_args_list[2].args[0]
        user_content = repair_messages[1]["content"]
        assert EXEC_ERROR in user_content
        assert "SELECT * FROM users" in user_content

    def test_failed_run_repair_fails_keeps_original_error(self):
        result, mock, sandbox = _run_pipeline(
            complete_side_effect=[PASS1_OK, PASS2_OK, RuntimeError("all models down")],
            sandbox_side_effect=[_fail_result(EXEC_ERROR)],
        )
        assert result["status"] == "error"
        assert result["error"] == EXEC_ERROR
        assert sandbox.call_count == 1

    def test_failed_run_repair_returns_same_sql_no_rereun(self):
        # Model "repairs" by echoing the identical SQL — avoid a pointless rerun.
        same_sql = '{"sql": "SELECT * FROM users", "explanation": "unchanged"}'
        result, mock, sandbox = _run_pipeline(
            complete_side_effect=[PASS1_OK, PASS2_OK, same_sql],
            sandbox_side_effect=[_fail_result(EXEC_ERROR)],
        )
        assert result["status"] == "error"
        assert sandbox.call_count == 1


class TestConversationalShortCircuit:
    def test_greeting_never_touches_llm_or_sandbox(self):
        async def scenario():
            from unittest.mock import MagicMock

            with patch(
                "app.core.llm_client.complete", new=AsyncMock()
            ) as mock, patch(
                "app.core.llm_client.complete_stream",
                new=MagicMock(side_effect=_fake_stream),
            ) as stream, patch(
                "app.core.agent_loop.run_in_sandbox"
            ) as sandbox:
                result = await run_nl_to_sql(
                    question="hi there",
                    schema=SCHEMA,
                    db_connection_url="postgresql://u:p@host/db",
                )
            return result, mock, stream, sandbox

        result, mock, stream, sandbox = asyncio.run(scenario())
        assert result["status"] == "success"
        assert result["sql"] == ""
        assert result["route"] == "conversational"
        assert result["summary"]
        mock.assert_not_awaited()
        stream.assert_not_called()
        sandbox.assert_not_called()

    def test_acknowledgement_uses_canned_reply(self):
        async def scenario():
            with patch(
                "app.core.llm_client.complete", new=AsyncMock()
            ) as mock, patch(
                "app.core.llm_client.complete_stream", new=_fake_stream
            ), patch(
                "app.core.agent_loop.run_in_sandbox"
            ) as sandbox:
                result = await run_nl_to_sql(
                    question="got it",
                    schema=SCHEMA,
                    db_connection_url="postgresql://u:p@host/db",
                )
            return result, mock, sandbox

        result, mock, sandbox = asyncio.run(scenario())
        assert result["status"] == "success"
        assert result["route"] == "conversational"
        assert "Got it" in result["summary"]
        mock.assert_not_awaited()
        sandbox.assert_not_called()

    def test_data_question_still_runs_pipeline(self):
        # A normal query must be unaffected by the router (route label only).
        result, mock, sandbox = _run_pipeline(
            complete_side_effect=[PASS1_OK, PASS2_OK],
            sandbox_side_effect=[_success_result()],
        )
        assert result["status"] == "success"
        assert result["sql"] == "SELECT * FROM users"
        assert result["route"] in ("simple_query", "full_pipeline")
        assert mock.await_count == 2
        sandbox.assert_called_once()


class TestEarlyExit:
    def test_high_confidence_simple_read_skips_pass2(self):
        result, mock, sandbox = _run_pipeline(
            complete_side_effect=[PASS1_HIGH],
            sandbox_side_effect=[_success_result()],
        )
        assert result["status"] == "success"
        assert result["pass2_skipped"] is True
        assert result["sql"] == "SELECT name FROM users"
        # pass 1 only — no pass 2 call, no repair call
        assert mock.await_count == 1
        sandbox.assert_called_once()
        # rebalanced composite: 0.7*0.95 + 0.3*1.0 = 0.965 -> 0.96 (banker's rounding)
        assert result["confidence_score"] == 0.96

    def test_low_confidence_never_skips_pass2(self):
        result, mock, sandbox = _run_pipeline(
            complete_side_effect=[PASS1_OK, PASS2_OK],
            sandbox_side_effect=[_success_result()],
        )
        assert result["pass2_skipped"] is False
        assert mock.await_count == 2

    def test_unknown_table_vetoes_skip(self):
        result, mock, sandbox = _run_pipeline(
            complete_side_effect=[PASS1_HIGH_BAD_TABLE, PASS2_OK],
            sandbox_side_effect=[_success_result()],
        )
        assert result["pass2_skipped"] is False
        assert mock.await_count == 2
        sandbox.assert_called_once()

    def test_write_never_skips_pass2(self):
        async def scenario():
            with patch(
                "app.core.llm_client.complete",
                new=AsyncMock(side_effect=[PASS1_HIGH_WRITE, PASS2_WRITE]),
            ) as mock, patch(
                "app.core.llm_client.complete_stream", new=_fake_stream
            ), patch(
                "app.core.agent_loop.run_in_sandbox",
                side_effect=[_write_success_result()],
            ) as sandbox:
                result = await run_nl_to_sql(
                    question="List all users",
                    schema=SCHEMA,
                    db_connection_url="postgresql://u:p@host/db",
                )
            return result, mock, sandbox

        result, mock, sandbox = asyncio.run(scenario())
        assert result["pass2_skipped"] is False
        assert mock.await_count == 2
        sandbox.assert_called_once()


class TestConfidenceTrace:
    def test_normal_run_trace_reflects_composite(self):
        result, mock, sandbox = _run_pipeline(
            complete_side_effect=[PASS1_OK, PASS2_OK],
            sandbox_side_effect=[_success_result()],
        )
        trace = result["confidence_trace"]
        assert trace is not None
        assert trace["composite"] == result["confidence_score"]
        assert trace["label"] == result["confidence_label"]
        assert trace["formula"] == "0.3*pass1 + 0.4*pass2 + 0.3*execution"
        assert trace["weights"] == {"pass1": 0.3, "pass2": 0.4, "execution": 0.3}
        assert trace["components"]["pass1"]["score"] == 0.85
        assert trace["components"]["pass2"]["score"] == 0.9
        assert trace["components"]["pass2"]["skipped"] is False
        assert trace["components"]["execution"]["success"] is True
        assert trace["components"]["routing"]["route"] in ("simple_query", "full_pipeline")
        assert trace["notes"] == []

    def test_early_exit_trace_uses_rebalanced_weights(self):
        result, mock, sandbox = _run_pipeline(
            complete_side_effect=[PASS1_HIGH],
            sandbox_side_effect=[_success_result()],
        )
        trace = result["confidence_trace"]
        assert trace["formula"] == "0.7*pass1 + 0.3*execution"
        assert trace["weights"] == {"pass1": 0.7, "pass2": 0.0, "execution": 0.3}
        assert trace["components"]["pass2"]["skipped"] is True
        assert trace["components"]["pass2"]["score"] is None
        assert trace["components"]["pass2"]["skip_reason"]
        assert any("skipped" in n for n in trace["notes"])

    def test_self_healed_pass1_trace_notes_it(self):
        result, mock, sandbox = _run_pipeline(
            complete_side_effect=[MALFORMED_PASS1, PASS1_OK, PASS2_OK],
            sandbox_side_effect=[_success_result()],
        )
        trace = result["confidence_trace"]
        assert trace["components"]["pass1"]["self_healed"] is True
        assert any("self-heal" in n for n in trace["notes"])

    def test_repair_trace_records_execution_retry(self):
        result, mock, sandbox = _run_pipeline(
            complete_side_effect=[PASS1_OK, PASS2_OK, REPAIR_OK],
            sandbox_side_effect=[_fail_result(EXEC_ERROR), _success_result()],
        )
        trace = result["confidence_trace"]
        exec_comp = trace["components"]["execution"]
        assert exec_comp["repair_attempted"] is True
        assert exec_comp["retried"] is True
        assert exec_comp["success"] is True
        assert any("repaired" in n for n in trace["notes"])

    def test_trace_records_serving_models(self):
        async def side_effect(messages, **kwargs):
            report = kwargs.get("report")
            if report is not None:
                report.update({"model": "openai/gpt-oss-120b", "attempts": 1, "fallback": False})
            system = messages[0]["content"]
            return PASS1_OK if "expert SQL assistant" in system else PASS2_OK

        async def scenario():
            with patch(
                "app.core.llm_client.complete",
                new=AsyncMock(side_effect=side_effect),
            ) as mock, patch(
                "app.core.llm_client.complete_stream", new=_fake_stream
            ), patch(
                "app.core.agent_loop.run_in_sandbox", side_effect=[_success_result()]
            ) as sandbox:
                result = await run_nl_to_sql(
                    question="List all users",
                    schema=SCHEMA,
                    db_connection_url="postgresql://u:p@host/db",
                )
            return result, mock, sandbox

        result, mock, sandbox = asyncio.run(scenario())
        trace = result["confidence_trace"]
        assert trace["components"]["pass1"]["model"] == "openai/gpt-oss-120b"
        assert trace["components"]["pass2"]["model"] == "openai/gpt-oss-120b"
        assert trace["components"]["pass2"]["skipped"] is False

    def test_failed_run_still_has_explanatory_trace(self):
        # A sandbox failure (even unrepaired) still produces a trace that says so.
        result, mock, sandbox = _run_pipeline(
            complete_side_effect=[PASS1_OK, PASS2_OK, RuntimeError("down")],
            sandbox_side_effect=[_fail_result(EXEC_ERROR)],
        )
        assert result["status"] == "error"
        trace = result["confidence_trace"]
        assert trace is not None
        assert trace["components"]["execution"]["success"] is False
        assert trace["components"]["execution"]["repair_attempted"] is True
        assert trace["composite"] == result["confidence_score"]
        assert any("Execution failed once" in n for n in trace["notes"])
