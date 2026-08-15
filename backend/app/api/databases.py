from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db
from app.models.models import User, LinkedDatabase, SchemaCache
from app.api.auth import get_current_user
from app.core.security import encrypt_credentials, decrypt_credentials
from app.core.schema_extractor import extract_schema
from app.schemas.database import (
    LinkDatabaseRequest, DatabaseResponse, DatabaseDetailResponse,
    SchemaResponse, ConnectionTestResponse
)

router = APIRouter(prefix="/databases", tags=["databases"])

SCHEMA_CACHE_TTL_HOURS = 24


@router.get("", response_model=list[DatabaseResponse])
async def list_databases(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(LinkedDatabase).where(LinkedDatabase.user_id == current_user.id)
    )
    dbs = result.scalars().all()
    return [
        DatabaseResponse(
            id=str(d.id),
            display_name=d.display_name,
            db_type=d.db_type,
            created_at=d.created_at.isoformat(),
            last_schema_scan_at=d.last_schema_scan_at.isoformat() if d.last_schema_scan_at else None,
        )
        for d in dbs
    ]


@router.post("", response_model=DatabaseDetailResponse, status_code=status.HTTP_201_CREATED)
async def link_database(
    body: LinkDatabaseRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # Verify connection before storing
    try:
        schema = extract_schema(body.connection_url)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Could not connect to database: {exc}")

    # Encrypt credentials immediately — plaintext never persisted
    encrypted = encrypt_credentials(body.connection_url)

    linked_db = LinkedDatabase(
        user_id=current_user.id,
        db_type=body.db_type,
        display_name=body.display_name,
        encrypted_credentials=encrypted,
        last_schema_scan_at=datetime.now(timezone.utc),
    )
    db.add(linked_db)
    await db.flush()

    # Store initial schema cache
    expires_at = datetime.now(timezone.utc) + timedelta(hours=SCHEMA_CACHE_TTL_HOURS)
    cache = SchemaCache(
        linked_database_id=linked_db.id,
        schema_json=schema,
        expires_at=expires_at,
    )
    db.add(cache)

    return DatabaseDetailResponse(
        id=str(linked_db.id),
        display_name=linked_db.display_name,
        db_type=linked_db.db_type,
        created_at=linked_db.created_at.isoformat(),
        status="connected",
    )


@router.get("/{db_id}", response_model=DatabaseDetailResponse)
async def get_database(
    db_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    linked_db = await _get_linked_db(db_id, current_user, db)
    return DatabaseDetailResponse(
        id=str(linked_db.id),
        display_name=linked_db.display_name,
        db_type=linked_db.db_type,
        created_at=linked_db.created_at.isoformat(),
        last_schema_scan_at=linked_db.last_schema_scan_at.isoformat() if linked_db.last_schema_scan_at else None,
        status="connected",
    )


@router.delete("/{db_id}", status_code=status.HTTP_204_NO_CONTENT)
async def unlink_database(
    db_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Hard-deletes the linked database row and all cascading data.
    Encrypted credentials are permanently destroyed (project.md Section 7).
    """
    linked_db = await _get_linked_db(db_id, current_user, db)
    await db.delete(linked_db)


@router.post("/{db_id}/test", response_model=ConnectionTestResponse)
async def test_connection(
    db_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    linked_db = await _get_linked_db(db_id, current_user, db)
    connection_url = decrypt_credentials(linked_db.encrypted_credentials)

    try:
        extract_schema(connection_url)
        return ConnectionTestResponse(status="success", message="Connection successful")
    except Exception as exc:
        return ConnectionTestResponse(status="failed", message=str(exc))


@router.get("/{db_id}/schema", response_model=SchemaResponse)
async def get_schema(
    db_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    linked_db = await _get_linked_db(db_id, current_user, db)

    # Check cache validity
    cache_result = await db.execute(
        select(SchemaCache).where(SchemaCache.linked_database_id == linked_db.id)
    )
    cache = cache_result.scalar_one_or_none()

    now = datetime.now(timezone.utc)
    if cache and cache.expires_at > now:
        return SchemaResponse(
            tables=cache.schema_json.get("tables", []),
            dialect=cache.schema_json.get("dialect", "postgres"),
            scanned_at=cache.scanned_at.isoformat(),
        )

    # Cache expired or missing — re-scan
    return await _refresh_schema(linked_db, db)


@router.post("/{db_id}/schema/refresh", response_model=SchemaResponse)
async def refresh_schema(
    db_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    linked_db = await _get_linked_db(db_id, current_user, db)
    return await _refresh_schema(linked_db, db)


# --- Helpers ---

async def _get_linked_db(db_id: str, current_user: User, db: AsyncSession) -> LinkedDatabase:
    result = await db.execute(
        select(LinkedDatabase).where(
            LinkedDatabase.id == db_id,
            LinkedDatabase.user_id == current_user.id,
        )
    )
    linked_db = result.scalar_one_or_none()
    if not linked_db:
        raise HTTPException(status_code=404, detail="Database not found")
    return linked_db


async def _refresh_schema(linked_db: LinkedDatabase, db: AsyncSession) -> SchemaResponse:
    connection_url = decrypt_credentials(linked_db.encrypted_credentials)
    try:
        schema = extract_schema(connection_url)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Schema extraction failed: {exc}")

    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(hours=SCHEMA_CACHE_TTL_HOURS)

    cache_result = await db.execute(
        select(SchemaCache).where(SchemaCache.linked_database_id == linked_db.id)
    )
    cache = cache_result.scalar_one_or_none()

    if cache:
        cache.schema_json = schema
        cache.scanned_at = now
        cache.expires_at = expires_at
    else:
        cache = SchemaCache(
            linked_database_id=linked_db.id,
            schema_json=schema,
            scanned_at=now,
            expires_at=expires_at,
        )
        db.add(cache)

    linked_db.last_schema_scan_at = now

    return SchemaResponse(
        tables=schema.get("tables", []),
        dialect=schema.get("dialect", "postgres"),
        scanned_at=now.isoformat(),
    )
