"""
End-to-end verification of the NL->SQL pipeline's chart generation + streaming.

Runs the REAL app.core.agent_loop.run_nl_to_sql() pipeline against a REAL
SQLite database (so the generated SQL genuinely executes and returns rows),
with only two external services mocked deterministically:

  * LLM  -> app.core.agent_loop.llm_client.complete / complete_stream
             (returns a fixed "group by month" SQL + a token-streamed summary)
  * E2B  -> app.core.agent_loop.run_in_sandbox
             (executes the extracted SQL against SQLite, mirroring the real
              sandbox's stdout contract including default=str serialization)

It captures every on_status / on_token callback — the exact events the API
turns into SSE "status" / "token" events — and prints the resulting
chart_data JSON.

Usage:
    python scripts/test_chart_e2e.py
"""
import asyncio
import json
import random
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import sqlalchemy as sa

from app.core import agent_loop
from app.core.sandbox import SandboxResult

# ---------------------------------------------------------------------------
# 1. Real data: SQLite in-memory DB with signups spread across 12 months
# ---------------------------------------------------------------------------
TEST_SQL = (
    "SELECT strftime('%Y-%m', created_at) AS month, COUNT(*) AS count "
    "FROM users GROUP BY month ORDER BY month"
)

_ENGINE = sa.create_engine("sqlite://")


def _seed_users() -> None:
    random.seed(42)
    with _ENGINE.begin() as conn:
        conn.execute(sa.text("DROP TABLE IF EXISTS users"))
        conn.execute(sa.text(
            "CREATE TABLE users (id INTEGER PRIMARY KEY, email TEXT, created_at TEXT)"
        ))
        for i in range(1, 200):
            month = 1 + (i % 12)
            year = 2025 if month <= 10 else 2024
            day = random.randint(1, 28)
            conn.execute(
                sa.text(
                    "INSERT INTO users (id, email, created_at) "
                    "VALUES (:id, :email, :created_at)"
                ),
                {"id": i, "email": f"user{i}@example.com",
                 "created_at": f"{year}-{month:02d}-{day:02d}"},
            )


# ---------------------------------------------------------------------------
# 2. Mock the E2B sandbox: actually run the SQL the pipeline generated
# ---------------------------------------------------------------------------
def fake_run_in_sandbox(code: str, db_connection_url: str, timeout_seconds: int = 30):
    start = time.monotonic()
    match = re.search(r'text\("(.*)"\)', code, re.DOTALL)
    sql = match.group(1) if match else None
    try:
        if sql is None:
            raise RuntimeError("No SQL literal found in generated sandbox code")
        with _ENGINE.connect() as conn:
            result = conn.execute(sa.text(sql))
            conn.commit()
            if result.returns_rows:
                rows = [dict(r._mapping) for r in result.fetchmany(100)]
                out = json.dumps(
                    {"rows": rows, "row_count": len(rows),
                     "rows_affected": 0, "returns_rows": True},
                    default=str,
                )
            else:
                out = json.dumps(
                    {"rows": [], "row_count": 0,
                     "rows_affected": result.rowcount, "returns_rows": False},
                    default=str,
                )
        elapsed = int((time.monotonic() - start) * 1000)
        return SandboxResult(
            stdout=out, stderr="", error=None, results=[],
            execution_ms=elapsed, sandbox_session_id="test-sandbox", success=True,
        )
    except Exception as exc:
        elapsed = int((time.monotonic() - start) * 1000)
        return SandboxResult(
            stdout="", stderr="", error=str(exc), results=[],
            execution_ms=elapsed, sandbox_session_id="test-sandbox", success=False,
        )


# ---------------------------------------------------------------------------
# 3. Mock the LLM (deterministic pass-1 / pass-2 / streaming summary)
# ---------------------------------------------------------------------------
SUMMARY = (
    "Signups grew steadily across the 12 months. The strongest month was "
    "September with the most new users, while January had the fewest."
)


async def fake_complete(messages: list[dict], **kwargs) -> str:
    last = messages[-1]["content"]
    if last.startswith("Original Question:"):  # Pass 2: self-recheck
        return json.dumps({
            "approved_sql": TEST_SQL,
            "issues_found": [],
            "confidence": 0.95,
            "changes_made": "none",
        })
    # Pass 1: candidate SQL + reasoning + confidence
    return json.dumps({
        "sql": TEST_SQL,
        "explanation": "Counts user signups per calendar month.",
        "confidence": 0.85,
        "reasoning": "Groups users by month of created_at and counts them.",
    })


async def fake_complete_stream(messages: list[dict], **kwargs):
    for token in SUMMARY.split(" "):
        yield token + " "
        await asyncio.sleep(0)


def _patch():
    agent_loop.llm_client.complete = fake_complete
    agent_loop.llm_client.complete_stream = fake_complete_stream
    agent_loop.run_in_sandbox = fake_run_in_sandbox


# ---------------------------------------------------------------------------
# 4. Chart-detection unit checks (the four documented rules)
# ---------------------------------------------------------------------------
def _check_detection_rules() -> None:
    build = agent_loop._build_chart_data

    bar = build([{"region": "North", "sales": 120},
                 {"region": "South", "sales": 80},
                 {"region": "East", "sales": 95}])
    assert bar and bar["type"] == "bar", f"expected bar, got {bar}"
    assert bar["x_key"] == "region" and bar["y_keys"] == ["sales"], bar

    line = build([{"month": "2024-01", "count": 15},
                  {"month": "2024-02", "count": 22},
                  {"month": "2024-03", "count": 18}])
    assert line and line["type"] == "line", f"expected line, got {line}"
    assert line["x_key"] == "month" and line["y_keys"] == ["count"], line

    pie = build([{"category": "Free", "share": 0.7},
                 {"category": "Pro", "share": 0.3}])
    assert pie and pie["type"] == "pie", f"expected pie, got {pie}"

    # >15 categories -> table only (None)
    many = [{"cat": f"c{i}", "val": i} for i in range(20)]
    assert build(many) is None, "expected None (table only) for >15 categories"

    # no numeric column -> table only
    assert build([{"a": "x", "b": "y"}]) is None, "expected None without numeric col"

    print("[rule-check] bar / line / pie / skip(>15) / skip(no-numeric) all PASS")


# ---------------------------------------------------------------------------
# 5. Full pipeline test
# ---------------------------------------------------------------------------
async def run_pipeline_test() -> dict:
    _seed_users()
    _patch()

    schema = {
        "dialect": "sqlite",
        "tables": [{
            "name": "users",
            "row_count": 199,
            "columns": [
                {"name": "id", "type": "integer", "primary_key": True},
                {"name": "email", "type": "text", "primary_key": False},
                {"name": "created_at", "type": "datetime", "primary_key": False},
            ],
            "foreign_keys": [],
        }],
    }

    statuses: list[str] = []
    tokens: list[str] = []

    async def on_status(msg: str) -> None:
        statuses.append(msg)

    async def on_token(delta: str) -> None:
        tokens.append(delta)

    result = await agent_loop.run_nl_to_sql(
        question="show me user signups grouped by month",
        schema=schema,
        db_connection_url="sqlite://",
        on_status=on_status,
        on_token=on_token,
    )

    print("\n=== SSE-equivalent status events (in order) ===")
    for i, s in enumerate(statuses, 1):
        print(f"  status[{i}]: {s}")

    print(f"\n=== Token stream (summary, {len(tokens)} chunks) ===")
    print("  " + "".join(tokens).strip())

    print("\n=== chart_data JSON ===")
    print(json.dumps(result.get("chart_data"), indent=2))

    # Assertions
    assert result["status"] == "success", result.get("error")
    assert "Building chart..." in statuses, "chart status missing"
    assert statuses.index("Building chart...") < statuses.index(
        "Generating explanation..."
    ), "chart status must precede explanation"
    expected_prefix = [
        "Analyzing schema context...",
        "Generating SQL query...",
        "Reviewing query for correctness...",
        "Executing query...",
        "Analyzing results for visualization...",
        "Building chart...",
        "Generating explanation...",
    ]
    assert statuses == expected_prefix, f"status order mismatch:\n{statuses}"
    assert tokens, "expected streamed summary tokens"

    cd = result["chart_data"]
    assert cd is not None
    assert cd["type"] == "line"
    assert cd["x_key"] == "month" and cd["y_keys"] == ["count"]
    assert len(cd["data"]) == 12
    assert all("month" in row and "count" in row for row in cd["data"])
    assert len(result["results"]) == 12
    print("\n[pipeline] all assertions PASS")
    return result


async def main() -> None:
    _check_detection_rules()
    result = await run_pipeline_test()
    print(f"\n[row_count={result['row_count']} confidence={result['confidence_score']} "
          f"op={result['operation_type']} ms={result['execution_ms']}]")


if __name__ == "__main__":
    asyncio.run(main())
