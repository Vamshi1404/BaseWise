from pydantic import BaseModel
from typing import Optional, Any, Literal


class CreateConversationRequest(BaseModel):
    mode: Literal["query", "analysis"] = "query"


class ConversationResponse(BaseModel):
    id: str
    mode: str
    linked_database_id: str
    created_at: str


class SendMessageRequest(BaseModel):
    content: str


class MessageResponse(BaseModel):
    id: str
    conversation_id: str
    role: str
    content: str
    sql_generated: Optional[str] = None
    confidence_score: Optional[float] = None
    confidence_label: Optional[str] = None
    reasoning: Optional[str] = None
    chart_data: Optional[Any] = None
    confidence_trace: Optional[Any] = None
    created_at: str


class QueryResultResponse(BaseModel):
    message: MessageResponse
    results: Optional[list[dict]] = None
    row_count: int = 0
    rows_affected: int = 0
    operation_type: str = "read"
    execution_ms: int = 0
    status: str
    error: Optional[str] = None
