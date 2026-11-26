"""
Users Report Generator.

Generates a CSV report of all users in an organization with their details and roles.
Uses streaming/chunked processing to prevent OOM with large datasets.
"""

from collections.abc import AsyncIterator
import csv
import io
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.models.user import User
from src.models.user_role import UserRole


# Batch size for streaming user report generation
REPORT_BATCH_SIZE = 500


async def _stream_users(
    session: AsyncSession,
    organization_id: UUID,
    parameters: dict[str, Any],
) -> AsyncIterator[User]:
    """
    Stream users in batches to avoid loading all into memory.

    Yields users one at a time, fetching in batches internally.
    """
    offset = 0

    while True:
        # Build query for users
        query = (
            select(User)
            .where(
                User.organization_id == organization_id,
                User.deleted_time.is_(None),
            )
            .options(selectinload(User.user_roles).selectinload(UserRole.role))
            .order_by(User.created_time.desc())
            .limit(REPORT_BATCH_SIZE)
            .offset(offset)
        )

        # Apply optional filters
        if "email_verified" in parameters:
            query = query.where(User.email_verified == parameters["email_verified"])

        if "suspension_status" in parameters:
            query = query.where(
                User.suspension_status == parameters["suspension_status"]
            )

        result = await session.execute(query)
        users = result.scalars().all()

        if not users:
            break

        for user in users:
            yield user

        if len(users) < REPORT_BATCH_SIZE:
            break

        offset += REPORT_BATCH_SIZE


async def generate_users_report(
    session: AsyncSession,
    organization_id: str,
    parameters: Optional[dict[str, Any]] = None,
) -> tuple[bytes, str, int]:
    """
    Generate a CSV report of users in the organization.

    Uses streaming/chunked processing to prevent OOM with large datasets.

    Args:
        session: Database session
        organization_id: Organization UUID string
        parameters: Optional filter parameters:
            - email_verified: Filter by email verification status (bool)
            - suspension_status: Filter by status ("active", "suspended")

    Returns:
        Tuple of (file_bytes, content_type, row_count)
    """
    org_uuid = UUID(organization_id)
    parameters = parameters or {}

    # Generate CSV with streaming
    output = io.StringIO()
    writer = csv.writer(output)

    # Write header
    headers = [
        "ID",
        "Email",
        "First Name",
        "Last Name",
        "Phone",
        "Email Verified",
        "Phone Verified",
        "Status",
        "Roles",
        "Created At",
        "Created Via",
    ]
    writer.writerow(headers)

    # Stream and write data rows
    row_count = 0
    async for user in _stream_users(session, org_uuid, parameters):
        # Get active roles for this user
        roles = []
        for user_role in user.user_roles:
            if user_role.deleted_time is None and user_role.role:
                roles.append(user_role.role.name)
        roles_str = ", ".join(sorted(roles)) if roles else ""

        # Format created_time
        created_at = ""
        if user.created_time:
            created_at = user.created_time.strftime("%Y-%m-%d %H:%M:%S UTC")

        writer.writerow(
            [
                str(user.id),
                user.email,
                user.first_name or "",
                user.last_name or "",
                user.phone or "",
                "Yes" if user.email_verified else "No",
                "Yes" if user.phone_verified else "No",
                user.suspension_status.value if user.suspension_status else "active",
                roles_str,
                created_at,
                user.created_via.value if user.created_via else "email",
            ]
        )
        row_count += 1

    # Get CSV content as bytes
    csv_content = output.getvalue()
    file_bytes = csv_content.encode(
        "utf-8-sig"
    )  # UTF-8 with BOM for Excel compatibility

    return file_bytes, "text/csv", row_count
