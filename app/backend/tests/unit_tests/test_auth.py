"""
Unit tests for authentication functions.
Tests security utilities and refresh token CRUD operations.
"""

from datetime import datetime, timedelta, timezone

import jwt
import pytest

from src.core.config import settings
from src.core.security import (
    create_access_token,
    decode_token,
    get_token_expiry,
    hash_password,
    verify_password,
)
from src.core.security import (
    create_refresh_token as create_jwt_refresh_token,
)
from src.crud.refresh_token import (
    create_refresh_token,
    delete_all_refresh_tokens_for_user,
    delete_refresh_token,
    get_refresh_token,
)


# ==================== Password Hashing Tests ====================


class TestPasswordHashing:
    """Tests for password hashing and verification."""

    def test_hash_password_returns_hash(self):
        """Test that hash_password returns a bcrypt hash."""
        password = "securepassword123"
        hashed = hash_password(password)

        assert hashed is not None
        assert hashed != password
        assert hashed.startswith("$2b$")  # bcrypt hash prefix

    def test_hash_password_different_for_same_input(self):
        """Test that hashing the same password twice gives different hashes (salted)."""
        password = "securepassword123"
        hash1 = hash_password(password)
        hash2 = hash_password(password)

        assert hash1 != hash2

    def test_verify_password_correct(self):
        """Test that verify_password returns True for correct password."""
        password = "securepassword123"
        hashed = hash_password(password)

        assert verify_password(password, hashed) is True

    def test_verify_password_incorrect(self):
        """Test that verify_password returns False for incorrect password."""
        password = "securepassword123"
        wrong_password = "wrongpassword"
        hashed = hash_password(password)

        assert verify_password(wrong_password, hashed) is False

    def test_verify_password_empty_password(self):
        """Test that verify_password handles empty password."""
        password = "securepassword123"
        hashed = hash_password(password)

        assert verify_password("", hashed) is False


# ==================== JWT Token Tests ====================


class TestJWTTokens:
    """Tests for JWT token creation and decoding."""

    def test_create_access_token(self):
        """Test creating an access token with required claims."""
        user_id = "test-user-id"
        org_id = "test-org-id"

        token = create_access_token(user_id, org_id)

        assert token is not None
        assert isinstance(token, str)

        # Decode and verify claims
        decoded = jwt.decode(
            token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM]
        )
        assert decoded["user_id"] == user_id
        assert decoded["organization_id"] == org_id
        assert decoded["type"] == "access"
        assert "exp" in decoded
        assert "iat" in decoded

    def test_create_access_token_with_extra_claims(self):
        """Test creating an access token with extra claims."""
        user_id = "test-user-id"
        org_id = "test-org-id"
        extra = {"email": "test@test.com", "role": "admin"}

        token = create_access_token(user_id, org_id, extra_claims=extra)

        decoded = jwt.decode(
            token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM]
        )
        assert decoded["email"] == "test@test.com"
        assert decoded["role"] == "admin"

    def test_create_refresh_token(self):
        """Test creating a refresh token."""
        user_id = "test-user-id"
        org_id = "test-org-id"

        token = create_jwt_refresh_token(user_id, org_id)

        assert token is not None

        decoded = jwt.decode(
            token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM]
        )
        assert decoded["user_id"] == user_id
        assert decoded["organization_id"] == org_id
        assert decoded["type"] == "refresh"

    def test_decode_token_valid(self):
        """Test decoding a valid token."""
        user_id = "test-user-id"
        org_id = "test-org-id"

        token = create_access_token(user_id, org_id)
        decoded = decode_token(token)

        assert decoded["user_id"] == user_id
        assert decoded["organization_id"] == org_id

    def test_decode_token_expired(self):
        """Test decoding an expired token raises ValueError."""
        # Create an already expired token
        payload = {
            "user_id": "test-user-id",
            "organization_id": "test-org-id",
            "exp": datetime.now(timezone.utc) - timedelta(hours=1),
            "iat": datetime.now(timezone.utc) - timedelta(hours=2),
        }
        token = jwt.encode(
            payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM
        )

        with pytest.raises(ValueError, match="expired"):
            decode_token(token)

    def test_decode_token_invalid(self):
        """Test decoding an invalid token raises ValueError."""
        with pytest.raises(ValueError, match="Invalid token"):
            decode_token("invalid.token.here")

    def test_decode_token_wrong_secret(self):
        """Test decoding a token with wrong secret raises ValueError."""
        payload = {
            "user_id": "test-user-id",
            "exp": datetime.now(timezone.utc) + timedelta(hours=1),
        }
        token = jwt.encode(payload, "wrong-secret", algorithm="HS256")

        with pytest.raises(ValueError, match="Invalid token"):
            decode_token(token)

    def test_get_token_expiry(self):
        """Test getting token expiry timestamp."""
        user_id = "test-user-id"
        org_id = "test-org-id"

        token = create_access_token(user_id, org_id)
        expiry = get_token_expiry(token)

        assert expiry is not None
        assert isinstance(expiry, int)
        assert expiry > int(datetime.now(timezone.utc).timestamp())

    def test_get_token_expiry_invalid_token(self):
        """Test getting expiry from invalid token returns None."""
        expiry = get_token_expiry("invalid.token")
        assert expiry is None


# ==================== Refresh Token CRUD Tests ====================


@pytest.mark.asyncio
async def test_create_refresh_token_crud(async_session, test_user, test_organization):
    """Test creating a refresh token in the database."""
    org_id = str(test_organization.id)

    token = await create_refresh_token(async_session, test_user.id, org_id)

    assert token is not None
    assert isinstance(token, str)
    assert len(token) == 36  # UUID format


@pytest.mark.asyncio
async def test_get_refresh_token_valid(async_session, test_user, test_organization):
    """Test getting a valid refresh token."""
    org_id = str(test_organization.id)

    token_str = await create_refresh_token(async_session, test_user.id, org_id)

    stored_token = await get_refresh_token(async_session, token_str)

    assert stored_token is not None
    assert stored_token.token == token_str
    assert str(stored_token.user_id) == str(test_user.id)
    assert str(stored_token.organization_id) == org_id


@pytest.mark.asyncio
async def test_get_refresh_token_with_org_filter(
    async_session, test_user, test_organization
):
    """Test getting a refresh token with organization filter."""
    org_id = str(test_organization.id)

    token_str = await create_refresh_token(async_session, test_user.id, org_id)

    # Should find with correct org
    stored_token = await get_refresh_token(async_session, token_str, org_id)
    assert stored_token is not None

    # Should not find with wrong org
    wrong_org = await get_refresh_token(
        async_session, token_str, "00000000-0000-0000-0000-000000000000"
    )
    assert wrong_org is None


@pytest.mark.asyncio
async def test_get_refresh_token_not_found(async_session):
    """Test getting a non-existent refresh token."""
    stored_token = await get_refresh_token(async_session, "non-existent-token")
    assert stored_token is None


@pytest.mark.asyncio
async def test_delete_refresh_token(async_session, test_user, test_organization):
    """Test deleting a refresh token."""
    org_id = str(test_organization.id)

    token_str = await create_refresh_token(async_session, test_user.id, org_id)

    # Verify it exists
    stored = await get_refresh_token(async_session, token_str)
    assert stored is not None

    # Delete it
    result = await delete_refresh_token(async_session, token_str, org_id)
    assert result is True

    # Verify it's deleted (soft delete)
    stored_after = await get_refresh_token(async_session, token_str)
    assert stored_after is None


@pytest.mark.asyncio
async def test_delete_refresh_token_not_found(async_session, test_organization):
    """Test deleting a non-existent refresh token."""
    org_id = str(test_organization.id)

    result = await delete_refresh_token(async_session, "non-existent-token", org_id)
    assert result is False


@pytest.mark.asyncio
async def test_delete_all_refresh_tokens_for_user(
    async_session, test_user, test_organization
):
    """Test deleting all refresh tokens for a user."""
    org_id = str(test_organization.id)

    # Create multiple tokens
    token1 = await create_refresh_token(async_session, test_user.id, org_id)
    token2 = await create_refresh_token(async_session, test_user.id, org_id)
    token3 = await create_refresh_token(async_session, test_user.id, org_id)

    # Verify they exist
    assert await get_refresh_token(async_session, token1) is not None
    assert await get_refresh_token(async_session, token2) is not None
    assert await get_refresh_token(async_session, token3) is not None

    # Delete all
    await delete_all_refresh_tokens_for_user(async_session, str(test_user.id), org_id)

    # Verify all are deleted
    assert await get_refresh_token(async_session, token1) is None
    assert await get_refresh_token(async_session, token2) is None
    assert await get_refresh_token(async_session, token3) is None


@pytest.mark.asyncio
async def test_refresh_token_isolation_between_orgs(
    async_session, test_user, test_organization, second_organization
):
    """Test that refresh tokens are isolated between organizations."""
    org1_id = str(test_organization.id)
    org2_id = str(second_organization.id)

    # Create token for org1
    token1 = await create_refresh_token(async_session, test_user.id, org1_id)

    # Should find with org1
    stored = await get_refresh_token(async_session, token1, org1_id)
    assert stored is not None

    # Should not find with org2
    stored_wrong_org = await get_refresh_token(async_session, token1, org2_id)
    assert stored_wrong_org is None

    # Delete should fail with wrong org
    result = await delete_refresh_token(async_session, token1, org2_id)
    assert result is False

    # Token should still exist
    stored_still = await get_refresh_token(async_session, token1, org1_id)
    assert stored_still is not None
