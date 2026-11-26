"""
CRUD operations for NotificationTemplate model.

Templates support mixed scope:
- organization_id=None: System templates (available to all organizations)
- organization_id=UUID: Organization-specific templates

When fetching templates, check org-specific first, then fall back to system templates.
"""

from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import ColumnElement, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.query_builder import (
    apply_filters,
    apply_pagination,
    apply_sort,
    get_total_count,
)
from src.core.query_params import FilterSpec, SortSpec
from src.models.notification_template import NotificationTemplate


# SDL configuration for notification templates
TEMPLATE_FILTER_FIELDS = {"channel"}
TEMPLATE_FIELD_MAPPING: dict[str, str] = {}


async def get_template_by_code(
    session: AsyncSession,
    organization_id: str,
    code: str,
    channel: str,
) -> Optional[NotificationTemplate]:
    """
    Get template by code, checking organization first, then system templates.

    This implements the fallback pattern:
    1. First, try to find an org-specific template
    2. If not found, fall back to system template (organization_id=None)

    Args:
        session: Database session
        organization_id: Organization UUID string
        code: Template code (e.g., 'welcome_email', 'password_reset')
        channel: Channel type ('email', 'sms', 'whatsapp', 'in_app')

    Returns:
        The NotificationTemplate or None if not found
    """
    org_uuid = UUID(organization_id)

    # First try organization-specific template
    result = await session.execute(
        select(NotificationTemplate).where(
            NotificationTemplate.organization_id == org_uuid,
            NotificationTemplate.code == code,
            NotificationTemplate.channel == channel,
            NotificationTemplate.is_active.is_(True),
            NotificationTemplate.deleted_time.is_(None),
        )
    )
    template = result.scalars().first()

    if template:
        return template

    # Fall back to system template
    result = await session.execute(
        select(NotificationTemplate).where(
            NotificationTemplate.organization_id.is_(None),
            NotificationTemplate.code == code,
            NotificationTemplate.channel == channel,
            NotificationTemplate.is_active.is_(True),
            NotificationTemplate.deleted_time.is_(None),
        )
    )
    return result.scalars().first()


async def get_templates(
    session: AsyncSession,
    organization_id: str,
    filters: Optional[list[FilterSpec]] = None,
    sorts: Optional[list[SortSpec]] = None,
    limit: int = 100,
    offset: int = 0,
) -> tuple[list[NotificationTemplate], int]:
    """
    Get all templates available to an organization with SDL filtering and sorting.

    Returns both organization-specific templates and system templates.

    Args:
        session: Database session
        organization_id: Organization UUID string
        filters: List of FilterSpec objects for filtering
        sorts: List of SortSpec objects for sorting
        limit: Maximum number of results
        offset: Number of results to skip

    Returns:
        Tuple of (list of templates, total count)
    """
    org_uuid = UUID(organization_id)

    # Build base query - include both org templates and system templates
    base_query = select(NotificationTemplate).where(
        or_(
            NotificationTemplate.organization_id == org_uuid,
            NotificationTemplate.organization_id.is_(None),
        ),
        NotificationTemplate.is_active.is_(True),
        NotificationTemplate.deleted_time.is_(None),
    )

    # Apply SDL filters
    if filters:
        base_query = apply_filters(
            base_query, NotificationTemplate, filters, TEMPLATE_FIELD_MAPPING
        )

    # Get total count before pagination
    total_count = await get_total_count(session, base_query)

    # Apply sorting (default to org templates first, then by code)
    if sorts:
        base_query = apply_sort(
            base_query, NotificationTemplate, sorts, TEMPLATE_FIELD_MAPPING
        )
    else:
        base_query = base_query.order_by(
            NotificationTemplate.organization_id.desc().nulls_last(),
            NotificationTemplate.code.asc(),
        )

    # Apply pagination
    data_query = apply_pagination(base_query, limit, offset)

    result = await session.execute(data_query)
    templates = result.scalars().all()

    return list(templates), total_count


async def get_template_by_id(
    session: AsyncSession,
    template_id: str,
    organization_id: str,
) -> Optional[NotificationTemplate]:
    """
    Get template by ID within organization context.

    Returns the template if it belongs to the organization or is a system template.

    Args:
        session: Database session
        template_id: Template UUID string
        organization_id: Organization UUID string

    Returns:
        The NotificationTemplate or None if not found
    """
    org_uuid = UUID(organization_id)
    tmpl_uuid = UUID(template_id)

    result = await session.execute(
        select(NotificationTemplate).where(
            NotificationTemplate.id == tmpl_uuid,
            or_(
                NotificationTemplate.organization_id == org_uuid,
                NotificationTemplate.organization_id.is_(None),
            ),
            NotificationTemplate.deleted_time.is_(None),
        )
    )
    return result.scalars().first()


async def create_template(
    session: AsyncSession,
    organization_id: str,
    template_data: dict[str, Any],
) -> NotificationTemplate:
    """
    Create an organization-specific template.

    Args:
        session: Database session
        organization_id: Organization UUID string
        template_data: Template data including:
            - code: Template code (required)
            - name: Template name (required)
            - channel: Channel type (required)
            - body_text: Text body (required)
            - description: Description (optional)
            - subject: Email subject (optional)
            - body_html: HTML body for email (optional)
            - variables: JSON schema for template variables (optional)
            - is_active: Whether template is active (default: True)

    Returns:
        The created NotificationTemplate

    Raises:
        ValueError: If template with same code/channel already exists for organization
    """
    org_uuid = UUID(organization_id)

    # Check if template with same code and channel exists for this org
    existing_result = await session.execute(
        select(NotificationTemplate).where(
            NotificationTemplate.organization_id == org_uuid,
            NotificationTemplate.code == template_data["code"],
            NotificationTemplate.channel == template_data["channel"],
            NotificationTemplate.deleted_time.is_(None),
        )
    )
    existing = existing_result.scalars().first()

    if existing:
        raise ValueError(
            f"Template with code '{template_data['code']}' and channel "
            f"'{template_data['channel']}' already exists for this organization"
        )

    template = NotificationTemplate(
        organization_id=org_uuid,
        code=template_data["code"],
        name=template_data["name"],
        description=template_data.get("description"),
        channel=template_data["channel"],
        subject=template_data.get("subject"),
        body_text=template_data["body_text"],
        body_html=template_data.get("body_html"),
        variables=template_data.get("variables"),
        is_active=template_data.get("is_active", True),
    )

    session.add(template)
    try:
        await session.commit()
        await session.refresh(template)
    except Exception as e:
        await session.rollback()
        raise e

    return template


async def update_template(
    session: AsyncSession,
    template_id: str,
    organization_id: str,
    template_data: dict[str, Any],
) -> Optional[NotificationTemplate]:
    """
    Update an organization-specific template.

    Only org-specific templates can be updated. System templates are read-only.

    Args:
        session: Database session
        template_id: Template UUID string
        organization_id: Organization UUID string
        template_data: Fields to update (all optional):
            - name, description, subject, body_text, body_html, variables, is_active

    Returns:
        The updated NotificationTemplate or None if not found

    Raises:
        ValueError: If trying to update a system template
    """
    org_uuid = UUID(organization_id)
    tmpl_uuid = UUID(template_id)

    result = await session.execute(
        select(NotificationTemplate).where(
            NotificationTemplate.id == tmpl_uuid,
            NotificationTemplate.deleted_time.is_(None),
        )
    )
    template = result.scalars().first()

    if not template:
        return None

    # Check if this is a system template (cannot be updated by org)
    if template.organization_id is None:
        raise ValueError(
            "System templates cannot be modified. Create an org-specific override instead."
        )

    # Check if template belongs to this organization
    if template.organization_id != org_uuid:
        return None

    # Update allowed fields
    updatable_fields = [
        "name",
        "description",
        "subject",
        "body_text",
        "body_html",
        "variables",
        "is_active",
    ]
    for field in updatable_fields:
        if field in template_data:
            setattr(template, field, template_data[field])

    try:
        await session.commit()
        await session.refresh(template)
    except Exception as e:
        await session.rollback()
        raise e

    return template


async def delete_template(
    session: AsyncSession,
    template_id: str,
    organization_id: str,
) -> Optional[NotificationTemplate]:
    """
    Soft delete an organization-specific template.

    Only org-specific templates can be deleted. System templates are protected.

    Args:
        session: Database session
        template_id: Template UUID string
        organization_id: Organization UUID string

    Returns:
        The deleted NotificationTemplate or None if not found

    Raises:
        ValueError: If trying to delete a system template
    """
    org_uuid = UUID(organization_id)
    tmpl_uuid = UUID(template_id)

    result = await session.execute(
        select(NotificationTemplate).where(
            NotificationTemplate.id == tmpl_uuid,
            NotificationTemplate.deleted_time.is_(None),
        )
    )
    template = result.scalars().first()

    if not template:
        return None

    # Check if this is a system template
    if template.organization_id is None:
        raise ValueError("System templates cannot be deleted.")

    # Check if template belongs to this organization
    if template.organization_id != org_uuid:
        return None

    template.deleted_time = datetime.now(timezone.utc)

    try:
        await session.commit()
        await session.refresh(template)
    except Exception as e:
        await session.rollback()
        raise e

    return template


# Admin-only functions for system templates


async def create_system_template(
    session: AsyncSession,
    template_data: dict[str, Any],
) -> NotificationTemplate:
    """
    Create a system template (admin only).

    Args:
        session: Database session
        template_data: Template data (same as create_template)

    Returns:
        The created NotificationTemplate

    Raises:
        ValueError: If template with same code/channel already exists
    """
    # Check if system template with same code and channel exists
    existing_result = await session.execute(
        select(NotificationTemplate).where(
            NotificationTemplate.organization_id.is_(None),
            NotificationTemplate.code == template_data["code"],
            NotificationTemplate.channel == template_data["channel"],
            NotificationTemplate.deleted_time.is_(None),
        )
    )
    existing = existing_result.scalars().first()

    if existing:
        raise ValueError(
            f"System template with code '{template_data['code']}' and channel "
            f"'{template_data['channel']}' already exists"
        )

    template = NotificationTemplate(
        organization_id=None,  # System template
        code=template_data["code"],
        name=template_data["name"],
        description=template_data.get("description"),
        channel=template_data["channel"],
        subject=template_data.get("subject"),
        body_text=template_data["body_text"],
        body_html=template_data.get("body_html"),
        variables=template_data.get("variables"),
        is_active=template_data.get("is_active", True),
    )

    session.add(template)
    try:
        await session.commit()
        await session.refresh(template)
    except Exception as e:
        await session.rollback()
        raise e

    return template


async def get_system_templates(
    session: AsyncSession,
    channel: Optional[str] = None,
    include_inactive: bool = False,
    limit: int = 100,
    offset: int = 0,
) -> tuple[list[NotificationTemplate], int]:
    """
    Get all system templates (admin only).

    Args:
        session: Database session
        channel: Filter by channel (optional)
        include_inactive: Include inactive templates
        limit: Maximum number of results
        offset: Number of results to skip

    Returns:
        Tuple of (list of templates, total count)
    """
    conditions: list[ColumnElement[bool]] = [
        NotificationTemplate.organization_id.is_(None),
        NotificationTemplate.deleted_time.is_(None),
    ]

    if not include_inactive:
        conditions.append(NotificationTemplate.is_active.is_(True))

    if channel:
        conditions.append(NotificationTemplate.channel == channel)

    base_query = select(NotificationTemplate).where(*conditions)

    # Count query - count directly on model with same conditions
    count_query = select(func.count(NotificationTemplate.id)).where(*conditions)
    count_result = await session.execute(count_query)
    total_count = count_result.scalar() or 0

    # Data query
    data_query = (
        base_query.order_by(
            NotificationTemplate.channel.asc(),
            NotificationTemplate.code.asc(),
        )
        .limit(limit)
        .offset(offset)
    )

    result = await session.execute(data_query)
    templates = result.scalars().all()

    return list(templates), total_count


async def update_system_template(
    session: AsyncSession,
    template_id: str,
    template_data: dict[str, Any],
) -> Optional[NotificationTemplate]:
    """
    Update a system template (admin only).

    Args:
        session: Database session
        template_id: Template UUID string
        template_data: Fields to update

    Returns:
        Updated NotificationTemplate or None if not found

    Raises:
        ValueError: If trying to update a non-system template
    """
    template_uuid = UUID(template_id)

    result = await session.execute(
        select(NotificationTemplate).where(
            NotificationTemplate.id == template_uuid,
            NotificationTemplate.deleted_time.is_(None),
        )
    )
    template = result.scalars().first()

    if not template:
        return None

    # Verify this is a system template
    if template.organization_id is not None:
        raise ValueError("This is not a system template")

    # Update allowed fields
    updatable_fields = [
        "name",
        "description",
        "channel",
        "subject",
        "body_text",
        "body_html",
        "variables",
        "is_active",
    ]

    for field in updatable_fields:
        if field in template_data:
            setattr(template, field, template_data[field])

    try:
        await session.commit()
        await session.refresh(template)
    except Exception as e:
        await session.rollback()
        raise e

    return template


async def delete_system_template(
    session: AsyncSession,
    template_id: str,
) -> Optional[NotificationTemplate]:
    """
    Soft delete a system template (admin only).

    Args:
        session: Database session
        template_id: Template UUID string

    Returns:
        Deleted NotificationTemplate or None if not found

    Raises:
        ValueError: If trying to delete a non-system template
    """
    template_uuid = UUID(template_id)

    result = await session.execute(
        select(NotificationTemplate).where(
            NotificationTemplate.id == template_uuid,
            NotificationTemplate.deleted_time.is_(None),
        )
    )
    template = result.scalars().first()

    if not template:
        return None

    # Verify this is a system template
    if template.organization_id is not None:
        raise ValueError("This is not a system template")

    template.deleted_time = datetime.now(timezone.utc)

    try:
        await session.commit()
        await session.refresh(template)
    except Exception as e:
        await session.rollback()
        raise e

    return template
