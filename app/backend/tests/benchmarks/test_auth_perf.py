"""
Authentication micro-benchmarks: password hashing and JWT encode/decode.
"""

import uuid

import pytest

from src.core.security import (
    create_access_token,
    decode_token,
    hash_password,
    verify_password,
)


@pytest.mark.benchmark(group="auth")
def test_password_hash_time(benchmark):
    """bcrypt hash should take 100-300ms (tuned rounds)."""
    benchmark(hash_password, "test-password-123!")


@pytest.mark.benchmark(group="auth")
def test_password_verify_time(benchmark):
    """bcrypt verify should take roughly the same as hashing."""
    hashed = hash_password("test-password-123!")
    benchmark(verify_password, "test-password-123!", hashed)


@pytest.mark.benchmark(group="auth")
def test_jwt_encode_decode(benchmark):
    """JWT round-trip (encode + decode) should complete in < 5ms."""
    user_id = str(uuid.uuid4())
    org_id = str(uuid.uuid4())

    def run():
        token = create_access_token(user_id=user_id, organization_id=org_id)
        decode_token(token)

    benchmark(run)


@pytest.mark.benchmark(group="auth")
def test_jwt_encode_only(benchmark):
    """JWT encode alone."""
    user_id = str(uuid.uuid4())
    org_id = str(uuid.uuid4())
    benchmark(create_access_token, user_id=user_id, organization_id=org_id)


@pytest.mark.benchmark(group="auth")
def test_jwt_decode_only(benchmark):
    """JWT decode alone."""
    user_id = str(uuid.uuid4())
    org_id = str(uuid.uuid4())
    token = create_access_token(user_id=user_id, organization_id=org_id)
    benchmark(decode_token, token)
