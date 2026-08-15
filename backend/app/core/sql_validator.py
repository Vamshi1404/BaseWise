"""
#4: Heuristic SQL-vs-schema validation (VETO-only gate, no LLM call).

Deterministically checks that a candidate SQL statement (1) parses with sqlglot
and (2) only references tables and columns that exist in the schema. It exists
purely to decide whether the pass-2 self-recheck may be SKIPPED.

Conservative by design: any doubt — parse error, unknown table or column,
unresolvable qualifier, or any exception — returns False, which forces the full
pipeline. The gate can never grant confidence; it can only decline to skip.
"""
import logging

from sqlglot import exp, parse_one

logger = logging.getLogger(__name__)


def validate_sql_against_schema(sql: str, schema: dict) -> tuple[bool, str]:
    """True when `sql` parses and every table/column reference resolves.

    Returns (valid, reason). `valid=True` means the statement is structurally
    sound against the schema and therefore eligible to skip the self-recheck.
    """
    tables: dict[str, set[str]] = {}
    for table in (schema or {}).get("tables", []):
        name = table.get("name")
        if name:
            tables[name] = {c.get("name") for c in table.get("columns", [])}
    if not tables:
        return False, "no schema tables to validate against"

    text = (sql or "").strip()
    if not text:
        return False, "empty SQL"

    try:
        tree = parse_one(text, read=schema.get("dialect", "postgres"))
    except Exception as exc:
        logger.info(f"[sql_validator] parse error: {exc}")
        return False, f"syntax error: {exc}"
    if tree is None:
        return False, "not a single parseable statement"

    # CTE names are references to the WITH clause, not real tables.
    cte_names = {cte.alias_or_name for cte in tree.find_all(exp.CTE)}

    referenced_tables: list[str] = []
    alias_map: dict[str, str] = {}
    for node in tree.find_all(exp.Table):
        name = node.name
        if name in cte_names:
            continue
        if name not in tables:
            return False, f"unknown table: {name}"
        referenced_tables.append(name)
        alias = node.alias
        if alias:
            alias_map[alias] = name

    referenced_columns: set[str] = set()
    for name in referenced_tables:
        referenced_columns |= tables[name]

    for col in tree.find_all(exp.Column):
        cname = col.name
        if cname == "*":
            continue
        qualifier = col.table
        if qualifier:
            real = alias_map.get(qualifier, qualifier)
            if real in cte_names:
                continue
            if real not in tables:
                return False, f"column {qualifier}.{cname} references unknown table"
            if cname not in tables[real]:
                return False, f"unknown column: {qualifier}.{cname}"
        else:
            if cname not in referenced_columns:
                return False, f"unknown column: {cname}"

    return True, "syntax OK and all tables/columns resolve"
