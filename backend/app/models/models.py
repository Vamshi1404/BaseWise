import uuid
from datetime import datetime, timezone
from sqlalchemy import (
    Column, String, Text, Float, Integer, Boolean,
    DateTime, ForeignKey, Enum, JSON
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.database import Base


def utcnow():
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)

    linked_databases = relationship("LinkedDatabase", back_populates="user", cascade="all, delete-orphan")


class LinkedDatabase(Base):
    __tablename__ = "linked_databases"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    # db_type stored from day one for future multi-dialect support (mysql, sqlite, etc.)
    db_type = Column(String(50), nullable=False, default="postgres")
    display_name = Column(String(255), nullable=False)
    encrypted_credentials = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)
    last_schema_scan_at = Column(DateTime(timezone=True), nullable=True)

    user = relationship("User", back_populates="linked_databases")
    schema_cache = relationship("SchemaCache", back_populates="linked_database", cascade="all, delete-orphan", uselist=False)
    conversations = relationship("Conversation", back_populates="linked_database", cascade="all, delete-orphan")


class SchemaCache(Base):
    __tablename__ = "schema_cache"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    linked_database_id = Column(UUID(as_uuid=True), ForeignKey("linked_databases.id", ondelete="CASCADE"), nullable=False, unique=True)
    schema_json = Column(JSON, nullable=False)
    scanned_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)

    linked_database = relationship("LinkedDatabase", back_populates="schema_cache")


class Conversation(Base):
    __tablename__ = "conversations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    linked_database_id = Column(UUID(as_uuid=True), ForeignKey("linked_databases.id", ondelete="CASCADE"), nullable=False)
    # mode enforces query/analysis thread separation (project.md Section 5)
    mode = Column(Enum("query", "analysis", name="conversation_mode"), nullable=False, default="query")
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)

    linked_database = relationship("LinkedDatabase", back_populates="conversations")
    messages = relationship("Message", back_populates="conversation", cascade="all, delete-orphan")


class Message(Base):
    __tablename__ = "messages"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    conversation_id = Column(UUID(as_uuid=True), ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False)
    role = Column(Enum("user", "assistant", name="message_role"), nullable=False)
    content = Column(Text, nullable=False)
    sql_generated = Column(Text, nullable=True)
    confidence_score = Column(Float, nullable=True)
    # Model's explanation of WHY it chose this query (surfaced in the UI)
    reasoning = Column(Text, nullable=True)
    # Structured chart data JSON — never rendered images (project.md Section 6)
    chart_data = Column(JSON, nullable=True)
    # #6: structured explanation of how confidence_score was derived
    confidence_trace = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)

    conversation = relationship("Conversation", back_populates="messages")
    query_runs = relationship("QueryRun", back_populates="message", cascade="all, delete-orphan")


class QueryRun(Base):
    __tablename__ = "query_runs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    message_id = Column(UUID(as_uuid=True), ForeignKey("messages.id", ondelete="SET NULL"), nullable=True)
    sql_text = Column(Text, nullable=False)
    # operation_type logged for audit trail — no gating (project.md Section 3.2)
    operation_type = Column(Enum("read", "write", "ddl", name="operation_type"), nullable=False, default="read")
    row_count = Column(Integer, default=0)
    rows_affected = Column(Integer, default=0)
    execution_ms = Column(Integer, nullable=False)
    sandbox_session_id = Column(String(255), nullable=True)
    status = Column(Enum("success", "error", name="run_status"), nullable=False)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)

    message = relationship("Message", back_populates="query_runs")
