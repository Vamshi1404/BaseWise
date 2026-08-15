"""
Unit tests to verify auth logging functionality.
Tests that authentication failures are properly logged.
"""
import os
import sys
import pytest
import logging
from unittest.mock import AsyncMock, patch, MagicMock
from dotenv import load_dotenv

# Load environment variables from backend/.env
backend_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
dotenv_path = os.path.join(backend_dir, '.env')
load_dotenv(dotenv_path)

# Ensure backend directory is in python path
sys.path.insert(0, backend_dir)

from fastapi import HTTPException
from app.api.auth import login, signup, refresh, get_current_user
from app.schemas.auth import LoginRequest, SignupRequest, RefreshRequest
from app.models.models import User


class TestAuthLogging:
    """Test authentication logging for failures and successes."""
    
    @pytest.mark.asyncio
    async def test_signup_logs_duplicate_email(self, caplog):
        """Test that signup logs warning when email already registered."""
        # Mock existing user
        mock_existing_user = User(
            id="existing-user",
            email="existing@example.com",
            password_hash="$2b$12$mockhashedpassword"
        )
        
        # Mock database session
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_existing_user
        mock_db.execute.return_value = mock_result
        
        # Create signup request
        request = SignupRequest(email="existing@example.com", password="password123")
        
        # Capture logs
        with caplog.at_level(logging.WARNING):
            with pytest.raises(HTTPException):
                await signup(request, mock_db)
        
        # Verify log entry - the logging module uses 'extra' dict which may not appear in caplog.text
        # but we can verify the main message is logged
        assert "Signup failed: email already registered" in caplog.text
        # Note: email is in the 'extra' dict, which may not be in caplog.text
        # The important part is that the warning is logged

