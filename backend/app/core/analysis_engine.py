"""
Analysis Mode Engine (project.md Section 5)

Scans the schema cache and proactively suggests business insight starting points.
When the user selects one, generates and executes Python analysis code in the E2B sandbox
and returns structured chart data (project.md Section 6).

The sandbox is a DATA COMPUTATION layer only: it aggregates, stats, and groups data
with pandas/sqlalchemy, then prints a Recharts-compatible JSON spec. It never draws
images — chart rendering is entirely the frontend's job (the same ChartRenderer that
Query Mode uses). No matplotlib is even installed in the sandbox.
"""
import logging
from typing import Any, Awaitable, Callable, Optional

from app.core import llm_client
from app.core import structured_output
from app.core.sandbox import run_in_sandbox
from app.core.db_context import render_db_context

logger = logging.getLogger(__name__)

ProgressCallback = Optional[Callable[[str], Awaitable[None]]]

# Upper bound on chart categories. Even when a location column mixes full addresses
# with short names, we never show more than this many labels.
MAX_LOCATION_CATEGORIES = 10
# A label this long is unusable in a chart — collapse it to its leading locality.
_LONG_LABEL_LEN = 24


def _short_location_label(value: Any) -> str:
    """Collapse an address/location string to its short leading locality.

    'Uppal Road, Abhilekhagaram, Osmania University, Hyderabad 500007, Telangana'
      -> 'Uppal Road'
    'LB Nagar, Hyderabad, Telangana' -> 'LB Nagar'
    'HITEC City' -> 'HITEC City' (unchanged — already short)
    """
    if not isinstance(value, str):
        return str(value)
    s = value.strip()
    if not s:
        return s
    first_segment = s.split(",")[0].strip()
    # Collapse any internal runs of whitespace
    return " ".join(first_segment.split())


def _pretty_location_label(label: str) -> str:
    """Title-case purely-lowercase locality labels ('lb nagar' -> 'Lb Nagar').

    Leaves mixed/uppercase labels ('HITEC City', 'Uppal Road') untouched.
    """
    if label and label.islower() and len(label) >= 3:
        return " ".join(word.capitalize() for word in label.split())
    return label


def _to_number(value: Any) -> float:
    try:
        if isinstance(value, bool) or value is None:
            return 0.0
        if isinstance(value, (int, float)):
            return float(value)
        return float(str(value).strip())
    except (TypeError, ValueError):
        return 0.0


def _needs_label_cleanup(chart_data: dict) -> bool:
    """True when the x-axis labels look like long/address-style strings."""
    data = chart_data.get("data") or []
    x_key = chart_data.get("x_key")
    if not data or not x_key:
        return False
    return any(
        isinstance(row.get(x_key), str)
        and ("," in row.get(x_key) or len(row.get(x_key)) > _LONG_LABEL_LEN)
        for row in data
    )


def _normalize_location_labels(chart_data: dict) -> dict:
    """
    Deterministic safety net over whatever the sandbox returned.

    If the x-axis labels mix full addresses and short names (a common shape for
    location data — e.g. one column holding both 'HITEC City' and
    'Uppal Road, Abhilekhagaram, ..., Hyderabad 500007, Telangana'), collapse each
    label to its leading locality, merge case-variants by summing values, sort
    descending, and cap the category count. Guarantees readable, non-flattened charts
    even if the model misses the labelling instruction in the prompt.
    """
    if not _needs_label_cleanup(chart_data):
        return chart_data

    x_key = chart_data["x_key"]
    rows = chart_data.get("data") or []
    y_keys = [k for k in (chart_data.get("y_keys") or []) if k in rows[0]]
    if not y_keys:
        return chart_data

    merged: dict[str, dict] = {}
    for row in rows:
        raw = _short_location_label(row.get(x_key))
        label = _pretty_location_label(raw)
        key = raw.casefold()
        if key in merged:
            entry = merged[key]
            for yk in y_keys:
                entry[yk] = _to_number(entry.get(yk)) + _to_number(row.get(yk))
            if len(label) < len(merged[key][x_key]):
                merged[key][x_key] = label
        else:
            entry = dict(row)
            entry[x_key] = label
            for yk in y_keys:
                entry[yk] = _to_number(entry.get(yk))
            merged[key] = entry

    ordered = sorted(merged.values(), key=lambda r: -_to_number(r.get(y_keys[0])))
    cleaned = dict(chart_data)
    cleaned["data"] = ordered[:MAX_LOCATION_CATEGORIES]
    return cleaned


async def generate_suggestions(schema: dict) -> list[str]:
    """
    Given schema metadata, ask the LLM to suggest 3–5 business analysis starting points.
    Output is scoped to business insights only — schema browsing stays in query mode.
    """
    # Light context (names + types + keys) so suggestions reference real columns,
    # not concepts the model invents.
    schema_context = render_db_context(schema, light=True)

    messages = [
        {
            "role": "system",
            "content": (
                "You are a business intelligence assistant. Given a database schema, "
                "suggest 3 to 5 concise, business-relevant analysis questions a non-technical user "
                "might want to explore. Focus on trends, growth, performance, and risk — not schema structure. "
                "Base each suggestion on the actual tables and columns listed — never invent fields. "
                "Respond ONLY with a JSON array of strings. No markdown, no extra text.\n"
                'Example: ["What are the revenue trends over the last 6 months?", "Which customers have churned?"]'
            ),
        },
        {
            "role": "user",
            "content": f"Database Schema:\n{schema_context}",
        },
    ]

    raw = await llm_client.complete(messages, temperature=0.3, max_tokens=512)

    # Self-healing JSON: one corrective follow-up call on a malformed (or
    # non-list) response before falling back to line-by-line parsing.
    parsed, _ = await structured_output.parse_llm_json(
        raw,
        expected_shape="a JSON array of strings",
        validate=lambda v: isinstance(v, list),
        temperature=0.3,
        max_tokens=512,
    )
    if isinstance(parsed, list):
        return [str(s) for s in parsed[:5]]

    # Fallback: parse line-by-line
    lines = [l.strip().strip('"').strip("'") for l in raw.splitlines() if l.strip()]
    return lines[:5] if lines else ["Show overall data summary", "Identify top performers", "Analyze trends over time"]


def _build_analysis_messages(
    prompt: str,
    schema_context: str,
    retry_error: Optional[str] = None,
) -> list[dict]:
    """Build the code-generation prompt. On retry, feeds the sandbox error back
    so the model fixes its assumptions (e.g. invented column names)."""
    user_content = (
        f"Database Schema:\n{schema_context}\n\n"
        f"Analysis request: {prompt}"
    )
    if retry_error:
        user_content += (
            "\n\nYour previous attempt failed to execute in the sandbox. Use the "
            "error below and the schema above to fix the code — for example, you "
            "may have referenced a table or column that does not exist, or "
            "misused a column's type. Do NOT repeat the same mistake.\n"
            f"<ERROR>\n{retry_error}\n</ERROR>"
        )
    return [
        {
            "role": "system",
            "content": (
                "You are a data analyst. Your job is DATA COMPUTATION ONLY — "
                "compute aggregations, stats, and groupings in Python; you never "
                "render charts or images. The frontend renders the chart from the "
                "JSON you return.\n"
                "Generate Python code that:\n"
                "1. Connects to a database using: import os; db_url = os.environ['DB_URL']\n"
                "2. Uses sqlalchemy + pandas to fetch and compute the requested analysis\n"
                "3. Prints a result dict as JSON in this exact format:\n"
                '{"type": "bar", "title": "...", "data": [...], "x_key": "...", "y_keys": ["..."], '
                '"summary": "plain English summary for non-technical user"}\n'
                "data must be a list of flat dicts (one per category/point). "
                "type can be bar, pie, line, area, scatter, funnel, or treemap.\n"
                "  - bar/line/area/pie: ranking, trend, and share questions. For ranking questions like "
                "'most visited X', prefer bar (or pie for a small share breakdown).\n"
                "  - scatter: the relationship/correlation between two numeric fields "
                "(e.g. distance vs cost) -> data rows are the individual points, x_key = first "
                "numeric, y_keys = [second numeric]; optionally add z_key for a third numeric "
                "(point size).\n"
                "  - funnel: conversion/drop-off across ordered lifecycle stages (e.g. requests -> "
                "accepted -> completed -> cancelled) -> data rows are {'stage': '...', 'count': N}, "
                "ordered from largest to smallest, x_key = stage column, y_keys = [count].\n"
                "  - treemap: hierarchical proportions, a two-level breakdown (e.g. city then status) "
                "-> data is a nested list of {'name': parent, 'children': [{'name': child, 'value': N}]} "
                "and set value_key to the value column name.\n"
                "4. For LOCATION/ADDRESS data specifically:\n"
                "   - If the schema has a dedicated short field (city/area/locality), group by that.\n"
                "   - If location values MIX short names and full addresses in one column "
                "(e.g. 'HITEC City' alongside 'Uppal Road, Abhilekhagaram, Osmania University, "
                "Hyderabad 500007, Telangana'), derive a SHORT label before grouping: take the "
                "text before the first comma, trim whitespace, and standardize casing so the "
                "same place collapses together. Group by that derived label.\n"
                "   - Merge case/spelling variants of the same place and SUM their counts "
                "so one destination shows one bar with its real total (do NOT split one "
                "destination across many near-unique address strings — that flattens the chart).\n"
                "   - Keep at most 8-10 categories, ordered by value descending.\n"
                "5. NEVER use matplotlib, plt, savefig, figure, imshow, or any image/plot "
                "generation — do not draw anything. The sandbox has no matplotlib installed "
                "and image output is not supported.\n"
                "print(json.dumps(result_dict)) must ALWAYS run last so the JSON spec is in stdout.\n"
                "CRITICAL: Use ONLY the tables and columns listed in the Database Schema. "
                "Never invent column names that are not present — a non-existent column "
                "fails with 'UndefinedColumn'.\n"
                "Respond with ONLY the Python code, no markdown fences."
            ),
        },
        {"role": "user", "content": user_content},
    ]


async def execute_analysis(
    prompt: str,
    schema: dict,
    db_connection_url: str,
    on_status: ProgressCallback = None,
) -> dict[str, Any]:
    """
    Given a user's analysis request:
    1. LLM generates a Python analysis script (using pandas + sqlalchemy)
    2. Runs in E2B sandbox against the real DB (data computation only — no images)
    3. Returns structured chart data JSON + plain English summary

    Chart data format (Recharts-compatible — identical to Query Mode):
    {
        "type": "bar"|"line"|"pie"|"area"|"scatter"|"funnel"|"treemap",
        "title": str,
        "data": [...],
        "x_key": str,
        "y_keys": [str],
    }
    """
    async def _progress(msg: str) -> None:
        if on_status:
            await on_status(msg)

    # Full schema context (real columns/types/keys/stats/samples) so the model
    # never hallucinates column names — that was the source of
    # "column X does not exist" failures.
    schema_context = render_db_context(schema)

    max_attempts = 2
    sandbox_result = None
    last_error = None

    for attempt in range(1, max_attempts + 1):
        if attempt == 1:
            await _progress("Designing analysis code from your request...")
        else:
            await _progress("Execution failed — asking the model to fix the code...")

        # Generate analysis code (with the previous sandbox error as feedback
        # on retries so the model corrects its assumptions about the schema).
        messages = _build_analysis_messages(prompt, schema_context, last_error)
        code_raw = await llm_client.complete(messages, temperature=0.2, max_tokens=2048)
        # Strip any accidental markdown fences
        code = code_raw.strip().strip("```python").strip("```").strip()

        await _progress("Running analysis in sandboxed environment...")
        sandbox_result = run_in_sandbox(code=code, db_connection_url=db_connection_url)

        if sandbox_result.success:
            break
        last_error = sandbox_result.error

    if not sandbox_result.success:
        return {
            "status": "error",
            "error": sandbox_result.error,
            "execution_ms": sandbox_result.execution_ms,
            "sandbox_session_id": sandbox_result.sandbox_session_id,
        }

    chart_value, _ = structured_output.extract_json(sandbox_result.stdout)
    if isinstance(chart_value, dict):
        chart_data = chart_value
    else:
        chart_data = {"type": "table", "data": [], "summary": sandbox_result.stdout[:1000]}

    # Safety net: guarantee short, readable, non-flattened location labels.
    chart_data = _normalize_location_labels(chart_data)

    return {
        "status": "success",
        "chart_data": chart_data,
        "python_code": code,
        "execution_ms": sandbox_result.execution_ms,
        "sandbox_session_id": sandbox_result.sandbox_session_id,
    }
