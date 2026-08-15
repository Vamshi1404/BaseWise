"""
E2B Sandbox Executor — Abstraction interface over the E2B cloud sandbox.

Design principle (project.md Section 3.1):
  SandboxExecutor.run(code, context) -> result

The rest of the backend NEVER calls E2B SDK methods directly — only this module does.
This decouples the backend from E2B's SDK specifics and allows swapping the provider
(e.g. Firecracker/gVisor self-hosted) by changing only this file.

SECURITY:
- The decrypted DB connection string is passed in-memory as context, scoped to one call.
- It is never logged, never returned in results, never stored in the sandbox.
- Sandboxes are ephemeral: created per execution, torn down after.
"""
import time
from dataclasses import dataclass, field
from typing import Any, Optional
import sqlalchemy as sa
from e2b_code_interpreter import Sandbox
from app.config import settings


@dataclass
class SandboxResult:
    stdout: str
    stderr: str
    error: Optional[str]
    results: list[Any]          # Structured outputs (tables, JSON, charts)
    execution_ms: int
    sandbox_session_id: str
    success: bool


def _flatten_logs(raw) -> str:
    """E2B's execution.logs.stdout/stderr are lists of chunks — normalize to str."""
    if raw is None:
        return ""
    if isinstance(raw, list):
        return "\n".join(str(item) for item in raw)
    return str(raw)


def _normalize_connection_url(url_str: str) -> str:
    """
    Sandboxes only have sync drivers installed (psycopg2/pymysql).
    Map async-only drivers to a sync equivalent before the code runs
    (mirrors schema_extractor's normalization for the metadata connection).

    NOTE: str(URL) masks the password as `***` — must use
    render_as_string(hide_password=False) or the sandbox would auth with "***".
    """
    try:
        url = sa.engine.make_url(url_str)
        backend = url.get_backend_name()
        driver = url.get_driver_name()
        if backend == "postgresql" and driver != "psycopg2":
            url = url.set(drivername="postgresql")
        elif backend == "mysql" and driver not in ("pymysql", "mysqldb"):
            url = url.set(drivername="pymysql")
        return url.render_as_string(hide_password=False)
    except Exception:
        return url_str


def run_in_sandbox(
    code: str,
    db_connection_url: str,      # Decrypted in-memory, never logged
    timeout_seconds: int = 30,
) -> SandboxResult:
    """
    Execute LLM-generated Python code in an isolated E2B cloud sandbox.

    The sandbox receives:
      - The Python code to execute
      - The DB connection URL injected as an environment variable (DB_URL)
      - Nothing from other users/sessions

    Returns SandboxResult with stdout, stderr, structured results, timing, and status.
    """
    start = time.monotonic()
    sandbox_id = "unknown"

    try:
        with Sandbox(api_key=settings.e2b_api_key, timeout=timeout_seconds) as sandbox:
            sandbox_id = getattr(sandbox, "sandbox_id", "unknown")

            # Install DB driver inside sandbox (psycopg2-binary for Postgres, pymysql for MySQL).
            # The sandbox is DATA COMPUTATION only — no matplotlib, so analysis code can never
            # produce chart images (the frontend renders charts from the returned JSON spec).
            sandbox.commands.run(
                "pip install psycopg2-binary sqlalchemy pandas pymysql -q"
            )

            # Inject connection URL as env var — never as a string literal in code.
            # Normalize async-only drivers (asyncpg/aiomysql) to the sync driver the
            # sandbox actually has installed.
            env_db_url = _normalize_connection_url(db_connection_url)
            execution = sandbox.run_code(code, envs={"DB_URL": env_db_url})

            elapsed_ms = int((time.monotonic() - start) * 1000)

            error_text = None
            if execution.error:
                error_text = str(execution.error.value or execution.error.name or execution.error)

            return SandboxResult(
                stdout=_flatten_logs(execution.logs.stdout),
                stderr=_flatten_logs(execution.logs.stderr),
                error=error_text,
                results=execution.results if execution.results else [],
                execution_ms=elapsed_ms,
                sandbox_session_id=sandbox_id,
                success=execution.error is None,
            )

    except Exception as exc:
        elapsed_ms = int((time.monotonic() - start) * 1000)
        return SandboxResult(
            stdout="",
            stderr="",
            error=str(exc),
            results=[],
            execution_ms=elapsed_ms,
            sandbox_session_id=sandbox_id,
            success=False,
        )
