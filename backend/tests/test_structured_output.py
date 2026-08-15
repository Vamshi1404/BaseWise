"""Unit tests for structured-output parsing with self-healing (#1).

Covers extract_json robustness (fences, thinking prefix, trailing prose,
braces/quotes inside string data) and parse_llm_json's single corrective
follow-up call (success, wrong shape, repair failure, still-malformed).
"""
import asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core import structured_output
from app.core.structured_output import extract_json


def _run(coro):
    return asyncio.run(coro)


class TestExtractJson:
    def test_plain_object(self):
        value, err = extract_json('{"a": 1}')
        assert err == ""
        assert value == {"a": 1}

    def test_plain_array(self):
        value, err = extract_json('["x", "y"]')
        assert err == ""
        assert value == ["x", "y"]

    def test_json_fence(self):
        value, err = extract_json('```json\n{"a": 1}\n```')
        assert err == ""
        assert value == {"a": 1}

    def test_bare_fence(self):
        value, err = extract_json('```\n{"a": 1}\n```')
        assert err == ""
        assert value == {"a": 1}

    def test_leading_prose(self):
        value, err = extract_json('Here is the answer:\n{"a": 1}\nHope this helps.')
        assert err == ""
        assert value == {"a": 1}

    def test_trailing_prose(self):
        value, err = extract_json('{"a": 1}\nThat should do it.')
        assert err == ""
        assert value == {"a": 1}

    def test_thinking_prefix(self):
        value, err = extract_json('Let me reason: first I parse. {"sql": "SELECT 1"}')
        assert err == ""
        assert value == {"sql": "SELECT 1"}

    def test_braces_inside_string_literals(self):
        value, err = extract_json('{"a": [1, {"b": "x} y"}], "c": 2}\ntrailing')
        assert err == ""
        assert value == {"a": [1, {"b": "x} y"}], "c": 2}

    def test_escaped_quotes_in_strings(self):
        value, err = extract_json('{"a": "say \\"hi\\" {there}"}')
        assert err == ""
        assert value == {"a": 'say "hi" {there}'}

    def test_fence_markers_inside_string_value(self):
        value, err = extract_json('{"sql": "SELECT 1 ```from x```"}')
        assert err == ""
        assert value == {"sql": "SELECT 1 ```from x```"}

    def test_array_inside_prose(self):
        value, err = extract_json('Results: ["revenue", "growth"] — see above.')
        assert err == ""
        assert value == ["revenue", "growth"]

    def test_empty_string_fails(self):
        value, err = extract_json("")
        assert value is None
        assert err

    def test_none_fails(self):
        value, err = extract_json(None)
        assert value is None
        assert err

    def test_truncated_fails(self):
        value, err = extract_json('{"a": 1')
        assert value is None
        assert err

    def test_plain_prose_fails(self):
        value, err = extract_json("no json here at all")
        assert value is None
        assert err


class TestParseLlmJson:
    def test_valid_input_no_repair_call(self):
        async def scenario():
            with patch(
                "app.core.llm_client.complete", new=AsyncMock()
            ) as mock:
                value, err = await structured_output.parse_llm_json(
                    '{"a": 1}', validate=lambda v: isinstance(v, dict)
                )
            return value, err, mock

        value, err, mock = _run(scenario())
        assert err == ""
        assert value == {"a": 1}
        mock.assert_not_awaited()

    def test_malformed_triggers_repair_and_recovers(self):
        async def scenario():
            with patch(
                "app.core.llm_client.complete",
                new=AsyncMock(side_effect=['{"a": 1}']),
            ) as mock:
                value, err = await structured_output.parse_llm_json(
                    '{"a": 1,', validate=lambda v: isinstance(v, dict)
                )
            return value, err, mock

        value, err, mock = _run(scenario())
        assert err == ""
        assert value == {"a": 1}
        mock.assert_awaited_once()

    def test_repair_prompt_includes_previous_output_and_error(self):
        async def scenario():
            with patch(
                "app.core.llm_client.complete",
                new=AsyncMock(side_effect=['{"a": 1}']),
            ) as mock:
                await structured_output.parse_llm_json(
                    '{"a": 1,', validate=lambda v: isinstance(v, dict)
                )
            return mock

        mock = _run(scenario())
        messages = mock.await_args.args[0]
        user_content = messages[1]["content"]
        assert "<PREVIOUS_OUTPUT>" in user_content
        assert '{"a": 1,' in user_content
        assert "Parser error:" in user_content
        assert "Expecting" in user_content

    def test_wrong_shape_triggers_repair(self):
        async def scenario():
            with patch(
                "app.core.llm_client.complete",
                new=AsyncMock(side_effect=['{"a": 1}']),
            ) as mock:
                value, err = await structured_output.parse_llm_json(
                    "[1, 2, 3]", validate=lambda v: isinstance(v, dict)
                )
            return value, err, mock

        value, err, mock = _run(scenario())
        assert err == ""
        assert value == {"a": 1}
        mock.assert_awaited_once()

    def test_repair_call_raises_returns_original_error(self):
        async def scenario():
            with patch(
                "app.core.llm_client.complete",
                new=AsyncMock(side_effect=RuntimeError("all models down")),
            ) as mock:
                value, err = await structured_output.parse_llm_json('{"a": 1,')
            return value, err, mock

        value, err, mock = _run(scenario())
        assert value is None
        assert "Expecting" in err
        mock.assert_awaited_once()

    def test_repair_still_malformed_returns_original_error(self):
        async def scenario():
            with patch(
                "app.core.llm_client.complete",
                new=AsyncMock(side_effect=["still { not json"]),
            ) as mock:
                value, err = await structured_output.parse_llm_json('{"a": 1,')
            return value, err, mock

        value, err, mock = _run(scenario())
        assert value is None
        assert "Expecting" in err
        mock.assert_awaited_once()

    def test_repair_returns_wrong_shape(self):
        async def scenario():
            with patch(
                "app.core.llm_client.complete",
                new=AsyncMock(side_effect=["[1]"]),
            ) as mock:
                value, err = await structured_output.parse_llm_json(
                    '{"a": 1}', validate=lambda v: isinstance(v, list)
                )
            return value, err, mock

        value, err, mock = _run(scenario())
        assert err == ""
        assert value == [1]
        mock.assert_awaited_once()
