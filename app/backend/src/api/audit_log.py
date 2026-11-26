"""
Audit Log API endpoints.
Admin-only endpoints for viewing audit logs.
"""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.requests import Request

from src.api.deps import CurrentUser, get_session, require_permission
from src.core.exceptions import create_http_exception
from src.core.query_params import (
    get_pagination_params,
    get_search_param,
    parse_filters,
    parse_sort,
)
from src.crud.audit_log import get_audit_log_by_id, get_audit_logs, get_resource_history
from src.models.audit_log import AuditLog
from src.models.user import User
from src.serialisers.audit_log import (
    AuditLogListResponse,
    AuditLogResponse,
    ResourceHistoryResponse,
)


# DSL configuration for audit logs
ALLOWED_FILTERS = {
    "action",
    "resource_type",
    "resource_id",
    "actor_id",
    "created_time",
    "ip_address",
    "resource_name",
}
ALLOWED_SORTS = {"created_time", "action", "resource_type", "resource_name"}

router = APIRouter(prefix="/audit-logs", tags=["audit-logs"])


def audit_log_to_response(
    log: AuditLog,
    resource_names: dict[str, str] | None = None,
) -> AuditLogResponse:
    """
    Convert an AuditLog model to response schema with enriched data.

    Args:
        log: The AuditLog model instance
        resource_names: Optional mapping of resource_id -> human-readable name
                       (fallback for old records without stored resource_name)
    """
    actor_email = None
    if log.actor:
        actor_email = log.actor.email

    # Use stored resource_name if available, otherwise fallback to resolved name
    resource_name = log.resource_name
    if not resource_name and resource_names and str(log.resource_id) in resource_names:
        resource_name = resource_names[str(log.resource_id)]

    return AuditLogResponse(
        id=log.id,
        created_time=log.created_time,
        organization_id=log.organization_id,
        actor_id=log.actor_id,
        actor_email=actor_email,
        action=log.action,
        resource_type=log.resource_type,
        resource_id=log.resource_id,
        resource_name=resource_name,
        resource_context=log.resource_context,
        changes=log.changes,
        ip_address=log.ip_address,
        user_agent=log.user_agent,
        impersonated_by=log.impersonated_by,
        impersonator_email=None,
    )


async def resolve_resource_names(
    session: AsyncSession,
    audit_logs: list[AuditLog],
    organization_id: str,
) -> dict[str, str]:
    """
    Resolve human-readable names for resources in audit logs.
    Currently supports User resource types.
    """
    resource_names: dict[str, str] = {}

    # Collect User resource IDs
    user_ids = {log.resource_id for log in audit_logs if log.resource_type == "User"}

    if user_ids:
        # Batch fetch users
        result = await session.execute(
            select(User).where(
                User.id.in_(user_ids),
                User.organization_id == UUID(organization_id),
            )
        )
        users = result.scalars().all()
        for user in users:
            resource_names[str(user.id)] = user.email

    return resource_names


@router.get("", response_model=AuditLogListResponse)
async def list_audit_logs(
    request: Request,
    current_user: Annotated[
        CurrentUser, Depends(require_permission("audit_logs:read"))
    ],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """
    List audit logs for the organization with DSL filtering, sorting, and search.

    Requires audit_logs:read permission.

    **Filter examples:**
    - `filter[resource_type]=User` - exact match
    - `filter[action][in]=CREATE,UPDATE` - value in list
    - `filter[created_time][gte]=2024-01-01T00:00:00Z` - date comparison
    - `filter[resource_name][contains]=john` - partial text match

    **Search:** `q=searchterm` (searches resource_name)

    **Sort:** `sort=created_time:desc` or `sort=resource_type:asc,created_time:desc`

    **Pagination:** `limit=50&offset=0`
    """
    # Parse DSL parameters from request
    filters = parse_filters(request, allowed_fields=ALLOWED_FILTERS)
    sorts = parse_sort(
        request.query_params.get("sort"),
        allowed_fields=ALLOWED_SORTS,
        default_sort="created_time:desc",
    )
    search_term = get_search_param(request)
    limit, offset = get_pagination_params(request)

    audit_logs, total = await get_audit_logs(
        session=session,
        organization_id=current_user.organization_id,
        filters=filters,
        sorts=sorts,
        search_term=search_term,
        limit=limit,
        offset=offset,
    )

    # Resolve resource names for display (fallback for old records without resource_name)
    resource_names = await resolve_resource_names(
        session, audit_logs, current_user.organization_id
    )

    return AuditLogListResponse(
        items=[audit_log_to_response(log, resource_names) for log in audit_logs],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{audit_log_id}", response_model=AuditLogResponse)
async def get_audit_log(
    audit_log_id: UUID,
    current_user: Annotated[
        CurrentUser, Depends(require_permission("audit_logs:read"))
    ],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """
    Get a single audit log entry by ID.

    Requires audit_logs:read permission.
    """
    audit_log = await get_audit_log_by_id(
        session=session,
        audit_log_id=str(audit_log_id),
        organization_id=current_user.organization_id,
    )

    if not audit_log:
        raise create_http_exception(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Audit log not found",
            detail_code="common.not_found",
        )

    # Resolve resource name for display
    resource_names = await resolve_resource_names(
        session, [audit_log], current_user.organization_id
    )

    return audit_log_to_response(audit_log, resource_names)


@router.get(
    "/resource/{resource_type}/{resource_id}", response_model=ResourceHistoryResponse
)
async def get_resource_audit_history(
    resource_type: str,
    resource_id: UUID,
    current_user: Annotated[
        CurrentUser, Depends(require_permission("audit_logs:read"))
    ],
    session: Annotated[AsyncSession, Depends(get_session)],
    limit: int = Query(
        100, ge=1, le=500, description="Maximum number of history entries"
    ),
):
    """
    Get the complete audit history for a specific resource.

    Requires audit_logs:read permission.

    Returns all audit log entries for the specified resource,
    ordered by time (newest first).
    """
    history = await get_resource_history(
        session=session,
        organization_id=current_user.organization_id,
        resource_type=resource_type,
        resource_id=str(resource_id),
        limit=limit,
    )

    # Resolve resource names for display
    resource_names = await resolve_resource_names(
        session, history, current_user.organization_id
    )

    return ResourceHistoryResponse(
        resource_type=resource_type,
        resource_id=resource_id,
        history=[audit_log_to_response(log, resource_names) for log in history],
        total=len(history),
    )
