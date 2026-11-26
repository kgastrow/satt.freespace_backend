from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from pydantic import ValidationError
from sqlalchemy import asc, desc, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.core.security import hash_password
from src.models import User
from src.models.user import SuspensionStatus
from src.serialisers.user import (
    CreateUserRequest,
    DeleteUserRequest,
    GetUserRequest,
    UpdateUserRequest,
)


async def get_users(
    session: AsyncSession, organization_id: str, limit: int = 10, offset: int = 0
):
    """Get all users for an organization with pagination, including their active roles."""
    from src.models.user_role import UserRole

    org_uuid = UUID(organization_id)

    # Count query
    count_result = await session.execute(
        select(func.count())
        .select_from(User)
        .where(User.organization_id == org_uuid, User.deleted_time.is_(None))
    )
    total_count = count_result.scalar() or 0

    # Data query with eager loading of user_roles and their associated roles
    result = await session.execute(
        select(User)
        .options(selectinload(User.user_roles).selectinload(UserRole.role))
        .where(User.organization_id == org_uuid, User.deleted_time.is_(None))
        .limit(limit)
        .offset(offset)
    )
    users = result.scalars().all()

    return users, total_count


async def get_user_by_id(session: AsyncSession, user_id: str, organization_id: str):
    """Get user by ID within organization context. organization_id is required for tenant isolation."""
    try:
        request = GetUserRequest(id=UUID(user_id), email=None)
    except ValidationError as e:
        raise ValueError(f"Invalid input: {e}")

    org_uuid = UUID(organization_id)
    result = await session.execute(
        select(User)
        .options(selectinload(User.organization), selectinload(User.avatar))
        .where(
            User.id == request.id,
            User.organization_id == org_uuid,
            User.deleted_time.is_(None),
        )
    )
    user = result.scalars().first()

    return user


async def count_super_admins(
    session: AsyncSession, organization_id: str, exclude_user_id: str | None = None
) -> int:
    """Count super admins in an organization, optionally excluding a specific user."""
    org_uuid = UUID(organization_id)
    query = (
        select(func.count())
        .select_from(User)
        .where(
            User.organization_id == org_uuid,
            User.deleted_time.is_(None),
            User.is_admin.is_(True),
        )
    )
    if exclude_user_id:
        query = query.where(User.id != UUID(exclude_user_id))
    result = await session.execute(query)
    return result.scalar() or 0


async def get_user_by_email(session: AsyncSession, email: str, organization_id: str):
    try:
        request = GetUserRequest(id=None, email=email)
    except ValidationError as e:
        raise ValueError(f"Invalid input: {e}")

    org_uuid = UUID(organization_id)
    result = await session.execute(
        select(User).where(
            User.email == request.email,
            User.organization_id == org_uuid,
            User.deleted_time.is_(None),
        )
    )
    user = result.scalars().first()

    return user


async def get_user_by_phone(
    session: AsyncSession,
    phone: str,
    organization_id: str,
    exclude_user_id: str | None = None,
):
    """Get user by phone within organization context.

    Args:
        session: Database session
        phone: Phone number to search for
        organization_id: Organization UUID for tenant isolation
        exclude_user_id: Optional user ID to exclude from the search (useful for checking
            if the phone belongs to a different user)

    Returns:
        User if found, None otherwise
    """
    org_uuid = UUID(organization_id)
    query = select(User).where(
        User.phone == phone,
        User.organization_id == org_uuid,
        User.deleted_time.is_(None),
    )

    if exclude_user_id:
        query = query.where(User.id != UUID(exclude_user_id))

    result = await session.execute(query)
    user = result.scalars().first()

    return user


async def create_user(session: AsyncSession, request: dict, organization_id: str):
    try:
        validated_request = CreateUserRequest(**request)
    except ValidationError as e:
        raise ValueError(f"Invalid input: {e}")

    org_uuid = UUID(organization_id)

    # Check email uniqueness within organization
    existing_result = await session.execute(
        select(User).where(
            User.email == validated_request.email,
            User.organization_id == org_uuid,
            User.deleted_time.is_(None),
        )
    )
    existing_user = existing_result.scalars().first()

    if existing_user:
        raise ValueError("A user with this email already exists in this organization.")

    # Hash password if provided (SSO users have None password)
    hashed_password = (
        hash_password(validated_request.password)
        if validated_request.password
        else None
    )

    new_user_data = validated_request.model_dump(
        exclude={"password", "created_via"}, exclude_unset=True
    )
    new_user_data["password"] = hashed_password
    new_user_data["organization_id"] = org_uuid

    # Handle created_via if provided
    if validated_request.created_via:
        from src.models.user import CreatedVia

        new_user_data["created_via"] = CreatedVia(validated_request.created_via)

    new_user = User(**new_user_data)

    session.add(new_user)
    try:
        await session.commit()
        await session.refresh(new_user)
    except Exception as e:
        await session.rollback()
        raise e

    return new_user


async def update_user(session: AsyncSession, request: dict, organization_id: str):
    try:
        update_user_request = UpdateUserRequest(**request)
    except ValidationError as e:
        raise ValueError(f"Invalid input: {e}")

    org_uuid = UUID(organization_id)
    result = await session.execute(
        select(User).where(
            User.id == update_user_request.id,
            User.organization_id == org_uuid,
            User.deleted_time.is_(None),
        )
    )
    user = result.scalars().first()

    if not user:
        raise ValueError(f"User with id {update_user_request.id} not found.")

    update_data = update_user_request.model_dump(
        exclude_unset=True, exclude={"password", "id"}
    )

    if update_user_request.password:
        update_data["password"] = hash_password(update_user_request.password)

    for key, value in update_data.items():
        setattr(user, key, value)

    try:
        await session.commit()
        await session.refresh(user)
    except Exception as e:
        await session.rollback()
        raise e

    return user


async def delete_user(session: AsyncSession, user_id: str, organization_id: str):
    try:
        delete_user_request = DeleteUserRequest(id=UUID(user_id))
    except ValidationError as e:
        raise ValueError(f"Invalid input: {e}")

    org_uuid = UUID(organization_id)
    result = await session.execute(
        select(User).where(
            User.id == delete_user_request.id,
            User.organization_id == org_uuid,
            User.deleted_time.is_(None),
        )
    )
    user = result.scalars().first()

    if not user:
        raise ValueError(f"User with id {delete_user_request.id} not found.")

    user.deleted_time = datetime.now(timezone.utc)

    try:
        await session.commit()
        await session.refresh(user)
    except Exception as e:
        await session.rollback()
        raise e

    return user


async def suspend_user(
    session: AsyncSession,
    user_id: str,
    organization_id: str,
    suspended_by: str,
    reason: str | None = None,
):
    """Suspend a user within organization context."""
    from src.models.user import SuspensionStatus

    org_uuid = UUID(organization_id)
    user_uuid = UUID(user_id)
    suspended_by_uuid = UUID(suspended_by)

    result = await session.execute(
        select(User).where(
            User.id == user_uuid,
            User.organization_id == org_uuid,
            User.deleted_time.is_(None),
        )
    )
    user = result.scalars().first()

    if not user:
        raise ValueError(f"User with id {user_id} not found.")

    user.suspension_status = SuspensionStatus.SUSPENDED
    user.suspended_time = datetime.now(timezone.utc)
    user.suspended_by = suspended_by_uuid
    user.suspension_reason = reason

    try:
        await session.commit()
        await session.refresh(user)
    except Exception as e:
        await session.rollback()
        raise e

    return user


async def unsuspend_user(session: AsyncSession, user_id: str, organization_id: str):
    """Unsuspend a user within organization context."""
    from src.models.user import SuspensionStatus

    org_uuid = UUID(organization_id)
    user_uuid = UUID(user_id)

    result = await session.execute(
        select(User).where(
            User.id == user_uuid,
            User.organization_id == org_uuid,
            User.deleted_time.is_(None),
        )
    )
    user = result.scalars().first()

    if not user:
        raise ValueError(f"User with id {user_id} not found.")

    user.suspension_status = SuspensionStatus.ACTIVE
    user.suspended_time = None
    user.suspended_by = None
    user.suspension_reason = None

    try:
        await session.commit()
        await session.refresh(user)
    except Exception as e:
        await session.rollback()
        raise e

    return user


async def update_user_avatar(
    session: AsyncSession,
    user_id: str,
    organization_id: str,
    avatar_file_id: str | None,
):
    """Update user's avatar_file_id within organization context."""
    org_uuid = UUID(organization_id)
    user_uuid = UUID(user_id)
    avatar_uuid = UUID(avatar_file_id) if avatar_file_id else None

    result = await session.execute(
        select(User).where(
            User.id == user_uuid,
            User.organization_id == org_uuid,
            User.deleted_time.is_(None),
        )
    )
    user = result.scalars().first()

    if not user:
        raise ValueError(f"User with id {user_id} not found.")

    user.avatar_file_id = avatar_uuid

    try:
        await session.commit()
        await session.refresh(user)
    except Exception as e:
        await session.rollback()
        raise e

    return user


# Enhanced user query functions for admin user management


VALID_SORT_FIELDS = {
    "email": User.email,
    "first_name": User.first_name,
    "last_name": User.last_name,
    "created_time": User.created_time,
}


async def get_users_cursor(
    session: AsyncSession,
    organization_id: str,
    limit: int = 10,
    cursor: Optional[str] = None,
    fields: Optional[list[str]] = None,
    filter_status: Optional[str] = None,
    filter_user_type_id: Optional[str] = None,
    filter_created_via: Optional[str] = None,
    filter_email_verified: Optional[bool] = None,
    search: Optional[str] = None,
):
    """
    Get users with cursor-based pagination for better performance on large datasets.

    Cursor pagination provides O(1) performance regardless of page depth, unlike
    OFFSET pagination which degrades linearly (page 1000 scans 100K rows).

    The cursor is based on (created_time, id) for stable ordering.

    Args:
        session: Database session
        organization_id: Organization UUID for tenant isolation
        limit: Max users to return
        cursor: Cursor string in format "timestamp_uuid" (e.g., "2024-01-15T10:30:00_uuid123")
        fields: Optional list of fields to include (sparse fieldset)
        filter_status: Filter by suspension status (active/suspended)
        filter_user_type_id: Filter by user type ID
        filter_created_via: Filter by creation method (email/google)
        filter_email_verified: Filter by email verification status
        search: Search term for name, email, phone

    Returns:
        (users[], total_count, needs_storage, needs_user_types, needs_last_login, next_cursor)
    """
    from src.models.user import CreatedVia
    from src.models.user_role import UserRole
    from src.models.user_user_type import UserUserType

    org_uuid = UUID(organization_id)

    # Build base query
    base_conditions = [
        User.organization_id == org_uuid,
        User.deleted_time.is_(None),
    ]

    # Apply filters
    if filter_status:
        if filter_status.lower() == "active":
            base_conditions.append(User.suspension_status == SuspensionStatus.ACTIVE)
        elif filter_status.lower() == "suspended":
            base_conditions.append(User.suspension_status == SuspensionStatus.SUSPENDED)

    if filter_created_via:
        try:
            created_via_enum = CreatedVia(filter_created_via.lower())
            base_conditions.append(User.created_via == created_via_enum)
        except ValueError:
            pass  # Invalid created_via value, skip filter

    if filter_email_verified is not None:
        base_conditions.append(User.email_verified == filter_email_verified)

    # Search filter
    if search:
        search_term = f"%{search}%"
        search_conditions = or_(
            User.email.ilike(search_term),
            User.first_name.ilike(search_term),
            User.last_name.ilike(search_term),
            User.phone.ilike(search_term),
        )
        base_conditions.append(search_conditions)

    # User type filter requires a subquery
    if filter_user_type_id:
        user_type_uuid = UUID(filter_user_type_id)
        user_type_subquery = (
            select(UserUserType.user_id)
            .where(
                UserUserType.organization_id == org_uuid,
                UserUserType.user_type_id == user_type_uuid,
                UserUserType.deleted_time.is_(None),
            )
            .scalar_subquery()
        )
        base_conditions.append(User.id.in_(user_type_subquery))

    # Count query
    count_result = await session.execute(
        select(func.count()).select_from(User).where(*base_conditions)
    )
    total_count = count_result.scalar() or 0

    # Apply cursor-based pagination (keyset pagination)
    cursor_conditions = list(base_conditions)
    if cursor:
        # Parse cursor: "timestamp_uuid" format
        try:
            parts = cursor.rsplit("_", 1)
            cursor_time = datetime.fromisoformat(parts[0])
            cursor_id = UUID(parts[1])
            # For descending order: get items with created_time < cursor_time
            # OR created_time == cursor_time AND id < cursor_id
            cursor_conditions.append(
                or_(
                    User.created_time < cursor_time,
                    (User.created_time == cursor_time) & (User.id < cursor_id),
                )
            )
        except (ValueError, IndexError):
            pass  # Invalid cursor, ignore

    # Build data query with eager loading
    data_query = (
        select(User)
        .options(
            selectinload(User.user_roles).selectinload(UserRole.role),
            selectinload(User.avatar),
        )
        .where(*cursor_conditions)
    )

    # Determine what additional data we need based on fields
    needs_storage = fields is None or "total_storage_bytes" in fields
    needs_user_types = fields is None or "user_types" in fields
    needs_last_login = fields is None or "last_login" in fields

    if needs_user_types:
        data_query = data_query.options(
            selectinload(User.user_user_types).selectinload(UserUserType.user_type)
        )

    # Always order by created_time desc, then id for stable cursor pagination
    data_query = data_query.order_by(desc(User.created_time), desc(User.id))

    # Fetch one extra to determine if there are more results
    data_query = data_query.limit(limit + 1)

    result = await session.execute(data_query)
    users = list(result.scalars().all())

    # Determine next cursor
    has_more = len(users) > limit
    if has_more:
        users = users[:limit]  # Remove the extra item

    next_cursor = None
    if has_more and users:
        last_user = users[-1]
        if last_user.created_time:
            next_cursor = f"{last_user.created_time.isoformat()}_{last_user.id}"

    return (
        users,
        total_count,
        needs_storage,
        needs_user_types,
        needs_last_login,
        next_cursor,
    )


async def get_users_enhanced(
    session: AsyncSession,
    organization_id: str,
    limit: int = 10,
    offset: int = 0,
    fields: Optional[list[str]] = None,
    filter_status: Optional[str] = None,
    filter_user_type_id: Optional[str] = None,
    filter_created_via: Optional[str] = None,
    filter_email_verified: Optional[bool] = None,
    sort: Optional[str] = None,
    search: Optional[str] = None,
):
    """
    Get users with enhanced filtering, sorting, and sparse fieldsets.

    Args:
        session: Database session
        organization_id: Organization UUID for tenant isolation
        limit: Max users to return
        offset: Pagination offset
        fields: Optional list of fields to include (sparse fieldset)
        filter_status: Filter by suspension status (active/suspended)
        filter_user_type_id: Filter by user type ID
        filter_created_via: Filter by creation method (email/google)
        filter_email_verified: Filter by email verification status
        sort: Sort string in format "field:direction" (e.g., "created_time:desc")
        search: Search term for name, email, phone

    Returns:
        (users[], total_count, needs_storage, needs_user_types, needs_last_login)
    """
    from src.models.user import CreatedVia
    from src.models.user_role import UserRole
    from src.models.user_user_type import UserUserType

    org_uuid = UUID(organization_id)

    # Build base query
    base_conditions = [
        User.organization_id == org_uuid,
        User.deleted_time.is_(None),
    ]

    # Apply filters
    if filter_status:
        if filter_status.lower() == "active":
            base_conditions.append(User.suspension_status == SuspensionStatus.ACTIVE)
        elif filter_status.lower() == "suspended":
            base_conditions.append(User.suspension_status == SuspensionStatus.SUSPENDED)

    if filter_created_via:
        try:
            created_via_enum = CreatedVia(filter_created_via.lower())
            base_conditions.append(User.created_via == created_via_enum)
        except ValueError:
            pass  # Invalid created_via value, skip filter

    if filter_email_verified is not None:
        base_conditions.append(User.email_verified == filter_email_verified)

    # Search filter
    if search:
        search_term = f"%{search}%"
        search_conditions = or_(
            User.email.ilike(search_term),
            User.first_name.ilike(search_term),
            User.last_name.ilike(search_term),
            User.phone.ilike(search_term),
        )
        base_conditions.append(search_conditions)

    # User type filter requires a subquery
    if filter_user_type_id:
        user_type_uuid = UUID(filter_user_type_id)
        user_type_subquery = (
            select(UserUserType.user_id)
            .where(
                UserUserType.organization_id == org_uuid,
                UserUserType.user_type_id == user_type_uuid,
                UserUserType.deleted_time.is_(None),
            )
            .scalar_subquery()
        )
        base_conditions.append(User.id.in_(user_type_subquery))

    # Count query
    count_result = await session.execute(
        select(func.count()).select_from(User).where(*base_conditions)
    )
    total_count = count_result.scalar() or 0

    # Build data query with eager loading
    data_query = (
        select(User)
        .options(
            selectinload(User.user_roles).selectinload(UserRole.role),
            selectinload(User.avatar),
        )
        .where(*base_conditions)
    )

    # Determine what additional data we need based on fields
    needs_storage = fields is None or "total_storage_bytes" in fields
    needs_user_types = fields is None or "user_types" in fields
    needs_last_login = fields is None or "last_login" in fields

    if needs_user_types:

        data_query = data_query.options(
            selectinload(User.user_user_types).selectinload(UserUserType.user_type)
        )

    # Apply sorting
    if sort:
        parts = sort.split(":")
        field_name = parts[0]
        direction = parts[1] if len(parts) > 1 else "asc"

        if field_name in VALID_SORT_FIELDS:
            sort_column = VALID_SORT_FIELDS[field_name]
            if direction.lower() == "desc":
                data_query = data_query.order_by(desc(sort_column))
            else:
                data_query = data_query.order_by(asc(sort_column))
        else:
            # Default sort by created_time desc
            data_query = data_query.order_by(desc(User.created_time))
    else:
        data_query = data_query.order_by(desc(User.created_time))

    # Apply pagination
    data_query = data_query.limit(limit).offset(offset)

    result = await session.execute(data_query)
    users = result.scalars().all()

    return users, total_count, needs_storage, needs_user_types, needs_last_login


async def get_user_storage(
    session: AsyncSession,
    user_id: str,
    organization_id: str,
) -> int | None:
    """Get total storage bytes for a user."""
    from src.models.file_usage import FileUsage

    org_uuid = UUID(organization_id)
    user_uuid = UUID(user_id)

    result = await session.execute(
        select(FileUsage.total_size_bytes).where(
            FileUsage.organization_id == org_uuid,
            FileUsage.user_id == user_uuid,
            FileUsage.deleted_time.is_(None),
        )
    )
    return result.scalar()


async def get_user_last_login(
    session: AsyncSession,
    user_id: str,
    organization_id: str,
) -> datetime | None:
    """Get user's most recent login (refresh token update time)."""
    from src.models.refresh_token import RefreshToken

    org_uuid = UUID(organization_id)
    user_uuid = UUID(user_id)

    result = await session.execute(
        select(RefreshToken.updated_time)
        .where(
            RefreshToken.organization_id == org_uuid,
            RefreshToken.user_id == user_uuid,
            RefreshToken.deleted_time.is_(None),
        )
        .order_by(desc(RefreshToken.updated_time))
        .limit(1)
    )
    return result.scalar()


async def get_users_storage_batch(
    session: AsyncSession,
    user_ids: list[str],
    organization_id: str,
) -> dict[str, int | None]:
    """
    Get total storage bytes for multiple users in a single query.

    Returns a dict mapping user_id -> total_size_bytes (or None if no record).
    """
    if not user_ids:
        return {}

    from src.models.file_usage import FileUsage

    org_uuid = UUID(organization_id)
    user_uuids = [UUID(uid) for uid in user_ids]

    result = await session.execute(
        select(FileUsage.user_id, FileUsage.total_size_bytes).where(
            FileUsage.organization_id == org_uuid,
            FileUsage.user_id.in_(user_uuids),
            FileUsage.deleted_time.is_(None),
        )
    )
    rows = result.all()

    return {str(row.user_id): row.total_size_bytes for row in rows}


async def get_users_last_login_batch(
    session: AsyncSession,
    user_ids: list[str],
    organization_id: str,
) -> dict[str, datetime | None]:
    """
    Get most recent login time for multiple users in a single query.

    Returns a dict mapping user_id -> most recent updated_time from refresh tokens.
    """
    if not user_ids:
        return {}

    from src.models.refresh_token import RefreshToken

    org_uuid = UUID(organization_id)
    user_uuids = [UUID(uid) for uid in user_ids]

    # Use a subquery with DISTINCT ON to get max updated_time per user
    result = await session.execute(
        select(
            RefreshToken.user_id,
            func.max(RefreshToken.updated_time).label("last_login"),
        )
        .where(
            RefreshToken.organization_id == org_uuid,
            RefreshToken.user_id.in_(user_uuids),
            RefreshToken.deleted_time.is_(None),
        )
        .group_by(RefreshToken.user_id)
    )
    rows = result.all()

    return {str(row.user_id): row.last_login for row in rows}


async def get_user_full_detail(
    session: AsyncSession,
    user_id: str,
    organization_id: str,
    current_session_id: Optional[str] = None,
):
    """
    Get complete user details including all related data.

    Returns user with all relationships eagerly loaded, plus:
    - sessions
    - two_factor status
    - file_usage
    - feedback
    - data_exports
    - impersonation_history
    - identity_providers
    - notification_preferences
    """
    from src.models.data_export_request import DataExportRequest
    from src.models.feedback import Feedback
    from src.models.file_usage import FileUsage
    from src.models.impersonation_session import ImpersonationSession
    from src.models.refresh_token import RefreshToken
    from src.models.user_identity import UserIdentity
    from src.models.user_notification_preference import UserNotificationPreference
    from src.models.user_role import UserRole
    from src.models.user_two_factor import UserTwoFactor
    from src.models.user_user_type import UserUserType

    org_uuid = UUID(organization_id)
    user_uuid = UUID(user_id)

    # Get user with eager loading
    user_result = await session.execute(
        select(User)
        .options(
            selectinload(User.user_roles).selectinload(UserRole.role),
            selectinload(User.user_user_types).selectinload(UserUserType.user_type),
            selectinload(User.avatar),
            selectinload(User.suspended_by_user),
        )
        .where(
            User.id == user_uuid,
            User.organization_id == org_uuid,
            User.deleted_time.is_(None),
        )
    )
    user = user_result.scalars().first()

    if not user:
        return None

    # Get sessions
    sessions_result = await session.execute(
        select(RefreshToken)
        .where(
            RefreshToken.user_id == user_uuid,
            RefreshToken.organization_id == org_uuid,
            RefreshToken.deleted_time.is_(None),
            RefreshToken.expires_at > datetime.now(timezone.utc),
        )
        .order_by(desc(RefreshToken.updated_time))
    )
    sessions = sessions_result.scalars().all()

    # Get two-factor status
    two_factor_result = await session.execute(
        select(UserTwoFactor)
        .options(selectinload(UserTwoFactor.backup_codes))
        .where(
            UserTwoFactor.user_id == user_uuid,
            UserTwoFactor.organization_id == org_uuid,
            UserTwoFactor.deleted_time.is_(None),
        )
    )
    two_factor = two_factor_result.scalars().first()

    # Get file usage
    file_usage_result = await session.execute(
        select(FileUsage).where(
            FileUsage.user_id == user_uuid,
            FileUsage.organization_id == org_uuid,
            FileUsage.deleted_time.is_(None),
        )
    )
    file_usage = file_usage_result.scalars().first()

    # Get feedback (limit to recent 20)
    feedback_result = await session.execute(
        select(Feedback)
        .where(
            Feedback.user_id == user_uuid,
            Feedback.organization_id == org_uuid,
            Feedback.deleted_time.is_(None),
        )
        .order_by(desc(Feedback.created_time))
        .limit(20)
    )
    feedback_items = feedback_result.scalars().all()

    # Get data exports
    exports_result = await session.execute(
        select(DataExportRequest)
        .where(
            DataExportRequest.user_id == user_uuid,
            DataExportRequest.organization_id == org_uuid,
            DataExportRequest.deleted_time.is_(None),
        )
        .order_by(desc(DataExportRequest.created_time))
        .limit(10)
    )
    data_exports = exports_result.scalars().all()

    # Get impersonation history (where this user was impersonated)
    impersonation_result = await session.execute(
        select(ImpersonationSession)
        .options(selectinload(ImpersonationSession.impersonator))
        .where(
            ImpersonationSession.target_user_id == user_uuid,
            ImpersonationSession.target_organization_id == org_uuid,
        )
        .order_by(desc(ImpersonationSession.created_time))
        .limit(20)
    )
    impersonation_sessions = impersonation_result.scalars().all()

    # Get identity providers
    identities_result = await session.execute(
        select(UserIdentity).where(
            UserIdentity.user_id == user_uuid,
            UserIdentity.organization_id == org_uuid,
            UserIdentity.deleted_time.is_(None),
        )
    )
    identities = identities_result.scalars().all()

    # Get notification preferences
    notif_pref_result = await session.execute(
        select(UserNotificationPreference).where(
            UserNotificationPreference.user_id == user_uuid,
            UserNotificationPreference.organization_id == org_uuid,
            UserNotificationPreference.deleted_time.is_(None),
        )
    )
    notification_preferences = notif_pref_result.scalars().first()

    return {
        "user": user,
        "sessions": sessions,
        "current_session_id": current_session_id,
        "two_factor": two_factor,
        "file_usage": file_usage,
        "feedback": feedback_items,
        "data_exports": data_exports,
        "impersonation_history": impersonation_sessions,
        "identities": identities,
        "notification_preferences": notification_preferences,
    }


async def invalidate_user_session(
    session: AsyncSession,
    session_id: str,
    user_id: str,
    organization_id: str,
) -> bool:
    """
    Invalidate a specific user session (soft delete refresh token).

    Returns True if session was found and invalidated.
    """
    from src.models.refresh_token import RefreshToken

    org_uuid = UUID(organization_id)
    user_uuid = UUID(user_id)

    result = await session.execute(
        select(RefreshToken).where(
            RefreshToken.id == session_id,
            RefreshToken.user_id == user_uuid,
            RefreshToken.organization_id == org_uuid,
            RefreshToken.deleted_time.is_(None),
        )
    )
    token = result.scalars().first()

    if not token:
        return False

    token.deleted_time = datetime.now(timezone.utc)

    try:
        await session.commit()
        return True
    except Exception as e:
        await session.rollback()
        raise e
