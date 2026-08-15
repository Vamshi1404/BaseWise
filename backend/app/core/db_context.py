"""
Database Context — the "complete context state" built when a DB is loaded/scanned.

The schema_cache row for a linked DB holds the extracted schema (tables, columns,
types, keys, row counts, sample rows, column stats). This module renders that
state into a compact, LLM-friendly "database profile" so the model understands
the data before writing any SQL — and also produces plain-English descriptions of
tables/columns via heuristics (no extra LLM cost).
"""
from typing import Any

_KNOWN_COLUMN_HINTS: dict[str, str] = {
    "id": "primary identifier",
    "uuid": "unique identifier",
    "email": "email address",
    "username": "login name",
    "password": "password hash (never expose)",
    "created_at": "record creation timestamp",
    "createdon": "record creation timestamp",
    "updated_at": "last update timestamp",
    "deleted_at": "soft-delete timestamp",
    "is_active": "active flag (boolean)",
    "is_admin": "admin flag (boolean)",
    "status": "record status / state",
    "role": "user role or permission level",
    "type": "kind/category discriminator",
    "category": "category label",
    "name": "display name",
    "title": "title or heading",
    "description": "free-text description",
    "first_name": "first name",
    "last_name": "last name",
    "amount": "monetary amount",
    "price": "monetary price",
    "total": "total amount",
    "quantity": "count of items",
    "count": "aggregated count",
    "date": "calendar date",
    "start_date": "start date",
    "end_date": "end date",
    "due_date": "due date",
    "phone": "phone number",
    "address": "postal address",
    "url": "web address",
    "image_url": "image web address",
    "currency": "ISO currency code",
    "language": "language code",
    "country": "country code/name",
    "city": "city name",
    "state": "state or province",
    "zip": "postal code",
    "lat": "latitude",
    "long": "longitude",
    "longitude": "longitude",
}


def _describe_column(col: dict[str, Any]) -> str:
    name = col["name"].lower()
    hint = _KNOWN_COLUMN_HINTS.get(name)
    type_str = col["type"]
    suffix = f" ({type_str})" if type_str else ""
    if hint:
        return f"{col['name']}{suffix} — {hint}"
    return f"{col['name']}{suffix}"


def _describe_table(table: dict[str, Any]) -> str:
    name = table["name"]
    n_cols = len(table["columns"])
    fks = table.get("foreign_keys", [])
    fk_note = ""
    if fks:
        links = ", ".join(
            f"{fk['column']}->{fk['references_table']}.{fk['references_column']}"
            for fk in fks[:4]
        )
        fk_note = f"; links: {links}"
    pk_note = f"; PK: {', '.join(table.get('primary_keys', []))}" if table.get("primary_keys") else ""
    return (
        f"{name} ({n_cols} columns, ~{table.get('row_count') or '?'} rows"
        f"{pk_note}{fk_note})"
    )


def render_db_context(
    schema: dict[str, Any], max_tables: int = 40, light: bool = False
) -> str:
    """
    Render the full database context state into a prompt string.
    Includes per-table descriptions, column semantics, keys, and sample data.

    light=True: table/column names + types + keys only (no column semantics,
    stats, or sample rows) — for self-check/review passes that only need the
    schema shape, not the data profile.
    """
    dialect = schema.get("dialect", "unknown")
    tables = schema.get("tables", [])[:max_tables]

    lines: list[str] = []
    lines.append(f"[DATABASE CONTEXT] dialect: {dialect}")
    lines.append("")

    for table in tables:
        lines.append(f"## TABLE {_describe_table(table)}")

        for col in table.get("columns", []):
            if light:
                type_str = f" ({col['type']})" if col.get("type") else ""
                lines.append(f"  - {col['name']}{type_str}")
            else:
                lines.append(f"  - {_describe_column(col)}")

        if not light:
            stats = table.get("column_stats", {})
            if stats:
                stat_lines = []
                for col_name, col_stats in list(stats.items())[:12]:
                    parts = [f"distinct={col_stats.get('distinct')}"]
                    if col_stats.get("min") is not None:
                        parts.append(f"min={col_stats['min']}")
                    if col_stats.get("max") is not None:
                        parts.append(f"max={col_stats['max']}")
                    stat_lines.append(f"    {col_name}: {', '.join(parts)}")
                if stat_lines:
                    lines.append("  [stats]")
                    lines.extend(stat_lines)

            samples = table.get("sample_rows", [])
            if samples:
                lines.append("  [sample rows]")
                for sample in samples[:3]:
                    lines.append(f"    {sample}")

        lines.append("")

    return "\n".join(lines).strip()
