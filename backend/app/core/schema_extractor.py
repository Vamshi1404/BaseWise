"""
Schema Extractor — Deterministic, hardcoded SQLAlchemy-based metadata extraction.

This module is the ONLY place that connects to a user's linked database deterministically.
Everything downstream (queries, analysis, plots) is LLM-generated code run in the E2B sandbox.

Built dialect-agnostically using SQLAlchemy's inspect() API so MySQL, SQLite, and other
Postgres-compatible sources can be added in Milestone 7 with zero changes here.
"""
from typing import Any
import datetime
import decimal
import uuid
import sqlalchemy as sa
from sqlalchemy import inspect, text

# Threshold below which we compute per-column stats + samples. Above it we only
# keep metadata (avoids slow/distinct scans over huge tables).
STATS_ROW_LIMIT = 50_000
SAMPLE_ROWS = 3
MAX_STATS_COLUMNS = 20


def _serialize_value(value: Any) -> Any:
    """Convert a raw DB value into a JSON-serializable Python value."""
    if value is None:
        return None
    if isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, decimal.Decimal):
        return float(value)
    if isinstance(value, (datetime.datetime, datetime.date, datetime.time)):
        return value.isoformat()
    if isinstance(value, datetime.timedelta):
        return str(value)
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, bytes):
        try:
            return value.decode("utf-8", errors="replace")
        except Exception:
            return f"<bytes:{len(value)}>"
    if isinstance(value, (list, tuple)):
        return [_serialize_value(v) for v in value]
    if isinstance(value, dict):
        return {str(k): _serialize_value(v) for k, v in value.items()}
    return str(value)


def _is_numeric_or_temporal(type_str: str) -> bool:
    t = type_str.lower()
    return any(
        k in t
        for k in (
            "int", "float", "double", "numeric", "decimal", "real",
            "date", "time", "year", "timestamp", "money", "number",
        )
    )


def extract_schema(connection_url: str) -> dict[str, Any]:
    """
    Connect to a database using its raw connection URL and extract schema metadata.

    Returns a dict with:
    {
        "dialect": str,
        "tables": [
            {
                "name": str,
                "columns": [{"name", "type", "nullable", "primary_key"}],
                "primary_keys": [str],
                "foreign_keys": [{"column", "references_table", "references_column"}],
                "row_count": int | None,
            }
        ]
    }

    SECURITY NOTE: connection_url is decrypted transiently in-memory before this call.
    It is never logged, never stored, never passed to LLM prompts.
    """
    # Use a synchronous engine for one-shot schema extraction
    # (async not needed here — this is a short-lived metadata-only connection)
    url = sa.engine.make_url(connection_url)

    # Async-only drivers can't run a sync engine. Map them to a sync driver:
    # postgresql+asyncpg -> postgresql (psycopg2), etc.
    if url.get_backend_name() == "postgresql" and url.get_driver_name() == "asyncpg":
        url = url.set(drivername="postgresql")

    # connect_timeout is psycopg2/MySQL-specific; other dialects reject it
    connect_args = {"connect_timeout": 10} if url.get_backend_name() in ("postgresql", "mysql") else {}
    engine = sa.create_engine(url, connect_args=connect_args)

    try:
        with engine.connect() as conn:
            inspector = inspect(engine)
            dialect = engine.dialect.name

            tables = []
            for table_name in inspector.get_table_names():
                columns = []
                for col in inspector.get_columns(table_name):
                    columns.append({
                        "name": col["name"],
                        "type": str(col["type"]),
                        "nullable": col.get("nullable", True),
                        "primary_key": col.get("primary_key", False),
                    })

                pk_constraint = inspector.get_pk_constraint(table_name)
                primary_keys = pk_constraint.get("constrained_columns", [])

                raw_fks = inspector.get_foreign_keys(table_name)
                foreign_keys = []
                for fk in raw_fks:
                    for local_col, ref_col in zip(
                        fk.get("constrained_columns", []),
                        fk.get("referred_columns", []),
                    ):
                        foreign_keys.append({
                            "column": local_col,
                            "references_table": fk.get("referred_table"),
                            "references_column": ref_col,
                        })

                # Approximate row count — best-effort, not exact
                row_count = None
                try:
                    result = conn.execute(
                        text(f'SELECT COUNT(*) FROM "{table_name}"')  # noqa: S608
                    )
                    row_count = result.scalar()
                except Exception:
                    pass  # If count fails (permissions, views), skip gracefully

                # --- Sample rows: the model understands real data shapes from these ---
                sample_rows = []
                try:
                    if row_count is not None and 0 < row_count <= STATS_ROW_LIMIT:
                        sample_result = conn.execute(
                            text(f'SELECT * FROM "{table_name}" LIMIT {SAMPLE_ROWS}')  # noqa: S608
                        )
                        cols = sample_result.keys()
                        for row in sample_result.fetchall():
                            sample_rows.append({
                                c: _serialize_value(row[i]) for i, c in enumerate(cols)
                            })
                except Exception:
                    pass

                # --- Per-column stats: distinct count + min/max for numeric/date ---
                column_stats: dict[str, dict[str, Any]] = {}
                if (
                    row_count is not None
                    and 0 < row_count <= STATS_ROW_LIMIT
                    and len(columns) <= MAX_STATS_COLUMNS
                ):
                    try:
                        distinct_parts = [
                            f'COUNT(DISTINCT "{c["name"]}") AS "d_{i}"'
                            for i, c in enumerate(columns)
                        ]
                        if distinct_parts:
                            stats_result = conn.execute(
                                text(
                                    f'SELECT {", ".join(distinct_parts)} '
                                    f'FROM "{table_name}"'  # noqa: S608
                                )
                            )
                            stats_row = stats_result.fetchone()
                            for i, c in enumerate(columns):
                                column_stats[c["name"]] = {
                                    "distinct": _serialize_value(stats_row[i]),
                                }
                    except Exception:
                        pass

                    try:
                        stat_cols = [
                            (i, c["name"])
                            for i, c in enumerate(columns)
                            if _is_numeric_or_temporal(c["type"])
                        ][:8]
                        if stat_cols:
                            minmax_parts = []
                            for j, (_, cname) in enumerate(stat_cols):
                                minmax_parts.append(f'MIN("{cname}") AS "min_{j}"')
                                minmax_parts.append(f'MAX("{cname}") AS "max_{j}"')
                            mm_result = conn.execute(
                                text(
                                    f'SELECT {", ".join(minmax_parts)} '
                                    f'FROM "{table_name}"'  # noqa: S608
                                )
                            )
                            mm_row = mm_result.fetchone()
                            for j, (_, cname) in enumerate(stat_cols):
                                if cname in column_stats:
                                    column_stats[cname]["min"] = _serialize_value(mm_row[j * 2])
                                    column_stats[cname]["max"] = _serialize_value(mm_row[j * 2 + 1])
                    except Exception:
                        pass

                tables.append({
                    "name": table_name,
                    "columns": columns,
                    "primary_keys": primary_keys,
                    "foreign_keys": foreign_keys,
                    "row_count": row_count,
                    "sample_rows": sample_rows,
                    "column_stats": column_stats,
                })

        return {"dialect": dialect, "tables": tables}

    finally:
        engine.dispose()
