# Basewise — AI-Powered Database Intelligence Platform

`project.md` — canonical scoping document. Any agent picking up this project should read this in full before writing code.

---

## 1. Vision

Basewise lets non-technical users query, understand, and analyze relational databases entirely in plain English. It converts natural language into validated, explainable SQL, catches its own mistakes before returning an answer, and — once a database is fully connected — can be switched into an **Analysis Mode** that proactively surfaces business insights and visualizations without the user needing to know what to ask.

**Long-term target:** work against any cloud-hosted relational database the user can supply credentials for (Postgres, MySQL, SQLite, Supabase, and beyond), reachable via a Python SDK and (later) an MCP server for AI-agent integration.

**This document scopes the full vision.** There is no fixed deadline (~6 month soft horizon), and no Stage-1/Stage-2 split has been defined yet — build order should follow the milestone breakdown in Section 11, not an academic submission schedule.

**Solo-built.** One person builds the entire system. No role/module ownership split is needed in this doc.

---

## 2. Problem Statement (from source material)

- Writing SQL is a barrier for non-technical users, even for simple questions.
- Existing NL-to-SQL tools translate text to queries but explain nothing — no insight into _why_ a query was built, what the schema means, or whether the query is trustworthy.
- Even technically skilled users struggle to turn raw query results into business insight.
- Database performance issues (missing/duplicate indexes, inefficient joins) go unnoticed until they cause real problems.
- Dashboards/reports require separate BI tooling, disconnected from the query layer.
- No single system unifies conversational querying, schema intelligence, performance optimization, and reporting.

---

## 3. Core Architectural Decision: Hardcoded Connection, Sandboxed Everything Else

This is the central design principle and should not be violated by future implementation:

- **Connecting to a database and extracting schema metadata** (tables, columns, foreign keys, basic stats) is **hardcoded**, built once using SQLAlchemy as the dialect-abstraction layer. This is deterministic, security-sensitive, and doesn't benefit from being LLM-driven.
- **Everything downstream of that** — running the actual query, generating plots, computing analysis, answering "tell me about this specific customer," or any other user-driven task — happens by having the **LLM write and execute Python code in a sandboxed environment**, rather than Basewise hand-writing separate logic paths per database type or per query pattern. This is what lets Basewise generalize to "any cloud DB with a URL/key" without a combinatorial explosion of per-database, per-task code.

### 3.1 Sandbox execution model

Because the sandbox runs LLM-generated code against **live, real, user-supplied database credentials**, isolation matters more than convenience here — a sandbox escape or a prompt-injected result set that tricks the model into writing malicious code must not be able to reach another user's session or credentials.

**Decision:** Use **E2B** (e2b.dev) as the sandbox-execution provider — a fully managed, cloud-hosted API called from the backend over HTTPS. **Not** containers spun up inside the Render web service, and **not** any self-hosted sandbox infrastructure. This is the same shape as the OpenRouter integration: an external API call out to a third-party cloud service, nothing to provision, patch, or scale yourself, and nothing runs on any local device — the entire system stays online end-to-end (Vercel frontend → Render backend → OpenRouter for LLM → E2B for sandboxed execution → Supabase for data). This decouples sandbox lifecycle (spin up, execute, tear down, resource caps) from the web backend's lifecycle and is the standard pattern for products that execute LLM-generated code. Document the interface as an abstraction (`SandboxExecutor.run(code, context) -> result`) so the backend doesn't hard-couple to E2B's specific SDK calls elsewhere in the codebase, even though E2B is the concrete choice.

_(A self-hosted microVM pool — e.g., Firecracker/gVisor you run and maintain yourself — is a possible future alternative if E2B's cost or limits ever become a problem at real scale, but it is explicitly not the default and not something to build toward now.)_

**Account & cost notes:**

- Signup is via email/GitHub (no Google-account dependency) and does **not** require a credit card for the free Hobby tier — verify this hasn't changed at actual integration time, since signup flows and pricing shift.
- Hobby tier: one-time **$100 free usage credit**, sandboxes billed per-second (~$0.10-0.12/hr at default 2 vCPU + ~1 GiB RAM), 1-hour max session length, up to 20 concurrent sandboxes, 10 GiB storage.
- Given Basewise's usage pattern is short-lived sandboxes per query/analysis task (seconds to tens of seconds each, not continuous), the $100 credit covers on the order of **tens to hundreds of thousands of individual sandboxed task runs** — comfortably enough for the entire build/test phase and an active demo period. This is not unlimited-forever like OpenRouter's free models, though — sandbox compute is the one component of this stack with real usage-based cost, and becomes a genuine budget line only once there are many concurrent real users running frequent sessions (a Section 14 scale-later concern, not a build-phase concern).
- Upgrade to Pro ($150/mo) only becomes relevant for longer sessions (24h) or higher concurrency (100+) at real production scale.

Each sandbox invocation should receive: the decrypted DB connection object (scoped to that session only, never persisted in the sandbox), the relevant schema context, and nothing else from other sessions/users.

### 3.2 Query execution model: full read/write power

Basewise's LLM-generated code has full execution power against the linked database — `SELECT`, `INSERT`, `UPDATE`, `DELETE`, and DDL (`ALTER`/`DROP`/`CREATE`/etc.) are all permitted with no operation-type gating, no confirmation step, and no read-only restriction. There is no classification tier and no forced pause before a write or destructive statement runs — if the task calls for it, the LLM writes the SQL and the sandbox executes it.

**What this means concretely:**

- The DB role/credentials the user supplies define the actual ceiling on what's possible — Basewise does not itself restrict which SQL statements can be attempted.
- Section 4.2's self-recheck pass still runs (catching misjoins, wrong filters, misread intent) but it is a **correctness** check, not a **permission** check — a self-recheck that says "yes this SQL does what was asked" does not imply any additional write-safety review, because none is enforced.
- `query_runs` (Section 6.1) still logs every statement executed, including writes/DDL, so there is a full audit trail after the fact even though there's no gate before the fact.
- **Documented tradeoff:** this means a misread question, a hallucinated intent, or successful prompt-injected content in row data (Section 3.3) can result in real data being altered or destroyed with no human checkpoint in between. That's an accepted, explicit design choice for this project, not an oversight — noted here so it's visible to anyone picking up this doc later, not because it changes the decision.

### 3.3 Untrusted data re-entering the LLM (prompt injection via row data)

Section 3's isolation concerns cover sandbox code-execution risk. A separate, easy-to-miss risk: the _content_ of the user's own database (e.g., a `notes` or `comments` column containing text like "ignore prior instructions and...") can flow back into a later LLM call — the self-recheck pass (Section 4.2) or Analysis Mode's summarization step (Section 5) — and attempt to manipulate that call.

Mitigations to build in from the start, not retrofit later:

- Treat all query **results** as untrusted data, never as instructions, in every prompt template. Wrap returned row data in clearly delimited blocks and instruct the model explicitly that content inside those blocks is data to summarize/analyze, not commands to follow.
- Cap how much raw row content is echoed back into any prompt (row/character limits) — summarization and analysis should work off aggregated/truncated data, not unbounded raw text blobs.
- The self-recheck step (Section 4.2) only needs the SQL, the schema, and the original question — it does not need actual row-level result data, so keep it out of that prompt entirely.
- Given Section 3.2's execution model has no write/DDL gate, injected row content that successfully manipulates a later LLM call into generating an unintended write or destructive statement has a direct, unmitigated path to executing against real data — there is no confirmation step downstream to catch it. This raises the importance of the prompt-hygiene mitigations above; it does not change the Section 3.2 decision.

---

## 4. Natural Language → SQL Engine

### 4.0 Orchestration: hand-rolled, not LangChain

Decision, with rationale (since a recommendation was requested rather than a lock-in): **hand-roll the agent/tool-calling loop** rather than using LangChain.

- The core loop here is a small, well-defined set of custom tools (schema lookup, sandbox code execution, confidence self-check) — this doesn't need a general-purpose framework's abstraction layer.
- Free-tier OpenRouter models come with tight rate limits and occasional availability changes; a thin hand-rolled loop makes it much easier to add retry/fallback/model-swap logic exactly where needed, without fighting a framework's assumptions.
- Full transparency into the confidence-scoring and self-recheck step (Section 4.2) is easier to reason about and debug without an intermediate abstraction.
- LangChain adds dependency weight and version churn that isn't earning its keep at this scope.

If the project later needs multi-step planning across many more tools, this decision can be revisited — but start hand-rolled.

### 4.1 LLM Provider

- **Provider:** OpenRouter, free tier.
- **Recommended default model:** `openai/gpt-oss-120b:free` (or `:20b` variant as a lighter fallback) — currently among the strongest free OpenRouter models for tool-calling and code-adjacent reasoning, which this project depends on heavily (SQL generation _and_ sandbox code generation both need it).
- **Important caveat to document in code comments, not just here:** OpenRouter's free-tier model lineup changes within days, sometimes without notice, and free-tier rate limits are tight (order of 20 req/min, low daily caps). The LLM client must be built behind a provider-agnostic interface (`LLMClient.complete(...)`) with:
  - A configured **fallback list** of 2-3 free models to retry against on rate-limit/availability errors.
  - Model name driven by config/env var, not hardcoded, so swapping is a one-line change.
- Bring-your-own-API-key (paid tier) is **explicitly out of scope for this document** — not designed for, not mentioned further.

### 4.2 SQL Generation, Self-Recheck, and Confidence Scoring

Flow for every natural-language query:

1. LLM receives the question + relevant schema context (tables/columns/FKs/stats relevant to the question, not the entire schema dump — see 4.3 for how "relevant" is determined).
2. LLM generates candidate SQL **and**, in the same pass, a first-pass confidence signal + reasoning for why it believes the query answers the question.
3. **Self-recheck step:** the LLM is prompted a second time — schema + question + candidate SQL only, no row data (3.3) — to critique its own SQL against the original question and schema, checking for misread columns, wrong joins, ambiguous intent, missing filters, before it's shown to the user. This is a genuine second LLM pass, not just a restated first answer.
4. The (rechecked) SQL executes directly in the sandbox — no operation-type gate (Section 3.2). Execution success/failure and result shape sanity (non-error, reasonable row/rows-affected count) feed into the final confidence score alongside the LLM's own self-assessed confidence.
5. Final response to user: SQL, plain-English explanation, confidence score, and results.

Confidence score = combination of (a) LLM's self-reported confidence after the recheck pass, and (b) execution-based signal (did it run cleanly, does the result shape look sane). Exact weighting is an implementation detail to tune, not fixed here (Section 15).

### 4.3 Schema-context relevance selection

For small schemas (roughly under ~30 tables), the simplest approach — include the full table/column/FK list in the prompt — is fine and should be the starting implementation; don't over-engineer this early.

For larger schemas, a naive full-dump approach burns context and free-tier tokens fast. The intended escalation path, to build when the mock/demo DB (Section 13) or a real linked DB exceeds the small-schema threshold:

1. **Keyword/name matching first** — match terms in the NL question against table and column names (cheap, no extra LLM/embedding call).
2. **Embedding-based retrieval as a fallback** — if keyword matching returns too little (e.g., a vague or terse question), embed table/column descriptions once at schema-scan time, embed the question at query time, and retrieve top-N relevant tables by similarity.
3. Always include tables reachable via foreign key from anything already selected (one hop), so joins the user didn't explicitly name aren't missed.

This is a Milestone 3/7 concern, not a Milestone 1 blocker — start with full-dump, add retrieval when a schema large enough to need it exists.

### 4.4 Conversation memory (multi-turn context)

Within a single chat thread for a linked DB, the user should be able to ask follow-ups like "now filter that by region" without repeating full context. To support this:

- The backend stores the running conversation (Section 6.1) and, on each new turn, feeds a bounded window of recent turns (e.g., last 5-10 exchanges, or fewer if token budget is tight) back into the prompt alongside the schema context.
- What's carried forward is the **NL question/answer/SQL history**, not raw result-set row data (consistent with 3.3 — keep untrusted row content out of prompts wherever avoidable).
- Each linked DB has its own independent conversation thread; Analysis Mode (Section 5) is a **separate** thread from the regular query chat, per Section 6 — they do not share history with each other.
- This is a Milestone 3/4 concern (needs both the SQL engine and basic chat storage in place) — not required for the very first end-to-end query to work, but should be designed for from the data-model stage (Section 6.1) so it isn't a retrofit.

---

## 5. Analysis Mode

Distinct from ordinary querying. Entered explicitly per connected database, not automatically.

**Flow:**

1. From the dashboard, each linked DB has an "Enter Analysis Mode" action, opening a **new tab/view** dedicated to that DB.
2. On entry, Basewise scans the schema and proactively suggests starting points for analysis (e.g., "I can look at revenue trends, customer growth, or inventory risk — want me to start with one of these, or ask your own?"). This is scoped to **business insights and visualization only** — schema browsing/management stays in the regular query interface, not here.
3. When the user says "do this" (in their own words, not a fixed menu), the LLM confirms it's a sound way to proceed, then autonomously carries it out — running sandboxed analysis code, producing plots, and summarizing findings — without the user needing to specify implementation details.
4. Output is aimed at non-technical users throughout: plain-English framing, plots over raw tables, actionable recommendations rather than just numbers.

---

## 6. Frontend (Stage-1 scope: functional testing surface only)

Explicitly **not** the final UX — built to exercise the backend end-to-end, refine later.

- **Landing/dashboard:** list of the user's linked databases + a way to link a new one.
- **Linking a DB:** user selects DB type → pastes connection URL/API key/credentials → backend encrypts and stores them.
- **Clicking a linked DB:** opens a ChatGPT/Claude-style chat interface for natural-language querying against that DB (Section 4 flow).
- **Analysis Mode:** a switch/tab within that DB's view (conceptually like switching models in a chat UI) that moves into the Section 5 flow — separate conversation thread focused on insights/plots, not query building.
- **Plots:** backend returns **structured chart data**, not rendered images. Frontend renders using Plotly or Recharts. This keeps the sandbox's job to "produce data," not "produce pixels," and gives the frontend full control over interactivity/styling later.
- **Stack:** React/Next.js frontend on Vercel.
- No separate BI-style dashboard builder in this phase — that's future work per the original roadmap (Section 12).

### 6.1 Basewise's own data model

These are Basewise's application tables (in its own Supabase/Postgres instance), distinct from the user's _linked_ databases. This is the baseline schema Milestone 1 builds against:

| Table              | Key columns                                                                                                                                                                                           | Notes                                                                                                                        |
| ------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------- |
| `users`            | `id`, `email`, `password_hash` (or auth-provider id), `created_at`                                                                                                                                    | Standard auth entity.                                                                                                        |
| `linked_databases` | `id`, `user_id` (FK), `db_type`, `display_name`, `encrypted_credentials`, `created_at`, `last_schema_scan_at`                                                                                         | `encrypted_credentials` uses the Fernet scheme from Section 7, never the raw string.                                         |
| `schema_cache`     | `id`, `linked_database_id` (FK), `schema_json`, `scanned_at`, `expires_at`                                                                                                                            | Serialized table/column/FK/stat metadata from Section 3's hardcoded extractor; see Section 8 for invalidation.               |
| `conversations`    | `id`, `linked_database_id` (FK), `mode` (`query` \| `analysis`), `created_at`                                                                                                                         | One row per chat thread; `mode` enforces the query/Analysis Mode thread separation from Section 5.                           |
| `messages`         | `id`, `conversation_id` (FK), `role` (`user` \| `assistant`), `content`, `sql_generated` (nullable), `confidence_score` (nullable), `chart_data` (nullable JSON), `created_at`                        | Chart data stored as structured JSON per Section 6, not images.                                                              |
| `query_runs`       | `id`, `message_id` (FK), `sql_text`, `operation_type` (`read` \| `write` \| `ddl`), `row_count`, `rows_affected`, `execution_ms`, `sandbox_session_id`, `status` (`success` \| `error`), `created_at` | Full audit trail of every statement executed, including writes/DDL — also what Section 4.4's conversation memory reads from. |

This table list is a starting point for Milestone 1, not a frozen final schema — expect minor iteration once real implementation starts, but the shape (users → linked_databases → schema_cache / conversations → messages → query_runs) should hold.

---

## 7. Backend, Auth, and Security

- **Backend:** Python (FastAPI recommended for async support, which matters given LLM calls + sandbox calls are both I/O-bound and potentially slow).
- **Auth flow:** user logs in → selects DB type → pastes connection URL/API key/credentials.
- **Session auth:** JWT, used for authenticating the logged-in user's session — standard usage, not used to protect stored secrets. Access tokens should be short-lived (e.g., 15-60 min) with a refresh token flow; exact expiry values are a Milestone 1 implementation detail, not fixed here.
- **Credential-at-rest protection:** DB connection strings/keys are encrypted with a server-held symmetric key (AES via Fernet is a reasonable default) before storage — **not** the same mechanism as the session JWT. This distinction should be preserved in implementation; conflating "auth token" and "encrypted secret" is a common and serious mistake.
- Decrypted credentials should only ever exist transiently, in-memory, scoped to the sandbox invocation that needs them (Section 3) — never logged, never passed to the LLM as plain text in prompts.
- **Unlinking a database:** deleting a `linked_databases` row should cascade-delete (or at minimum immediately invalidate) its `schema_cache` entry and encrypted credentials — soft-delete is acceptable for `conversations`/`messages` (preserve history for the user if they relink later) but the encrypted credential itself must be a hard delete, not retained "just in case."
- **Mock/demo database:** a complex live database will be created separately for demo/testing purposes (domain/schema TBD — flagged as an open item in Section 13, not blocking architecture work).

---

## 8. Caching

Cache what's necessary, not everything by default — free-tier LLM usage is the main cost/rate-limit pressure point, so prioritize caching that reduces LLM calls:

- **Schema introspection results** per linked DB — re-scanning schema on every query is wasteful; invalidate on a reasonable TTL (starting default: 24h) or on explicit user "refresh schema" action. Change-detection (e.g., hashing the extracted schema and comparing on next scan) is a nice-to-have to layer on later, not a Milestone 1 requirement.
- **LLM-generated SQL for repeated/near-duplicate NL questions** against the same DB — worth caching given free-tier rate limits. Keyed on (linked_database_id, normalized question text, current schema_cache version) so a schema change correctly invalidates stale cached SQL.
- Result-set caching is lower priority (data changes underneath) — leave out unless it becomes an obvious bottleneck.

---

## 10. Failure and Degraded-Mode Behavior

The happy path (Sections 4-5) is fully specified; the unhappy paths need at least baseline behavior defined so they aren't improvised late:

- **OpenRouter free-tier exhausted/rate-limited across the entire fallback list (4.1):** return a clear, user-visible error distinct from a generic 500 (e.g., "AI query service is temporarily at capacity — try again in a moment"), not a silent hang or a fabricated answer.
- **Sandbox spin-up/execution failure (E2B error, timeout, etc.):** surfaced as a distinct error state in the message (Section 6.1's `query_runs.status = 'error'`), with the SQL still shown to the user if it was generated successfully — don't hide a working query behind an unrelated infra failure.
- **SQL execution failure of any kind (syntax error, constraint violation, missing table, etc.):** surfaced as a distinct error state in the message (Section 6.1's `query_runs.status = 'error'`), with the SQL still shown to the user if it was generated successfully — don't hide a working query behind an unrelated infra failure. Since writes/DDL can fail partway through, the sandbox should still report exactly what was attempted so the user isn't left guessing what state their data is in.
- **Low self-recheck confidence (4.2):** below some threshold (exact number tunable, Section 15), the response should still be shown but visibly flagged as low-confidence, with the option for the user to ask a follow-up rather than the system silently refusing to answer.

---

## 11. SDK & MCP Server

- **SDK:** Python only for this phase.
- **MCP server:** explicitly **not built now**, but the backend's internal architecture (LLM client interface, sandbox executor interface, schema-extraction module) should be designed as clean, swappable components from the start specifically so an MCP server can be added later as another consumer of the same internals, rather than requiring a rewrite.

---

## 12. Deployment

- **Backend:** Render.
- **Frontend:** Vercel.
- **Sandbox execution:**e2b sandbox- external/decoupled service (Section 3) — not hosted inside the Render web service.
- Deployment choices should never be allowed to compromise feature scope (explicit user constraint) — if Render's constraints conflict with the sandbox isolation requirement, solve it via a separate sandbox service (as already decided), not by weakening isolation.

---

## 13. Milestone Breakdown (build order, not a fixed calendar)

Each milestone lists a rough "done means" bar so a solo build has a concrete checkpoint instead of an open-ended task.

1. **Core DB connectivity + schema extraction** — hardcoded SQLAlchemy-based connector for Supabase Postgres first; auth, credential encryption, JWT sessions; Section 6.1 data model stood up.
   _Done when:_ a user can sign up, link a real Supabase Postgres DB, and see its extracted schema (tables/columns/FKs) persisted in `schema_cache`.
2. **Sandbox execution layer** — stand up the external sandbox service and the `SandboxExecutor` interface; prove out LLM-generated code running safely against a real DB, including read, write, and DDL statements (3.2).
   _Done when:_ arbitrary Python code, generated by hand (not yet by the LLM), executes in E2B against the linked DB's real credentials — confirmed working for a `SELECT`, an `INSERT`/`UPDATE`, and a DDL statement (e.g., `ALTER`), with results/effects logged to `query_runs`.
3. **NL → SQL engine** — hand-rolled agent loop, OpenRouter integration with fallback models, self-recheck pass, confidence scoring, schema-context selection (4.3).
   _Done when:_ a plain-English question against the linked DB returns SQL + explanation + confidence score + results end-to-end, including at least one forced fallback-model retry test.
4. **Basic chat frontend** — dashboard, DB linking, chat interface wired to the above, conversation memory (4.4), streaming responses (Section 9).
   _Done when:_ the full Section 6 frontend flow works against a deployed (not just local) backend.
5. **Analysis Mode** — schema-scan-driven suggestions, confirm-then-execute loop, structured chart data output.
   _Done when:_ entering Analysis Mode on the linked DB produces at least one real suggested-and-executed analysis with a rendered chart.
6. **Plot rendering** — Plotly/Recharts integration on the frontend.
   _Done when:_ structured chart data from Analysis Mode renders as an interactive chart, not a static image.
7. **Extend beyond Supabase Postgres** — MySQL, SQLite, other Postgres-compatible sources, validating the hardcoded-connect / sandboxed-everything-else split actually generalizes.
   _Done when:_ one additional DB type is linkable and queryable through the identical flow with no DB-type-specific branching outside the connector module.
8. **Python SDK** — expose the above as an installable package.
   _Done when:_ `pip install`-able package can perform a query against a linked DB from a script, using the same internal interfaces as the web backend.
9. **(Future) MCP server** — built on the same internals once the above is stable.

---

## 14. Explicitly Out of Scope (this document)

- Paid tier / "packages" / bring-your-own-API-key flow — noted as existing in concept but deliberately left undocumented here per current decision; revisit in a future doc.
- Dashboard-builder / report-export UI beyond Analysis Mode's plots.
- MCP server implementation (interfaces should support it later; the server itself is not built now).
- Multi-database-type support beyond Supabase Postgres for the first working version.

---

## 15. Open Questions / TBD

- **Mock database domain/complexity** — a complex live DB will be created for demo purposes; its schema/domain isn't decided yet and should be filled in once created, since it will inform what "common useful insights" Analysis Mode should default to suggesting, and what schema size Section 4.3's retrieval escalation needs to handle.
- **Exact confidence-score weighting formula** (LLM self-report vs execution-based signal) and the low-confidence threshold referenced in Section 10 — left as tunable implementation details. Note confidence is purely informational here — it does not gate execution, since Section 3.2 imposes no permission or confirmation layer.
- **Cache invalidation trigger for schema cache** — TTL vs explicit refresh vs change-detection; pick during Milestone 1 implementation (default TTL of 24h proposed in Section 8 as a starting point).
- **JWT access/refresh token lifetimes** — proposed defaults given in Section 7, to be finalized during Milestone 1.
- **Streaming transport (SSE vs WebSocket)** for `POST /conversations/{id}/messages` — proposed SSE as the simpler default in Section 9, to be finalized during Milestone 4.
