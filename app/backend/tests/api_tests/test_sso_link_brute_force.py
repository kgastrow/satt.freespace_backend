"""Brute-force limits on the ``POST /auth/sso/link`` password proof.

The proof requirement stopped a link token being enough on its own, but it put
``verify_password`` behind nothing more than ``RATE_LIMIT_DEFAULT`` (100/min).
``/auth/login`` guards the same primitive with ``RATE_LIMIT_LOGIN`` plus a
5-failure IP block plus a 5-failure account lockout; this endpoint had neither.

Worse, the single-use nonce is burned only AFTER the proof succeeds - correct
for UX, since a mistyped password must not cost the user their link token - so
a wrong guess was entirely free. That made the endpoint a ~500-guess-per-token
password oracle, and a fresh token is one OAuth round-trip away.

These tests pin the fix:

* a rejected password now answers 403 ``auth.invalid_password`` so it is
  distinguishable from the 401 ``sso.link_proof_required`` "you sent no proof";
* guesses are capped per link token and per target account, not only per IP
  (the IP is attacker-chosen in the general case);
* hitting a cap REFUSES further attempts - it does not burn the nonce and does
  not lock the account out of ``/auth/login``;
* the bearer-session proof is deliberately exempt, so an attacker who can mint
  link tokens for a victim cannot use the cap to stop that victim linking;
* with no Redis the endpoint refuses outright instead of grading the guess.
"""

from datetime import datetime, timedelta, timezone
import secrets

import fakeredis.aioredis
from httpx import AsyncClient
import jwt
import pytest
import pytest_asyncio

from src.api.account_linking import (
    LINK_PROOF_ACCOUNT_MAX_ATTEMPTS,
    LINK_PROOF_ACCOUNT_WINDOW_SECONDS,
    LINK_PROOF_TOKEN_MAX_ATTEMPTS,
    LINK_PROOF_TOKEN_WINDOW_SECONDS,
    _link_account_attempt_key,
    _link_token_attempt_key,
)
from src.core.config import settings
from src.core.security import create_access_token, hash_password
from src.models.user import User
from src.services.brute_force_detector import brute_force_detector
from src.services.cache import cache_service


PASSWORD = "LinkBruteForce123!"
WRONG_PASSWORD = "NotThePassword123!"
LINK_PATH = "/api/v1/auth/sso/link"


# ============================================================================
# FIXTURES
# ============================================================================


@pytest_asyncio.fixture
async def nonce_store():
    """The nonce guard fails closed, so every request here needs a store."""
    previous = cache_service._redis
    fake = fakeredis.aioredis.FakeRedis(decode_responses=True)
    cache_service._redis = fake
    try:
        yield fake
    finally:
        cache_service._redis = previous
        await fake.aclose()


@pytest_asyncio.fixture
async def no_nonce_store():
    """Redis absent: neither the replay guard nor the throttle can run."""
    previous = cache_service._redis
    cache_service._redis = None
    try:
        yield
    finally:
        cache_service._redis = previous


@pytest_asyncio.fixture
async def attempt_store():
    """Give the shared brute-force detector a store of its own.

    Without one it fails open (its documented behaviour), which is exactly why
    every other test in the suite is unaffected by the counters added here.
    """
    previous_redis = brute_force_detector._redis
    previous_enabled = brute_force_detector._enabled
    fake = fakeredis.aioredis.FakeRedis(decode_responses=True)
    brute_force_detector._redis = fake
    brute_force_detector._enabled = True
    try:
        yield fake
    finally:
        brute_force_detector._redis = previous_redis
        brute_force_detector._enabled = previous_enabled
        await fake.aclose()


@pytest_asyncio.fixture
async def link_user(async_session, test_organization):
    user = User(
        email="bruteforce_link@example.com",
        password=hash_password(PASSWORD),
        email_verified=True,
        organization_id=test_organization.id,
    )
    async_session.add(user)
    await async_session.commit()
    await async_session.refresh(user)
    return user


# ============================================================================
# HELPERS
# ============================================================================


def _link_token(user_id, org_id, nonce: str, *, provider_user_id: str) -> str:
    return jwt.encode(
        {
            "user_id": str(user_id),
            "provider": "google",
            "provider_user_id": provider_user_id,
            "provider_email": "bruteforce_link@example.com",
            "org_id": str(org_id),
            "nonce": nonce,
            "purpose": "sso_link",
            "exp": datetime.now(timezone.utc) + timedelta(minutes=5),
        },
        settings.JWT_SECRET,
        algorithm="HS256",
    )


async def _mint_link(nonce_store, user_id, org_id, *, provider_user_id="google-bf-1"):
    """Register a fresh nonce and return the matching link token."""
    nonce = secrets.token_urlsafe(16)
    await nonce_store.setex(f"sso_link:{nonce}", 300, str(user_id))
    return nonce, _link_token(user_id, org_id, nonce, provider_user_id=provider_user_id)


def _detail_code(response) -> str:
    body = response.json()
    detail = body.get("detail")
    if isinstance(detail, dict):
        return detail.get("detail_code", "")
    return body.get("detail_code", "")


async def _guess(client: AsyncClient, token: str, password: str):
    return await client.post(
        LINK_PATH, json={"link_token": token, "password": password}
    )


# ============================================================================
# 1. The two refusals are now distinguishable by status
# ============================================================================


@pytest.mark.asyncio
async def test_wrong_password_answers_403_not_401(
    client: AsyncClient, test_organization, link_user, nonce_store, attempt_store
):
    """ "Your proof was rejected" must not share a status with "send a proof"."""
    nonce, token = await _mint_link(nonce_store, link_user.id, test_organization.id)

    response = await _guess(client, token, WRONG_PASSWORD)

    assert response.status_code == 403, response.text
    assert _detail_code(response) == "auth.invalid_password"


@pytest.mark.asyncio
async def test_missing_proof_still_answers_401(
    client: AsyncClient, test_organization, link_user, nonce_store, attempt_store
):
    """The companion half: no proof at all stays a 401 with its own code."""
    nonce, token = await _mint_link(nonce_store, link_user.id, test_organization.id)

    response = await client.post(LINK_PATH, json={"link_token": token})

    assert response.status_code == 401, response.text
    assert _detail_code(response) == "sso.link_proof_required"


# ============================================================================
# 2. Per-link-token cap
# ============================================================================


@pytest.mark.asyncio
async def test_guesses_against_one_link_token_are_capped(
    client: AsyncClient, test_organization, link_user, nonce_store, attempt_store
):
    """The oracle: unlimited guesses against a single 5-minute link token."""
    nonce, token = await _mint_link(nonce_store, link_user.id, test_organization.id)

    # Seed the counter to one short of the cap so this test exercises the cap
    # itself rather than the shared per-IP threshold that trips alongside it.
    for _ in range(LINK_PROOF_TOKEN_MAX_ATTEMPTS - 1):
        await brute_force_detector.record_failure(
            _link_token_attempt_key(nonce),
            "sso_link",
            threshold=LINK_PROOF_TOKEN_MAX_ATTEMPTS,
            window_seconds=LINK_PROOF_TOKEN_WINDOW_SECONDS,
        )

    # The last attempt inside the cap is still graded...
    within_cap = await _guess(client, token, WRONG_PASSWORD)
    assert within_cap.status_code == 403
    assert _detail_code(within_cap) == "auth.invalid_password"

    # ...and the next one is refused without reaching verify_password.
    over_cap = await _guess(client, token, WRONG_PASSWORD)
    assert over_cap.status_code == 429, over_cap.text
    assert _detail_code(over_cap) in {
        "sso.link_attempts_exceeded",
        "auth.ip_blocked",
    }


@pytest.mark.asyncio
async def test_capped_token_refuses_even_the_correct_password(
    client: AsyncClient, test_organization, link_user, nonce_store, attempt_store
):
    """Hitting the cap kills the token for guessing, correct answer included."""
    nonce, token = await _mint_link(nonce_store, link_user.id, test_organization.id)

    for _ in range(LINK_PROOF_TOKEN_MAX_ATTEMPTS):
        await brute_force_detector.record_failure(
            _link_token_attempt_key(nonce),
            "sso_link",
            threshold=LINK_PROOF_TOKEN_MAX_ATTEMPTS,
            window_seconds=LINK_PROOF_TOKEN_WINDOW_SECONDS,
        )

    response = await _guess(client, token, PASSWORD)

    assert response.status_code == 429, response.text
    assert _detail_code(response) == "sso.link_attempts_exceeded"


@pytest.mark.asyncio
async def test_hitting_the_cap_does_not_burn_the_nonce(
    client: AsyncClient, test_organization, link_user, nonce_store, attempt_store
):
    """Capping is a refusal, not a destruction: the token is still on record.

    The whole reason ``_consume_link_nonce`` runs after the proof is that a
    mistyped password must not cost the user their token. The throttle must not
    reintroduce that by the back door.
    """
    nonce, token = await _mint_link(nonce_store, link_user.id, test_organization.id)

    for _ in range(LINK_PROOF_TOKEN_MAX_ATTEMPTS + 1):
        await _guess(client, token, WRONG_PASSWORD)

    assert await nonce_store.get(f"sso_link:{nonce}") == str(link_user.id)


@pytest.mark.asyncio
async def test_a_correct_password_clears_the_token_counter(
    client: AsyncClient, test_organization, link_user, nonce_store, attempt_store
):
    """A user who mistypes a few times and then succeeds starts clean again."""
    nonce, token = await _mint_link(nonce_store, link_user.id, test_organization.id)

    for _ in range(LINK_PROOF_TOKEN_MAX_ATTEMPTS - 1):
        assert (await _guess(client, token, WRONG_PASSWORD)).status_code == 403

    accepted = await _guess(client, token, PASSWORD)
    assert accepted.status_code == 200, accepted.text

    assert (
        await brute_force_detector.get_failure_count(
            _link_token_attempt_key(nonce),
            window_seconds=LINK_PROOF_TOKEN_WINDOW_SECONDS,
        )
        == 0
    )
    assert (
        await brute_force_detector.get_failure_count(
            _link_account_attempt_key(str(test_organization.id), str(link_user.id)),
            window_seconds=LINK_PROOF_ACCOUNT_WINDOW_SECONDS,
        )
        == 0
    )


# ============================================================================
# 3. Per-account cap - closes the "mint a fresh token" refresh
# ============================================================================


@pytest.mark.asyncio
async def test_guesses_are_capped_across_fresh_link_tokens(
    client: AsyncClient, test_organization, link_user, nonce_store, attempt_store
):
    """A new OAuth round-trip must not hand the attacker a new guess budget."""
    account_key = _link_account_attempt_key(
        str(test_organization.id), str(link_user.id)
    )
    for _ in range(LINK_PROOF_ACCOUNT_MAX_ATTEMPTS):
        await brute_force_detector.record_failure(
            account_key,
            "sso_link",
            threshold=LINK_PROOF_ACCOUNT_MAX_ATTEMPTS,
            window_seconds=LINK_PROOF_ACCOUNT_WINDOW_SECONDS,
        )

    # A brand new token, with an untouched per-token counter, is still refused.
    _, fresh_token = await _mint_link(
        nonce_store, link_user.id, test_organization.id, provider_user_id="google-bf-2"
    )
    response = await _guess(client, fresh_token, WRONG_PASSWORD)

    assert response.status_code == 429, response.text
    assert _detail_code(response) == "sso.link_attempts_exceeded"


# ============================================================================
# 4. The cap must not become a denial of service against the victim
# ============================================================================


@pytest.mark.asyncio
async def test_account_cap_does_not_block_the_session_proof(
    client: AsyncClient, test_organization, link_user, nonce_store, attempt_store
):
    """The signed-in path stays open, so linking is never fully denied.

    Anyone who can register a provider account on the victim's address can mint
    link tokens for them and burn the account counter. Because the counter is
    checked only on the guessable (password) branch, the victim can still sign
    in normally and complete the link from inside the app.
    """
    account_key = _link_account_attempt_key(
        str(test_organization.id), str(link_user.id)
    )
    for _ in range(LINK_PROOF_ACCOUNT_MAX_ATTEMPTS * 2):
        await brute_force_detector.record_failure(
            account_key,
            "sso_link",
            threshold=LINK_PROOF_ACCOUNT_MAX_ATTEMPTS,
            window_seconds=LINK_PROOF_ACCOUNT_WINDOW_SECONDS,
        )

    _, token = await _mint_link(
        nonce_store, link_user.id, test_organization.id, provider_user_id="google-bf-3"
    )
    bearer = create_access_token(
        user_id=str(link_user.id), organization_id=str(test_organization.id)
    )

    response = await client.post(
        LINK_PATH,
        json={"link_token": token},
        headers={"Authorization": f"Bearer {bearer}"},
    )

    assert response.status_code == 200, response.text


@pytest.mark.asyncio
async def test_link_cap_does_not_lock_the_account_out_of_login(
    client: AsyncClient, test_organization, link_user, nonce_store, attempt_store
):
    """Capping linking must not become an account lockout on /auth/login."""
    _, token = await _mint_link(nonce_store, link_user.id, test_organization.id)
    for _ in range(LINK_PROOF_TOKEN_MAX_ATTEMPTS + 1):
        await _guess(client, token, WRONG_PASSWORD)

    assert not await brute_force_detector.is_account_locked(
        link_user.email, test_organization.slug
    )


# ============================================================================
# 5. No Redis: refuse rather than grade the guess
# ============================================================================


@pytest.mark.asyncio
async def test_wrong_password_without_redis_is_503_not_an_oracle(
    client: AsyncClient, test_organization, link_user, no_nonce_store
):
    """With the store gone the throttle cannot run, so nothing may be graded.

    Before this check the replay guard's 503 fired only AFTER the proof, so a
    Redis-less deployment still answered "wrong password" (401) vs "correct
    password" (503) - a free oracle at the worst possible moment.
    """
    token = _link_token(
        link_user.id,
        test_organization.id,
        secrets.token_urlsafe(16),
        provider_user_id="google-bf-4",
    )

    wrong = await _guess(client, token, WRONG_PASSWORD)
    right = await _guess(client, token, PASSWORD)

    assert wrong.status_code == 503, wrong.text
    assert _detail_code(wrong) == "sso.link_verification_unavailable"
    # Indistinguishable from the correct password: no signal leaks.
    assert right.status_code == wrong.status_code
    assert _detail_code(right) == _detail_code(wrong)
