from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models import (
    OrganizationTwoFactorSettings,
    TwoFactorPolicy,
    UserTwoFactor,
    UserTwoFactorBackupCode,
)


@pytest.mark.asyncio
async def test_create_organization_two_factor_settings(
    async_session: AsyncSession, test_organization
):
    """Test creating organization 2FA settings."""
    settings = OrganizationTwoFactorSettings(
        organization_id=test_organization.id,
        two_factor_allowed=True,
        two_factor_policy=TwoFactorPolicy.OPTIONAL.value,
        grace_period_days=7,
    )
    async_session.add(settings)
    await async_session.commit()
    await async_session.refresh(settings)

    assert settings.id is not None
    assert settings.organization_id == test_organization.id
    assert settings.two_factor_allowed is True
    assert settings.two_factor_policy == TwoFactorPolicy.OPTIONAL.value
    assert settings.grace_period_days == 7
    assert settings.enforcement_start_time is None
    assert settings.deleted_time is None


@pytest.mark.asyncio
async def test_organization_two_factor_settings_defaults(
    async_session: AsyncSession, test_organization
):
    """Test default values for organization 2FA settings."""
    settings = OrganizationTwoFactorSettings(
        organization_id=test_organization.id,
    )
    async_session.add(settings)
    await async_session.commit()
    await async_session.refresh(settings)

    assert settings.two_factor_allowed is False
    assert settings.two_factor_policy == TwoFactorPolicy.DISABLED.value
    assert settings.grace_period_days == 7


@pytest.mark.asyncio
async def test_organization_two_factor_settings_relationship(
    async_session: AsyncSession, test_organization
):
    """Test relationship between Organization and OrganizationTwoFactorSettings."""
    settings = OrganizationTwoFactorSettings(
        organization_id=test_organization.id,
        two_factor_allowed=True,
        two_factor_policy=TwoFactorPolicy.MANDATORY.value,
    )
    async_session.add(settings)
    await async_session.commit()

    result = await async_session.execute(
        select(OrganizationTwoFactorSettings).where(
            OrganizationTwoFactorSettings.organization_id == test_organization.id
        )
    )
    retrieved_settings = result.scalars().first()

    assert retrieved_settings is not None
    assert retrieved_settings.two_factor_allowed is True
    assert retrieved_settings.two_factor_policy == TwoFactorPolicy.MANDATORY.value


@pytest.mark.asyncio
async def test_organization_two_factor_settings_unique_per_org(
    async_session: AsyncSession, test_organization
):
    """Test that only one active settings record exists per organization."""
    settings1 = OrganizationTwoFactorSettings(
        organization_id=test_organization.id,
        two_factor_allowed=True,
    )
    async_session.add(settings1)
    await async_session.commit()

    settings2 = OrganizationTwoFactorSettings(
        organization_id=test_organization.id,
        two_factor_allowed=False,
    )
    async_session.add(settings2)

    with pytest.raises(Exception):
        await async_session.commit()


@pytest.mark.asyncio
async def test_create_user_two_factor(
    async_session: AsyncSession, test_organization, test_user
):
    """Test creating user 2FA record."""
    user_2fa = UserTwoFactor(
        user_id=test_user.id,
        organization_id=test_organization.id,
        secret="JBSWY3DPEHPK3PXP",
        is_enabled=False,
    )
    async_session.add(user_2fa)
    await async_session.commit()
    await async_session.refresh(user_2fa)

    assert user_2fa.id is not None
    assert user_2fa.user_id == test_user.id
    assert user_2fa.organization_id == test_organization.id
    assert user_2fa.secret == "JBSWY3DPEHPK3PXP"
    assert user_2fa.is_enabled is False
    assert user_2fa.verified_at is None
    assert user_2fa.deleted_time is None


@pytest.mark.asyncio
async def test_user_two_factor_enable_and_verify(
    async_session: AsyncSession, test_organization, test_user
):
    """Test enabling and verifying user 2FA."""
    user_2fa = UserTwoFactor(
        user_id=test_user.id,
        organization_id=test_organization.id,
        secret="JBSWY3DPEHPK3PXP",
        is_enabled=True,
        verified_at=datetime.now(timezone.utc),
    )
    async_session.add(user_2fa)
    await async_session.commit()
    await async_session.refresh(user_2fa)

    assert user_2fa.is_enabled is True
    assert user_2fa.verified_at is not None


@pytest.mark.asyncio
async def test_user_two_factor_relationships(
    async_session: AsyncSession, test_organization, test_user
):
    """Test relationships between User, Organization, and UserTwoFactor."""
    user_2fa = UserTwoFactor(
        user_id=test_user.id,
        organization_id=test_organization.id,
        secret="JBSWY3DPEHPK3PXP",
        is_enabled=True,
    )
    async_session.add(user_2fa)
    await async_session.commit()

    result = await async_session.execute(
        select(UserTwoFactor).where(UserTwoFactor.user_id == test_user.id)
    )
    retrieved_2fa = result.scalars().first()

    assert retrieved_2fa is not None
    assert retrieved_2fa.secret == "JBSWY3DPEHPK3PXP"

    result = await async_session.execute(
        select(UserTwoFactor).where(
            UserTwoFactor.organization_id == test_organization.id
        )
    )
    org_2fa_records = result.scalars().all()
    assert len(org_2fa_records) > 0


@pytest.mark.asyncio
async def test_user_two_factor_unique_per_user(
    async_session: AsyncSession, test_organization, test_user
):
    """Test that only one active 2FA record exists per user."""
    user_2fa1 = UserTwoFactor(
        user_id=test_user.id,
        organization_id=test_organization.id,
        secret="SECRET1",
        is_enabled=True,
    )
    async_session.add(user_2fa1)
    await async_session.commit()

    user_2fa2 = UserTwoFactor(
        user_id=test_user.id,
        organization_id=test_organization.id,
        secret="SECRET2",
        is_enabled=True,
    )
    async_session.add(user_2fa2)

    with pytest.raises(Exception):
        await async_session.commit()


@pytest.mark.asyncio
async def test_create_backup_code(
    async_session: AsyncSession, test_organization, test_user
):
    """Test creating backup codes."""
    user_2fa = UserTwoFactor(
        user_id=test_user.id,
        organization_id=test_organization.id,
        secret="JBSWY3DPEHPK3PXP",
        is_enabled=True,
    )
    async_session.add(user_2fa)
    await async_session.commit()

    backup_code = UserTwoFactorBackupCode(
        user_two_factor_id=user_2fa.id,
        code="hashed_backup_code_123",
    )
    async_session.add(backup_code)
    await async_session.commit()
    await async_session.refresh(backup_code)

    assert backup_code.id is not None
    assert backup_code.user_two_factor_id == user_2fa.id
    assert backup_code.code == "hashed_backup_code_123"
    assert backup_code.used_at is None
    assert backup_code.deleted_time is None


@pytest.mark.asyncio
async def test_backup_code_mark_as_used(
    async_session: AsyncSession, test_organization, test_user
):
    """Test marking backup code as used."""
    user_2fa = UserTwoFactor(
        user_id=test_user.id,
        organization_id=test_organization.id,
        secret="JBSWY3DPEHPK3PXP",
        is_enabled=True,
    )
    async_session.add(user_2fa)
    await async_session.commit()

    backup_code = UserTwoFactorBackupCode(
        user_two_factor_id=user_2fa.id,
        code="hashed_backup_code_123",
    )
    async_session.add(backup_code)
    await async_session.commit()

    backup_code.used_at = datetime.now(timezone.utc)
    await async_session.commit()
    await async_session.refresh(backup_code)

    assert backup_code.used_at is not None


@pytest.mark.asyncio
async def test_backup_codes_relationship(
    async_session: AsyncSession, test_organization, test_user
):
    """Test relationship between UserTwoFactor and backup codes."""
    user_2fa = UserTwoFactor(
        user_id=test_user.id,
        organization_id=test_organization.id,
        secret="JBSWY3DPEHPK3PXP",
        is_enabled=True,
    )
    async_session.add(user_2fa)
    await async_session.commit()

    backup_codes = [
        UserTwoFactorBackupCode(
            user_two_factor_id=user_2fa.id,
            code=f"hashed_code_{i}",
        )
        for i in range(10)
    ]
    for code in backup_codes:
        async_session.add(code)
    await async_session.commit()

    result = await async_session.execute(
        select(UserTwoFactorBackupCode).where(
            UserTwoFactorBackupCode.user_two_factor_id == user_2fa.id
        )
    )
    retrieved_codes = result.scalars().all()

    assert len(retrieved_codes) == 10


@pytest.mark.asyncio
async def test_multitenancy_isolation(
    async_session: AsyncSession,
    test_organization,
    second_organization,
    test_user,
    second_org_user,
):
    """Test that 2FA settings and user 2FA records are properly isolated by organization."""
    settings1 = OrganizationTwoFactorSettings(
        organization_id=test_organization.id,
        two_factor_allowed=True,
        two_factor_policy=TwoFactorPolicy.MANDATORY.value,
    )
    settings2 = OrganizationTwoFactorSettings(
        organization_id=second_organization.id,
        two_factor_allowed=False,
        two_factor_policy=TwoFactorPolicy.DISABLED.value,
    )
    async_session.add(settings1)
    async_session.add(settings2)
    await async_session.commit()

    user_2fa1 = UserTwoFactor(
        user_id=test_user.id,
        organization_id=test_organization.id,
        secret="SECRET1",
        is_enabled=True,
    )
    user_2fa2 = UserTwoFactor(
        user_id=second_org_user.id,
        organization_id=second_organization.id,
        secret="SECRET2",
        is_enabled=False,
    )
    async_session.add(user_2fa1)
    async_session.add(user_2fa2)
    await async_session.commit()

    result = await async_session.execute(
        select(UserTwoFactor).where(
            UserTwoFactor.organization_id == test_organization.id,
            UserTwoFactor.deleted_time.is_(None),
        )
    )
    org1_2fa_records = result.scalars().all()

    assert len(org1_2fa_records) == 1
    assert org1_2fa_records[0].user_id == test_user.id

    result = await async_session.execute(
        select(UserTwoFactor).where(
            UserTwoFactor.organization_id == second_organization.id,
            UserTwoFactor.deleted_time.is_(None),
        )
    )
    org2_2fa_records = result.scalars().all()

    assert len(org2_2fa_records) == 1
    assert org2_2fa_records[0].user_id == second_org_user.id


@pytest.mark.asyncio
async def test_soft_delete_two_factor(
    async_session: AsyncSession, test_organization, test_user
):
    """Test soft delete for 2FA records."""
    user_2fa = UserTwoFactor(
        user_id=test_user.id,
        organization_id=test_organization.id,
        secret="JBSWY3DPEHPK3PXP",
        is_enabled=True,
    )
    async_session.add(user_2fa)
    await async_session.commit()

    user_2fa.deleted_time = datetime.now(timezone.utc)
    await async_session.commit()

    result = await async_session.execute(
        select(UserTwoFactor).where(
            UserTwoFactor.user_id == test_user.id, UserTwoFactor.deleted_time.is_(None)
        )
    )
    active_2fa = result.scalars().first()

    assert active_2fa is None

    result = await async_session.execute(
        select(UserTwoFactor).where(UserTwoFactor.user_id == test_user.id)
    )
    all_2fa = result.scalars().first()

    assert all_2fa is not None
    assert all_2fa.deleted_time is not None


# ============================================================================
# CRUD TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_crud_get_organization_2fa_settings(
    async_session: AsyncSession, test_organization
):
    """Test getting organization 2FA settings via CRUD."""
    from src.crud.organization_two_factor_settings import get_by_organization_id

    settings = OrganizationTwoFactorSettings(
        organization_id=test_organization.id,
        two_factor_allowed=True,
        two_factor_policy=TwoFactorPolicy.OPTIONAL.value,
    )
    async_session.add(settings)
    await async_session.commit()

    retrieved = await get_by_organization_id(async_session, str(test_organization.id))
    assert retrieved is not None
    assert retrieved.organization_id == test_organization.id
    assert retrieved.two_factor_allowed is True


@pytest.mark.asyncio
async def test_crud_create_organization_2fa_settings(
    async_session: AsyncSession, test_organization
):
    """Test creating organization 2FA settings via CRUD."""
    from src.crud.organization_two_factor_settings import create_settings

    settings = await create_settings(
        async_session,
        {
            "two_factor_allowed": True,
            "two_factor_policy": TwoFactorPolicy.MANDATORY.value,
            "grace_period_days": 10,
        },
        str(test_organization.id),
    )

    assert settings.organization_id == test_organization.id
    assert settings.two_factor_allowed is True
    assert settings.two_factor_policy == TwoFactorPolicy.MANDATORY.value
    assert settings.grace_period_days == 10


@pytest.mark.asyncio
async def test_crud_update_organization_2fa_settings(
    async_session: AsyncSession, test_organization
):
    """Test updating organization 2FA settings via CRUD."""
    from src.crud.organization_two_factor_settings import (
        create_settings,
        update_settings,
    )

    await create_settings(
        async_session,
        {
            "two_factor_allowed": True,
            "two_factor_policy": TwoFactorPolicy.OPTIONAL.value,
        },
        str(test_organization.id),
    )

    updated = await update_settings(
        async_session,
        {"two_factor_policy": TwoFactorPolicy.MANDATORY.value},
        str(test_organization.id),
    )

    assert updated.two_factor_policy == TwoFactorPolicy.MANDATORY.value
    assert updated.enforcement_start_time is not None


@pytest.mark.asyncio
async def test_crud_get_user_2fa(
    async_session: AsyncSession, test_organization, test_user
):
    """Test getting user 2FA via CRUD."""
    from src.crud.user_two_factor import get_by_user_id

    user_2fa = UserTwoFactor(
        user_id=test_user.id,
        organization_id=test_organization.id,
        secret="SECRET123",
        is_enabled=True,
    )
    async_session.add(user_2fa)
    await async_session.commit()

    retrieved = await get_by_user_id(
        async_session, str(test_user.id), str(test_organization.id)
    )
    assert retrieved is not None
    assert retrieved.user_id == test_user.id


@pytest.mark.asyncio
async def test_crud_create_user_2fa(
    async_session: AsyncSession, test_organization, test_user
):
    """Test creating user 2FA via CRUD - secret should be encrypted."""
    from src.crud.user_two_factor import create, get_decrypted_secret

    user_2fa = await create(
        async_session,
        {"user_id": str(test_user.id), "secret": "SECRET123", "is_enabled": False},
        str(test_organization.id),
    )

    assert user_2fa.user_id == test_user.id
    # The stored secret should be encrypted, not plain text
    assert user_2fa.secret != "SECRET123"
    assert user_2fa.secret.startswith("gAAAAA")  # Fernet encrypted prefix
    assert user_2fa.is_enabled is False

    # Verify we can decrypt and get the original secret
    decrypted = await get_decrypted_secret(
        async_session, str(test_user.id), str(test_organization.id)
    )
    assert decrypted == "SECRET123"


@pytest.mark.asyncio
async def test_crud_delete_user_2fa(
    async_session: AsyncSession, test_organization, test_user
):
    """Test soft deleting user 2FA via CRUD."""
    from src.crud.user_two_factor import create, delete

    await create(
        async_session,
        {"user_id": str(test_user.id), "secret": "SECRET123"},
        str(test_organization.id),
    )

    deleted = await delete(async_session, str(test_user.id), str(test_organization.id))
    assert deleted.deleted_time is not None


# ============================================================================
# TWO FACTOR SERVICE TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_two_factor_service_generate_secret():
    """Test generating TOTP secret."""
    from src.services.two_factor import TwoFactorService

    secret = TwoFactorService.generate_secret()
    assert secret is not None
    assert len(secret) == 32  # Base32 encoded
    assert secret.isalnum()
    assert secret.isupper()


@pytest.mark.asyncio
async def test_two_factor_service_generate_provisioning_uri():
    """Test generating provisioning URI for QR code."""
    from urllib.parse import unquote

    from src.services.two_factor import TwoFactorService

    secret = "JBSWY3DPEHPK3PXP"
    email = "test@example.com"
    uri = TwoFactorService.generate_provisioning_uri(secret, email)

    assert uri.startswith("otpauth://totp/")
    # Email may be URL encoded in the URI
    assert email in unquote(uri)
    assert "AYZER" in unquote(uri)
    assert secret in uri


@pytest.mark.asyncio
async def test_two_factor_service_verify_totp():
    """Test TOTP verification."""
    import pyotp

    from src.services.two_factor import TwoFactorService

    secret = "JBSWY3DPEHPK3PXP"
    totp = pyotp.TOTP(secret)
    valid_code = totp.now()

    # Valid code should verify
    assert TwoFactorService.verify_totp(secret, valid_code) is True

    # Invalid code should fail
    assert TwoFactorService.verify_totp(secret, "000000") is False
    assert TwoFactorService.verify_totp(secret, "invalid") is False
    assert TwoFactorService.verify_totp(secret, "") is False


@pytest.mark.asyncio
async def test_two_factor_service_generate_backup_codes():
    """Test generating backup codes."""
    from src.services.two_factor import TwoFactorService

    plain_codes, hashed_codes = TwoFactorService.generate_backup_codes(count=10)

    assert len(plain_codes) == 10
    assert len(hashed_codes) == 10

    # Check plain codes format
    for code in plain_codes:
        assert len(code) == 8
        assert code.isalnum()
        # Use code == code.upper() instead of isupper() because codes can be
        # all digits (e.g., '03214404'), and isupper() returns False for strings
        # with no cased characters. upper() leaves digits unchanged.
        assert code == code.upper()

    # Check hashed codes are different from plain codes
    for i, hashed in enumerate(hashed_codes):
        assert hashed != plain_codes[i]
        assert len(hashed) > 50  # bcrypt hashes are long


@pytest.mark.asyncio
async def test_two_factor_service_verify_backup_code():
    """Test backup code verification."""
    from src.services.two_factor import TwoFactorService

    plain_codes, hashed_codes = TwoFactorService.generate_backup_codes(count=1)
    plain_code = plain_codes[0]
    hashed_code = hashed_codes[0]

    # Valid code should verify
    assert TwoFactorService.verify_backup_code(plain_code, hashed_code) is True

    # Invalid code should fail
    assert TwoFactorService.verify_backup_code("WRONG123", hashed_code) is False


# ============================================================================
# AUTH FLOW TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_login_without_2fa(
    client, async_session: AsyncSession, test_organization, test_user
):
    """Test login flow when user doesn't have 2FA enabled."""
    response = await client.post(
        "/api/v1/auth/login",
        json={
            "email": test_user.email,
            "password": "Password123!",
            "organization_slug": test_organization.slug,
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert "refresh_token" not in data  # Refresh token is in httpOnly cookie
    assert "requires_2fa" not in data


@pytest.mark.asyncio
async def test_login_with_2fa_enabled(
    client, async_session: AsyncSession, test_organization, test_user
):
    """Test login flow when user has 2FA enabled - should return 2FA token."""
    from src.core.encryption import encrypt_field
    from src.models import UserTwoFactor

    # Enable 2FA for user - encrypt the secret before storing
    secret = "JBSWY3DPEHPK3PXP"
    encrypted_secret = encrypt_field(secret)
    user_2fa = UserTwoFactor(
        user_id=test_user.id,
        organization_id=test_organization.id,
        secret=encrypted_secret,
        is_enabled=True,
        verified_at=datetime.now(timezone.utc),
    )
    async_session.add(user_2fa)
    await async_session.commit()

    response = await client.post(
        "/api/v1/auth/login",
        json={
            "email": test_user.email,
            "password": "Password123!",
            "organization_slug": test_organization.slug,
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["requires_2fa"] is True
    assert "two_factor_token" in data
    assert "access_token" not in data


@pytest.mark.asyncio
async def test_verify_2fa_with_totp(
    client, async_session: AsyncSession, test_organization, test_user
):
    """Test 2FA verification with valid TOTP code."""
    import pyotp

    from src.core.encryption import encrypt_field
    from src.models import UserTwoFactor

    secret = "JBSWY3DPEHPK3PXP"

    # Enable 2FA for user - encrypt the secret before storing
    encrypted_secret = encrypt_field(secret)
    user_2fa = UserTwoFactor(
        user_id=test_user.id,
        organization_id=test_organization.id,
        secret=encrypted_secret,
        is_enabled=True,
        verified_at=datetime.now(timezone.utc),
    )
    async_session.add(user_2fa)
    await async_session.commit()

    # First, login to get 2FA token
    login_response = await client.post(
        "/api/v1/auth/login",
        json={
            "email": test_user.email,
            "password": "Password123!",
            "organization_slug": test_organization.slug,
        },
    )
    two_factor_token = login_response.json()["two_factor_token"]

    # Generate valid TOTP code
    totp = pyotp.TOTP(secret)
    valid_code = totp.now()

    # Verify 2FA
    verify_response = await client.post(
        "/api/v1/auth/verify-2fa",
        json={
            "two_factor_token": two_factor_token,
            "code": valid_code,
        },
    )

    assert verify_response.status_code == 200
    data = verify_response.json()
    assert "access_token" in data
    assert "refresh_token" not in data  # Refresh token is in httpOnly cookie


@pytest.mark.asyncio
async def test_verify_2fa_with_invalid_code(
    client, async_session: AsyncSession, test_organization, test_user
):
    """Test 2FA verification with invalid code."""
    from src.core.encryption import encrypt_field
    from src.models import UserTwoFactor

    # Enable 2FA for user - encrypt the secret before storing
    secret = "JBSWY3DPEHPK3PXP"
    encrypted_secret = encrypt_field(secret)
    user_2fa = UserTwoFactor(
        user_id=test_user.id,
        organization_id=test_organization.id,
        secret=encrypted_secret,
        is_enabled=True,
        verified_at=datetime.now(timezone.utc),
    )
    async_session.add(user_2fa)
    await async_session.commit()

    # First, login to get 2FA token
    login_response = await client.post(
        "/api/v1/auth/login",
        json={
            "email": test_user.email,
            "password": "Password123!",
            "organization_slug": test_organization.slug,
        },
    )
    two_factor_token = login_response.json()["two_factor_token"]

    # Verify with invalid code
    verify_response = await client.post(
        "/api/v1/auth/verify-2fa",
        json={
            "two_factor_token": two_factor_token,
            "code": "000000",
        },
    )

    assert verify_response.status_code == 401


@pytest.mark.asyncio
async def test_verify_2fa_with_backup_code(
    client, async_session: AsyncSession, test_organization, test_user
):
    """Test 2FA verification with backup code."""
    from src.core.encryption import encrypt_field
    from src.models import UserTwoFactor, UserTwoFactorBackupCode
    from src.services.two_factor import TwoFactorService

    # Enable 2FA for user - encrypt the secret before storing
    secret = "JBSWY3DPEHPK3PXP"
    encrypted_secret = encrypt_field(secret)
    user_2fa = UserTwoFactor(
        user_id=test_user.id,
        organization_id=test_organization.id,
        secret=encrypted_secret,
        is_enabled=True,
        verified_at=datetime.now(timezone.utc),
    )
    async_session.add(user_2fa)
    await async_session.commit()

    # Generate backup code
    plain_codes, hashed_codes = TwoFactorService.generate_backup_codes(count=1)
    backup_code_record = UserTwoFactorBackupCode(
        user_two_factor_id=user_2fa.id,
        code=hashed_codes[0],
    )
    async_session.add(backup_code_record)
    await async_session.commit()

    # First, login to get 2FA token
    login_response = await client.post(
        "/api/v1/auth/login",
        json={
            "email": test_user.email,
            "password": "Password123!",
            "organization_slug": test_organization.slug,
        },
    )
    two_factor_token = login_response.json()["two_factor_token"]

    # Verify with backup code
    verify_response = await client.post(
        "/api/v1/auth/verify-2fa",
        json={
            "two_factor_token": two_factor_token,
            "code": plain_codes[0],
        },
    )

    assert verify_response.status_code == 200
    data = verify_response.json()
    assert "access_token" in data
    assert "refresh_token" not in data  # Refresh token is in httpOnly cookie

    # Verify backup code was marked as used
    await async_session.refresh(backup_code_record)
    assert backup_code_record.used_at is not None


@pytest.mark.asyncio
async def test_verify_2fa_backup_code_single_use(
    client, async_session: AsyncSession, test_organization, test_user
):
    """Test that backup codes can only be used once."""
    from src.core.encryption import encrypt_field
    from src.models import UserTwoFactor, UserTwoFactorBackupCode
    from src.services.two_factor import TwoFactorService

    # Enable 2FA for user - encrypt the secret before storing
    secret = "JBSWY3DPEHPK3PXP"
    encrypted_secret = encrypt_field(secret)
    user_2fa = UserTwoFactor(
        user_id=test_user.id,
        organization_id=test_organization.id,
        secret=encrypted_secret,
        is_enabled=True,
        verified_at=datetime.now(timezone.utc),
    )
    async_session.add(user_2fa)
    await async_session.commit()

    # Generate backup code
    plain_codes, hashed_codes = TwoFactorService.generate_backup_codes(count=1)
    backup_code_record = UserTwoFactorBackupCode(
        user_two_factor_id=user_2fa.id,
        code=hashed_codes[0],
    )
    async_session.add(backup_code_record)
    await async_session.commit()

    # First use - should succeed
    login_response = await client.post(
        "/api/v1/auth/login",
        json={
            "email": test_user.email,
            "password": "Password123!",
            "organization_slug": test_organization.slug,
        },
    )
    two_factor_token = login_response.json()["two_factor_token"]

    verify_response = await client.post(
        "/api/v1/auth/verify-2fa",
        json={
            "two_factor_token": two_factor_token,
            "code": plain_codes[0],
        },
    )
    assert verify_response.status_code == 200

    # Second use - should fail
    login_response2 = await client.post(
        "/api/v1/auth/login",
        json={
            "email": test_user.email,
            "password": "Password123!",
            "organization_slug": test_organization.slug,
        },
    )
    two_factor_token2 = login_response2.json()["two_factor_token"]

    verify_response2 = await client.post(
        "/api/v1/auth/verify-2fa",
        json={
            "two_factor_token": two_factor_token2,
            "code": plain_codes[0],
        },
    )
    assert verify_response2.status_code == 401


@pytest.mark.asyncio
async def test_verify_2fa_expired_token(
    client, async_session: AsyncSession, test_organization, test_user
):
    """Test 2FA verification with expired token."""
    import jwt

    from src.core.config import settings

    # Create expired 2FA token
    expired_token = jwt.encode(
        {
            "user_id": str(test_user.id),
            "organization_id": str(test_organization.id),
            "purpose": "2fa_verification",
            "exp": datetime.now(timezone.utc) - timedelta(minutes=10),
        },
        settings.JWT_SECRET,
        algorithm="HS256",
    )

    # Try to verify with expired token
    verify_response = await client.post(
        "/api/v1/auth/verify-2fa",
        json={
            "two_factor_token": expired_token,
            "code": "123456",
        },
    )

    assert verify_response.status_code == 401


# ============================================================================
# NOTIFICATION AND GRACE PERIOD TESTS
# ============================================================================


@pytest.mark.asyncio
async def test_policy_change_triggers_notification_task(
    async_session: AsyncSession, test_organization, test_user, monkeypatch
):
    """Test that changing policy to mandatory triggers notification task."""
    from src.crud.organization_two_factor_settings import (
        create_settings,
        update_settings,
    )

    # Track if enqueue_job was called
    enqueue_calls = []

    async def mock_enqueue_job(task_name, **kwargs):
        enqueue_calls.append((task_name, kwargs))

    # Mock task_queue.enqueue_job
    import src.crud.organization_two_factor_settings

    monkeypatch.setattr(
        src.crud.organization_two_factor_settings.task_queue,
        "enqueue_job",
        mock_enqueue_job,
    )

    # Create initial settings with optional policy
    await create_settings(
        async_session,
        {
            "two_factor_allowed": True,
            "two_factor_policy": TwoFactorPolicy.OPTIONAL.value,
            "grace_period_days": 7,
        },
        str(test_organization.id),
    )

    # Update to mandatory - should trigger notification
    await update_settings(
        async_session,
        {"two_factor_policy": TwoFactorPolicy.MANDATORY.value},
        str(test_organization.id),
    )

    # Verify notification task was enqueued
    assert len(enqueue_calls) == 1
    assert enqueue_calls[0][0] == "notify_2fa_mandatory_change"
    assert enqueue_calls[0][1]["organization_id"] == str(test_organization.id)


@pytest.mark.asyncio
async def test_policy_change_sets_enforcement_start_time(
    async_session: AsyncSession, test_organization
):
    """Test that enforcement_start_time is set when policy changes to mandatory."""
    from datetime import datetime, timezone

    from src.crud.organization_two_factor_settings import (
        create_settings,
        update_settings,
    )

    # Create initial settings
    settings = await create_settings(
        async_session,
        {
            "two_factor_allowed": True,
            "two_factor_policy": TwoFactorPolicy.OPTIONAL.value,
        },
        str(test_organization.id),
    )
    assert settings.enforcement_start_time is None

    # Update to mandatory
    updated = await update_settings(
        async_session,
        {"two_factor_policy": TwoFactorPolicy.MANDATORY.value},
        str(test_organization.id),
    )

    # Verify enforcement_start_time was set (just check it's recent, within last minute)
    assert updated.enforcement_start_time is not None
    # Handle timezone-naive datetimes from SQLite test database
    enforcement_time = updated.enforcement_start_time
    if enforcement_time.tzinfo is None:
        enforcement_time = enforcement_time.replace(tzinfo=timezone.utc)
    time_diff = datetime.now(timezone.utc) - enforcement_time
    assert time_diff.total_seconds() < 60  # Should be set within last minute


@pytest.mark.asyncio
async def test_notify_2fa_mandatory_change_creates_notifications(
    async_session: AsyncSession, test_organization, test_user
):
    """Test that notify_2fa_mandatory_change creates notifications for users without 2FA."""
    from datetime import datetime, timezone

    # Create a second user in the same organization
    from src.models import User
    from src.models.notification import Notification
    from src.workers.two_factor_tasks import notify_2fa_mandatory_change

    second_user = User(
        organization_id=test_organization.id,
        email="second@example.com",
        password="hashed_password",
        first_name="Second",
        last_name="User",
    )
    async_session.add(second_user)
    await async_session.commit()

    # Create org settings with mandatory policy
    settings = OrganizationTwoFactorSettings(
        organization_id=test_organization.id,
        two_factor_allowed=True,
        two_factor_policy=TwoFactorPolicy.MANDATORY.value,
        grace_period_days=7,
        enforcement_start_time=datetime.now(timezone.utc),
    )
    async_session.add(settings)
    await async_session.commit()

    # Mock the context and task_queue.enqueue
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def session_factory():
        yield async_session

    class MockContext:
        def get(self, key):
            if key == "session_factory":
                return session_factory
            return None

    # Mock task_queue.enqueue_job to avoid actual enqueueing
    import src.workers.two_factor_tasks

    original_enqueue_job = src.workers.two_factor_tasks.task_queue.enqueue_job
    enqueued_notifications = []

    async def mock_enqueue_job(task_name, **kwargs):
        if task_name == "send_notification_task":
            enqueued_notifications.append(kwargs["notification_id"])
        return None

    src.workers.two_factor_tasks.task_queue.enqueue_job = mock_enqueue_job

    try:
        # Run the task
        result = await notify_2fa_mandatory_change(
            MockContext(), str(test_organization.id)
        )

        # Verify result
        assert result["status"] == "completed"
        assert result["notifications_queued"] == 2  # test_user and second_user_same_org
        assert result["failed"] == 0

        # Verify notifications were created
        notifications_result = await async_session.execute(
            select(Notification).where(
                Notification.organization_id == test_organization.id,
                Notification.deleted_time.is_(None),
            )
        )
        notifications = notifications_result.scalars().all()

        assert len(notifications) == 2
        for notif in notifications:
            assert notif.channel == "email"
            assert notif.status == "pending"
            assert "mandatory" in notif.subject.lower()
            assert (
                "2fa" in notif.subject.lower() or "two-factor" in notif.subject.lower()
            )
    finally:
        # Restore original enqueue_job
        src.workers.two_factor_tasks.task_queue.enqueue_job = original_enqueue_job


@pytest.mark.asyncio
async def test_notify_2fa_excludes_users_with_2fa(
    async_session: AsyncSession, test_organization, test_user
):
    """Test that users with 2FA enabled don't receive mandatory notifications."""
    from datetime import datetime, timezone

    # Create a second user in the same organization
    from src.models import User
    from src.models.notification import Notification
    from src.workers.two_factor_tasks import notify_2fa_mandatory_change

    second_user = User(
        organization_id=test_organization.id,
        email="second@example.com",
        password="hashed_password",
        first_name="Second",
        last_name="User",
    )
    async_session.add(second_user)
    await async_session.commit()

    # Create org settings
    settings = OrganizationTwoFactorSettings(
        organization_id=test_organization.id,
        two_factor_allowed=True,
        two_factor_policy=TwoFactorPolicy.MANDATORY.value,
        grace_period_days=7,
        enforcement_start_time=datetime.now(timezone.utc),
    )
    async_session.add(settings)

    # Enable 2FA for test_user
    user_2fa = UserTwoFactor(
        user_id=test_user.id,
        organization_id=test_organization.id,
        secret="SECRET123",
        is_enabled=True,
        verified_at=datetime.now(timezone.utc),
    )
    async_session.add(user_2fa)
    await async_session.commit()

    # Mock context
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def session_factory():
        yield async_session

    class MockContext:
        def get(self, key):
            if key == "session_factory":
                return session_factory
            return None

    # Mock task_queue.enqueue_job with async function
    import src.workers.two_factor_tasks

    original_enqueue_job = src.workers.two_factor_tasks.task_queue.enqueue_job

    async def mock_enqueue_job(*args, **kwargs):
        pass  # Async no-op

    src.workers.two_factor_tasks.task_queue.enqueue_job = mock_enqueue_job

    try:
        # Run the task
        result = await notify_2fa_mandatory_change(
            MockContext(), str(test_organization.id)
        )

        # Only second_user_same_org should receive notification (test_user has 2FA)
        assert result["notifications_queued"] == 1

        # Verify notification was created for the right user
        notifications_result = await async_session.execute(
            select(Notification).where(
                Notification.organization_id == test_organization.id,
                Notification.deleted_time.is_(None),
            )
        )
        notifications = notifications_result.scalars().all()

        assert len(notifications) == 1
        assert notifications[0].user_id == second_user.id
    finally:
        src.workers.two_factor_tasks.task_queue.enqueue_job = original_enqueue_job


@pytest.mark.asyncio
async def test_notification_includes_grace_period_info(
    async_session: AsyncSession, test_organization, test_user
):
    """Test that notification includes grace period deadline in metadata."""
    from datetime import datetime, timezone

    from src.models.notification import Notification
    from src.workers.two_factor_tasks import notify_2fa_mandatory_change

    grace_days = 7
    enforcement_time = datetime.now(timezone.utc)

    settings = OrganizationTwoFactorSettings(
        organization_id=test_organization.id,
        two_factor_allowed=True,
        two_factor_policy=TwoFactorPolicy.MANDATORY.value,
        grace_period_days=grace_days,
        enforcement_start_time=enforcement_time,
    )
    async_session.add(settings)
    await async_session.commit()

    # Mock context
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def session_factory():
        yield async_session

    class MockContext:
        def get(self, key):
            if key == "session_factory":
                return session_factory
            return None

    # Mock task_queue.enqueue with async function
    import src.workers.two_factor_tasks

    original_enqueue_job = src.workers.two_factor_tasks.task_queue.enqueue_job

    async def mock_enqueue_job(*args, **kwargs):
        pass  # Async no-op

    src.workers.two_factor_tasks.task_queue.enqueue_job = mock_enqueue_job

    try:
        await notify_2fa_mandatory_change(MockContext(), str(test_organization.id))

        # Check notification metadata
        notifications_result = await async_session.execute(
            select(Notification).where(
                Notification.organization_id == test_organization.id,
                Notification.user_id == test_user.id,
            )
        )
        notification = notifications_result.scalar_one()

        assert notification.extra_data is not None
        assert "deadline" in notification.extra_data
        assert "grace_period_days" in notification.extra_data
        assert notification.extra_data["grace_period_days"] == grace_days
    finally:
        src.workers.two_factor_tasks.task_queue.enqueue_job = original_enqueue_job
