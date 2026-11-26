from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.encryption import decrypt_field, encrypt_field
from src.models import User, UserTwoFactor, UserTwoFactorBackupCode


async def get_by_user_id(
    session: AsyncSession, user_id: str, organization_id: str
) -> UserTwoFactor | None:
    """Get user 2FA record by user ID within organization context."""
    user_uuid = UUID(user_id)
    org_uuid = UUID(organization_id)
    result = await session.execute(
        select(UserTwoFactor).where(
            UserTwoFactor.user_id == user_uuid,
            UserTwoFactor.organization_id == org_uuid,
            UserTwoFactor.deleted_time.is_(None),
        )
    )
    return result.scalars().first()


async def create(
    session: AsyncSession, data: dict, organization_id: str
) -> UserTwoFactor:
    """Create user 2FA record with encrypted secret."""
    user_uuid = UUID(data["user_id"])
    org_uuid = UUID(organization_id)

    existing = await get_by_user_id(session, str(user_uuid), organization_id)
    if existing:
        raise ValueError("2FA already exists for this user")

    # Encrypt the TOTP secret before storage
    encrypted_secret = encrypt_field(data["secret"])
    if not encrypted_secret:
        raise ValueError("Failed to encrypt TOTP secret")

    user_2fa = UserTwoFactor(
        user_id=user_uuid,
        organization_id=org_uuid,
        secret=encrypted_secret,
        is_enabled=data.get("is_enabled", False),
        verified_at=data.get("verified_at"),
    )
    session.add(user_2fa)
    await session.commit()
    await session.refresh(user_2fa)
    return user_2fa


async def update(
    session: AsyncSession, user_id: str, data: dict, organization_id: str
) -> UserTwoFactor:
    """Update user 2FA record with encrypted secret if provided."""
    user_2fa = await get_by_user_id(session, user_id, organization_id)
    if not user_2fa:
        raise ValueError("2FA not found for this user")

    if "is_enabled" in data:
        user_2fa.is_enabled = data["is_enabled"]
    if "verified_at" in data:
        user_2fa.verified_at = data["verified_at"]
    if "secret" in data:
        # Encrypt the new secret before storage
        encrypted_secret = encrypt_field(data["secret"])
        if not encrypted_secret:
            raise ValueError("Failed to encrypt TOTP secret")
        user_2fa.secret = encrypted_secret

    await session.commit()
    await session.refresh(user_2fa)
    return user_2fa


async def delete(
    session: AsyncSession, user_id: str, organization_id: str
) -> UserTwoFactor:
    """Soft delete user 2FA record."""
    user_2fa = await get_by_user_id(session, user_id, organization_id)
    if not user_2fa:
        raise ValueError("2FA not found for this user")

    user_2fa.deleted_time = datetime.now(timezone.utc)
    await session.commit()
    return user_2fa


async def get_decrypted_secret(
    session: AsyncSession, user_id: str, organization_id: str
) -> str | None:
    """Get the decrypted TOTP secret for verification purposes."""
    user_2fa = await get_by_user_id(session, user_id, organization_id)
    if not user_2fa:
        return None

    # Decrypt the secret for TOTP verification
    return decrypt_field(user_2fa.secret)


async def get_backup_codes(
    session: AsyncSession, user_id: str, organization_id: str
) -> list[UserTwoFactorBackupCode]:
    """Get backup codes for a user's 2FA."""
    user_2fa = await get_by_user_id(session, user_id, organization_id)
    if not user_2fa:
        raise ValueError("2FA not found for this user")

    result = await session.execute(
        select(UserTwoFactorBackupCode).where(
            UserTwoFactorBackupCode.user_two_factor_id == user_2fa.id,
            UserTwoFactorBackupCode.deleted_time.is_(None),
        )
    )
    return list(result.scalars().all())


async def create_backup_code(
    session: AsyncSession, user_two_factor_id: str, code: str
) -> UserTwoFactorBackupCode:
    """Create a backup code for user 2FA."""
    backup_code = UserTwoFactorBackupCode(
        user_two_factor_id=UUID(user_two_factor_id),
        code=code,
    )
    session.add(backup_code)
    await session.commit()
    await session.refresh(backup_code)
    return backup_code


async def get_backup_code_by_id(
    session: AsyncSession, backup_code_id: str
) -> UserTwoFactorBackupCode | None:
    """Get a backup code by ID."""
    result = await session.execute(
        select(UserTwoFactorBackupCode).where(
            UserTwoFactorBackupCode.id == UUID(backup_code_id),
            UserTwoFactorBackupCode.deleted_time.is_(None),
        )
    )
    return result.scalars().first()


async def mark_backup_code_used(
    session: AsyncSession, backup_code_id: str
) -> UserTwoFactorBackupCode:
    """Mark a backup code as used."""
    backup_code = await get_backup_code_by_id(session, backup_code_id)
    if not backup_code:
        raise ValueError("Backup code not found")

    backup_code.used_at = datetime.now(timezone.utc)
    await session.commit()
    await session.refresh(backup_code)
    return backup_code


async def get_users_without_2fa(
    session: AsyncSession, organization_id: str
) -> list[User]:
    """Get all active users in an organization who don't have 2FA enabled.

    Returns users who either:
    - Have no UserTwoFactor record
    - Have a UserTwoFactor record with is_enabled=False
    """
    org_uuid = UUID(organization_id)

    # Subquery to find users with enabled 2FA
    users_with_2fa_subquery = select(UserTwoFactor.user_id).where(
        UserTwoFactor.organization_id == org_uuid,
        UserTwoFactor.is_enabled == True,  # noqa: E712
        UserTwoFactor.deleted_time.is_(None),
    )

    # Get users NOT in the subquery (i.e., without enabled 2FA)
    result = await session.execute(
        select(User)
        .where(
            User.organization_id == org_uuid,
            User.deleted_time.is_(None),
            User.id.not_in(users_with_2fa_subquery),
        )
        .order_by(User.first_name, User.last_name)
    )
    return list(result.scalars().all())
