from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class LinkDatabaseRequest(BaseModel):
    display_name: str
    db_type: str = "postgres"       # extensible for future dialects
    connection_url: str             # plaintext; encrypted immediately on receipt


class DatabaseResponse(BaseModel):
    id: str
    display_name: str
    db_type: str
    created_at: str
    last_schema_scan_at: Optional[str] = None


class DatabaseDetailResponse(DatabaseResponse):
    status: str = "connected"


class SchemaResponse(BaseModel):
    tables: list
    dialect: str
    scanned_at: str


class ConnectionTestResponse(BaseModel):
    status: str         # "success" | "failed"
    message: str
