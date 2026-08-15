"""
Unit tests for JWT token generation and validation.
Tests the security module's JWT functionality.
"""
import os
import sys
import pytest
from datetime import datetime, timedelta, timezone
import jwt
from dotenv import load_dotenv

# Load environment variables from backend/.env
backend_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
dotenv_path = os.path.join(backend_dir, '.env')
load_dotenv(dotenv_path)

# Ensure backend directory is in python path
sys.path.insert(0, backend_dir)

from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password
)
from app.config import settings


class TestJWTTokenGeneration:
    """Test JWT token generation functions."""
    
    def test_create_access_token_returns_valid_jwt(self):
        """Test that create_access_token returns a valid JWT string."""
        user_id = "test-user-123"
        token = create_access_token(user_id)
        
        # JWT tokens have 3 parts separated by dots
        assert isinstance(token, str)
        assert token.count('.') == 2
        
    def test_create_access_token_contains_correct_payload(self):
        """Test that access token contains correct subject and type."""
        user_id = "test-user-456"
        token = create_access_token(user_id)
        
        # Decode without verification to check payload
        payload = jwt.decode(token, options={"verify_signature": False})
        
        assert payload["sub"] == user_id
        assert payload["type"] == "access"
        assert "exp" in payload
        
    def test_create_access_token_expiration_time(self):
        """Test that access token has correct expiration time."""
        user_id = "test-user-789"
        before_creation = datetime.now(timezone.utc)
        token = create_access_token(user_id)
        after_creation = datetime.now(timezone.utc)
        
        payload = jwt.decode(token, options={"verify_signature": False})
        exp_timestamp = payload["exp"]
        exp_datetime = datetime.fromtimestamp(exp_timestamp, tz=timezone.utc)
        
        # Expected expiration should be around access_token_expire_minutes from now
        # Allow a tolerance of 2 seconds for timing precision
        expected_exp_min = before_creation + timedelta(minutes=settings.access_token_expire_minutes) - timedelta(seconds=2)
        expected_exp_max = after_creation + timedelta(minutes=settings.access_token_expire_minutes) + timedelta(seconds=2)
        
        assert expected_exp_min <= exp_datetime <= expected_exp_max
        
    def test_create_refresh_token_returns_valid_jwt(self):
        """Test that create_refresh_token returns a valid JWT string."""
        user_id = "refresh-user-123"
        token = create_refresh_token(user_id)
        
        assert isinstance(token, str)
        assert token.count('.') == 2
        
    def test_create_refresh_token_contains_correct_payload(self):
        """Test that refresh token contains correct subject and type."""
        user_id = "refresh-user-456"
        token = create_refresh_token(user_id)
        
        payload = jwt.decode(token, options={"verify_signature": False})
        
        assert payload["sub"] == user_id
        assert payload["type"] == "refresh"
        assert "exp" in payload
        
    def test_create_refresh_token_expiration_time(self):
        """Test that refresh token has correct expiration time (days, not minutes)."""
        user_id = "refresh-user-789"
        before_creation = datetime.now(timezone.utc)
        token = create_refresh_token(user_id)
        after_creation = datetime.now(timezone.utc)
        
        payload = jwt.decode(token, options={"verify_signature": False})
        exp_timestamp = payload["exp"]
        exp_datetime = datetime.fromtimestamp(exp_timestamp, tz=timezone.utc)
        
        # Expected expiration should be around refresh_token_expire_days from now
        # Allow a tolerance of 2 seconds for timing precision
        expected_exp_min = before_creation + timedelta(days=settings.refresh_token_expire_days) - timedelta(seconds=2)
        expected_exp_max = after_creation + timedelta(days=settings.refresh_token_expire_days) + timedelta(seconds=2)
        
        assert expected_exp_min <= exp_datetime <= expected_exp_max
        
    def test_access_and_refresh_tokens_are_different(self):
        """Test that access and refresh tokens are different for same user."""
        user_id = "same-user-123"
        access_token = create_access_token(user_id)
        refresh_token = create_refresh_token(user_id)
        
        assert access_token != refresh_token


class TestJWTTokenValidation:
    """Test JWT token validation functions."""
    
    def test_decode_valid_access_token(self):
        """Test that decode_token successfully decodes a valid access token."""
        user_id = "valid-user-123"
        token = create_access_token(user_id)
        
        payload = decode_token(token)
        
        assert payload is not None
        assert payload["sub"] == user_id
        assert payload["type"] == "access"
        
    def test_decode_valid_refresh_token(self):
        """Test that decode_token successfully decodes a valid refresh token."""
        user_id = "valid-refresh-user-123"
        token = create_refresh_token(user_id)
        
        payload = decode_token(token)
        
        assert payload is not None
        assert payload["sub"] == user_id
        assert payload["type"] == "refresh"
        
    def test_decode_invalid_token_raises_error(self):
        """Test that decode_token raises ValueError for invalid token."""
        invalid_token = "invalid.token.here"
        
        with pytest.raises(ValueError, match="Invalid token"):
            decode_token(invalid_token)
            
    def test_decode_malformed_token_raises_error(self):
        """Test that decode_token raises ValueError for malformed token."""
        malformed_token = "not-a-jwt-token"
        
        with pytest.raises(ValueError, match="Invalid token"):
            decode_token(malformed_token)
            
    def test_decode_expired_token_raises_error(self):
        """Test that decode_token raises ValueError for expired token."""
        user_id = "expired-user-123"
        # Create a token that expired 1 hour ago
        past_time = datetime.now(timezone.utc) - timedelta(hours=1)
        payload = {"sub": user_id, "exp": past_time, "type": "access"}
        expired_token = jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)
        
        with pytest.raises(ValueError, match="Token has expired"):
            decode_token(expired_token)
            
    def test_decode_token_with_wrong_secret_raises_error(self):
        """Test that token signed with different secret fails validation."""
        user_id = "wrong-secret-user"
        wrong_secret = "wrong-secret-key-12345678901234567890"
        payload = {
            "sub": user_id,
            "exp": datetime.now(timezone.utc) + timedelta(minutes=30),
            "type": "access"
        }
        wrong_token = jwt.encode(payload, wrong_secret, algorithm=settings.jwt_algorithm)
        
        with pytest.raises(ValueError, match="Invalid token"):
            decode_token(wrong_token)
            
    def test_decode_token_preserves_subject(self):
        """Test that decoded token preserves the original subject."""
        user_ids = ["user-1", "user-2", "user-with-uuid-123e4567-e89b-12d3"]
        
        for user_id in user_ids:
            token = create_access_token(user_id)
            payload = decode_token(token)
            assert payload["sub"] == user_id


class TestPasswordHashing:
    """Test password hashing and verification functions."""
    
    def test_hash_password_returns_different_hash(self):
        """Test that hashing the same password twice returns different hashes."""
        password = "test-password-123"
        hash1 = hash_password(password)
        hash2 = hash_password(password)
        
        # Bcrypt includes salt, so hashes should be different
        assert hash1 != hash2
        assert isinstance(hash1, str)
        assert isinstance(hash2, str)
        
    def test_verify_password_with_correct_password(self):
        """Test that verify_password returns True for correct password."""
        password = "correct-password-456"
        password_hash = hash_password(password)
        
        assert verify_password(password, password_hash) is True
        
    def test_verify_password_with_incorrect_password(self):
        """Test that verify_password returns False for incorrect password."""
        correct_password = "correct-password-789"
        wrong_password = "wrong-password-789"
        password_hash = hash_password(correct_password)
        
        assert verify_password(wrong_password, password_hash) is False
        
    def test_password_hash_format(self):
        """Test that password hash has expected bcrypt format."""
        password = "test-password-format"
        password_hash = hash_password(password)
        
        # Bcrypt hashes start with $2b$ (Python bcrypt)
        assert password_hash.startswith("$2b$")
        
    def test_verify_password_case_sensitive(self):
        """Test that password verification is case-sensitive."""
        password = "CaseSensitive123"
        password_hash = hash_password(password)
        
        assert verify_password(password, password_hash) is True
        assert verify_password(password.lower(), password_hash) is False
        assert verify_password(password.upper(), password_hash) is False
        
    def test_hash_empty_password(self):
        """Test that empty password can be hashed and verified."""
        empty_password = ""
        password_hash = hash_password(empty_password)
        
        assert isinstance(password_hash, str)
        assert len(password_hash) > 0
        assert verify_password(empty_password, password_hash) is True
        assert verify_password("not-empty", password_hash) is False
        
    def test_hash_password_with_special_characters(self):
        """Test that passwords with special characters are handled correctly."""
        special_passwords = [
            "p@ssw0rd!#$%",
            "pass<>word&*()",
            "пароль123",  # Cyrillic
            "密码123",  # Chinese
            "🔒secure🔑",  # Emojis
            "tab\there",  # Tab character
            "new\nline",  # Newline character
        ]
        
        for password in special_passwords:
            password_hash = hash_password(password)
            assert verify_password(password, password_hash) is True
            assert verify_password(password + "x", password_hash) is False
            
    def test_hash_very_long_password(self):
        """Test that very long passwords are handled correctly.
        
        Note: bcrypt has a 72-byte limit. Passwords longer than this
        are truncated, which is standard bcrypt behavior.
        """
        # Test with a 50-character password (well within bcrypt's 72-byte limit)
        long_password = "a" * 50
        password_hash = hash_password(long_password)
        
        assert verify_password(long_password, password_hash) is True
        # Removing one character should make it different
        assert verify_password(long_password[:-1], password_hash) is False
        
        # Test that extremely long passwords (>72 bytes) are truncated by bcrypt
        # This is expected behavior - bcrypt only uses first 72 bytes
        very_long_password = "b" * 1000
        very_long_hash = hash_password(very_long_password)
        
        # Password should verify correctly
        assert verify_password(very_long_password, very_long_hash) is True
        # Due to bcrypt's 72-byte limit, truncated versions at 72 chars will also match
        truncated_password = "b" * 72
        assert verify_password(truncated_password, very_long_hash) is True
        
    def test_password_with_whitespace(self):
        """Test that whitespace in passwords is preserved."""
        passwords_with_whitespace = [
            " leading-space",
            "trailing-space ",
            "  multiple  spaces  ",
            "space in middle",
            "\tleading-tab",
            "trailing-newline\n",
        ]
        
        for password in passwords_with_whitespace:
            password_hash = hash_password(password)
            # Exact match should work
            assert verify_password(password, password_hash) is True
            # Stripped version should NOT work (whitespace is significant)
            if password != password.strip():
                assert verify_password(password.strip(), password_hash) is False
                
    def test_password_only_whitespace(self):
        """Test that password consisting only of whitespace works."""
        whitespace_passwords = [
            " ",
            "  ",
            "\t",
            "\n",
            "   \t\n   ",
        ]
        
        for password in whitespace_passwords:
            password_hash = hash_password(password)
            assert verify_password(password, password_hash) is True
            assert verify_password("", password_hash) is False


class TestJWTIntegration:
    """Integration tests for JWT token lifecycle."""
    
    def test_complete_token_lifecycle(self):
        """Test creating, decoding, and validating a token in sequence."""
        user_id = "lifecycle-user-123"
        
        # Create token
        token = create_access_token(user_id)
        assert token is not None
        
        # Decode and validate
        payload = decode_token(token)
        assert payload["sub"] == user_id
        assert payload["type"] == "access"
        
        # Token should be valid immediately after creation
        exp_timestamp = payload["exp"]
        exp_datetime = datetime.fromtimestamp(exp_timestamp, tz=timezone.utc)
        now = datetime.now(timezone.utc)
        assert exp_datetime > now
        
    def test_access_and_refresh_token_distinction(self):
        """Test that access and refresh tokens can be distinguished."""
        user_id = "distinction-user-123"
        
        access_token = create_access_token(user_id)
        refresh_token = create_refresh_token(user_id)
        
        access_payload = decode_token(access_token)
        refresh_payload = decode_token(refresh_token)
        
        assert access_payload["type"] == "access"
        assert refresh_payload["type"] == "refresh"
        assert access_payload["sub"] == refresh_payload["sub"] == user_id
        
    def test_token_for_different_users(self):
        """Test that tokens for different users have different subjects."""
        user_id_1 = "user-one-123"
        user_id_2 = "user-two-456"
        
        token_1 = create_access_token(user_id_1)
        token_2 = create_access_token(user_id_2)
        
        payload_1 = decode_token(token_1)
        payload_2 = decode_token(token_2)
        
        assert payload_1["sub"] == user_id_1
        assert payload_2["sub"] == user_id_2
        assert token_1 != token_2


if __name__ == "__main__":
    # Run tests with pytest
    pytest.main([__file__, "-v", "--tb=short"])
