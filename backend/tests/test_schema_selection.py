"""Unit tests for schema-relevance selection hardening.

Covers: table-level selection, one-hop FK closure in BOTH directions,
singular/plural + business-synonym matching, column pruning of wide tables,
and the small-vs-large-schema fallback behavior.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.agent_loop import (
    MAX_COLUMNS_PER_TABLE,
    FALLBACK_SELECT_COUNT,
    SMALL_SCHEMA_TABLE_LIMIT,
    _prune_columns,
    _select_relevant_schema,
    _stem,
)


def _table(name, columns, fks=None, pks=None, row_count=None):
    return {
        "name": name,
        "columns": [
            {"name": c, "type": "VARCHAR", "nullable": True, "primary_key": c in (pks or [])}
            for c in columns
        ],
        "primary_keys": list(pks or []),
        "foreign_keys": [
            {"column": a, "references_table": b, "references_column": c}
            for a, b, c in (fks or [])
        ],
        "row_count": row_count,
        "sample_rows": [],
        "column_stats": {},
    }


def _schema(*tables, dialect="postgres"):
    return {"dialect": dialect, "tables": list(tables)}


def _names(schema) -> list[str]:
    return [t["name"] for t in schema["tables"]]


class TestTableSelection:
    def test_single_table_returns_same_object(self):
        schema = _schema(_table("users", ["id"]))
        result = _select_relevant_schema(schema, "show users")
        assert result is schema

    def test_matched_tables_kept_unmatched_dropped(self):
        schema = _schema(
            _table("customers", ["id"]),
            _table("orders", ["id"]),
            _table("region", ["id"]),
        )
        result = _select_relevant_schema(schema, "orders by region")
        assert _names(result) == ["orders", "region"]

    def test_top_cap_limits_matched_tables(self):
        tables = [_table(f"user_profile_{i}", ["id"]) for i in range(5)]
        result = _select_relevant_schema(_schema(*tables), "user")
        # All match "user"; only the top 3 (schema order, stable sort) are kept.
        assert len(result["tables"]) == 3
        assert _names(result) == [t["name"] for t in tables[:3]]

    def test_fk_outgoing_included(self):
        schema = _schema(
            _table("orders", ["id", "customer_id"], fks=[("customer_id", "customers", "id")]),
            _table("customers", ["id"]),
            _table("audit_log", ["id"]),
        )
        result = _select_relevant_schema(schema, "orders")
        names = _names(result)
        assert "orders" in names
        assert "customers" in names
        assert "audit_log" not in names

    def test_fk_incoming_included_reverse_hop(self):
        # Question only names 'customers'; a table that references customers via
        # a non-descriptive column must still be kept so a join through it isn't
        # silently dropped (the old selector only followed outgoing FKs).
        schema = _schema(
            _table("customers", ["id"]),
            _table("ledger", ["id", "ref_id"], fks=[("ref_id", "customers", "id")]),
            _table("audit_log", ["id"]),
        )
        result = _select_relevant_schema(schema, "customers")
        names = _names(result)
        assert names[0] == "customers"   # matched table first
        assert "ledger" in names         # reverse FK hop added it
        assert "audit_log" not in names

    def test_matched_tables_first_then_neighbors(self):
        schema = _schema(
            _table("customers", ["id"]),
            _table("ledger", ["id", "ref_id"], fks=[("ref_id", "customers", "id")]),
        )
        result = _select_relevant_schema(schema, "customers")
        assert _names(result) == ["customers", "ledger"]

    def test_dialect_preserved(self):
        schema = _schema(_table("users", ["id"]), _table("orders", ["id"]), dialect="mysql")
        result = _select_relevant_schema(schema, "users")
        assert result["dialect"] == "mysql"


class TestStemmingAndSynonyms:
    def test_plural_matches_singular_table(self):
        schema = _schema(_table("customer", ["id"]), _table("region", ["id"]))
        assert _names(_select_relevant_schema(schema, "customers")) == ["customer"]

    def test_plural_matches_column(self):
        schema = _schema(
            _table("sales", ["id", "region"]),
            _table("region", ["id"]),
        )
        assert _names(_select_relevant_schema(schema, "sale by region")) == ["sales", "region"]

    def test_synonym_revenue_matches_amount_column(self):
        schema = _schema(
            _table("transactions", ["id", "amount"]),
            _table("audit_log", ["id"]),
        )
        result = _select_relevant_schema(schema, "total revenue")
        assert _names(result) == ["transactions"]

    def test_synonym_clients_matches_customers(self):
        schema = _schema(
            _table("customers", ["id"]),
            _table("orders", ["id"]),
        )
        assert _names(_select_relevant_schema(schema, "list clients")) == ["customers"]

    def test_stem_edge_cases(self):
        assert _stem("categories") == "category"
        assert _stem("customers") == "customer"
        assert _stem("sales") == "sale"
        assert _stem("users") == "user"
        assert _stem("id") == "id"


class TestFallback:
    def test_no_match_small_schema_full_dump(self):
        tables = [_table(f"t{i}", ["id"]) for i in range(5)]
        schema = _schema(*tables)
        result = _select_relevant_schema(schema, "what is the meaning of life")
        assert len(result["tables"]) == len(tables)

    def test_no_match_large_schema_top_by_row_count(self):
        tables = [_table(f"t{i}", ["id"], row_count=i) for i in range(1, SMALL_SCHEMA_TABLE_LIMIT + 6)]
        schema = _schema(*tables)
        result = _select_relevant_schema(schema, "what is the meaning of life")
        assert len(result["tables"]) == FALLBACK_SELECT_COUNT
        counts = [t["row_count"] for t in result["tables"]]
        assert counts == sorted(counts, reverse=True)

    def test_no_match_large_schema_unknown_row_count_ranks_last(self):
        tables = [
            _table(f"known{i}", ["id"], row_count=i) for i in range(1, SMALL_SCHEMA_TABLE_LIMIT + 6)
        ] + [_table("unknown", ["id"])]
        schema = _schema(*tables)
        result = _select_relevant_schema(schema, "what is the meaning of life")
        assert len(result["tables"]) == FALLBACK_SELECT_COUNT
        assert all(t["row_count"] is not None for t in result["tables"])

    def test_stopwords_only_question_uses_fallback(self):
        tables = [_table(f"t{i}", ["id"], row_count=i) for i in range(1, SMALL_SCHEMA_TABLE_LIMIT + 6)]
        result = _select_relevant_schema(_schema(*tables), "show me the list please")
        assert len(result["tables"]) == FALLBACK_SELECT_COUNT


class TestColumnPruning:
    def _wide_table(self, columns, fks=None, pks=None):
        stats = {c: {"distinct": 1} for c in columns}
        samples = [{c: 0 for c in columns}]
        table = _table("wide", columns, fks=fks, pks=pks)
        table["column_stats"] = stats
        table["sample_rows"] = samples
        return table

    def test_narrow_table_unchanged(self):
        cols = [f"c{i}" for i in range(MAX_COLUMNS_PER_TABLE)]
        table = _table("narrow", cols)
        result = _prune_columns(table, ["nothing"])
        assert result is table
        assert len(result["columns"]) == MAX_COLUMNS_PER_TABLE

    def test_wide_table_prunes_to_important(self):
        columns = ["id", "junk_1", "customer_id", "junk_2", "created_at", "amount"] + [
            f"junk_{i}" for i in range(3, 10)
        ]
        table = self._wide_table(columns, fks=[("customer_id", "customers", "id")], pks=["id"])
        result = _prune_columns(table, ["amount"])
        assert [c["name"] for c in result["columns"]] == ["id", "customer_id", "created_at", "amount"]
        # Stats/samples are filtered to the kept columns for context consistency.
        assert set(result["column_stats"].keys()) == {"id", "customer_id", "created_at", "amount"}
        assert set(result["sample_rows"][0].keys()) == {"id", "customer_id", "created_at", "amount"}

    def test_wide_table_no_important_keeps_first_n(self):
        columns = [f"junk_{i}" for i in range(MAX_COLUMNS_PER_TABLE + 5)]
        table = self._wide_table(columns)
        result = _prune_columns(table, ["amount"])
        assert len(result["columns"]) == MAX_COLUMNS_PER_TABLE
        assert [c["name"] for c in result["columns"]] == columns[:MAX_COLUMNS_PER_TABLE]

    def test_wide_table_id_like_and_date_kept(self):
        columns = ["row_id", "created_at", "junk_1", "junk_2", "junk_3", "junk_4",
                   "junk_5", "junk_6", "junk_7", "junk_8", "junk_9", "junk_10", "junk_11", "junk_12", "junk_13"]
        table = self._wide_table(columns)
        result = _prune_columns(table, ["irrelevant"])
        names = [c["name"] for c in result["columns"]]
        assert "row_id" in names
        assert "created_at" in names
        assert "junk_1" not in names
