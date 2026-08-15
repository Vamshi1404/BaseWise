from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from typing import Optional

from app.database import get_db
from app.models.models import User, LinkedDatabase, SchemaCache, Conversation, Message
from app.api.auth import get_current_user
from app.api.databases import _get_linked_db
from app.api.conversations import _get_conversation, _sse, _to_message_response
from app.core.security import decrypt_credentials
from app.core.analysis_engine import generate_suggestions, execute_analysis

router = APIRouter(tags=["analysis"])


class AnalysisExecuteRequest(BaseModel):
    prompt: str


@router.post("/databases/{db_id}/analysis/suggest")
async def suggest_analysis(
    db_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Proactively suggest business insight starting points based on the schema."""
    linked_db = await _get_linked_db(db_id, current_user, db)

    schema_result = await db.execute(
        select(SchemaCache).where(SchemaCache.linked_database_id == linked_db.id)
    )
    cache = schema_result.scalar_one_or_none()
    if not cache:
        raise HTTPException(status_code=400, detail="Schema not loaded. Refresh schema first.")

    suggestions = await generate_suggestions(cache.schema_json)
    return {"suggestions": suggestions}


@router.post("/conversations/{conv_id}/analysis/execute")
async def execute_analysis_task(
    conv_id: str,
    body: AnalysisExecuteRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Execute an autonomous analysis task in the E2B sandbox and return chart data.
    Streams Server-Sent Events so the user sees each stage as it runs.
    """
    import asyncio

    conv = await _get_conversation(conv_id, current_user, db)

    db_result = await db.execute(
        select(LinkedDatabase).where(LinkedDatabase.id == conv.linked_database_id)
    )
    linked_db = db_result.scalar_one_or_none()

    schema_result = await db.execute(
        select(SchemaCache).where(SchemaCache.linked_database_id == linked_db.id)
    )
    cache = schema_result.scalar_one_or_none()
    if not cache:
        raise HTTPException(status_code=400, detail="Schema not loaded.")

    connection_url = decrypt_credentials(linked_db.encrypted_credentials)

    # Save user message
    user_msg = Message(conversation_id=conv.id, role="user", content=body.prompt)
    db.add(user_msg)
    await db.flush()

    async def event_stream():
        queue: "asyncio.Queue[tuple[str, dict]]" = asyncio.Queue()

        async def emit(kind: str, data: dict) -> None:
            await queue.put((kind, data))

        async def run_pipeline():
            try:
                result = await execute_analysis(
                    prompt=body.prompt,
                    schema=cache.schema_json,
                    db_connection_url=connection_url,
                    on_status=lambda msg: emit("status", {"message": msg}),
                )
                await emit("pipeline_result", result)
            except Exception as exc:
                await emit("error", {"message": str(exc)})

        task = asyncio.create_task(run_pipeline())

        while True:
            kind, data = await queue.get()

            if kind == "error":
                yield _sse("error", data)
                task.cancel()
                return

            if kind == "status":
                yield _sse("status", data)
                continue

            if kind == "pipeline_result":
                result = data
                break

        task.cancel()

        if result.get("status") != "success":
            yield _sse("error", {"message": result.get("error", "Analysis failed")})
            return

        yield _sse("status", {"message": "Saving results..."})

        # Persist assistant message with chart data (structured JSON only — the
        # sandbox never returns images; charts render on the frontend).
        chart_data = dict(result.get("chart_data", {}))

        assistant_msg = Message(
            conversation_id=conv.id,
            role="assistant",
            content=result.get("chart_data", {}).get("summary", "Analysis complete."),
            chart_data=chart_data or None,
        )
        db.add(assistant_msg)
        await db.flush()
        await db.commit()

        yield _sse("result", {
            "message": _to_message_response(assistant_msg),
            "chart_data": chart_data,
            "python_code": result.get("python_code"),
            "execution_ms": result.get("execution_ms", 0),
            "status": "success",
        })

    return StreamingResponse(event_stream(), media_type="text/event-stream")
