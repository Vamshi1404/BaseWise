# BaseWise Complete Project Context

This document is a complete context pack for the BaseWise project. It includes architecture, implementation details, operational details, design decisions, file map, APIs, setup flow, testing flow, and practical guidance for another model or engineer to continue development without needing to re-discover the project from scratch.

---

## 1. Project Summary

BaseWise is an AI-powered database intelligence platform that lets users query relational databases in plain English and receive:

- natural-language SQL
- plain-English explanation of the query
- confidence scoring
- execution results
- optional chart/visualization output
- analysis mode with business insight generation

The system is designed as a full-stack app with:

- Python FastAPI backend
- React + TypeScript frontend
- PostgreSQL/Supabase as the application database
- user-linked external databases for querying
- secure encryption for stored database connection strings
- E2B sandbox execution for LLM-generated Python/data tasks
- LLM calls through Groq/OpenAI-compatible API and Gemini fallback
- self-recheck logic to validate generated SQL before execution

The project is intentionally built around a “hardcoded connection + sandboxed everything else” architecture.

---

## 2. High-Level Product Vision

BaseWise aims to let non-technical users:

- ask questions in normal English
- get SQL generated automatically
- understand why the SQL was chosen
- inspect confidence score and reasoning
- execute against real databases
- do analysis mode to find trend/business insights
- visualize outputs as interactive charts

Longer-term ambition described in the project docs includes:

- support for MySQL, SQLite, and other relational databases
- a Python SDK
- future MCP server integration

---

## 3. System Architecture

### 3.1 Core Architecture View

```text
[ React + TypeScript Frontend ]
            |
            | HTTPS / SSE / JWT auth
            v
[ FastAPI Backend ]
   |-- Auth & user management
   |-- Database linking + credential encryption
   |-- Schema extraction + cache
   |-- NL to SQL agent loop
   |-- Analysis mode engine
   |-- Query execution audit logging
   |
   +--> [ Supabase/Postgres ]  (BaseWise application DB)
   |
   +--> [ LLM Providers ]
   |       - Groq / OpenAI-compatible (primary)
   |       - Gemini fallback
   |
   +--> [ E2B Sandbox ]
           - Runs LLM-generated Python code
           - Executes SQL/analysis against user-linked DBs
           - Returns structured data, not rendered images
```

### 3.2 Architectural Design Principle

The project explicitly follows this rule:

- connecting to a database and extracting schema metadata is hardcoded and deterministic
- everything else is LLM-driven and run in a sandbox

This pattern appears across the code and design docs:

- schema extraction uses SQLAlchemy inspect() and dialect-aware logic
- queries, analysis, and chart generation are run through sandboxed Python code
- the backend never executes arbitrary LLM-generated code directly on the web server

This is a major design decision and should be respected in future changes.

---

## 4. Tech Stack

### Frontend

- React 19
- TypeScript
- Vite
- Recharts
- Axios
- Tailwind CSS (v4)
- lucide-react

### Backend

- Python
- FastAPI
- SQLAlchemy 2 (async)
- Pydantic v2
- pydantic-settings
- Async Postgres driver (`asyncpg`)
- sync Postgres driver (`psycopg2-binary`) for schema work

### LLM / AI

- Groq OpenAI-compatible endpoint using `openai/gpt-oss-120b` as primary model
- Gemini via `google-genai` as fallback
- provider routing by model slug
- structured output parsing for JSON responses

### Sandbox / Execution

- E2B Code Interpreter (`e2b-code-interpreter`)
- secure in-memory credential passing
- code runs inside E2B sandbox, not on backend server

### Storage / Auth

- Supabase Postgres for BaseWise system DB
- JWT access + refresh tokens
- bcrypt hashing for password storage
- Fernet symmetric encryption for linked database credentials

---

## 5. Repository Structure

```text
BaseWise/
├── README.md
├── project.md
├── actions.md
├── markdown.md
├── backend/
│   ├── .env
│   ├── requirements.txt
│   ├── schema.sql
│   ├── test_db.py
│   ├── app/
│   │   ├── __init__.py
│   │   ├── config.py
│   │   ├── database.py
│   │   ├── main.py
│   │   ├── api/
│   │   │   ├── __init__.py
│   │   │   ├── auth.py
│   │   │   ├── databases.py
│   │   │   ├── conversations.py
│   │   │   └── analysis.py
│   │   ├── core/
│   │   │   ├── __init__.py
│   │   │   ├── agent_loop.py
│   │   │   ├── analysis_engine.py
│   │   │   ├── db_context.py
│   │   │   ├── llm_client.py
│   │   │   ├── model_registry.py
│   │   │   ├── query_router.py
│   │   │   ├── sandbox.py
│   │   │   ├── schema_extractor.py
│   │   │   ├── security.py
│   │   │   ├── sql_validator.py
│   │   │   └── structured_output.py
│   │   ├── models/
│   │   │   ├── __init__.py
│   │   │   └── models.py
│   │   ├── schemas/
│   │   │   ├── __init__.py
│   │   │   ├── auth.py
│   │   │   ├── conversation.py
│   │   │   └── database.py
│   ├── scripts/
│   │   ├── test_chart_e2e.py
│   │   ├── test_models.py
│   │   ├── verify_auth_errors.py
│   │   ├── VERIFICATION_TASK_1.1.2.md
│   │   └── VERIFICATION_TASK_1.1.4.md
│   └── tests/
│       ├── test_agent_loop.py
│       ├── test_auth_logging.py
│       ├── test_chart_detection.py
│       ├── test_jwt_security.py
│       ├── test_llm_client.py
│       ├── test_model_registry.py
│       ├── test_query_router.py
│       ├── test_schema_selection.py
│       ├── test_sql_validator.py
│       ├── test_structured_output.py
│       └── ...
└── frontend/
    ├── package.json
    ├── vite.config.ts
    ├── tsconfig.*
    ├── index.html
    └── src/
        ├── App.tsx
        ├── App.css
        ├── index.css
        ├── main.tsx
        ├── api/
        │   └── client.ts
        ├── assets/
        ├── components/
        │   ├── AddDatabaseModal.tsx
        │   ├── ChartRenderer.tsx
        │   ├── ChatWindow.tsx
        │   ├── ConfidenceBadge.tsx
        │   ├── DatabaseCard.tsx
        │   ├── MessageItem.tsx
        │   ├── Navbar.tsx
        │   ├── QueryResultTable.tsx
        │   ├── SchemaViewer.tsx
        │   └── charts/
        │       ├── chartTheme.ts
        │       ├── ChartTooltip.tsx
        │       ├── FunnelChart.tsx
        │       ├── ScatterChart.tsx
        │       └── TreemapChart.tsx
        ├── hooks/
        │   └── useTypewriter.ts
        ├── pages/
        │   ├── ChartPreviewPage.tsx
        │   ├── DashboardPage.tsx
        │   ├── DatabaseWorkspace.tsx
        │   ├── LoginPage.tsx
        │   └── RegisterPage.tsx
        └── types/
            └── index.ts
```

---

## 6. Backend Application Structure and Responsibilities

### 6.1 `backend/app/main.py`

- creates the FastAPI app
- enables CORS from configured origins
- includes routers for auth, databases, conversations, and analysis
- exposes `/health` endpoint

### 6.2 `backend/app/config.py`

Configuration is loaded from `backend/.env` and includes:

- `DATABASE_URL`
- `FERNET_KEY`
- `JWT_SECRET`
- `JWT_ALGORITHM`
- `ACCESS_TOKEN_EXPIRE_MINUTES`
- `REFRESH_TOKEN_EXPIRE_DAYS`
- `GROQ_API_KEY`
- `GEMINI_API_KEY`
- `PRIMARY_LLM_MODEL`
- `FALLBACK_LLM_MODELS`
- `E2B_API_KEY`
- `ALLOWED_ORIGINS`
- `QUERY_ROUTER_ESCALATION`

It also contains the model routing logic:

- model slugs beginning with `gemini-` route to Google endpoint
- everything else uses Groq/OpenAI-compatible endpoint

### 6.3 `backend/app/database.py`

- sets up async SQLAlchemy engine
- provides `AsyncSessionLocal`
- defines `Base` declarative base
- `get_db()` yields an async database session

### 6.4 `backend/app/models/models.py`

Defines the application DB schema for BaseWise itself (not the user's linked DB). Tables include:

- `users`
- `linked_databases`
- `schema_cache`
- `conversations`
- `messages`
- `query_runs`

Important design notes:

- `linked_databases.encrypted_credentials` stores the encrypted connection string
- `schema_cache` stores extracted schema metadata JSON
- `conversations` tracks separate threads for query and analysis modes
- `messages` stores assistant content, SQL, chart data, reasoning, trace
- `query_runs` stores every executed SQL statement and response status

---

## 7. Security Model

### 7.1 Passwords

- Uses `passlib` with bcrypt
- password hashes are stored, never plaintext

### 7.2 JWT Sessions

- access token used for regular auth
- refresh token used to renew access tokens
- token secrets are separate from encryption keys

### 7.3 Database Credential Storage

- database connection strings are encrypted with Fernet before being stored
- this is intentionally separate from JWT auth
- plaintext credentials are never persisted in the DB
- credentials are only decrypted in memory at runtime

### 7.4 Prompt Injection Hygiene

The project explicitly treats database result content as untrusted data.

- row data is never treated as instructions
- raw row content is limited before re-use in prompts
- self-recheck step intentionally avoids row data and only uses SQL + schema + question
- prompts are designed to delimit data blocks so the model knows it is data, not commands

### 7.5 Sandbox Isolation

- arbitrary Python generation runs in E2B sandbox
- DB URL is injected as environment variable inside the sandbox
- user credentials are never stored in the sandbox permanently
- no direct execution on backend host

### 7.6 Ownership Validation

Every access to a linked database or conversation must validate that the current JWT user owns the resource.

---

## 8. API Design

The backend exposes routes under `/api/v1`.

### 8.1 Auth APIs

Defined in `backend/app/api/auth.py`

- `POST /api/v1/auth/signup`
- `POST /api/v1/auth/login`
- `POST /api/v1/auth/refresh`
- `GET /api/v1/auth/me`

### 8.2 Database APIs

Defined in `backend/app/api/databases.py`

- `GET /api/v1/databases`
- `POST /api/v1/databases`
- `GET /api/v1/databases/{db_id}`
- `DELETE /api/v1/databases/{db_id}`
- `POST /api/v1/databases/{db_id}/test`
- `GET /api/v1/databases/{db_id}/schema`
- `POST /api/v1/databases/{db_id}/schema/refresh`

These APIs:

- validate the database connection before persisting
- encrypt connection info immediately
- store a schema cache after initial extraction
- allow cache refresh when needed

### 8.3 Conversation APIs

Defined in `backend/app/api/conversations.py`

- `GET /api/v1/databases/{db_id}/conversations`
- `POST /api/v1/databases/{db_id}/conversations`
- `GET /api/v1/conversations/{conv_id}/messages`
- `POST /api/v1/conversations/{conv_id}/messages`

This route executes the complete NL → SQL pipeline and returns SSE stream events:

- `status`
- `token`
- `result`
- `error`

### 8.4 Analysis APIs

Defined in `backend/app/api/analysis.py`

- `POST /api/v1/databases/{db_id}/analysis/suggest`
- `POST /api/v1/conversations/{conv_id}/analysis/execute`

These are separate from normal query threads and use a separate conversation mode.

---

## 9. Natural-Language Query Pipeline

The main query engine exists in `backend/app/core/agent_loop.py` and is built around a custom hand-rolled loop rather than LangChain.

### 9.1 Routing / Intent Classification

Handled in `backend/app/core/query_router.py`.

It determines whether input is:

- `conversational`
- `simple_query`
- `full_pipeline`

Checks include:

- greeting / thanks / capability prompts
- presence of schema keywords in user question
- complexity indicators like aggregates, comparisons, trends, time windows
- history follow-up clues like “that”, “this”, “previous”, etc.
- destructive SQL intent like insert/update/delete/create/drop

This helps avoid sending every trivial message through the expensive full NL→SQL path.

### 9.2 Schema Relevance Selection

`agent_loop.py` includes a deterministic schema matching system:

- removes noise words from the question
- matches table/column names using normalized and synonym-expanded keywords
- includes one-hop foreign key neighbor tables
- prunes wide tables to keep column payload manageable
- keeps prompt size bounded to reduce token cost

This is important because free-tier LLMs are rate-constrained and context-limited.

### 9.3 Pass 1: SQL Generation

The prompt includes:

- the user question
- relevant schema slice
- bounded conversation history
- instructions to generate SQL and reasoning

The model outputs candidate SQL plus a first-pass confidence score.

### 9.4 Pass 2: Self-Recheck

`agent_loop.py` then invokes a second LLM pass for validation.

This second pass:

- checks the SQL against the original question
- checks schema compatibility
- catches misjoins, wrong columns, missing filters, bad intent
- does not use raw row data

The project explicitly avoids sending rows into the self-recheck step.

### 9.5 SQL Validation Gate

`backend/app/core/sql_validator.py` provides a heuristic gate that parses SQL and validates referenced tables/columns against the schema.

It is a veto-only gate:

- if parsing or reference validation fails, it forces a full self-recheck path
- it is not a positive trust signal, only a guardrail to skip unnecessary LLM work

### 9.6 Execution

The generated SQL is run in the E2B sandbox via `backend/app/core/sandbox.py`.

The sandbox:

- receives the DB URL as an environment variable
- executes Python/SQL logic against the actual database
- captures stdout/stderr, results, timing, and error status
- returns structured output to the backend

### 9.7 Final Response Construction

The final result includes:

- SQL
- explanation or summary
- confidence score
- confidence label
- reasoning
- chart data if appropriate
- row counts / execution metrics
- route classification / route reason
- operation type

---

## 10. Analysis Mode

Analysis mode is a separate conversation flow intended for business insights and visualizations.

### 10.1 Purpose

- not meant for normal schema browsing
- meant for high-level business analysis
- intended to suggest prompts like revenue trends, customer growth, inventory risk, etc.

### 10.2 Engine

Handled in `backend/app/core/analysis_engine.py`.

It:

- scans schema metadata
- asks the LLM for analysis suggestions
- generates analysis prompt code or python instructions
- runs code inside the sandbox to compute aggregations and produce JSON chart specs
- returns structured object with type, title, x_key, y_keys, summary, data

### 10.3 Chart Data Format

The project deliberately avoids image rendering in the sandbox.

Instead it returns structured JSON such as:

```json
{
  "type": "bar",
  "title": "Revenue by Region",
  "data": [
    { "region": "North", "revenue": 4200 },
    { "region": "South", "revenue": 3900 }
  ],
  "x_key": "region",
  "y_keys": ["revenue"],
  "summary": "North has the highest revenue"
}
```

The frontend renders the chart using Recharts.

### 10.4 Safety / Normalization

The analysis engine includes logic to normalize messy location labels by:

- collapsing address strings to the first locality segment
- merging case variants
- summing values for the same place
- limiting categories for readability

This prevents a chart from exploding into near-duplicate address labels.

---

## 11. LLM Client and Provider Routing

The provider-agnostic LLM client exists in `backend/app/core/llm_client.py`.

### 11.1 Routing Rules

- Gemini model slugs route to Google SDK path
- other model slugs route to Groq/OpenAI-compatible API path

### 11.2 Fallback Strategy

The design allows a list of fallback models and uses model registry logic to reorder failed models.

Key files:

- `backend/app/core/model_registry.py`
- `backend/app/config.py`

Model reliability is tracked with:

- calls count
- successes
- failures
- consecutive failures
- cooldown logic for degraded models

### 11.3 Retry / Rate-Limit Handling

The LLM client includes logic for:

- HTTP 429 handling
- Retry-After respect
- rate-limit delays
- fallback model retry on failure

This is essential because free-tier AI providers can throttle quickly.

---

## 12. Schema Extraction System

The project’s schema extraction module is the deterministic connection layer.

File: `backend/app/core/schema_extractor.py`

### 12.1 Purpose

This module connects to a user-linked database and extracts:

- table names
- columns
- types
- nullable metadata
- primary keys
- foreign keys
- approximate row counts
- sample rows
- per-column stats for small tables

### 12.2 Design Notes

- uses SQLAlchemy `inspect()`
- supports dialect-agnostic extraction
- normalizes async-only URLs to sync equivalents where required
- stores extracted schema in JSON under `schema_cache`

### 12.3 Constraints

- expensive table scans are avoided for large tables
- only small tables get deeper stats/sample extraction
- schema cache is refreshed periodically

---

## 13. Database Schema for BaseWise App

The app owns its own database in Supabase/Postgres. The actual schema is defined by `backend/schema.sql` and also reflected in ORM models.

Main tables:

### `users`

- `id`
- `email`
- `password_hash`
- `created_at`

### `linked_databases`

- `id`
- `user_id`
- `db_type`
- `display_name`
- `encrypted_credentials`
- `created_at`
- `last_schema_scan_at`

### `schema_cache`

- `id`
- `linked_database_id`
- `schema_json`
- `scanned_at`
- `expires_at`

### `conversations`

- `id`
- `linked_database_id`
- `mode` (`query` or `analysis`)
- `created_at`

### `messages`

- `id`
- `conversation_id`
- `role`
- `content`
- `sql_generated`
- `confidence_score`
- `reasoning`
- `chart_data`
- `confidence_trace`
- `created_at`

### `query_runs`

- `id`
- `message_id`
- `sql_text`
- `operation_type` (`read`, `write`, `ddl`)
- `row_count`
- `rows_affected`
- `execution_ms`
- `sandbox_session_id`
- `status`
- `created_at`

---

## 14. Frontend Structure and Behavior

### Main app shell

File: `frontend/src/App.tsx`

- checks for saved JWT tokens
- renders auth pages when logged out
- renders dashboard or active database workspace when logged in
- manages active database selection
- manages query vs analysis mode
- handles logout and add-database flow

### Dashboard

`frontend/src/pages/DashboardPage.tsx`

- shows user-linked databases
- lets user select a database
- open database workspace
- open add database modal

### Database Workspace

`frontend/src/pages/DatabaseWorkspace.tsx`

- query mode and analysis mode switching
- loads conversation threads
- shows chat UI and database schema
- renders query results and charts

### Chat and message components

- `ChatWindow.tsx`
- `MessageItem.tsx`
- `QueryResultTable.tsx`
- `SchemaViewer.tsx`
- `ConfidenceBadge.tsx`

### Chart rendering

- `ChartRenderer.tsx`
- `charts/FunnelChart.tsx`
- `charts/ScatterChart.tsx`
- `charts/TreemapChart.tsx`
- `charts/chartTheme.ts`
- `charts/ChartTooltip.tsx`

These render structured chart JSON from the backend into interactive visualizations.

---

## 15. SSE Streaming Behavior

The backend streams progress updates to the frontend over Server-Sent Events.

This is implemented in the conversation and analysis endpoints.

Event types include:

- status messages during progress
- token streams for incremental content
- final result payload
- errors

This lets the UI show real-time progress while the model is thinking and executing.

---

## 16. Environment Variables and Setup

### Backend `.env` requirements

Key values used by the app:

- `DATABASE_URL`
- `FERNET_KEY`
- `JWT_SECRET`
- `JWT_ALGORITHM`
- `ACCESS_TOKEN_EXPIRE_MINUTES`
- `REFRESH_TOKEN_EXPIRE_DAYS`
- `GROQ_API_KEY`
- `GEMINI_API_KEY`
- `PRIMARY_LLM_MODEL`
- `FALLBACK_LLM_MODELS`
- `E2B_API_KEY`
- `ALLOWED_ORIGINS`
- `QUERY_ROUTER_ESCALATION`

### Frontend `.env`

Used by the Vite app to reach backend:

- `VITE_API_BASE_URL` typically points to `http://localhost:8001/api/v1`

---

## 17. Local Setup Flow

### Backend

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate   # or source .venv/bin/activate
pip install -r requirements.txt
copy .env.example .env
# fill values in .env
uvicorn app.main:app --reload --port 8001
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

### Database

- create a Supabase project
- copy the connection string
- run `backend/schema.sql` in Supabase SQL editor
- link a target database through the app

---

## 18. Testing Strategy

### Backend tests

The repo includes a pytest suite under `backend/tests/`.

Examples:

- `test_agent_loop.py`
- `test_auth_logging.py`
- `test_chart_detection.py`
- `test_jwt_security.py`
- `test_llm_client.py`
- `test_model_registry.py`
- `test_query_router.py`
- `test_schema_selection.py`
- `test_sql_validator.py`
- `test_structured_output.py`

### Frontend validation

The frontend uses Vite/TypeScript and `oxlint`.

```bash
cd frontend
npm run lint
npm run build
```

### Verification scripts

The project also contains issue-specific verification tasks and scripts such as:

- `scripts/test_models.py`
- `scripts/test_chart_e2e.py`
- `scripts/verify_auth_errors.py`

---

## 19. Core Implementation Notes and Gotchas

### 19.1 Model availability changes

Free-tier provider limits change often.

This project intentionally treats the model lineup as config-driven and not hardcoded, since provider quotas and actual model availability shift over time.

### 19.2 Prompt injection risk is a first-class concern

The project explicitly calls out row-level prompt injection concerns and builds mitigations into the design.

### 19.3 No write/DDL gate

BaseWise intentionally allows writes and DDL to execute if the SQL generated by the model requests it. The safety model is audit-first, not prevention-first.

### 19.4 Sandbox is the real execution boundary

LLM-generated Python cannot be trusted to run in the web backend process. The sandbox is not optional; it is part of the security design.

### 19.5 Query/analysis mode separation

There are separate conversation threads for query mode and analysis mode.

---

## 20. Design Decisions That Must Not Be Broken Without Review

These are the most important architectural principles from the codebase:

1. hardcoded schema extraction, sandboxed downstream logic
2. external sandbox execution only
3. encrypted stored database credentials
4. JWT session separate from credential encryption
5. prompt injection mitigation through bounded, sanitized data handling
6. conversation mode separation for query vs analysis
7. structured chart data, not image generation in sandbox
8. model configuration via env vars, not hardcoded provider assumptions

---

## 21. Intended Future Roadmap

The project docs outline these milestones:

1. core DB connectivity and schema extraction
2. sandbox execution layer
3. NL → SQL engine
4. basic chat frontend
5. analysis mode
6. plot rendering
7. MySQL / SQLite / other DBs
8. Python SDK
9. future MCP server

---

## 22. Practical Handoff Guidance for Another Model

If another model is asked to work on this repo, it should assume:

- the architecture in `project.md` and `README.md` is canonical
- the code in `backend/app` is the actual implementation target
- `backend/config.py` drives provider and env settings
- `schema_extractor.py` and `sandbox.py` are the true security boundary layers
- do not bypass the sandbox for analysis or query execution
- preserve model routing and credential encryption patterns
- respect the separate query/analysis conversation semantics
- keep prompts bounded and avoid feeding raw row content back into the LLM unless intentionally required and sanitized

---

## 23. One-Sentence Executive Summary

BaseWise is a full-stack AI database assistant that lets users ask plain-English questions against connected databases, validates the generated SQL with a second-pass self-check, runs it in an isolated sandbox, and returns explainable structured results and chart-ready data while enforcing user ownership, schema caching, JWT auth, and encrypted credential handling.

---

## 24. Useful File Reference List

When continuing work, these are the most important files to read first:

- `README.md`
- `project.md`
- `actions.md`
- `backend/app/main.py`
- `backend/app/config.py`
- `backend/app/database.py`
- `backend/app/models/models.py`
- `backend/app/core/agent_loop.py`
- `backend/app/core/query_router.py`
- `backend/app/core/analysis_engine.py`
- `backend/app/core/sandbox.py`
- `backend/app/core/schema_extractor.py`
- `backend/app/core/security.py`
- `backend/app/api/databases.py`
- `backend/app/api/conversations.py`
- `backend/app/api/analysis.py`
- `frontend/src/App.tsx`
- `frontend/src/pages/DatabaseWorkspace.tsx`
- `frontend/src/components/ChartRenderer.tsx`

---

## 25. Final Notes

This project is in active product/engineering shape and should be treated as a real application, not just a prototype. The codebase already contains thoughtful design rules around security, prompt injection, LLM routing, sandbox execution, schema caching, and dashboard-driven interaction.

A future model or engineer should preserve the core architecture instead of trying to “simplify” it into a direct SQL wrapper or a single LLM call without the existing safeguards.
