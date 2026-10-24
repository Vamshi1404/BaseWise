# BaseWise — Complete End-to-End System Architecture

> Canonical engineering reference for the implemented system. It matches the
> presentation narrative (problem → objectives → methodology → architecture →
> design → stack) but every behavior below is grounded in the actual codebase.
> Where the slides simplified, this document states the real rule.
>
> Status: Postgres-linked querying + Analysis Mode are **implemented**.
> MySQL / SQLite, Python SDK, and MCP server are **planned future work**
> (Section 14) — they are not implemented today.

---

## 1. What BaseWise Is

**BaseWise: An AI-Powered Database Intelligence Platform.**

A user links their own relational database (today: PostgreSQL / Supabase
Postgres), then asks plain-English questions and gets back:

1. Validated SQL that actually ran,
2. A readable explanation + short summary of what was found,
3. An honest `high / medium / low` confidence label with a trace,
4. The result rows (bounded),
5. A structured chart spec rendered interactively (when the result shape supports it).

A separate **Analysis Mode** proactively suggests 3–5 business questions from
the schema, then runs LLM-written Python analysis in a sandbox and returns
structured chart data + summary — without the user needing to know what to ask.

### 1.1 Problem being solved

- Structured data drives decisions, but the people who need answers usually
  cannot write SQL (e.g. a sales manager wanting revenue by region last quarter
  must wait for an analyst).
- Even skilled users find raw result sets laborious to turn into insight.
- Dashboards normally require separate BI tooling disconnected from the query layer.
- Most LLM tools stop at translation: no explanation, no pre-execution schema
  check, and every answer is presented with the same unearned certainty.
- A wrong join that returns plausible numbers is worse than an error message.

### 1.2 Objectives (as implemented)

- Answer plain-English questions with validated SQL + explanation + data.
- Self-recheck every generated statement and report honest confidence.
- Surface business insights + charts in a separate Analysis Mode.
- Execute all model-written code in an isolated sandbox; never on the web server.
- Protect credentials (Fernet at rest, in-memory only at use), enforce ownership,
  keep an audit trail (`query_runs`), stay portable across engines.

---

## 2. Five-Tier Architecture

```
┌──────────────────┐      HTTPS / SSE (JWT)      ┌──────────────────┐
│   Presentation   │ ──────────────────────────▶ │       API        │
│ React 19 SPA     │ ◀────────────────────────── │ FastAPI (/api/v1)│
│ Vite + TS +      │   structured JSON +         └────────┬─────────┘
│ Tailwind 4 +     │   SSE (status/token/result/error)    │
│ Recharts         │                                      │ Orchestration
└──────────────────┘                                      │ (Python services)
                                                          ▼
                          ┌──────────────┬────────────────┼──────────────┬──────────────┐
                          ▼              ▼                ▼              ▼              ▼
                   ┌────────────┐ ┌────────────┐  ┌──────────────┐ ┌───────────┐ ┌──────────────┐
                   │ Groq       │ │ Gemini     │  │ E2B Sandbox  │ │ Supabase  │ │ Linked DBs   │
                   │ gpt-oss-   │ │ 3.6-flash  │  │ ephemeral    │ │ Postgres  │ │ (user owned) │
                   │ 120b       │ │ (fallback) │  │ Python exec  │ │ (app data)│ │ Postgres now │
                   │ (primary)  │ │ via SDK    │  │ only         │ │           │ │ MySQL/SQLite │
                   └────────────┘ └────────────┘  └──────────────┘ └───────────┘ │ planned      │
                                                                                └──────────────┘
```

| Tier | Contents | Code |
|------|----------|------|
| Presentation | React single-page app | `frontend/src/` |
| API | FastAPI routers: `auth`, `databases`, `conversations`, `analysis` | `backend/app/api/`, `backend/app/main.py` |
| Orchestration | `agent_loop`, `query_router`, `analysis_engine`, `llm_client`, `model_registry`, `structured_output`, `sql_validator`, `db_context`, `schema_extractor`, `sandbox`, `security` | `backend/app/core/` |
| External | Groq (OpenAI-compatible REST), Gemini (`google.genai` SDK), E2B Code Interpreter | `backend/app/core/llm_client.py`, `sandbox.py` |
| Persistence | Supabase Postgres holding BaseWise app data (not user data) | `backend/schema.sql`, `backend/app/models/models.py` |

### 2.1 Central design rule: hardcoded connection, sandboxed everything else

This rule is load-bearing — do not violate it:

- **Connecting + extracting schema is deterministic, hardcoded code** built once
  with SQLAlchemy (`inspect()`, dialect-aware). No LLM involved.
  (`backend/app/core/schema_extractor.py:1-9, 97-212`)
- **Everything downstream runs as LLM-written Python inside an E2B sandbox**:
  running the query, computing analysis, producing chart JSON.
  (`backend/app/core/agent_loop.py:583-606`, `analysis_engine.py:289-294`,
  `sandbox.py:66-99`)
- **No model-written code ever runs on the web server.** There is no
  `eval` / `exec` / `subprocess` on the backend; the only E2B SDK call site is
  `sandbox.py`. `grep create_engine` hits only `schema_extractor.py:93`
  (real metadata connection) plus the sandbox-code *string* in `agent_loop.py`.
- **Hand-rolled agent loop, not LangChain.** Small custom steps with explicit
  retry/fallback tuned for free-tier rate limits. No framework abstraction.
  (`agent_loop.py:1-13, 403-633`, `llm_client.py:259-337`)

---

## 3. Frontend — Presentation Tier

Stack: **React 19.2, TypeScript, Vite 8, Tailwind CSS 4, Recharts 3, Axios,
lucide-react** (`frontend/package.json:12-22`).

| Area | Files | Behavior |
|------|-------|----------|
| Shell | `src/App.tsx` | JWT check, auth vs dashboard vs workspace, query/analysis mode switch, logout, add-DB flow |
| Dashboard | `src/pages/DashboardPage.tsx` | Lists linked DBs, select workspace, open add-DB modal |
| Workspace | `src/pages/DatabaseWorkspace.tsx` | Per-DB query + analysis tabs, conversation threads, chat + schema + charts |
| Chat | `components/ChatWindow.tsx`, `MessageItem.tsx`, `QueryResultTable.tsx`, `SchemaViewer.tsx`, `ConfidenceBadge.tsx` | Message list, SQL viewer, data table, schema inspector, confidence badge |
| Charts | `components/ChartRenderer.tsx`, `charts/FunnelChart.tsx`, `ScatterChart.tsx`, `TreemapChart.tsx`, `chartTheme.ts`, `ChartTooltip.tsx` | Renders backend chart JSON with Recharts (`BarChart` / `ComposedChart` Area+Line / donut Pie / Scatter / Funnel / Treemap) |
| API + SSE | `src/api/client.ts` | Axios + `fetch` SSE; auto-refresh on 401 (see §9) |
| Misc | `pages/ChartPreviewPage.tsx`, `hooks/useTypewriter.ts` | Chart preview fixture, typewriter effect |

Key point: the sandbox **never produces images**. It returns a JSON spec; the
frontend renders it. Chart type union (frontend-accepted):
`bar | line | pie | area | scatter | funnel | treemap | table`
(`frontend/src/types/index.ts:83-92`).

---

## 4. API Tier — FastAPI

App: `FastAPI(title="Basewise API")` + `CORSMiddleware` + 4 routers under
`/api/v1` + `GET /health` (`backend/app/main.py:1-29`).

Base URL: `VITE_API_BASE_URL` (defaults to `http://localhost:8001/api/v1`)
(`frontend/src/api/client.ts:7`).

### 4.1 Auth — `/api/v1/auth`

| Method + Path | Body | Returns |
|---|---|---|
| `POST /auth/signup` | `{email, password}` | `{id, email, access_token, refresh_token}` |
| `POST /auth/login` | `{email, password}` | `{access_token, refresh_token, token_type}` |
| `POST /auth/refresh` | `{refresh_token}` | `{access_token, refresh_token}` |
| `GET /auth/me` | `Bearer <access>` | `{id, email, created_at}` |

JWT: access **30 min**, refresh **7 days** (`backend/app/config.py:13-14`,
`core/security.py:21-30`). Frontend auto-refreshes on 401 then retries, else
clears tokens and redirects to `/login` (`client.ts:26-51`).

### 4.2 Linked databases — `/api/v1/databases`

| Method + Path | Purpose |
|---|---|
| `GET /databases` | List own DBs |
| `POST /databases` `{db_type, display_name, connection_url}` | Validate by live `extract_schema`, Fernet-encrypt immediately, store + seed `schema_cache` |
| `GET /databases/{id}` | Detail |
| `DELETE /databases/{id}` | Hard-delete row → cascades to cache/conversations/messages; encrypted credential destroyed |
| `POST /databases/{id}/test` | Live connectivity test |
| `GET /databases/{id}/schema` | Cached schema if `expires_at > now` (24h TTL), else re-scan |
| `POST /databases/{id}/schema/refresh` | Force re-scan |

TTL constant: `SCHEMA_CACHE_TTL_HOURS = 24` (`api/databases.py:18`).
Creation seeds `expires_at = now + 24h` (`:68-74`).
Today the link modal offers **Postgres only**; `db_type` is stored from day one
for future dialects (`models.py:32-33`).

### 4.3 Conversations (query path) — `/api/v1/conversations`

| Method + Path | Purpose |
|---|---|
| `GET /databases/{db_id}/conversations?mode=query\|analysis` | List threads |
| `POST /databases/{db_id}/conversations` `{mode}` | Create thread |
| `GET /conversations/{id}/messages` | History |
| `POST /conversations/{id}/messages` `{content}` | **Run full NL→SQL pipeline, SSE stream** |

SSE (query): `status → token* → status("Saving results...") → result → done`
(`api/conversations.py:153-224`, helper `_sse:231-232`).
SSE (analysis): `status* → result` or `error`; **no `token`, no `done`**
(`api/analysis.py:100-142`). Frontend has matching parsers:
`sendMessageStream(status,token,result,error+done)` vs
`executeStream(status,result,error)` (`client.ts:83-159, 176-243`).

### 4.4 Analysis — `/api/v1/analysis`

| Method + Path | Purpose |
|---|---|
| `POST /databases/{db_id}/analysis/suggest` | 3–5 business starting-point questions from schema |
| `POST /conversations/{id}/analysis/execute` `{prompt}` | LLM writes Python → E2B runs it → chart JSON + summary, SSE stream |

---

## 5. Request Lifecycles (what actually happens)

### 5.1 Link a database

1. `POST /databases` → `extract_schema(connection_url)` live. Failure → `400`.
   (`api/databases.py:49-52`)
2. `encrypt_credentials(url)` immediately; plaintext never persisted. (`:54-55`)
3. Insert `linked_databases` + initial `schema_cache` (`expires_at = now+24h`).
4. All later reads go through `_get_linked_db` which enforces
   `LinkedDatabase.user_id == current_user.id`. (`:170-180`)

### 5.2 Ask a question (query path) — `POST /conversations/{id}/messages`

1. **Ownership check**: `_get_conversation` joins `Conversation → LinkedDatabase`
   and filters by `user_id` (`api/conversations.py:261-274`).
2. Load linked DB row (by `conv.linked_database_id`), load `SchemaCache`
   as-is (400 if missing — no TTL re-check on this path; TTL lives on
   `GET /databases/{id}/schema`), load last **10** messages (desc, then reversed)
   as `{role, content}`. (`:94-118`)
3. Persist the user message, `decrypt_credentials(...)` **in memory only**.
   (`:121-125`)
4. Stream via `asyncio.Queue + asyncio.create_task(run_pipeline())` inside a
   `StreamingResponse` — this is **not** FastAPI `BackgroundTasks`
   (no such usage in the repo). (`:127-148`)
5. `run_nl_to_sql(question, schema_json, connection_url, history, on_status, on_token)`
   runs the §6 pipeline, emitting `status`/`token` events live.
6. On `pipeline_result`: persist assistant message
   (`content = summary or explanation`, plus `sql_generated`, `confidence_score`,
   `reasoning`, `chart_data`, `confidence_trace`), then persist `QueryRun`
   **only `if result.get("sql")`** — conversational turns (`sql=""`) and
   clarifications (`SELECT 1` → error result) skip the audit row. (`:175-201`)
7. `commit`, yield `result` + `done:[DONE]`. (`:203-224`)

### 5.3 Analysis task — `POST /conversations/{id}/analysis/execute`

Same ownership + schema + decrypt preamble (`api/analysis.py:56-70`), save user
message, same Queue/task SSE pattern (`:77-95`), `execute_analysis(...)`
(§7), on success persist assistant message with `chart_data` and
`content = chart_data.summary`, commit, yield `result` (with `python_code`,
`execution_ms`). **Analysis never writes `query_runs`** — only `Message`.
(`:119-142`)

---

## 6. NL→SQL Pipeline — `backend/app/core/agent_loop.py`

Entry: `run_nl_to_sql(question, schema, db_connection_url,
conversation_history, on_status, on_token)` returns
`{sql, explanation, summary, reasoning, issues_found, changes_made,
confidence_score, confidence_label, results, chart_data, row_count,
rows_affected, operation_type, execution_ms, sandbox_session_id,
status, error, route, route_reason, pass2_skipped, confidence_trace}`
(`agent_loop.py:357-382`).

### 6.1 Step 0 — Route (intent classifier, zero LLM in common case)

Module: `backend/app/core/query_router.py`. Route strings are snake_case:

- `conversational` — greeting/thanks/ack/off-topic; answered directly.
- `simple_query` — clean single-table read; only labels for the §6.4 gate.
- `full_pipeline` — default: joins, aggregations, history refs, ambiguity,
  **and all write/destructive intent**.

Precedence (`query_router.py:247-262`):

1. `words ∩ _DESTRUCTIVE_WORDS ≠ ∅` → `full_pipeline`
   (list includes `insert/update/delete/remove/drop/truncate/alter/create/add/
   change/modify/rename/erase/purge/reset/clear/edit/set/merge/reassign`, `:72-76`).
2. Conversational regex hit **and** no schema reference → `conversational`
   (patterns: greeting/thanks/goodbye/ack/smalltalk/capability, `:154-194`;
   canned replies for all but open-ended `other`, `:196-227`).
3. Schema reference → `simple_query` iff `_is_simple_query`, else `full_pipeline`.
4. `words ∩ _QUERY_WORDS ≠ ∅` → `full_pipeline`.
5. Else `full_pipeline, needs_escalation=True, confidence=0.5`.

`_is_simple_query` (`:134-151`) is true only if **all** hold:

- `len(words) ≤ 12` (`MAX_SIMPLE_QUESTION_WORDS = 12`, `:32`),
- no `_COMPLEXITY_WORDS` (aggregates, `by/over/vs/per`, time words, `:57-63`),
- no `_HISTORY_REF_WORDS` (`that/this/it/previous/...`, `:66-69`),
- exactly **1** table-name match (table names + non-generic `len ≥ 4` columns,
  `:102-116, 128-151`).

Ambiguous band optionally costs **one small LLM call** (`_escalate`, `:265-306`,
gated by `settings.query_router_escalation`, default `True` in `config.py:35`).
`route_request` always returns with `needs_escalation=False` (`:342`).

Effect in pipeline (`agent_loop.py:387-389, 733-756`): `conversational` returns
via `_conversational_result` — canned reply (free) or one small `temperature=0.5,
max_tokens=150` call for `other` — with **zero SQL, zero sandbox**,
`status=success, confidence 1.0/high`, and **no `query_runs` row**.

### 6.2 Step 1 — Schema relevance selection (deterministic, no LLM)

Constants (`agent_loop.py:91-94`):

```
MAX_SELECTED_TABLES = 3
MAX_COLUMNS_PER_TABLE = 12
SMALL_SCHEMA_TABLE_LIMIT = 10
FALLBACK_SELECT_COUNT = 6
```

Algorithm (`_select_relevant_schema`, `:272-310`):

- `≤ 1` table → whole schema.
- Keywords = question + history words minus stopwords (`:183-186, 96-104`),
  matched with singular/plural stemming + business-synonym groups
  (customer/client/user, order/purchase/sale, price/cost/revenue, location/city/...,
  `:108-180`).
- Score tables by keyword overlap; keep `matched[:3]`.
- **No match**: `≤ 10` tables → whole schema; `> 10` → top-6 by `row_count`.
- **No keywords at all**: same small-whole / large-top-6 rule.
- Expand with **one FK hop in both directions** (referenced tables *and* tables
  referencing the selection), so joins the user didn't name survive
  (`_expand_fk_closure`, `:201-217`). Result can exceed 3 tables.
- Prune wide tables (`> 12` cols) keeping PKs, FK cols, `id/_id`, date/time
  fields, keyword-matching cols (`_prune_columns`, `:220-256`); stats/samples
  pruned to kept cols.

History budget: last **8 turns / 4000 chars**, oldest dropped first, NL only —
never row data (`HISTORY_MAX_TURNS = 8`, `HISTORY_MAX_CHARS = 4000`, `:36-37`,
`_build_history_text`, `:313-354`).

Rendering: Pass 1 gets the **full** context (columns + stats + 3 sample rows);
Pass 2 gets a **light** names/types/keys view
(`schema_context` vs `light_context`, `:394-395`; `db_context.py:86-137`).

### 6.3 Step 2 — Pass 1 (generate)

Prompt: question + full schema slice + bounded history; system instruction
demands JSON only:
`{"sql","explanation","confidence": 0.0–1.0,"reasoning"}`,
`temperature=0.1` (`agent_loop.py:405-440`).
History carry-over is explicit: build a checklist of every constraint from
current + prior turns; dropping a prior filter is a correctness error
(`:414-422`).

Parsing: `structured_output.parse_llm_json` with one corrective self-heal call;
on total failure regex-extract ````sql` else raw text, `confidence=0.4`
(`:445-467`). Dict path defaults `confidence` to `0.5` (`_as_float`, `:71-80`).

Ambiguity protocol (`:423-426, 481-482, 901-904`): model returns
`{"sql":"SELECT 1","explanation":"<clarifying question>","confidence":0.1,…}`.
`SELECT 1` + explanation ending in `?` surfaces the question as an error result
with **no execution**.

### 6.4 Step 3 — Gate (veto-only early exit, may skip Pass 2)

Eligible only if **all three** hold (`agent_loop.py:493-497`,
`EARLY_EXIT_MIN_CONFIDENCE = 0.9`, `:42`):

1. `route == "simple_query"`,
2. `llm_confidence_1 ≥ 0.9`,
3. `_detect_operation_type(candidate_sql) == "read"`
   (`SELECT/WITH/EXPLAIN` → read; `INSERT/UPDATE/DELETE/MERGE` → write;
   else DDL; leading comments skipped; `:907-928`).

Then `validate_sql_against_schema(candidate_sql, schema)` must pass — checked
against the **full** schema, not the pruned slice (`:498`). The validator
(`sql_validator.py:19-82`) parses with `sqlglot.parse_one(dialect=postgres)`,
excludes CTE names, rejects unknown tables/columns, skips `*`, and returns
`False` on any exception. It is documented veto-only: it can only decline to
skip, never grant confidence (`sql_validator.py:1-11`).

Skip path sets `final_sql = candidate`, `p2 = p1`, `issues = []`
(`agent_loop.py:507-512`) and emits `Query looks clean — skipping recheck...`.

### 6.5 Step 4 — Pass 2 (self-recheck; no row data)

Header guarantee: **row data never enters this prompt**
(`agent_loop.py:9-10, 505`). Inputs: original question + history + **light**
schema + candidate SQL (`:515-547`), `temperature=0.0` (`:549`).
The reviewer is told history-derived filters are legitimate and must not be
stripped (`:525-530`).

Expected output (`:531-533, 553-575`):
`{"approved_sql","issues_found": [],"confidence","changes_made"}`.
On parse failure: keep candidate, `p2 = p1 × 0.9`.

### 6.6 Step 5 — Execute in E2B (bounded)

Sandbox code builds `sqlalchemy + pandas`, injects `DB_URL` from env,
`conn.commit()`, `fetchmany(100)`, `json.dumps(..., default=str)` so
dates/Decimals stay JSON-safe (`agent_loop.py:583-606`,
`MAX_RESULT_ROWS = 100`, `:30`). Runner: ephemeral
`Sandbox(api_key, timeout=30)`, `pip install psycopg2-binary sqlalchemy pandas
pymysql -q`, `run_code(code, envs={"DB_URL": ...})`
(`sandbox.py:85-99`). No matplotlib by design — data only.

### 6.7 Step 6 — Repair once (bounded retry)

On failure: one repair call with question + history + **full** schema +
failed SQL + exact error text (no row data), expecting `{"sql","explanation"}`,
`temperature=0.1` (`_repair_failed_sql`, `:779-840`). Only if the repair
returns a *different* non-empty SQL is it re-executed once (`:614-633`).

### 6.8 Step 7 — Chart + summary

**Chart is deterministic — no LLM** (`_build_chart_data`, `:931-1182`):

- Empty, `< 2` cols, `> 15` rows (`MAX_CHART_CATEGORIES = 15`, `:944`), or no
  categorical + numeric pattern → `None` (table only).
- Pure-numeric (≥ 2 numerics, no categorical/date) → `scatter`
  (optional `z_key` for 3rd numeric).
- Intent-gated: `scatter` words (`scatter/correlat/...`, `:956-959`),
  `funnel` words (`funnel/conversion/pipeline/stage/...`, `:948-951`, needs
  1 categorical + 1 numeric, 3–8 distinct, no dates),
  `treemap` words (`treemap/hierarchy/breakdown/...`, `:952-955`, needs
  2 categoricals + 1 numeric → nested `{name, children:[{name,value}]}`).
- `pie` only for single category + share column (name hints `pct/percent/share/...`
  or all values in `[0,1]`, `:1052-1065`).
- Date x-axis → `line` (name hints + ISO-parse check, `:1023-1049`);
  otherwise categorical + numerics → `bar` (up to 3 `y_keys`).
- Query mode never emits `area` (analysis-only type).

**Summary** (`_summarize_results`, `:843-898`): empty → canned
`came back empty...`; else prompt wraps `json.dumps(results)[:5000]`
(`MAX_RESULT_CHARS = 5000`, `:31`) in `<RESULT_ROWS>` flagged as untrusted
data, asks for 2–4 conversational sentences, streams via
`llm_client.complete_stream` → `on_token`, falls back to non-streaming, then to
a hardcoded line. Summary tokens are what drive the frontend typewriter.

### 6.9 Step 8 — Composite confidence + trace

```text
skipped Pass 2:  C = round(0.7·p1 + 0.3·e, 2)
otherwise:       C = round(0.3·p1 + 0.4·p2 + 0.3·e, 2)
high:   C ≥ 0.75
medium: C ≥ 0.50
else    low
e = 1.0 on sandbox success, 0.0 on failure
```

(`agent_loop.py:636-652`.) Consequence: a failed SQL run caps at `0.7`, so it
**can never be labelled high**. The `confidence_trace` (`:686-706, 1211-1293+`)
records version, formula, weights, per-component scores/sources/models, routing,
self-heals, gate reason, and repair notes — safe to persist (no row data).

---

## 7. Analysis Mode — `backend/app/core/analysis_engine.py`

Separate conversation thread (`mode = "analysis"`, never shares history with
query threads). Two endpoints (§4.4).

### 7.1 Suggest — `generate_suggestions(schema)` (`:128-171`)

Light schema context → prompt demands **3 to 5** business questions (trends,
growth, performance, risk — never schema-structure trivia), JSON array only,
`temperature=0.3, max_tokens=512`. Returns `parsed[:5]`; line-split fallback;
final default `["Show overall data summary", ...]`.

### 7.2 Execute — `execute_analysis(prompt, schema, url)` (`:246-323`)

1. Full schema context (so the model never invents columns).
2. `max_attempts = 2`: generate Python (`temperature=0.2, max_tokens=2048`,
   strip fences), `run_in_sandbox(...)`; on failure feed `<ERROR>` back and
   regenerate once (`_build_analysis_messages`, `:174-243`).
3. Code contract: `os.environ['DB_URL'] + sqlalchemy + pandas`,
   `print(json.dumps(result_dict))` last, shape
   `{"type","title","data","x_key","y_keys","summary"}` with
   `type ∈ bar/pie/line/area/scatter/funnel/treemap`,
   `NEVER matplotlib`, `ONLY schema tables/cols` (`:196-239`).
4. Extract JSON from stdout (`structured_output.extract_json`); non-dict →
   `{"type":"table",...}`. Apply location-label safety net:
   collapse `> 24`-char / comma addresses to leading locality, merge
   case-variants by summing, sort desc, cap **10** categories
   (`MAX_LOCATION_CATEGORIES = 10`, `:27, 84-125`).
5. Return `{status, chart_data, python_code, execution_ms, sandbox_session_id}`.
   Failure → `{status:"error", error, ...}` surfaced as SSE `error`.

---

## 8. LLM Client, Fallback Chain, Model Registry

Config (`backend/app/config.py:16-29`):

```
PRIMARY_LLM_MODEL  = openai/gpt-oss-120b   # Groq OpenAI-compatible REST
FALLBACK_LLM_MODELS = gemini-3.6-flash      # google.genai SDK (Interactions API)
GROQ_BASE_URL  = https://api.groq.com/openai/v1
GEMINI_BASE_URL = https://generativelanguage.googleapis.com/v1beta/openai/
```

Provider routing follows the slug: `gemini-*` → SDK, everything else → Groq
REST (`config.endpoint_for`, `:51-59`; `llm_client.py:297-304`).
The SDK path is required because new `AQ.*` AI Studio keys 404 on Google's raw
OpenAI-compatible REST endpoint (`llm_client.py:1-18`).

`complete(messages, temperature=0.1, max_tokens=4096, timeout=60)` (`:259-337`):

- Order = `[primary] + fallbacks` reordered by `model_registry.order_chain`.
- Per model: up to **2 attempts** with short backoff honoring `Retry-After` /
  Groq `x-ratelimit-reset-requests` / Gemini `RetryInfo` (capped 30s)
  (`_rest_complete_with_retry`, `:195-232`; `_gemini_complete_with_retry`,
  `:235-256`).
- Empty content counts as failure → next model. Each outcome recorded.
  Success fills `report = {model, attempts, fallback}` (feeds confidence trace).
- Total exhaustion raises `RuntimeError("All LLM models exhausted... AI service
  is temporarily at capacity — try again in a moment.")` — a user-visible
  capacity error, not a silent hang or fabricated answer.

`complete_stream(...)` (`:340-453`) is **single-model only** (used for summaries);
no fallback chain.

Registry (`model_registry.py`): in-memory `{calls, successes, failures,
consecutive_failures, last_error, last_used_at}` per slug; `COOLDOWN_AFTER = 3`
(`:23`); `order_chain` moves cooldown models to the end, never drops/blocks;
success clears cooldown instantly; restart clears all (`:70-78, 17-18`).

Free-tier context (from `actions.md`): Groq ~30 RPM / 1000 RPD / 8000 TPM
(`gpt-oss-120b` reserves ~4900 tokens/call, so TPM 429s are expected and
retried); Gemini fallback ~20 req/day — hence fallback-only. Payloads bounded
via history 8/4000 + relevant-table/light-schema trimming. Verify live models
with `backend/scripts/test_models.py`.

---

## 9. Sandbox — `backend/app/core/sandbox.py`

Abstraction `run_in_sandbox(code, db_connection_url, timeout_seconds=30)
→ SandboxResult{stdout, stderr, error, results, execution_ms,
sandbox_session_id, success}` (`:66-127`). Backend never calls E2B elsewhere —
swap providers by changing this file (`:1-15`).

- Ephemeral `Sandbox` per call, torn down after.
- `DB_URL` injected via `envs` (normalized: `asyncpg → psycopg2`,
  `mysql → pymysql` with `hide_password=False` so `***`-masking doesn't break
  auth, `:44-63`); never logged, never in code literals, never persisted.
- Pre-installs `psycopg2-binary sqlalchemy pandas pymysql -q`; **no matplotlib**.
- `SandboxResult.success = (execution.error is None)`; E2B exceptions become
  `success=False` with `str(exc)`.

---

## 10. Schema Extraction + Context Rendering

Extractor (`schema_extractor.py:61-217`): sync SQLAlchemy engine
(`asyncpg → psycopg2` mapping, 10s `connect_timeout` on postgres/mysql),
`inspect(engine)` → per table: columns `{name, type, nullable, primary_key}`,
PKs, FKs `{column, references_table, references_column}`, best-effort
`COUNT(*)`, up to **3 sample rows** and per-column `distinct + min/max`
(numeric/temporal only, first 8 such cols) gated by
`STATS_ROW_LIMIT = 50_000` and `MAX_STATS_COLUMNS = 20` (`:19-21`).
All values JSON-serialized (Decimal/datetime/UUID/bytes handled, `:24-47`).
Connection URL is transient in-memory, never logged or sent to the LLM
(`:79-80`).

Renderer (`db_context.py:86-137`): `[DATABASE CONTEXT] dialect: …` +
`## TABLE name (n cols, ~rowcount rows; PK: …; links: …)` + columns
(full: semantic hints + `[stats]` + `[sample rows]`; `light=True`: names+types
+keys only). Heuristic column hints cover `email/password_hash (never expose)/
created_at/amount/price/city/...` (`:12-55`).

---

## 11. Persistence — BaseWise's Own Database

Supabase Postgres, DDL in `backend/schema.sql:1-102`, ORM in
`backend/app/models/models.py:1-105`, async engine via
`create_async_engine(settings.database_url)` + `AsyncSessionLocal`
(`app/database.py:5-11`). Expected `DATABASE_URL`:
`postgresql+asyncpg://...pooler.supabase.com:5432/postgres`.

| Table | Key columns | Notes |
|---|---|---|
| `users` | `id, email, password_hash, created_at` | bcrypt hash, never plaintext |
| `linked_databases` | `id, user_id→users, db_type, display_name, encrypted_credentials, created_at, last_schema_scan_at` | Fernet ciphertext; `db_type` default `postgres` for future dialects |
| `schema_cache` | `id, linked_database_id UNIQUE→linked_databases, schema_json, scanned_at, expires_at` | One row per DB; JSON from §10 |
| `conversations` | `id, linked_database_id→linked_databases, mode query\|analysis, created_at` | Enforces query/analysis thread separation |
| `messages` | `id, conversation_id→conversations, role user\|assistant, content, sql_generated, confidence_score, reasoning, chart_data JSON, confidence_trace JSON, created_at` | Chart = structured JSON, never images |
| `query_runs` | `id, message_id→messages SET NULL, sql_text, operation_type read\|write\|ddl, row_count, rows_affected, execution_ms, sandbox_session_id, status success\|error, created_at` | Audit trail (with the §11.4 caveats) |

Cascades: deleting `linked_databases` hard-deletes cache + conversations →
messages → runs. `messages → query_runs` is `SET NULL` at SQL level
(`schema.sql:91`) with ORM-level `delete-orphan` (`models.py:87, 104`).

---

## 12. Security Model

- **Passwords**: `passlib` bcrypt (`security.py:9-17`).
- **Sessions**: JWT access + refresh, `HS256`, 30 min / 7 days
  (`security.py:21-40`, `config.py:12-14`). Distinct from credential encryption.
- **Credentials at rest**: Fernet (`cryptography.fernet`) with server-held
  `FERNET_KEY`; `encrypt_credentials` on link, `decrypt_credentials` only
  transiently per request (`security.py:42-56`, `api/databases.py:54-55`).
  Plaintext never written to DB, never logged (`security.py:54-56`,
  `sandbox.py:68, 95-99`), never sent to the LLM.
- **Ownership**: every DB lookup via `_get_linked_db`
  (`user_id == current_user.id`); every conversation lookup via
  `_get_conversation` (join + `user_id` check). Second-hop loads
  (`LinkedDatabase` by `conv.linked_database_id` in `conversations.py:94-99`,
  `analysis.py:58-61`) rely on the prior conversation check.
- **Prompt-injection hygiene**: all row content treated as untrusted data —
  delimited `<RESULT_ROWS>` blocks flagged as data-not-instructions, capped at
  100 rows / 5000 chars, and **entirely excluded** from Pass 2 and repair prompts
  (`agent_loop.py:9-12, 505, 610-613, 861-866`). History carries NL only.
- **Sandbox isolation**: §9; nothing model-written executes on the backend.
- **Writes deliberately not gated**: `_detect_operation_type` is a display/audit
  label only (`agent_loop.py:907-912`); the sandbox runs whatever SQL the
  pipeline produced — `SELECT/INSERT/UPDATE/DELETE/DDL` all permitted, no
  confirmation. The DB role the user supplied is the ceiling. `query_runs` is
  the after-the-fact safety net. Users should link least-privilege roles.
  (Explicit choice per `project.md §3.2`, `README §Security Model`.)
- **Audit caveats (honest)**: `query_runs` rows are written only when
  `result.get("sql")` is non-empty — conversational and clarification turns skip
  it (`conversations.py:188-201`); Analysis Mode persists `Message` only, never
  `query_runs` (`analysis.py:125-133`).
- **Unlink**: hard delete of `linked_databases` destroys the ciphertext and
  cascades cache/threads (`databases.py:102-113`).

---

## 13. Technology Stack

| Layer | Technology |
|---|---|
| Frontend | React 19.2, TypeScript, Vite 8, Tailwind CSS 4, Recharts 3, Axios, lucide-react |
| API | FastAPI 0.115.5, Pydantic v2 + pydantic-settings, JWT (`HS256`, 30 min / 7 d) |
| LLM inference | Groq `openai/gpt-oss-120b` (primary, OpenAI-compatible REST) + Gemini `gemini-3.6-flash` (fallback, `google.genai` SDK); health registry + ordered fallback chain |
| Code execution | E2B Code Interpreter — ephemeral sandboxes running model-written Python |
| Persistence | Supabase Postgres, SQLAlchemy 2 (async) + `asyncpg`; sync `psycopg2-binary` for schema work |
| Linked DBs (today) | PostgreSQL only; `db_type` reserved for future |
| Security | Fernet credential encryption, bcrypt hashing, JWT sessions |
| Streaming | Server-Sent Events over HTTPS (`status`/`token`/`result`/`error`/`done` on query; `status`/`result`/`error` on analysis) |
| Deployment | Frontend on Vercel, backend on Render (docs-level; no `render.yaml`/`vercel.json`/`Dockerfile` in repo) |
| Testing | ~180 backend cases across 10 modules (`pytest --collect-only` ≈ 181); frontend `oxlint` + `tsc -b` |

Backend tests (`backend/tests/`): `test_agent_loop`, `test_auth_logging`,
`test_chart_detection`, `test_jwt_security`, `test_llm_client`,
`test_model_registry`, `test_query_router`, `test_schema_selection`,
`test_sql_validator`, `test_structured_output`. Scripts: `test_models.py`
(live model availability), `test_chart_e2e.py`, `verify_auth_errors.py`.

Run:

```bash
# Backend
cd backend
pytest
# Frontend
cd frontend
npm run lint
npm run build
```

Env (`backend/.env`, see `.env.example`): `DATABASE_URL`, `FERNET_KEY`
(generate via `python -c "from cryptography.fernet import Fernet;
print(Fernet.generate_key().decode())"`), `JWT_SECRET`, `JWT_ALGORITHM=HS256`,
`ACCESS_TOKEN_EXPIRE_MINUTES=30`, `REFRESH_TOKEN_EXPIRE_DAYS=7`,
`GROQ_API_KEY`, `GEMINI_API_KEY`, `PRIMARY_LLM_MODEL=openai/gpt-oss-120b`,
`FALLBACK_LLM_MODELS=gemini-3.6-flash`, `E2B_API_KEY`,
`ALLOWED_ORIGINS=http://localhost:5173`, `QUERY_ROUTER_ESCALATION=true`.
Frontend: `VITE_API_BASE_URL` (default `http://localhost:8001/api/v1`).

---

## 14. Roadmap — Future Work (explicitly not built yet)

These are scoped in `project.md`/`README.md` but have **no implementation** in
this repo today. The backend interfaces were shaped so each can reuse the same
internals without a rewrite.

1. **More dialects (Milestone 7)** — MySQL, SQLite, other Postgres-compatible
   sources through the identical flow, with branching confined to the connector
   module. Today: `db_type` stored, sandbox pre-installs `pymysql`, extractor
   normalizes `asyncpg → psycopg2` — but the link UI is Postgres-only and no
   second dialect is exercised end-to-end.
2. **Python SDK (Milestone 8)** — `pip`-installable client performing queries
   against a linked DB from a script, using the same `LLMClient.complete(...)`
   and `SandboxExecutor.run(code, context)` internals as the web backend.
3. **MCP server (Milestone 9, future)** — exposes the same internals
   (schema-extraction module, LLM client interface, sandbox executor,
   NL→SQL pipeline, analysis engine) as tools/resources over the
   Model Context Protocol for AI-agent integration. `project.md §11` requires
   the internal architecture stay clean and swappable specifically so the MCP
   layer becomes another consumer — not a rewrite. Not designed or built here.

Also out of scope for this document: paid tiers / bring-your-own-key,
dashboard-builder / report-export beyond Analysis plots.

---

## 15. Failure & Degraded-Mode Behavior

- **All LLM models exhausted / rate-limited**: user-visible capacity error
  (`All LLM models exhausted... try again in a moment`), never a silent hang or
  fabricated answer (`llm_client.py:333-337`).
- **Sandbox spin-up/execution failure**: `query_runs.status = 'error'` with the
  SQL still shown when generated; summary path degrades to hardcoded text
  (`agent_loop.py:654-668, 892-898`).
- **SQL execution failure**: same `error` state + exact error preserved; one
  bounded repair retry, then the final error is reported with what was attempted
  (important since writes/DDL can fail partway).
- **Low confidence**: still shown, visibly flagged `low` (`C < 0.5`), user can
  follow up; the system never silently refuses.
- **Missing schema cache** on query/analysis: `400/400` (`Schema not loaded...`);
  `GET /schema` instead re-scans on TTL expiry.

---

## 16. Key File Map (read these first to continue work)

```
backend/schema.sql                  Supabase DDL (app tables + enums)
backend/app/main.py                 FastAPI app + router registration
backend/app/config.py               Settings + Groq/Gemini routing + TTLs
backend/app/database.py             Async engine + session factory
backend/app/models/models.py        ORM: users → linked_databases → schema_cache / conversations → messages → query_runs
backend/app/api/auth.py             signup/login/refresh/me
backend/app/api/databases.py        link/list/test/schema (+24h TTL, Fernet, ownership)
backend/app/api/conversations.py    query pipeline + SSE (status/token/result/error/done)
backend/app/api/analysis.py         suggest + execute + SSE (status/result/error)
backend/app/core/agent_loop.py      NL→SQL: route → schema select → pass1 → gate → pass2 → E2B → repair → chart/summary → confidence
backend/app/core/query_router.py    conversational/simple_query/full_pipeline heuristics + optional 1-call escalation
backend/app/core/analysis_engine.py suggestions (3–5) + Python-in-sandbox + chart spec + label cleanup
backend/app/core/llm_client.py      Groq REST + Gemini SDK, 2-attempt 429 retry, fallback chain
backend/app/core/model_registry.py  in-memory health (cooldown after 3 consecutive failures, reorder-only)
backend/app/core/sandbox.py         sole E2B boundary (DB_URL env, 30s, no matplotlib)
backend/app/core/schema_extractor.py deterministic SQLAlchemy inspect() extraction
backend/app/core/db_context.py      full vs light prompt rendering
backend/app/core/sql_validator.py   veto-only sqlglot gate
backend/app/core/security.py        bcrypt + JWT (30m/7d) + Fernet (separate keys)
backend/app/core/structured_output.py JSON extract + one-call self-heal
frontend/src/api/client.ts          Axios + SSE helpers + 401 auto-refresh
frontend/src/components/ChartRenderer.tsx  Recharts rendering of chart JSON
frontend/src/pages/DatabaseWorkspace.tsx   query/analysis workspace
```

---

## 17. References

1. V. Zhong, C. Xiong and R. Socher, “Seq2SQL: Generating structured queries
   from natural language using reinforcement learning,” arXiv:1709.00103, 2017.
2. T. Yu et al., “Spider: A large-scale human-labeled dataset for complex and
   cross-domain semantic parsing and text-to-SQL task,” in Proc. EMNLP, 2018.
3. M. Pourreza and D. Rafiei, “DIN-SQL: Decomposed in-context learning of
   text-to-SQL with self-correction,” in Proc. NeurIPS, 2023.
4. J. Li et al., “Can LLM already serve as a database interface? A big bench
   for large-scale database grounded text-to-SQLs,” in Proc. NeurIPS, 2023
   (BIRD).
5. A. Madaan et al., “Self-Refine: Iterative refinement with self-feedback,”
   in Proc. NeurIPS, 2023.
6. K. Greshake et al., “Not what you’ve signed up for: Compromising real-world
   LLM-integrated applications with indirect prompt injection,” in Proc. ACM
   AISec Workshop, 2023.
7. M. Jones, J. Bradley and N. Sakimura, “JSON Web Token (JWT),” RFC 7519, IETF, 2015.
8. S. Ramírez, “FastAPI documentation,” fastapi.tiangolo.com; E2B, “E2B code
   interpreter documentation,” e2b.dev/docs.
