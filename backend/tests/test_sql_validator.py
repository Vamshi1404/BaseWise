"""Unit tests for the #4 heuristic SQL-vs-schema validator (VETO-only gate)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.sql_validator import validate_sql_against_schema

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
        },
    ],
}


class TestValidSQL:
    def test_simple_select(self):
        ok, reason = validate_sql_against_schema("SELECT name FROM users", SCHEMA)
        assert ok
        assert "resolve" in reason

    def test_select_star(self):
        ok, _ = validate_sql_against_schema("SELECT * FROM users", SCHEMA)
        assert ok

    def test_aggregate_and_where(self):
        ok, _ = validate_sql_against_schema(
            "SELECT count(*) FROM orders WHERE total_amount > 100", SCHEMA
        )
        assert ok

    def test_alias_qualified_column(self):
        ok, _ = validate_sql_against_schema(
            "SELECT u.name FROM users u WHERE u.active = TRUE", SCHEMA
        )
        assert ok

    def test_real_table_qualifier(self):
        ok, _ = validate_sql_against_schema(
            "SELECT users.name FROM users", SCHEMA
        )
        assert ok

    def test_join(self):
        ok, _ = validate_sql_against_schema(
            "SELECT u.name, o.total_amount FROM users u JOIN orders o ON o.user_id = u.id",
            SCHEMA,
        )
        assert ok

    def test_write_statement_resolves(self):
        ok, _ = validate_sql_against_schema(
            "INSERT INTO users (name) VALUES ('bob')", SCHEMA
        )
        assert ok

    def test_cte_is_not_a_real_table(self):
        ok, _ = validate_sql_against_schema(
            "WITH recent AS (SELECT id FROM users) SELECT * FROM recent", SCHEMA
        )
        assert ok

    def test_no_tables_statement(self):
        ok, _ = validate_sql_against_schema("SELECT 1", SCHEMA)
        assert ok


class TestVeto:
    def test_unknown_table(self):
        ok, reason = validate_sql_against_schema("SELECT * FROM nope", SCHEMA)
        assert not ok
        assert "nope" in reason

    def test_unknown_column(self):
        ok, reason = validate_sql_against_schema("SELECT missing_col FROM users", SCHEMA)
        assert not ok
        assert "missing_col" in reason

    def test_column_from_unrelated_table_vetoes(self):
        # total_amount exists in orders, not users — must still veto.
        ok, _ = validate_sql_against_schema("SELECT total_amount FROM users", SCHEMA)
        assert not ok

    def test_qualified_unknown_column(self):
        ok, _ = validate_sql_against_schema("SELECT u.name FROM users u", SCHEMA)  # sanity
        assert ok
        ok, reason = validate_sql_against_schema("SELECT u.bogus FROM users u", SCHEMA)
        assert not ok
        assert "bogus" in reason

    def test_unknown_qualifier(self):
        ok, reason = validate_sql_against_schema("SELECT x.name FROM users", SCHEMA)
        assert not ok
        assert "x.name" in reason

    def test_syntax_error(self):
        ok, reason = validate_sql_against_schema("SELECT FROM WHERE", SCHEMA)
        assert not ok
        assert "syntax error" in reason

    def test_empty_sql(self):
        ok, reason = validate_sql_against_schema("   ", SCHEMA)
        assert not ok
        assert "empty" in reason

    def test_no_schema(self):
        ok, _ = validate_sql_against_schema("SELECT * FROM users", {})
        assert not ok
