"""JWT clock-skew policy (``iat``) regression tests.

PyJWT >= 2.10 validates ``iat`` with zero tolerance and raises
``ImmatureSignatureError`` for a token issued "in the future". Every decode site
in this codebase maps that to "invalid token", so a host whose clock is a second
behind the minting host 401s every live session.

These tests pin the fix in both directions:

* a token whose ``iat`` is slightly in the future still validates, and
* an EXPIRED token is still rejected -- proving the fix did not extend any
  token's lifetime (which a blanket ``leeway=`` would have done).
"""

from datetime import datetime, timedelta, timezone

import jwt
import pytest

from src.core.config import settings
from src.core.security import (
    JWT_DECODE_OPTIONS,
    decode_token,
    get_token_expiry,
    jwt_decode_options,
)


def _mint(**claims) -> str:
    payload = {
        "user_id": "user-1",
        "organization_id": "org-1",
        "type": "access",
        **claims,
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


# ==================== jwt_decode_options helper ====================


def test_shared_policy_disables_iat_verification():
    assert JWT_DECODE_OPTIONS == {"verify_iat": False}


def test_helper_returns_a_fresh_dict_each_call():
    """Callers must not be able to mutate the shared policy."""
    first = jwt_decode_options()
    first["verify_exp"] = False
    first["verify_iat"] = True

    second = jwt_decode_options()
    assert second == {"verify_iat": False}
    assert JWT_DECODE_OPTIONS == {"verify_iat": False}
    assert second is not JWT_DECODE_OPTIONS


def test_helper_merges_overrides_without_dropping_the_policy():
    """get_token_expiry-style callers keep their options AND get the policy."""
    options = jwt_decode_options(verify_signature=False, verify_exp=False)
    assert options == {
        "verify_iat": False,
        "verify_signature": False,
        "verify_exp": False,
    }


def test_helper_override_of_the_policy_itself_wins():
    assert jwt_decode_options(verify_iat=True) == {"verify_iat": True}


# ==================== the actual skew failure ====================


def test_raw_pyjwt_rejects_a_future_iat():
    """Guard on the premise: without the fix this token is rejected."""
    now = datetime.now(timezone.utc)
    token = _mint(iat=now + timedelta(seconds=30), exp=now + timedelta(hours=1))

    with pytest.raises(jwt.ImmatureSignatureError):
        jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])


def test_decode_token_accepts_a_future_iat():
    """A clock step / multi-host skew must not invalidate a live token."""
    now = datetime.now(timezone.utc)
    token = _mint(iat=now + timedelta(seconds=30), exp=now + timedelta(hours=1))

    claims = decode_token(token)
    assert claims["user_id"] == "user-1"


def test_decode_token_accepts_a_wildly_future_iat():
    """The check is disabled, not widened -- magnitude is irrelevant."""
    now = datetime.now(timezone.utc)
    token = _mint(iat=now + timedelta(days=1), exp=now + timedelta(hours=1))

    assert decode_token(token)["organization_id"] == "org-1"


# ==================== lifetime must be unchanged ====================


def test_decode_token_still_rejects_an_expired_token():
    """Proves the fix did not extend token lifetime (no blanket leeway)."""
    now = datetime.now(timezone.utc)
    token = _mint(iat=now - timedelta(hours=2), exp=now - timedelta(seconds=1))

    with pytest.raises(ValueError, match="expired"):
        decode_token(token)


def test_decode_token_rejects_a_token_expired_by_one_second():
    """A leeway=N fix would have accepted this for N seconds. It must not."""
    now = datetime.now(timezone.utc)
    token = _mint(iat=now, exp=now - timedelta(seconds=1))

    with pytest.raises(ValueError, match="expired"):
        decode_token(token)


def test_decode_token_still_honours_nbf():
    """``nbf`` genuinely means "not valid before" and must stay strict."""
    now = datetime.now(timezone.utc)
    token = _mint(
        iat=now,
        nbf=now + timedelta(minutes=5),
        exp=now + timedelta(hours=1),
    )

    with pytest.raises(ValueError, match="Invalid token"):
        decode_token(token)


def test_decode_token_still_rejects_a_bad_signature():
    now = datetime.now(timezone.utc)
    token = jwt.encode(
        {"user_id": "u", "exp": now + timedelta(hours=1)},
        "not-the-real-secret",
        algorithm="HS256",
    )

    with pytest.raises(ValueError, match="Invalid token"):
        decode_token(token)


# ==================== get_token_expiry keeps verify_signature=False ==========


def test_get_token_expiry_still_reads_a_foreign_token():
    """Merging the policy must not have dropped verify_signature=False."""
    now = datetime.now(timezone.utc)
    expiry = now + timedelta(hours=1)
    foreign = jwt.encode(
        {"user_id": "u", "exp": expiry, "iat": now},
        "a-completely-different-secret",
        algorithm="HS256",
    )

    assert get_token_expiry(foreign) == int(expiry.timestamp())


def test_get_token_expiry_reads_an_expired_token():
    now = datetime.now(timezone.utc)
    expiry = now - timedelta(hours=1)
    token = _mint(iat=now - timedelta(hours=2), exp=expiry)

    assert get_token_expiry(token) == int(expiry.timestamp())


def test_get_token_expiry_reads_a_future_iat_token():
    now = datetime.now(timezone.utc)
    expiry = now + timedelta(hours=1)
    token = _mint(iat=now + timedelta(minutes=1), exp=expiry)

    assert get_token_expiry(token) == int(expiry.timestamp())


# ==================== file access tokens ====================


def test_decode_file_access_token_accepts_a_future_iat():
    from src.core.security import decode_file_access_token

    now = datetime.now(timezone.utc)
    token = jwt.encode(
        {
            "storage_key": "org/file.png",
            "organization_id": "org-1",
            "type": "file_access",
            "iat": now + timedelta(seconds=30),
            "exp": now + timedelta(hours=1),
        },
        settings.JWT_SECRET,
        algorithm=settings.JWT_ALGORITHM,
    )

    assert decode_file_access_token(token)["storage_key"] == "org/file.png"
