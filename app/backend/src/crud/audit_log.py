"""
CRUD operations for audit logs.
"""

from typing import Any, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.core.query_builder import (
    apply_filters,
    apply_pagination,
    apply_search,
    apply_sort,
    get_total_count,
)
from src.core.query_params import FilterSpec, SortSpec
from src.models.audit_log import AuditAction, AuditLog


# Configuration for audit log DSL queries
AUDIT_LOG_FILTER_FIELDS = {
    "action",
    "resource_type",
    "resource_id",
    "actor_id",
    "created_time",
    "ip_address",
    "resource_name",
}
AUDIT_LOG_SEARCH_FIELDS = ["resource_name"]
AUDIT_LOG_FIELD_MAPPING: dict[str, str] = {}


async def create_audit_log(
    session: AsyncSession,
    organization_id: str,
    action: AuditAction,
    resource_type: str,
    resource_id: str,
    actor_id: Optional[str] = None,
    changes: Optional[dict] = None,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
    impersonated_by: Optional[str] = None,
    resource_name: Optional[str] = None,
    resource_context: Optional[dict] = None,
) -> AuditLog:
    """
    Create an audit log entry.

    Args:
        session: Database session
        organization_id: Organization UUID string
        action: The action performed (CREATE, UPDATE, DELETE)
        resource_type: Type of resource (e.g., 'User', 'Role')
        resource_id: UUID of the affected resource
        actor_id: UUID of the user who performed the action (optional for system actions)
        changes: Dictionary of changes {field: {old: x, new: y}}
        ip_address: IP address of the request
        user_agent: User agent string of the request
        impersonated_by: UUID of the super admin who was impersonating (optional)
        resource_name: Human-readable name of the resource
        resource_context: Additional context captured at audit time

    Returns:
        The created AuditLog entry
    """
    org_uuid = (
        UUID(organization_id) if isinstance(organization_id, str) else organization_id
    )
    resource_uuid = UUID(resource_id) if isinstance(resource_id, str) else resource_id
    actor_uuid = UUID(actor_id) if actor_id and isinstance(actor_id, str) else actor_id
    impersonator_uuid = (
        UUID(impersonated_by)
        if impersonated_by and isinstance(impersonated_by, str)
        else impersonated_by
    )

    audit_log = AuditLog(
        organization_id=org_uuid,
        actor_id=actor_uuid,
        action=action.value if isinstance(action, AuditAction) else action,
        resource_type=resource_type,
        resource_id=resource_uuid,
        changes=changes,
        ip_address=ip_address,
        user_agent=user_agent,
        impersonated_by=impersonator_uuid,
        resource_name=resource_name,
        resource_context=resource_context,
    )

    session.add(audit_log)
    await session.commit()
    await session.refresh(audit_log)

    return audit_log


async def get_audit_logs(
    session: AsyncSession,
    organization_id: str,
    filters: Optional[list[FilterSpec]] = None,
    sorts: Optional[list[SortSpec]] = None,
    search_term: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[AuditLog], int]:
    """
    Get audit logs for an organization with DSL filtering, sorting, and search.

    Args:
        session: Database session
        organization_id: Organization UUID string
        filters: List of FilterSpec objects for filtering
        sorts: List of SortSpec objects for sorting
        search_term: Search term to match against resource_name
        limit: Maximum number of results
        offset: Number of results to skip

    Returns:
        Tuple of (list of audit logs, total count)
    """
    org_uuid = (
        UUID(organization_id) if isinstance(organization_id, str) else organization_id
    )

    # Build base query with eager loading of actor and impersonator relationships
    base_query = (
        select(AuditLog)
        .where(AuditLog.organization_id == org_uuid)
        .options(selectinload(AuditLog.actor), selectinload(AuditLog.impersonator))
    )

    # Apply DSL filters
    if filters:
        base_query = apply_filters(
            base_query, AuditLog, filters, AUDIT_LOG_FIELD_MAPPING
        )

    # Apply search (searches resource_name)
    if search_term:
        base_query = apply_search(
            base_query, AuditLog, search_term, AUDIT_LOG_SEARCH_FIELDS
        )

    # Get total count before pagination
    total_count = await get_total_count(session, base_query)

    # Apply sorting (default to created_time desc)
    if sorts:
        base_query = apply_sort(base_query, AuditLog, sorts, AUDIT_LOG_FIELD_MAPPING)
    else:
        base_query = base_query.order_by(AuditLog.created_time.desc())

    # Apply pagination
    data_query = apply_pagination(base_query, limit, offset)

    result = await session.execute(data_query)
    audit_logs = result.scalars().all()

    return list(audit_logs), total_count


async def get_audit_log_by_id(
    session: AsyncSession,
    audit_log_id: str,
    organization_id: str,
) -> Optional[AuditLog]:
    """
    Get a single audit log by ID within organization context.

    Args:
        session: Database session
        audit_log_id: Audit log UUID string
        organization_id: Organization UUID string

    Returns:
        The audit log or None if not found
    """
    org_uuid = (
        UUID(organization_id) if isinstance(organization_id, str) else organization_id
    )
    log_uuid = UUID(audit_log_id) if isinstance(audit_log_id, str) else audit_log_id

    result = await session.execute(
        select(AuditLog)
        .where(
            AuditLog.id == log_uuid,
            AuditLog.organization_id == org_uuid,
        )
        .options(selectinload(AuditLog.actor), selectinload(AuditLog.impersonator))
    )
    return result.scalars().first()


async def get_resource_history(
    session: AsyncSession,
    organization_id: str,
    resource_type: str,
    resource_id: str,
    limit: int = 100,
) -> list[AuditLog]:
    """
    Get the complete audit history for a specific resource.

    Args:
        session: Database session
        organization_id: Organization UUID string
        resource_type: Type of resource
        resource_id: Resource UUID string
        limit: Maximum number of results

    Returns:
        List of audit logs for the resource, ordered by time descending
    """
    org_uuid = (
        UUID(organization_id) if isinstance(organization_id, str) else organization_id
    )
    res_uuid = UUID(resource_id) if isinstance(resource_id, str) else resource_id

    result = await session.execute(
        select(AuditLog)
        .where(
            AuditLog.organization_id == org_uuid,
            AuditLog.resource_type == resource_type,
            AuditLog.resource_id == res_uuid,
        )
        .options(selectinload(AuditLog.actor), selectinload(AuditLog.impersonator))
        .order_by(AuditLog.created_time.desc())
        .limit(limit)
    )
    return list(result.scalars().all())


def compute_changes(
    old_values: dict[str, Any], new_values: dict[str, Any]
) -> dict[str, dict[str, Any]]:
    """
    Compute the difference between old and new values.

    Args:
        old_values: Dictionary of old field values
        new_values: Dictionary of new field values

    Returns:
        Dictionary of changes: {field: {old: x, new: y}}
    """
    changes: dict[str, dict[str, Any]] = {}

    # Get all keys from both dicts
    all_keys = set(old_values.keys()) | set(new_values.keys())

    for key in all_keys:
        old_val = old_values.get(key)
        new_val = new_values.get(key)

        # Skip if values are the same
        if old_val == new_val:
            continue

        # Skip sensitive fields (never log passwords, secrets, tokens, etc.)
        # Patterns to redact: password, secret, token, api_key, ssn, card numbers, etc.
        sensitive_patterns = [
            "password",
            "secret",
            "token",
            "api_key",
            "apikey",
            "ssn",
            "card",
            "cvv",
            "pin",
            "private_key",
            "privatekey",
            "auth_code",
            "authcode",
            "access_key",
            "accesskey",
        ]
        key_lower = key.lower()
        if any(pattern in key_lower for pattern in sensitive_patterns):
            if old_val != new_val:
                changes[key] = {"old": "[REDACTED]", "new": "[REDACTED]"}
            continue

        # Record the change
        changes[key] = {"old": old_val, "new": new_val}

    return changes
