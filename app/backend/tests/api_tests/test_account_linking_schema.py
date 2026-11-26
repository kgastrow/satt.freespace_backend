"""The SSO link endpoint must expose the SHARED request schema.

``src/api/account_linking.py`` used to declare a local
``ConfirmLinkRequestWithProof(ConfirmLinkRequest)`` subclass purely to bolt the
``password`` field on, because ``src/serialisers/auth.py`` was owned by another
change at the time. FastAPI names OpenAPI schemas after the Python class, so
that private subclass name leaked straight into the published API contract and
into the frontend's generated TypeScript types - a client-visible artefact of an
internal merge conflict.

``password`` now lives on ``ConfirmLinkRequest`` itself. These tests pin the
contract so the workaround cannot come back:

* the endpoint's request body references ``ConfirmLinkRequest``;
* no schema named after the old subclass exists anywhere in the document;
* the shared model still carries ``password`` and still forbids extras;
* the password proof still actually works end to end.
"""

from datetime import datetime, timedelta, timezone
import secrets

import fakeredis.aioredis
from httpx import AsyncClient
import jwt
import pytest
import pytest_asyncio

from src.core.config import settings
from src.core.security import hash_password
from src.models.user import User
from src.serialisers.auth import ConfirmLinkRequest
from src.services.cache import cache_service


PASSWORD = "SharedSchema123!"

LINK_PATH = "/api/v1/auth/sso/link"
SHARED_SCHEMA_NAME = "ConfirmLinkRequest"
RETIRED_SCHEMA_NAME = "ConfirmLinkRequestWithProof"


# ============================================================================
# FIXTURES / HELPERS
# ============================================================================


@pytest_asyncio.fixture
async def nonce_store():
    """The link nonce guard fails closed, so the happy path needs a store."""
    previous = cache_service._redis
    fake = fakeredis.aioredis.FakeRedis(decode_responses=True)
    cache_service._redis = fake
    try:
        yield fake
    finally:
        cache_service._redis = previous
        await fake.aclose()


def _openapi() -> dict:
    from main import app

    # Cached between tests by FastAPI; rebuild so we always read the live app.
    app.openapi_schema = None
    return app.openapi()


def _link_token(user_id, org_id, nonce: str) -> str:
    return jwt.encode(
        {
            "user_id": str(user_id),
            "provider": "google",
            "provider_user_id": "google-schema-1",
            "provider_email": "schema_link@example.com",
            "org_id": str(org_id),
            "nonce": nonce,
            "purpose": "sso_link",
            "exp": datetime.now(timezone.utc) + timedelta(minutes=5),
        },
        settings.JWT_SECRET,
        algorithm="HS256",
    )


@pytest_asyncio.fixture
async def link_user(async_session, test_organization):
    user = User(
        email="schema_link@example.com",
        password=hash_password(PASSWORD),
        email_verified=True,
        organization_id=test_organization.id,
    )
    async_session.add(user)
    await async_session.commit()
    await async_session.refresh(user)
    return user


# ============================================================================
# SCHEMA NAME
# ============================================================================


def test_link_endpoint_request_body_references_shared_schema():
    """The published contract must name the shared serialiser, not a subclass."""
    schema = _openapi()

    body = schema["paths"][LINK_PATH]["post"]["requestBody"]
    ref = body["content"]["application/json"]["schema"]["$ref"]

    assert ref == f"#/components/schemas/{SHARED_SCHEMA_NAME}", ref


def test_retired_subclass_name_appears_nowhere_in_the_contract():
    """A regression here means the local subclass workaround has come back."""
    schema = _openapi()

    assert RETIRED_SCHEMA_NAME not in schema["components"]["schemas"]

    import json

    assert RETIRED_SCHEMA_NAME not in json.dumps(schema)


def test_shared_schema_documents_the_password_proof():
    """``password`` must be an optional, documented field of the shared model."""
    schema = _openapi()
    model = schema["components"]["schemas"][SHARED_SCHEMA_NAME]

    assert "password" in model["properties"]
    assert "password" not in model.get("required", [])
    assert "link_token" in model["required"]

    description = model["properties"]["password"].get("description", "")
    assert description, "the password proof must be documented for API consumers"


def test_account_linking_module_no_longer_defines_a_local_subclass():
    import src.api.account_linking as account_linking

    assert not hasattr(account_linking, RETIRED_SCHEMA_NAME)


# ============================================================================
# MODEL BEHAVIOUR
# ============================================================================


def test_shared_model_accepts_password_and_defaults_it_to_none():
    assert ConfirmLinkRequest(link_token="t").password is None
    assert ConfirmLinkRequest(link_token="t", password="pw").password == "pw"


def test_shared_model_still_forbids_unknown_fields():
    """``extra="forbid"`` was the reason the subclass existed; keep it."""
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        ConfirmLinkRequest(link_token="t", passwrd="typo")


# ============================================================================
# END TO END: the password proof still works through the shared model
# ============================================================================


@pytest.mark.asyncio
async def test_link_still_accepts_a_password_proof(
    client: AsyncClient, test_organization, link_user, nonce_store
):
    nonce = secrets.token_urlsafe(16)
    await nonce_store.setex(f"sso_link:{nonce}", 300, str(link_user.id))
    token = _link_token(link_user.id, test_organization.id, nonce)

    response = await client.post(
        LINK_PATH, json={"link_token": token, "password": PASSWORD}
    )

    assert response.status_code == 200, response.text
    assert "access_token" in response.json()


@pytest.mark.asyncio
async def test_link_rejects_an_unknown_body_field(
    client: AsyncClient, test_organization, link_user, nonce_store
):
    """The shared model's ``extra="forbid"`` still applies at the endpoint."""
    nonce = secrets.token_urlsafe(16)
    await nonce_store.setex(f"sso_link:{nonce}", 300, str(link_user.id))
    token = _link_token(link_user.id, test_organization.id, nonce)

    response = await client.post(
        LINK_PATH,
        json={"link_token": token, "password": PASSWORD, "unexpected": "x"},
    )

    assert response.status_code == 422, response.text
    # A refused request must not have burned the single-use token.
    assert await nonce_store.get(f"sso_link:{nonce}") == str(link_user.id)
