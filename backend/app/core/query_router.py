"""
Pre-pipeline intent router (project.md Section 4.0).

Decides BEFORE the SQL pipeline runs what kind of request this is:

  conversational  -> no SQL, no sandbox; answer directly (greeting/thanks/off-topic)
  simple_query    -> a clean single-table read; labeled for the #4 early-exit
  full_pipeline   -> the default: everything else (joins, aggregations, history
                     references, ambiguity, and ALL write/destructive intent)

Heuristic-first and deterministic, so the common cases cost zero extra LLM calls.
An optional small LLM call (settings.query_router_escalation) only fires for the
genuinely ambiguous band — no conversational trigger, no schema keyword, no
generic query language — which would otherwise burn a full multi-pass pipeline
on chit-chat.
"""
import logging
import re
from dataclasses import dataclass
from typing import Optional

from app.config import settings
from app.core import llm_client
from app.core import structured_output

logger = logging.getLogger(__name__)

ROUTE_CONVERSATIONAL = "conversational"
ROUTE_SIMPLE = "simple_query"
ROUTE_FULL = "full_pipeline"

MAX_SIMPLE_QUESTION_WORDS = 12


@dataclass
class RouteDecision:
    route: str
    reason: str
    needs_escalation: bool = False
    confidence: float = 1.0


# Words that make a request look like it wants data, even without a schema hit.
_QUERY_WORDS = {
    "show", "list", "get", "find", "display", "count", "total", "sum",
    "average", "avg", "max", "min", "compare", "filter", "sort", "search",
    "select", "query", "generate", "report", "breakdown", "trend", "statistics",
    "stats", "details", "top", "bottom", "many", "much", "which", "when",
    "where", "how", "revenue", "profit", "cost", "sales", "orders", "customers",
    "chart", "graph", "number", "amount", "growth", "percent", "percentage",
    "by", "over", "vs", "from", "between", "after", "before", "today",
    "yesterday", "last", "month", "week", "year", "quarter", "summary",
    "summarize",
}

# A question containing any of these is NOT a clean single-table read.
_COMPLEXITY_WORDS = {
    "total", "sum", "average", "avg", "max", "min", "count", "compare",
    "comparison", "trend", "growth", "rank", "ranked", "group", "between",
    "top", "bottom", "percentage", "percent", "monthly", "weekly", "quarterly",
    "annual", "daily", "by", "over", "vs", "per", "most", "least", "last",
    "recent", "today", "yesterday", "week", "month", "year", "quarter",
}

# Follow-up phrasing that depends on earlier turns -> carry-over rules apply.
_HISTORY_REF_WORDS = {
    "that", "this", "these", "those", "same", "previous", "earlier", "prior",
    "above", "again", "also", "it", "one", "there",
}

# Write/DDL intent -> always the full pipeline (never conversational/simple).
_DESTRUCTIVE_WORDS = {
    "insert", "update", "delete", "remove", "drop", "truncate", "alter",
    "create", "add", "change", "modify", "rename", "erase", "purge", "reset",
    "clear", "edit", "set", "merge", "reassign",
}

# Generic column names that would make ordinary text look like a query.
_GENERIC_COLUMNS = {
    "id", "name", "title", "status", "type", "date", "time", "value", "user",
    "role", "count", "total", "active", "enabled", "description",
}


def _stem(word: str) -> str:
    """Conservative singular/plural reduction (mirrors agent_loop's matcher)."""
    if len(word) <= 4:
        return word
    if word.endswith("ies"):
        return word[:-3] + "y"
    if word.endswith("s"):
        return word[:-1]
    return word


def _question_words(question: str) -> set[str]:
    words = set(re.findall(r"\w+", (question or "").lower()))
    words |= {_stem(w) for w in words}
    return words


def _schema_keywords(schema: dict) -> set[str]:
    """Distinctive names (table names + non-generic column names) to detect a data question."""
    schema = schema or {}
    keywords: set[str] = set()
    for table in schema.get("tables", []):
        name = str(table.get("name", "")).strip().lower()
        if name:
            keywords.add(name)
            keywords.add(_stem(name))
        for col in table.get("columns", []):
            cname = str(col.get("name", "")).strip().lower()
            if len(cname) >= 4 and cname not in _GENERIC_COLUMNS:
                keywords.add(cname)
                keywords.add(_stem(cname))
    return keywords


def _has_schema_ref(question: str, schema_keywords: set[str]) -> bool:
    if not schema_keywords:
        return False
    lower = (question or "").lower()
    if any(kw in lower for kw in schema_keywords):
        return True
    return bool(_question_words(question) & schema_keywords)


def _table_matches(table: str, lower_question: str, words: set[str]) -> bool:
    if table in lower_question:
        return True
    return table in words or _stem(table) in words


def _is_simple_query(
    question: str, words: set[str], schema: dict, schema_keywords: set[str]
) -> bool:
    """True for a clean single-table read with no joins/aggregation/carry-over."""
    if len(words) > MAX_SIMPLE_QUESTION_WORDS:
        return False
    if words & _COMPLEXITY_WORDS:
        return False
    if words & _HISTORY_REF_WORDS:
        return False
    lower = (question or "").lower()
    tables = [
        str(t.get("name", "")).strip().lower()
        for t in (schema or {}).get("tables", [])
        if t.get("name")
    ]
    matched = [t for t in tables if _table_matches(t, lower, words)]
    return len(matched) == 1


_CONVERSATIONAL_PATTERNS: list[tuple[re.Pattern, str]] = [
    (
        re.compile(
            r"^(hi+|hii+|hello+|hey+|yo|howdy|hiya|good\s+(morning|afternoon|evening|night))\b",
            re.I,
        ),
        "greeting",
    ),
    (
        re.compile(
            r"(thank\s*(you|s)|thanks|thx|ty|appreciate\s+(it|that|the\s+help)|much\s+appreciated)",
            re.I,
        ),
        "thanks",
    ),
    (
        re.compile(r"^(bye|goodbye|cya|see\s+(you|ya)|catch\s+you\s+later)\b", re.I),
        "goodbye",
    ),
    (
        re.compile(
            r"^(ok|okay|okie|k|kk|sure|got\s+it|gotcha|yep|nope|yes|no|alright|alrighty|right|fine|perfect|great|nice|works|done|understood|roger)\b[\s.!?,;:]*$",
            re.I,
        ),
        "ack",
    ),
    (
        re.compile(
            r"^(how\s+are\s+you|how's\s+it\s+going|how\s+are\s+things|how\s+is\s+it\s+going|what's\s+up)\b",
            re.I,
        ),
        "smalltalk",
    ),
    (
        re.compile(
            r"(what\s+can\s+you\s+do|how\s+do\s+you\s+work|how\s+do\s+you\s+help|who\s+are\s+you|where\s+are\s+you|what\s+are\s+you|help\s+me|what\s+is\s+this|features|about\s+you|your\s+features)",
            re.I,
        ),
        "capability",
    ),
]

_CANNED_REPLIES = {
    "greeting": (
        'Hello! Ask me anything about your data — for example, "show me total sales by region".'
    ),
    "thanks": "You're welcome! Anything else you'd like to look up?",
    "ack": "Got it. What would you like to query next?",
    "goodbye": "Talk soon!",
    "smalltalk": "Doing great — ready to dig into your data whenever you are.",
    "capability": (
        "I can turn plain-English questions into SQL against your connected "
        "database, run them, and explain the results — and in Analysis mode I can "
        'suggest and build charts. Try asking something like "show total orders by month".'
    ),
}


def detect_conversation_category(question: str) -> Optional[str]:
    """Category of a conversational turn, or None if it is not conversational."""
    text = (question or "").strip()
    if not text:
        return "other"
    for pattern, category in _CONVERSATIONAL_PATTERNS:
        if pattern.search(text):
            return category
    return None


def canned_reply(category: Optional[str]) -> Optional[str]:
    """Canned reply for a conversational category, or None if it needs the LLM."""
    if not category:
        return None
    return _CANNED_REPLIES.get(category)


def classify_route(
    question: str, schema: dict, history_text: str = ""
) -> RouteDecision:
    """Deterministic heuristic routing — no LLM calls.

    Precedence: destructive intent > conversational (unless it also references
    the schema) > schema hit (simple vs complex) > generic query language >
    genuinely ambiguous (flagged for optional LLM escalation).
    """
    text = (question or "").strip()
    if not text:
        return RouteDecision(ROUTE_CONVERSATIONAL, "empty message", False, 1.0)

    schema_keywords = _schema_keywords(schema)
    has_ref = _has_schema_ref(text, schema_keywords)
    words = _question_words(text)

    if words & _DESTRUCTIVE_WORDS:
        return RouteDecision(ROUTE_FULL, "mentions write/destructive intent", False, 1.0)

    category = detect_conversation_category(text)
    if category and not has_ref:
        return RouteDecision(ROUTE_CONVERSATIONAL, f"conversational ({category})", False, 1.0)

    if has_ref:
        if _is_simple_query(text, words, schema, schema_keywords):
            return RouteDecision(ROUTE_SIMPLE, "clean single-table read", False, 0.9)
        return RouteDecision(ROUTE_FULL, "references schema (complex)", False, 1.0)

    if words & _QUERY_WORDS:
        return RouteDecision(ROUTE_FULL, "generic query language, no schema match", False, 1.0)

    return RouteDecision(ROUTE_FULL, "ambiguous, needs LLM escalation", True, 0.5)


async def _escalate(question: str, history_text: str = "") -> Optional[tuple[str, str]]:
    """One small LLM call classifying an ambiguous message. Returns (category, complexity)."""
    messages = [
        {
            "role": "system",
            "content": (
                "You are the query router for a database assistant. Classify the user's "
                "message. Respond ONLY with JSON, no other text:\n"
                '{"category": "conversational" | "query" | "write", '
                '"complexity": "simple" | "complex", "reason": "one short phrase"}\n'
                "conversational = greeting, thanks, chit-chat, or anything needing no "
                "data from the database. query = the user wants data from the database. "
                "write = the user wants to add, change, or delete data.\n"
                "complexity: simple = one table, no joins or aggregations; complex = "
                "joins, aggregations, time ranges, or ambiguity."
            ),
        },
        {
            "role": "user",
            "content": (
                f"Message: {question}\n"
                + (f"Conversation: {history_text}" if history_text else "")
            ),
        },
    ]
    raw = await llm_client.complete(messages, temperature=0.0, max_tokens=256)
    parsed, _ = await structured_output.parse_llm_json(
        raw,
        expected_shape="an object with keys 'category', 'complexity', 'reason'",
        validate=lambda v: isinstance(v, dict),
        temperature=0.0,
        max_tokens=256,
    )
    if not isinstance(parsed, dict):
        return None
    category = str(parsed.get("category", "")).strip().lower()
    complexity = str(parsed.get("complexity", "")).strip().lower()
    if category not in ("conversational", "query", "write"):
        return None
    if complexity not in ("simple", "complex"):
        complexity = "complex"
    return category, complexity


async def route_request(
    question: str, schema: dict, history_text: str = ""
) -> RouteDecision:
    """Heuristic routing with optional LLM escalation for the ambiguous band.

    The returned decision always has needs_escalation cleared — either the band
    was resolved, escalation was disabled, or escalation failed (best-effort).
    """
    decision = classify_route(question, schema, history_text)
    if decision.needs_escalation and settings.query_router_escalation:
        try:
            escalated = await _escalate(question, history_text)
        except Exception as exc:
            logger.warning(f"Route escalation failed, defaulting to full pipeline: {exc}")
            escalated = None
        if escalated is not None:
            category, complexity = escalated
            if category == "conversational":
                decision = RouteDecision(
                    ROUTE_CONVERSATIONAL, "LLM classified as conversational", False, 0.9
                )
            elif category == "write":
                decision = RouteDecision(
                    ROUTE_FULL, "LLM classified as write intent", False, 1.0
                )
            elif category == "query" and complexity == "simple":
                decision = RouteDecision(
                    ROUTE_SIMPLE, "LLM classified as simple query", False, 0.9
                )
            else:
                decision = RouteDecision(
                    ROUTE_FULL, "LLM classified as query (complex)", False, 1.0
                )
    return RouteDecision(decision.route, decision.reason, False, decision.confidence)
