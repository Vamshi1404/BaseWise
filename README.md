# BaseWise — AI-Powered Database Intelligence Platform

Query, understand, and analyze relational databases in **plain English**. BaseWise translates natural language into validated, explainable SQL, catches its own mistakes before answering, scores its own confidence, and — in **Analysis Mode** — proactively surfaces business insights and visualizations without you needing to know what to ask.

## What It Does

- **Natural Language → SQL** — ask questions like *"show me revenue by region for the last quarter"* and get back SQL, a plain-English explanation, a confidence score, and the results.
- **Self-Rechecking** — every query goes through a second LLM pass that critiques the generated SQL against the schema and the original question before it executes (misjoins, wrong filters, misread intent are caught early).
- **Confidence Scoring** — each answer carries a `high` / `medium` / `low` confidence label derived from the LLM's own self-assessment *plus* real execution signals (did it run cleanly, does the result shape look sane).
- **Analysis Mode** — per database, BaseWise scans the schema, suggests starting points (revenue trends, customer growth, inventory risk...), then autonomously executes sandboxed analysis code and returns **structured chart data** rendered interactively in the UI.
- **Multi-Turn Conversations** — follow up naturally ("now filter that by region") without repeating context; each linked DB keeps its own query and analysis threads.
- **Audit Trail** — every executed statement (reads, writes, and DDL) is logged to `query_runs`, including rows affected and execution time.

## Architecture

```
┌─────────────┐      HTTPS/SSE       ┌──────────────┐
│  Frontend   │ ───────────────────▶ │   Backend    │
│ React + Vite│ ◀─────────────────── │ FastAPI      │
└─────────────┘  structured JSON     └──────┬───────┘
                                            │
          ┌────────────┬────────────────────┼─────────────────┬──────────────┐
          ▼            ▼                    ▼                 ▼              ▼
   ┌───────────┐ ┌───────────┐      ┌─────────────┐    ┌────────────┐ ┌───────────┐
   │ LLM (Groq │ │ LLM (Gemini│      │ E2B Sandbox │    │ Supabase   │ │ Linked    │
   │ gpt-oss-  │ │ fallback)  │      │ executes    │    │ Postgres   │ │ Databases │
   │ 120b)     │ │            │      │ LLM-written │    │ (BaseWise  │ │ (user-    │
   └───────────┘ └───────────┘      │ Python code │    │  own data) │ │ supplied) │
                                     └─────────────┘    └────────────┘ └───────────┘
```

### Core design decisions

1. **Hardcoded connection, sandboxed everything else.** Connecting to a database and extracting its schema (tables, columns, foreign keys) is deterministic code built once with SQLAlchemy. Everything downstream — running queries, generating plots, analyzing data — runs as **LLM-written Python code inside an E2B sandbox** (e2b.dev), which is what lets the platform generalize to new database types without a combinatorial explosion of per-database code.
2. **Hand-rolled agent loop, not LangChain.** The NL→SQL pipeline is a small set of custom steps with explicit retry/fallback logic, tuned for free-tier LLM rate limits. No framework abstraction layer to fight.
3. **Credential encryption at rest.** Database connection strings are encrypted with Fernet (symmetric, server-held key) before storage — a completely separate mechanism from the JWT session tokens. Decrypted credentials exist only transiently in memory, scoped to a single sandbox invocation, and are never logged or sent to the LLM.
4. **Structured chart data, not images.** The sandbox produces data; the frontend renders it with Recharts. Charts stay interactive and styled consistently.

## Tech Stack

| Layer     | Technology |
|-----------|------------|
| Frontend  | React 19, TypeScript, Vite, Tailwind CSS 4, Recharts, Axios, lucide-react |
| Backend   | Python, FastAPI, SQLAlchemy 2 (async), Pydantic v2, pydantic-settings |
| LLM       | OpenRouter/Groq `openai/gpt-oss-120b` (primary), Gemini `gemini-3.6-flash` (fallback) |
| Sandbox   | E2B Code Interpreter (`e2b-code-interpreter`) |
| Storage   | Supabase Postgres (BaseWise's own app data) |
| Auth      | JWT (short-lived access + refresh), bcrypt password hashing |
| Encryption| Fernet (credentials at rest) |
| Streaming | Server-Sent Events (SSE) |

## Repository Structure

```
BaseWise/
├── backend/
│   ├── app/
│   │   ├── api/            # FastAPI routers: auth, databases, conversations, analysis
│   │   ├── core/           # agent_loop, analysis_engine, schema_extractor, sql_validator,
│   │   │                   # query_router, llm_client, model_registry, sandbox, security, ...
│   │   ├── models/         # SQLAlchemy ORM models
│   │   ├── schemas/        # Pydantic request/response models
│   │   ├── config.py       # Settings from .env (pydantic-settings)
│   │   ├── database.py     # Async engine + session factory
│   │   └── main.py         # FastAPI app + router registration
│   ├── tests/              # pytest suite (agent loop, SQL validation, routing, auth, ...)
│   ├── scripts/            # e2e & verification scripts
│   ├── schema.sql          # Supabase DDL — run in the SQL editor to set up app tables
│   ├── requirements.txt
│   └── .env.example
└── frontend/
    ├── src/
    │   ├── api/client.ts   # Axios client + SSE stream helpers
    │   ├── components/     # ChatWindow, charts/, QueryResultTable, SchemaViewer, ...
    │   ├── pages/          # Dashboard, DatabaseWorkspace, ChartPreview, Login, Register
    │   ├── hooks/          # useTypewriter
    │   └── types/
    ├── vite.config.ts
    ├── package.json
    └── .env
```

## Getting Started

### Prerequisites

- Python 3.11+
- Node.js 20+
- Free accounts: [Groq](https://console.groq.com/keys) (LLM key), [Google AI Studio](https://aistudio.google.com/apikey) (fallback key), [E2B](https://e2b.dev) (sandbox key), and a [Supabase](https://supabase.com) Postgres database.

### 1. Set up the database

1. Create a Supabase project and copy the **Session pooler** connection string (port 5432).
2. Open the **SQL Editor** and run the entire contents of `backend/schema.sql`. This creates `users`, `linked_databases`, `schema_cache`, `conversations`, `messages`, and `query_runs`, plus the enum types.
3. (Optional) Link a second Supabase/Postgres database that you want to query — this is the database you'll chat with in plain English.

### 2. Backend

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate        # Windows — on macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt

copy .env.example .env        # Windows — on macOS/Linux: cp .env.example .env
# then fill in DATABASE_URL, FERNET_KEY, JWT_SECRET, GROQ_API_KEY, GEMINI_API_KEY, E2B_API_KEY

# Generate a Fernet key:
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

uvicorn app.main:app --reload --port 8001
```

The API is now at `http://localhost:8001`. Interactive docs at `http://localhost:8001/docs`.

### 3. Frontend

```bash
cd frontend
npm install
npm run dev
```

The app opens at `http://localhost:5173` and talks to the backend via `VITE_API_BASE_URL` (defaults to `http://localhost:8001/api/v1` — override in `frontend/.env`).

### Environment Variables (backend `.env`)

| Variable | Description |
|----------|-------------|
| `DATABASE_URL` | BaseWise's own Supabase Postgres connection string (`postgresql+asyncpg://...`) |
| `FERNET_KEY` | Fernet key for encrypting stored DB credentials — generate with the command above |
| `JWT_SECRET` | Secret for signing JWTs |
| `JWT_ALGORITHM` | Default `HS256` |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | Default `30` |
| `REFRESH_TOKEN_EXPIRE_DAYS` | Default `7` |
| `GROQ_API_KEY` | Primary LLM provider (Groq, free tier: ~30 RPM / 1000 RPD) |
| `GEMINI_API_KEY` | Fallback LLM provider (Google AI Studio, free tier ~20 req/day — fallback only) |
| `PRIMARY_LLM_MODEL` | Default `openai/gpt-oss-120b` |
| `FALLBACK_LLM_MODELS` | Comma-separated fallbacks, default `gemini-3.6-flash` |
| `E2B_API_KEY` | E2B sandbox execution key |
| `ALLOWED_ORIGINS` | Comma-separated CORS origins, e.g. `http://localhost:5173` |
| `QUERY_ROUTER_ESCALATION` | `true` to spend one small LLM call when the intent classifier is ambiguous |

> Note: model names and free-tier limits change frequently. Verify current availability with `python scripts/test_models.py` before relying on a specific model.

## How the NL→SQL Pipeline Works

For every message in a query conversation:

1. **Route** — a heuristic intent classifier (with optional LLM escalation) decides whether this turn is a real data question or chit-chat.
2. **Schema context** — the cached schema (tables, columns, foreign keys, stats) for the linked DB is loaded. For small schemas the full metadata fits; larger schemas escalate to keyword matching and embedding-based retrieval.
3. **Generate** — the LLM produces candidate SQL **and** a first-pass confidence signal, given the question plus the relevant schema slice.
4. **Self-recheck (pass 2)** — a second LLM pass critiques the SQL against the schema and question **only** — no row data ever enters this prompt (prompt-injection hygiene). A heuristic `sqlglot` validation can early-exit on obvious SQL/schema mismatches without spending an LLM call.
5. **Execute** — the (rechecked) SQL runs in the E2B sandbox against the linked database with full read/write/DDL power — the DB role the user supplied is the ceiling.
6. **Score & respond** — confidence is combined from the LLM's self-report and real execution signals (ran cleanly, sane row/rows-affected count). The response includes SQL, explanation, confidence label + trace, results, and a structured `chart_data` payload when a chart is appropriate.
7. **Audit** — the statement is logged to `query_runs` regardless of outcome.

Progress and result tokens stream to the frontend over **Server-Sent Events** (`status`, `token`, `result` events), so the UI shows each stage live.

## Analysis Mode

Entered explicitly per database from the workspace UI (separate conversation thread, `mode = "analysis"`):

1. `POST /databases/{db_id}/analysis/suggest` — BaseWise inspects the schema and suggests starting points ("I can look at revenue trends, customer growth, or inventory risk — want me to start with one of these, or ask your own?").
2. `POST /conversations/{conv_id}/analysis/execute` — give the instruction in your own words. The LLM plans and runs sandboxed Python analysis against the live DB, producing plots and a plain-English summary.
3. The result is structured chart data (`chart_data`) persisted on the message and rendered interactively by the frontend.

## Security Model

- **Passwords** — bcrypt-hashed (never stored in plaintext).
- **Sessions** — short-lived JWT access tokens (30 min default) with a refresh-token flow; frontend auto-refreshes on 401.
- **Credentials at rest** — DB connection strings encrypted with Fernet before persistence; plaintext never written to the database. Deleting a linked database hard-deletes the encrypted credentials and cascades through schema cache and conversations.
- **Prompt injection hygiene** — query results are treated as untrusted data: row content is delimited and flagged as data, never instructions; row/character limits cap what's echoed back into prompts; the self-recheck pass never sees row data.
- **Sandbox isolation** — all LLM-written code runs in E2B's managed cloud sandboxes, scoped to a single session's credentials. Nothing executes directly on the web backend.
- **Ownership checks** — every database/conversation lookup validates the JWT user owns the resource.

> Design note: BaseWise intentionally does **not** gate writes or DDL — the LLM-written code has full execution power over the linked database, bounded only by the credentials supplied. A misread question or injected content in row data can therefore alter real data with no human checkpoint. This is an explicit, documented design choice (see `project.md` §3.2), and the `query_runs` audit log is the safety net.

## Testing

```bash
# Backend (pytest)
cd backend
pytest

# Frontend (lint)
cd frontend
npm run lint
```

## Deployment

- **Backend** — Render. `uvicorn app.main:app` with the `.env` variables configured.
- **Frontend** — Vercel. Build with `npm run build`, set `VITE_API_BASE_URL` to the deployed backend.
- **Sandbox** — E2B, fully managed and decoupled from the web backend.
- **Database** — Supabase (apply `backend/schema.sql` once).

## Roadmap

The canonical scoping document is [`project.md`](project.md). Planned milestones:

1. ~~Core DB connectivity + schema extraction~~ ✅
2. ~~Sandbox execution layer~~ ✅
3. ~~NL → SQL engine (self-recheck, confidence scoring)~~ ✅
4. ~~Basic chat frontend (conversation memory, SSE streaming)~~ ✅
5. ~~Analysis Mode (suggestions + autonomous execution)~~ ✅
6. ~~Plot rendering (Recharts)~~ ✅
7. Extend beyond Postgres — MySQL, SQLite, and other Postgres-compatible sources
8. Python SDK — `pip install`-able client on the same internal interfaces
9. (Future) MCP server built on the same internals

## License

Proprietary. All rights reserved.
