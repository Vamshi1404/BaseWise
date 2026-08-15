import json
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db
from app.models.models import User, LinkedDatabase, Conversation, Message, QueryRun, SchemaCache
from app.api.auth import get_current_user
from app.api.databases import _get_linked_db
from app.core.security import decrypt_credentials
from app.core.agent_loop import run_nl_to_sql
from app.schemas.conversation import (
    CreateConversationRequest, ConversationResponse,
    SendMessageRequest, MessageResponse, QueryResultResponse
)

router = APIRouter(tags=["conversations"])


@router.get("/databases/{db_id}/conversations", response_model=list[ConversationResponse])
async def list_conversations(
    db_id: str,
    mode: str = "query",
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    linked_db = await _get_linked_db(db_id, current_user, db)
    result = await db.execute(
        select(Conversation).where(
            Conversation.linked_database_id == linked_db.id,
            Conversation.mode == mode,
        ).order_by(Conversation.created_at.desc())
    )
    convs = result.scalars().all()
    return [
        ConversationResponse(
            id=str(c.id),
            mode=c.mode,
            linked_database_id=str(c.linked_database_id),
            created_at=c.created_at.isoformat(),
        )
        for c in convs
    ]


@router.post("/databases/{db_id}/conversations", response_model=ConversationResponse, status_code=201)
async def create_conversation(
    db_id: str,
    body: CreateConversationRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    linked_db = await _get_linked_db(db_id, current_user, db)
    conv = Conversation(linked_database_id=linked_db.id, mode=body.mode)
    db.add(conv)
    await db.flush()
    return ConversationResponse(
        id=str(conv.id),
        mode=conv.mode,
        linked_database_id=str(conv.linked_database_id),
        created_at=conv.created_at.isoformat(),
    )


@router.get("/conversations/{conv_id}/messages", response_model=list[MessageResponse])
async def get_messages(
    conv_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    conv = await _get_conversation(conv_id, current_user, db)
    result = await db.execute(
        select(Message).where(Message.conversation_id == conv.id).order_by(Message.created_at)
    )
    messages = result.scalars().all()
    return [_to_message_response(m) for m in messages]


@router.post("/conversations/{conv_id}/messages")
async def send_message(
    conv_id: str,
    body: SendMessageRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Execute the NL→SQL pipeline and return results.
    Streams a Server-Sent Events response: progress events then final JSON result.
    """
    conv = await _get_conversation(conv_id, current_user, db)

    # Load linked DB and schema
    db_result = await db.execute(
        select(LinkedDatabase).where(LinkedDatabase.id == conv.linked_database_id)
    )
    linked_db = db_result.scalar_one_or_none()
    if not linked_db:
        raise HTTPException(status_code=404, detail="Linked database not found")

    schema_result = await db.execute(
        select(SchemaCache).where(SchemaCache.linked_database_id == linked_db.id)
    )
    schema_cache = schema_result.scalar_one_or_none()
    if not schema_cache:
        raise HTTPException(status_code=400, detail="Schema not loaded. Refresh schema first.")

    # Load bounded conversation history (NL only — no row data per project.md 3.3)
    history_result = await db.execute(
        select(Message)
        .where(Message.conversation_id == conv.id)
        .order_by(Message.created_at.desc())
        .limit(10)
    )
    history = [
        {"role": m.role, "content": m.content}
        for m in reversed(history_result.scalars().all())
    ]

    # Save user message
    user_msg = Message(conversation_id=conv.id, role="user", content=body.content)
    db.add(user_msg)
    await db.flush()

    connection_url = decrypt_credentials(linked_db.encrypted_credentials)

    async def event_stream():
        import asyncio
        queue: "asyncio.Queue[tuple[str, dict]]" = asyncio.Queue()

        async def emit(kind: str, data: dict) -> None:
            await queue.put((kind, data))

        async def run_pipeline():
            try:
                result = await run_nl_to_sql(
                    question=body.content,
                    schema=schema_cache.schema_json,
                    db_connection_url=connection_url,
                    conversation_history=history,
                    on_status=lambda msg: emit("status", {"message": msg}),
                    on_token=lambda tok: emit("token", {"delta": tok}),
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

            if kind == "pipeline_result":
                result = data
                break

            if kind == "status":
                yield _sse("status", data)
                continue

            if kind == "token":
                yield _sse("token", data)
                continue

        task.cancel()

        yield _sse("status", {"message": "Saving results..."})

        # Save assistant message (content = what the query found, in plain English)
        assistant_msg = Message(
            conversation_id=conv.id,
            role="assistant",
            content=result.get("summary") or result["explanation"],
            sql_generated=result.get("sql"),
            confidence_score=result.get("confidence_score"),
            reasoning=result.get("reasoning"),
            chart_data=result.get("chart_data"),
            confidence_trace=result.get("confidence_trace"),
        )
        db.add(assistant_msg)
        await db.flush()

        # Save query run audit log (always, including writes/DDL — project.md 3.2)
        if result.get("sql"):
            run = QueryRun(
                message_id=assistant_msg.id,
                sql_text=result["sql"],
                operation_type=result.get("operation_type", "read"),
                row_count=result.get("row_count", 0),
                rows_affected=result.get("rows_affected", 0),
                execution_ms=result.get("execution_ms", 0),
                sandbox_session_id=result.get("sandbox_session_id"),
                status=result.get("status", "error"),
            )
            db.add(run)
            await db.flush()

        await db.commit()

        yield _sse("result", {
            "message": _to_message_response(assistant_msg),
            "results": result.get("results"),
            "chart_data": result.get("chart_data"),
            "row_count": result.get("row_count", 0),
            "rows_affected": result.get("rows_affected", 0),
            "operation_type": result.get("operation_type", "read"),
            "execution_ms": result.get("execution_ms", 0),
            "confidence_label": result.get("confidence_label", "low"),
            "reasoning": result.get("reasoning"),
            "summary": result.get("summary"),
            "status": result.get("status"),
            "error": result.get("error"),
            "route": result.get("route"),
            "route_reason": result.get("route_reason"),
            "pass2_skipped": result.get("pass2_skipped"),
            "confidence_trace": result.get("confidence_trace"),
        })

        yield "event: done\ndata: [DONE]\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


# --- Helpers ---

def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


def _confidence_label(score) -> str:
    if score is None:
        return "low"
    if score >= 0.75:
        return "high"
    if score >= 0.5:
        return "medium"
    return "low"


def _to_message_response(m: Message) -> dict:
    return {
        "id": str(m.id),
        "conversation_id": str(m.conversation_id),
        "role": m.role,
        "content": m.content,
        "sql_generated": m.sql_generated,
        "confidence_score": m.confidence_score,
        "confidence_label": _confidence_label(m.confidence_score),
        "reasoning": m.reasoning,
        "chart_data": m.chart_data,
        "confidence_trace": m.confidence_trace,
        "created_at": m.created_at.isoformat(),
    }


async def _get_conversation(conv_id: str, current_user: User, db: AsyncSession) -> Conversation:
    """Verify the conversation belongs to the current user via the linked DB."""
    result = await db.execute(
        select(Conversation)
        .join(LinkedDatabase, Conversation.linked_database_id == LinkedDatabase.id)
        .where(
            Conversation.id == conv_id,
            LinkedDatabase.user_id == current_user.id,
        )
    )
    conv = result.scalar_one_or_none()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return conv
