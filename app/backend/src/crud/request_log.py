"""
CRUD operations for request logs.
"""

import base64
from datetime import datetime, timezone
import json
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import ColumnElement, and_, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.request_log import RequestLog
from src.models.user import User


def escape_like_pattern(pattern: str) -> str:
    """
    Escape SQL LIKE special characters to prevent pattern injection.

    This ensures that user-provided search terms are treated as literal
    strings rather than LIKE wildcards, preventing unintended broad matches.

    Args:
        pattern: User-provided search pattern

    Returns:
        Escaped pattern safe for use in SQL LIKE queries
    """
    # Escape backslash first, then other special characters
    pattern = pattern.replace("\\", "\\\\")
    pattern = pattern.replace("%", "\\%")
    pattern = pattern.replace("_", "\\_")
    return pattern


def encode_cursor(created_time: datetime, log_id: UUID) -> str:
    """
    Encode a cursor from created_time and id.
    Cursor format: base64(json({"t": iso_timestamp, "i": uuid_string}))
    """
    data = {
        "t": created_time.isoformat(),
        "i": str(log_id),
    }
    return base64.urlsafe_b64encode(json.dumps(data).encode()).decode()


def decode_cursor(cursor: str) -> tuple[datetime, UUID]:
    """
    Decode a cursor to (created_time, id).
    Raises ValueError if cursor is invalid.
    """
    try:
        data = json.loads(base64.urlsafe_b64decode(cursor.encode()).decode())
        created_time = datetime.fromisoformat(data["t"])
        log_id = UUID(data["i"])
        return created_time, log_id
    except (json.JSONDecodeError, KeyError, ValueError) as e:
        raise ValueError(f"Invalid cursor: {e}")


async def create_request_log(
    session: AsyncSession,
    method: str,
    path: str,
    status_code: int,
    duration_ms: int,
    request_body: Optional[dict[str, Any]] = None,
    response_body: Optional[dict[str, Any]] = None,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
    organization_id: Optional[str] = None,
    user_id: Optional[str] = None,
    error_traceback: Optional[str] = None,
) -> RequestLog:
    """
    Create a request log entry.

    Args:
        session: Database session
        method: HTTP method (GET, POST, etc.)
        path: Request path
        status_code: HTTP status code
        duration_ms: Request duration in milliseconds
        request_body: Sanitized request body (optional)
        response_body: Sanitized response body (optional)
        ip_address: IP address of the request
        user_agent: User agent string of the request
        organization_id: Organization UUID string (optional for unauthenticated requests)
        user_id: User UUID string (optional for unauthenticated requests)
        error_traceback: Full stack trace for 500 errors (optional)

    Returns:
        The created RequestLog entry
    """
    org_uuid = None
    if organization_id:
        org_uuid = (
            UUID(organization_id)
            if isinstance(organization_id, str)
            else organization_id
        )

    usr_uuid = None
    if user_id:
        usr_uuid = UUID(user_id) if isinstance(user_id, str) else user_id

    request_log = RequestLog(
        method=method,
        path=path,
        status_code=status_code,
        duration_ms=duration_ms,
        request_body=request_body,
        response_body=response_body,
        ip_address=ip_address,
        user_agent=user_agent,
        organization_id=org_uuid,
        user_id=usr_uuid,
        error_traceback=error_traceback,
    )

    session.add(request_log)
    await session.commit()
    await session.refresh(request_log)

    return request_log


async def get_request_logs(
    session: AsyncSession,
    limit: int = 50,
    cursor: Optional[str] = None,
    method: Optional[str] = None,
    path_pattern: Optional[str] = None,
    status_code_min: Optional[int] = None,
    status_code_max: Optional[int] = None,
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
    organization_id: Optional[str] = None,
    user_id: Optional[str] = None,
    user_email: Optional[str] = None,
) -> tuple[list[RequestLog], Optional[str], bool]:
    """
    Get request logs with optional filters using cursor-based pagination.

    Uses keyset pagination on (created_time, id) for consistent O(1) performance
    regardless of how deep into the result set the user navigates.

    Args:
        session: Database session
        limit: Maximum number of results (default 50)
        cursor: Cursor for pagination (opaque string from previous response)
        method: Filter by HTTP method
        path_pattern: Filter by path pattern (uses SQL LIKE)
        status_code_min: Filter by minimum status code
        status_code_max: Filter by maximum status code
        date_from: Filter from this date
        date_to: Filter until this date
        organization_id: Filter by organization UUID string
        user_id: Filter by user UUID string
        user_email: Filter by user email (partial match, case-insensitive)

    Returns:
        Tuple of (list of request logs, next_cursor or None, has_more)
    """
    # Build conditions list with proper type annotation
    conditions: list[ColumnElement[bool]] = [RequestLog.deleted_time.is_(None)]

    if method:
        conditions.append(RequestLog.method == method)

    if path_pattern:
        escaped_path = escape_like_pattern(path_pattern)
        conditions.append(RequestLog.path.like(f"%{escaped_path}%", escape="\\"))

    if status_code_min is not None:
        conditions.append(RequestLog.status_code >= status_code_min)

    if status_code_max is not None:
        conditions.append(RequestLog.status_code <= status_code_max)

    if date_from:
        conditions.append(RequestLog.created_time >= date_from)

    if date_to:
        conditions.append(RequestLog.created_time <= date_to)

    if organization_id:
        org_uuid = (
            UUID(organization_id)
            if isinstance(organization_id, str)
            else organization_id
        )
        conditions.append(RequestLog.organization_id == org_uuid)

    if user_id:
        usr_uuid = UUID(user_id) if isinstance(user_id, str) else user_id
        conditions.append(RequestLog.user_id == usr_uuid)

    # Track if we need to join with User table
    join_user = False
    if user_email:
        join_user = True
        escaped_email = escape_like_pattern(user_email)
        conditions.append(User.email.ilike(f"%{escaped_email}%", escape="\\"))

    # Apply cursor condition for keyset pagination
    # We're sorting by (created_time DESC, id DESC), so "next page" means
    # rows where (created_time, id) < (cursor_time, cursor_id)
    if cursor:
        cursor_time, cursor_id = decode_cursor(cursor)
        # For DESC ordering: get rows where (created_time, id) < (cursor_time, cursor_id)
        cursor_condition = or_(
            RequestLog.created_time < cursor_time,
            and_(
                RequestLog.created_time == cursor_time,
                RequestLog.id < cursor_id,
            ),
        )
        conditions.append(cursor_condition)

    # Fetch one extra row to determine if there are more results
    query = select(RequestLog)
    if join_user:
        query = query.join(User, RequestLog.user_id == User.id)
    query = (
        query.where(*conditions)
        .order_by(RequestLog.created_time.desc(), RequestLog.id.desc())
        .limit(limit + 1)
    )
    result = await session.execute(query)
    request_logs = list(result.scalars().all())

    # Check if there are more results
    has_more = len(request_logs) > limit
    if has_more:
        request_logs = request_logs[:limit]  # Remove the extra row

    # Generate next cursor from the last item
    next_cursor = None
    if has_more and request_logs:
        last_log = request_logs[-1]
        next_cursor = encode_cursor(last_log.created_time, last_log.id)

    return request_logs, next_cursor, has_more


async def get_request_log_by_id(
    session: AsyncSession,
    request_log_id: str,
) -> Optional[RequestLog]:
    """
    Get a single request log by ID.

    Note: This function does not require organization_id since it's used
    by super admins who can view all request logs.

    Args:
        session: Database session
        request_log_id: Request log UUID string

    Returns:
        The request log or None if not found
    """
    log_uuid = (
        UUID(request_log_id) if isinstance(request_log_id, str) else request_log_id
    )

    result = await session.execute(
        select(RequestLog).where(
            RequestLog.id == log_uuid,
            RequestLog.deleted_time.is_(None),
        )
    )
    return result.scalars().first()


async def delete_old_request_logs(
    session: AsyncSession,
    cutoff_date: datetime,
) -> int:
    """
    Soft-delete request logs older than the cutoff date.

    Used by the log retention cleanup job. Uses bulk UPDATE for efficiency
    instead of loading all rows into memory.

    Args:
        session: Database session
        cutoff_date: Delete logs created before this date

    Returns:
        Number of logs deleted
    """
    now = datetime.now(timezone.utc)

    # Use bulk UPDATE for efficiency - no need to load rows into memory
    result = await session.execute(
        update(RequestLog)
        .where(
            RequestLog.created_time < cutoff_date,
            RequestLog.deleted_time.is_(None),
        )
        .values(deleted_time=now)
    )

    await session.commit()

    return result.rowcount
