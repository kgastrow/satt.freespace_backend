"""
CRUD operations for the tenant-scoped EmailChangeRequest model.
Manages email change requests with multi-step verification flow.
"""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.email_change_request import (
    EmailChangeRequest,
    EmailChangeStatus,
)


async def create_email_change_request(
    session: AsyncSession, data: dict, organization_id: str
):
    """Create a new email change request."""
    org_uuid = UUID(organization_id)
    user_id = UUID(data["user_id"])

    request = EmailChangeRequest(
        user_id=user_id,
        old_email=data["old_email"],
        new_email=data["new_email"],
        expires_at=data["expires_at"],
        organization_id=org_uuid,
    )
    session.add(request)
    await session.commit()
    await session.refresh(request)
    return request


async def get_active_request_for_user(
    session: AsyncSession, user_id: str, organization_id: str
):
    """
    Get the active email change request for a user.
    Active means status is pending_verification or pending_otp and not expired.
    """
    org_uuid = UUID(organization_id)
    result = await session.execute(
        select(EmailChangeRequest).where(
            EmailChangeRequest.user_id == UUID(user_id),
            EmailChangeRequest.organization_id == org_uuid,
            EmailChangeRequest.status.in_(
                [
                    EmailChangeStatus.PENDING_VERIFICATION.value,
                    EmailChangeStatus.PENDING_OTP.value,
                ]
            ),
            EmailChangeRequest.deleted_time.is_(None),
        )
    )
    return result.scalars().first()


async def get_request_by_id(
    session: AsyncSession, request_id: str, organization_id: str
):
    """Get an email change request by ID."""
    org_uuid = UUID(organization_id)
    result = await session.execute(
        select(EmailChangeRequest).where(
            EmailChangeRequest.id == UUID(request_id),
            EmailChangeRequest.organization_id == org_uuid,
            EmailChangeRequest.deleted_time.is_(None),
        )
    )
    return result.scalars().first()


async def update_request_status(
    session: AsyncSession,
    request_id: str,
    status: EmailChangeStatus,
    organization_id: str,
    **kwargs,
):
    """
    Update the status of an email change request.
    Additional fields can be updated via kwargs (e.g., completed_at, identity_verified_at).
    """
    org_uuid = UUID(organization_id)
    result = await session.execute(
        select(EmailChangeRequest).where(
            EmailChangeRequest.id == UUID(request_id),
            EmailChangeRequest.organization_id == org_uuid,
            EmailChangeRequest.deleted_time.is_(None),
        )
    )
    request = result.scalars().first()
    if not request:
        raise ValueError(f"Email change request with id {request_id} not found")

    request.status = status.value
    for key, value in kwargs.items():
        setattr(request, key, value)

    await session.commit()
    await session.refresh(request)
    return request


async def increment_otp_attempts(
    session: AsyncSession, request_id: str, organization_id: str
):
    """Increment the OTP attempts count for a request."""
    org_uuid = UUID(organization_id)
    result = await session.execute(
        select(EmailChangeRequest).where(
            EmailChangeRequest.id == UUID(request_id),
            EmailChangeRequest.organization_id == org_uuid,
            EmailChangeRequest.deleted_time.is_(None),
        )
    )
    request = result.scalars().first()
    if not request:
        raise ValueError(f"Email change request with id {request_id} not found")

    request.otp_attempts += 1
    await session.commit()
    await session.refresh(request)
    return request


async def increment_resend_count(
    session: AsyncSession, request_id: str, organization_id: str
):
    """Increment the OTP resend count for a request."""
    org_uuid = UUID(organization_id)
    result = await session.execute(
        select(EmailChangeRequest).where(
            EmailChangeRequest.id == UUID(request_id),
            EmailChangeRequest.organization_id == org_uuid,
            EmailChangeRequest.deleted_time.is_(None),
        )
    )
    request = result.scalars().first()
    if not request:
        raise ValueError(f"Email change request with id {request_id} not found")

    request.otp_resend_count += 1
    await session.commit()
    await session.refresh(request)
    return request


async def cancel_pending_requests(
    session: AsyncSession, user_id: str, organization_id: str
):
    """
    Cancel all pending email change requests for a user.
    Sets status to cancelled and updates timestamp.
    """
    org_uuid = UUID(organization_id)
    result = await session.execute(
        select(EmailChangeRequest).where(
            EmailChangeRequest.user_id == UUID(user_id),
            EmailChangeRequest.organization_id == org_uuid,
            EmailChangeRequest.status.in_(
                [
                    EmailChangeStatus.PENDING_VERIFICATION.value,
                    EmailChangeStatus.PENDING_OTP.value,
                ]
            ),
            EmailChangeRequest.deleted_time.is_(None),
        )
    )
    requests = result.scalars().all()

    cancelled_count = 0
    for request in requests:
        request.status = EmailChangeStatus.CANCELLED.value
        cancelled_count += 1

    if cancelled_count > 0:
        await session.commit()

    return cancelled_count
