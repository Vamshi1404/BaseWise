import logging
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db
from app.models.models import User
from app.core.security import (
    hash_password, verify_password,
    create_access_token, create_refresh_token, decode_token
)
from app.schemas.auth import (
    SignupRequest, LoginRequest, RefreshRequest,
    TokenResponse, UserResponse
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])
bearer_scheme = HTTPBearer()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    """FastAPI dependency: validates JWT and returns the current User."""
    try:
        payload = decode_token(credentials.credentials)
        if payload.get("type") != "access":
            logger.warning(
                "Token validation failed: invalid token type",
                extra={"token_type": payload.get("type"), "expected": "access"}
            )
            raise ValueError("Not an access token")
        user_id = payload.get("sub")
    except ValueError as e:
        logger.warning(f"Token validation failed: {e}")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        logger.warning(f"Token validation failed: user not found", extra={"user_id": user_id})
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    return user


@router.post("/signup", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def signup(body: SignupRequest, db: AsyncSession = Depends(get_db)):
    existing = await db.execute(select(User).where(User.email == body.email))
    if existing.scalar_one_or_none():
        logger.warning(f"Signup failed: email already registered", extra={"email": body.email})
        raise HTTPException(status_code=400, detail="Email already registered")

    user = User(email=body.email, password_hash=hash_password(body.password))
    db.add(user)
    await db.flush()

    logger.info(f"User registered successfully", extra={"user_id": str(user.id), "email": body.email})
    return TokenResponse(
        access_token=create_access_token(str(user.id)),
        refresh_token=create_refresh_token(str(user.id)),
    )


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == body.email))
    user = result.scalar_one_or_none()
    if not user:
        logger.warning(f"Login failed: user not found", extra={"email": body.email})
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    if not verify_password(body.password, user.password_hash):
        logger.warning(f"Login failed: invalid password", extra={"email": body.email, "user_id": str(user.id)})
        raise HTTPException(status_code=401, detail="Invalid credentials")

    logger.info(f"User logged in successfully", extra={"user_id": str(user.id), "email": body.email})
    return TokenResponse(
        access_token=create_access_token(str(user.id)),
        refresh_token=create_refresh_token(str(user.id)),
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh(body: RefreshRequest, db: AsyncSession = Depends(get_db)):
    try:
        payload = decode_token(body.refresh_token)
        if payload.get("type") != "refresh":
            logger.warning(
                "Token refresh failed: invalid token type",
                extra={"token_type": payload.get("type"), "expected": "refresh"}
            )
            raise ValueError("Not a refresh token")
        user_id = payload.get("sub")
    except ValueError as e:
        logger.warning(f"Token refresh failed: {e}")
        raise HTTPException(status_code=401, detail=str(e))

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        logger.warning(f"Token refresh failed: user not found", extra={"user_id": user_id})
        raise HTTPException(status_code=401, detail="User not found")

    logger.info(f"Token refreshed successfully", extra={"user_id": str(user.id)})
    return TokenResponse(
        access_token=create_access_token(str(user.id)),
        refresh_token=create_refresh_token(str(user.id)),
    )


@router.get("/me", response_model=UserResponse)
async def me(current_user: User = Depends(get_current_user)):
    return UserResponse(
        id=str(current_user.id),
        email=current_user.email,
        created_at=current_user.created_at.isoformat(),
    )
