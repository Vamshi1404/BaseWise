from datetime import datetime, timedelta, timezone
from typing import Optional
import jwt
from cryptography.fernet import Fernet
from passlib.context import CryptContext
from app.config import settings

# --- Password hashing ---
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


# --- JWT ---
def create_access_token(subject: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.access_token_expire_minutes)
    payload = {"sub": subject, "exp": expire, "type": "access"}
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def create_refresh_token(subject: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(days=settings.refresh_token_expire_days)
    payload = {"sub": subject, "exp": expire, "type": "refresh"}
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_token(token: str) -> Optional[dict]:
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except jwt.ExpiredSignatureError:
        raise ValueError("Token has expired")
    except jwt.InvalidTokenError:
        raise ValueError("Invalid token")


# --- Fernet symmetric encryption for DB credentials ---
# IMPORTANT: Fernet key != JWT secret. These are separate mechanisms.
# Fernet protects stored DB connection strings at rest.
# JWT protects the user's session. Never conflate the two.
_fernet = Fernet(settings.fernet_key.encode())


def encrypt_credentials(plaintext: str) -> str:
    """Encrypt a DB connection string for storage. Returns base64 token string."""
    return _fernet.encrypt(plaintext.encode()).decode()


def decrypt_credentials(token: str) -> str:
    """Decrypt a stored DB connection string. Only call in-memory, never log result."""
    return _fernet.decrypt(token.encode()).decode()
