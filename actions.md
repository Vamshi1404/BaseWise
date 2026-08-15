# Basewise — Actions & API Specifications

This file defines the detailed API contracts, database schema design, and step-by-step action plan for building **Basewise**, featuring a **Python (FastAPI)** backend and a **React TypeScript** frontend.

---

## 1. System Architecture Overview

```
 [ React + TS Frontend ] (Vercel)
          │
          │ HTTP / SSE (JWT Auth)
          ▼
 [ FastAPI Python Backend ] (Render)
    ├── Auth & Credentials (Fernet Encryption)
    ├── Schema Extractor (SQLAlchemy dialect-agnostic)
    ├── OpenRouter LLM Client (Qwen3-235B-A22B MoE primary + fallback routing)
    └── E2B Sandbox Executor (Isolated Code Execution)
          │
          ├──▶ [ Supabase Postgres ]  ← Basewise system DB only (users, conversations, etc.)
          │
          └──▶ [ User's Linked DB ]  ← Supabase Postgres for M1; extensible to MySQL/SQLite/etc. later
```

---

## 2. API Endpoints Specification (`/api/v1`)

### 2.1 Authentication (`/api/v1/auth`)

| Endpoint | Method | Request Body | Response Body | Description |
|---|---|---|---|---|
| `/auth/signup` | `POST` | `{ email, password }` | `{ id, email, access_token, refresh_token }` | Register new user |
| `/auth/login` | `POST` | `{ email, password }` | `{ access_token, refresh_token, token_type }` | Login and get JWT |
| `/auth/refresh` | `POST` | `{ refresh_token }` | `{ access_token, refresh_token }` | Refresh expired access token |
| `/auth/me` | `GET` | Headers: `Bearer <token>` | `{ id, email, created_at }` | Get current user details |

### 2.2 Linked Databases (`/api/v1/databases`)

| Endpoint | Method | Request Body | Response Body | Description |
|---|---|---|---|---|
| `/databases` | `GET` | - | `[{ id, display_name, db_type, created_at, last_schema_scan_at }]` | List user's linked databases |
| `/databases` | `POST` | `{ db_type, display_name, connection_url }` | `{ id, display_name, db_type, status }` | Link database (encrypts creds) |
| `/databases/{id}` | `GET` | - | `{ id, display_name, db_type, status, last_schema_scan_at }` | Get database details |
| `/databases/{id}` | `DELETE` | - | `{ message: "Database unlinked successfully" }` | Hard-delete database creds & cache |
| `/databases/{id}/test` | `POST` | - | `{ status: "success" \| "failed", message }` | Test DB connectivity |
| `/databases/{id}/schema` | `GET` | - | `{ tables: [...], scanned_at }` | Get cached schema metadata |
| `/databases/{id}/schema/refresh` | `POST` | - | `{ tables: [...], scanned_at }` | Force re-scan schema metadata |

### 2.3 Conversations & Natural Language Query (`/api/v1/conversations`)

| Endpoint | Method | Request Body | Response Body | Description |
|---|---|---|---|---|
| `/databases/{db_id}/conversations` | `GET` | Query params: `?mode=query\|analysis` | `[{ id, mode, created_at }]` | List conversation threads |
| `/databases/{db_id}/conversations` | `POST` | `{ mode: "query" \| "analysis" }` | `{ id, mode, created_at }` | Create new conversation thread |
| `/conversations/{id}/messages` | `GET` | - | `[{ id, role, content, sql_generated, confidence_score, chart_data, created_at }]` | Get conversation history |
| `/conversations/{id}/messages` | `POST` | `{ content: "natural language prompt" }` | SSE Stream / JSON response | Execute NL query pipeline |

### 2.4 Analysis Mode (`/api/v1/analysis`)

| Endpoint | Method | Request Body | Response Body | Description |
|---|---|---|---|---|
| `/databases/{db_id}/analysis/suggest` | `POST` | - | `{ suggestions: ["Revenue trends", "Customer growth", "Inventory risk"] }` | Generate proactive business insight prompts |
| `/conversations/{id}/analysis/execute` | `POST` | `{ prompt: "Analyze revenue trends" }` | `{ explanation, python_code, chart_data, summary }` | Execute sandboxed analysis & return chart spec |

---

## 3. Database Schema Design (Basewise Application Database)

```sql
-- Users Entity
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Linked Databases (Fernet Symmetric Encryption)
CREATE TABLE linked_databases (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    db_type VARCHAR(50) NOT NULL, -- 'postgres', 'mysql', 'sqlite'
    display_name VARCHAR(255) NOT NULL,
    encrypted_credentials TEXT NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    last_schema_scan_at TIMESTAMP WITH TIME ZONE
);

-- Cached Schema Metadata
CREATE TABLE schema_cache (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    linked_database_id UUID NOT NULL REFERENCES linked_databases(id) ON DELETE CASCADE,
    schema_json JSONB NOT NULL,
    scanned_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL
);

-- Conversation Threads
CREATE TABLE conversations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    linked_database_id UUID NOT NULL REFERENCES linked_databases(id) ON DELETE CASCADE,
    mode VARCHAR(20) NOT NULL CHECK (mode IN ('query', 'analysis')),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Messages Log
CREATE TABLE messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id UUID NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    role VARCHAR(20) NOT NULL CHECK (role IN ('user', 'assistant')),
    content TEXT NOT NULL,
    sql_generated TEXT,
    confidence_score FLOAT,
    chart_data JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Query Execution Audit Log
CREATE TABLE query_runs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    message_id UUID REFERENCES messages(id) ON DELETE SET NULL,
    sql_text TEXT NOT NULL,
    operation_type VARCHAR(20) NOT NULL CHECK (operation_type IN ('read', 'write', 'ddl')),
    row_count INT DEFAULT 0,
    rows_affected INT DEFAULT 0,
    execution_ms INT NOT NULL,
    sandbox_session_id VARCHAR(255),
    status VARCHAR(20) NOT NULL CHECK (status IN ('success', 'error')),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
```

---

## 4. Detailed Action Plan

### Phase 1: Setup & Infrastructure
- [ ] Initialize Python FastAPI project inside `backend/` with dependencies (`fastapi`, `uvicorn`, `sqlalchemy`, `asyncpg`, `cryptography`, `pyjwt`, `e2b-code-interpreter`, `httpx`, `pydantic`).
- [ ] Initialize React TypeScript Vite project inside `frontend/` with dependencies (`react`, `react-dom`, `axios`, `recharts`, `lucide-react`, `tailwindcss`).
- [ ] Configure environment variables (`GEMINI_API_KEY`, `GROQ_API_KEY`, `E2B_API_KEY`, `FERNET_KEY`, `JWT_SECRET`, `DATABASE_URL`, `PRIMARY_LLM_MODEL=openai/gpt-oss-120b`, `FALLBACK_LLM_MODELS=gemini-3.6-flash`).

> **Model status (2026-08-14) — do not re-promote Gemini to primary without re-reading this:**
> The Gemini `gemini-3.6-flash` free tier is capped at **~20 generate_content requests/day per project+model**
> (`GenerateRequestsPerDayPerProjectPerModel-FreeTier`). The pipeline burns 3 requests per user query
> (pass1 + pass2 + summary), so as primary it would exhaust almost immediately in real usage. That is why
> **Groq `openai/gpt-oss-120b` (30 RPM / 1000 RPD / **8000 TPM**) is the primary** and `gemini-3.6-flash` is only the
> fallback. `google.genai` SDK (Interactions API) is required for Gemini because new `AQ.`-format AI Studio
> keys 404 on Google's raw OpenAI-compatible REST endpoint. To re-test Gemini availability run
> `python scripts/test_models.py`.
>
> **Groq TPM gotcha (2026-08-14):** `gpt-oss-120b` is a reasoning model that *reserves ~4900 tokens per call*
> (max_tokens=4096 output budget + input) against the 8000 TPM free cap — so rapid queries will regularly hit
> transient HTTP 429 (TPM), not RPD. `llm_client` retries 429s once with backoff (honoring `Retry-After`),
> so a single hiccup no longer cascades into "all models exhausted." Payloads are kept bounded via
> `HISTORY_MAX_TURNS=8`/`HISTORY_MAX_CHARS=4000` and relevant-table/light-schema trimming (stats+sample rows
> only in pass1).

### Phase 2: Core Auth & Schema Extraction (Milestone 1)
- [ ] Provision a **Supabase project** for Basewise's own system database. Apply DDL schema from Section 3 via Supabase dashboard or CLI.
- [ ] Set `DATABASE_URL` env var to the Supabase Postgres connection string (Session mode pooler, port 5432, for asyncpg compatibility).
- [ ] Implement Fernet credential encryption/decryption in `backend/app/core/security.py`.
- [ ] Build `SchemaExtractor` in `backend/app/core/schema_extractor.py` using SQLAlchemy's dialect-agnostic `inspect()` API — works against any SQLAlchemy-supported DB. Milestone 1 targets Supabase Postgres; adding MySQL/SQLite later requires zero changes to this module.
- [ ] Implement Auth API (`signup`, `login`, `me`) and Database Management API (`link`, `list`, `schema`). `db_type` field stored on `linked_databases` table to support multi-dialect routing in future milestones.

### Phase 3: E2B Sandbox Execution Engine (Milestone 2)
- [ ] Implement `SandboxExecutor` abstraction in `backend/app/core/sandbox.py` using `e2b_code_interpreter`.
- [ ] Ensure sandboxed code decrypts connection strings in-memory, executes SQL/Python, captures timing and row stats, and records entries in `query_runs`.
- [ ] Verify execution of `SELECT`, `INSERT`/`UPDATE` (writes), and `ALTER`/`CREATE` (DDL).

### Phase 4: OpenRouter LLM Agent & Self-Recheck Pipeline (Milestone 3)
- [ ] Implement `LLMClient` using **`qwen/qwen3-235b-a22b:free`** as primary — a 235B MoE model that activates only **22B parameters per token**, delivering near-frontier SQL generation and reasoning quality at much lower latency than dense large models. Ideal for demo UX. Fallback chain: `qwen/qwen3-30b-a3b:free` (30B MoE, only 3B active params — very fast) → `deepseek/deepseek-r1:free`. Model read from `PRIMARY_LLM_MODEL` env var — swap in `.env` with no code changes.
- [ ] Build hand-rolled NL-to-SQL 2-pass loop:
  - **Pass 1**: Prompt LLM with question + relevant schema context -> Generate Candidate SQL + Reasoning.
  - **Pass 2 (Self-Recheck)**: Prompt LLM with question + schema + Candidate SQL -> Audit joins, column names, filters, intent.
- [ ] Execute checked SQL in E2B sandbox -> Calculate composite confidence score -> Return plain English explanation + results.

### Phase 5: React TS Frontend Implementation (Milestone 4)
- [ ] Build Auth pages (Login / Register).
- [ ] Build Dashboard for managing linked databases & viewing connection health.
- [ ] Build Database Workspace with dual tabs:
  - **Query Tab**: Chat interface, schema inspector, SQL viewer, confidence score badge, dynamic data table.
  - **Analysis Tab**: Business insight suggestion chips, interactive charts.

### Phase 6: Analysis Mode & Interactive Visualization (Milestone 5 & 6)
- [ ] Build `/analysis/suggest` engine to generate relevant analysis starting points based on schema structure.
- [ ] Build Python sandbox analysis script generator that computes aggregations and returns structured JSON chart specs.
- [ ] Render interactive charts in React TS using Recharts (bar, line, pie, area charts).
