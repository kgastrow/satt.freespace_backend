"""
Audit logging service for tracking CRUD operations.

This service provides helper functions to log audit events from API endpoints.
"""

from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

# Re-exported for the ~30 modules that import get_client_ip from here; see the
# note further down for why the implementation moved.
from src.core.client_ip import get_client_ip  # noqa: F401
from src.crud.audit_log import compute_changes, create_audit_log
from src.logger.logger import Logger
from src.models.audit_log import AuditAction


def extract_resource_name(
    resource_type: str, resource_data: Optional[dict]
) -> Optional[str]:
    """
    Extract human-readable name based on resource type.

    Args:
        resource_type: Type of resource (e.g., 'User', 'Role')
        resource_data: Dictionary of resource fields

    Returns:
        Human-readable name for the resource, or None if not found
    """
    if not resource_data:
        return None

    # Map resource types to their name fields (in priority order)
    name_fields = {
        "User": ["email"],
        "Organization": ["name"],
        "Role": ["name"],
        "File": ["filename", "original_filename"],
        "ApiKey": ["name"],
        "FeatureFlag": ["code"],
        "Announcement": ["title"],
        "HelpArticle": ["title"],
        "HelpCategory": ["name"],
        "CronJob": ["name", "code"],
        "NotificationTemplate": ["code"],
        "SsoProvider": ["name"],
    }

    # Get fields to check for this resource type, or use defaults
    fields_to_check = name_fields.get(resource_type, ["name", "title", "email", "code"])

    for field in fields_to_check:
        if field in resource_data and resource_data[field]:
            return str(resource_data[field])

    return None


class AuditService:
    """
    Service for logging audit events.

    Usage:
        await audit_service.log_create(
            session=session,
            organization_id=current_user.organization_id,
            actor_id=current_user.id,
            resource_type="User",
            resource_id=str(new_user.id),
            ip_address=request.client.host,
        )
    """

    async def log_action(
        self,
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
    ) -> None:
        """
        Log an audit event.

        Args:
            session: Database session
            organization_id: Organization UUID string
            action: The action performed
            resource_type: Type of resource (e.g., 'User', 'Role')
            resource_id: UUID of the affected resource
            actor_id: UUID of the user who performed the action
            changes: Dictionary of changes for UPDATE actions
            ip_address: IP address of the request
            user_agent: User agent string
            impersonated_by: UUID of super admin who was impersonating (optional)
            resource_name: Human-readable name of the resource
            resource_context: Additional context captured at audit time
        """
        try:
            await create_audit_log(
                session=session,
                organization_id=organization_id,
                action=action,
                resource_type=resource_type,
                resource_id=resource_id,
                actor_id=actor_id,
                changes=changes,
                ip_address=ip_address,
                user_agent=user_agent,
                impersonated_by=impersonated_by,
                resource_name=resource_name,
                resource_context=resource_context,
            )
            impersonation_suffix = (
                f" (impersonated by {impersonated_by})" if impersonated_by else ""
            )
            Logger.debug(
                f"Audit: {action.value} {resource_type}:{resource_id} by {actor_id or 'system'}{impersonation_suffix}"
            )
        except Exception as e:
            # Don't fail the main operation if audit logging fails
            Logger.error(f"Failed to create audit log: {e}")

    async def log_create(
        self,
        session: AsyncSession,
        organization_id: str,
        resource_type: str,
        resource_id: str,
        actor_id: Optional[str] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        resource_data: Optional[dict] = None,
        impersonated_by: Optional[str] = None,
        resource_context: Optional[dict] = None,
    ) -> None:
        """
        Log a CREATE action.

        Args:
            session: Database session
            organization_id: Organization UUID string
            resource_type: Type of resource created
            resource_id: UUID of the new resource
            actor_id: UUID of the user who created it
            ip_address: IP address of the request
            user_agent: User agent string
            resource_data: Optional dict of resource fields (passwords will be redacted)
            impersonated_by: UUID of super admin who was impersonating (optional)
            resource_context: Additional context to store with the audit log
        """
        changes = None
        if resource_data:
            # For create, show new values only
            changes = {k: {"old": None, "new": v} for k, v in resource_data.items()}
            # Redact sensitive fields
            for key in list(changes.keys()):
                if "password" in key.lower():
                    changes[key] = {"old": None, "new": "[REDACTED]"}

        # Extract resource name from resource data
        resource_name = extract_resource_name(resource_type, resource_data)

        await self.log_action(
            session=session,
            organization_id=organization_id,
            action=AuditAction.CREATE,
            resource_type=resource_type,
            resource_id=resource_id,
            actor_id=actor_id,
            changes=changes,
            ip_address=ip_address,
            user_agent=user_agent,
            impersonated_by=impersonated_by,
            resource_name=resource_name,
            resource_context=resource_context,
        )

    async def log_update(
        self,
        session: AsyncSession,
        organization_id: str,
        resource_type: str,
        resource_id: str,
        old_values: dict,
        new_values: dict,
        actor_id: Optional[str] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        impersonated_by: Optional[str] = None,
        resource_context: Optional[dict] = None,
    ) -> None:
        """
        Log an UPDATE action with change tracking.

        Args:
            session: Database session
            organization_id: Organization UUID string
            resource_type: Type of resource updated
            resource_id: UUID of the updated resource
            old_values: Dict of old field values
            new_values: Dict of new field values
            actor_id: UUID of the user who updated it
            ip_address: IP address of the request
            user_agent: User agent string
            impersonated_by: UUID of super admin who was impersonating (optional)
            resource_context: Additional context to store with the audit log
        """
        changes = compute_changes(old_values, new_values)

        # Only log if there are actual changes
        if not changes:
            return

        # Extract resource name from new values (use updated name if available)
        resource_name = extract_resource_name(resource_type, new_values)

        await self.log_action(
            session=session,
            organization_id=organization_id,
            action=AuditAction.UPDATE,
            resource_type=resource_type,
            resource_id=resource_id,
            actor_id=actor_id,
            changes=changes,
            ip_address=ip_address,
            user_agent=user_agent,
            impersonated_by=impersonated_by,
            resource_name=resource_name,
            resource_context=resource_context,
        )

    async def log_delete(
        self,
        session: AsyncSession,
        organization_id: str,
        resource_type: str,
        resource_id: str,
        actor_id: Optional[str] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        resource_data: Optional[dict] = None,
        impersonated_by: Optional[str] = None,
        resource_context: Optional[dict] = None,
    ) -> None:
        """
        Log a DELETE action.

        Args:
            session: Database session
            organization_id: Organization UUID string
            resource_type: Type of resource deleted
            resource_id: UUID of the deleted resource
            actor_id: UUID of the user who deleted it
            ip_address: IP address of the request
            user_agent: User agent string
            resource_data: Optional dict of resource fields before deletion
            impersonated_by: UUID of super admin who was impersonating (optional)
            resource_context: Additional context to store with the audit log
        """
        changes = None
        if resource_data:
            # For delete, show old values only
            changes = {k: {"old": v, "new": None} for k, v in resource_data.items()}
            # Redact sensitive fields
            for key in list(changes.keys()):
                if "password" in key.lower():
                    changes[key] = {"old": "[REDACTED]", "new": None}

        # Extract resource name from resource data before deletion
        resource_name = extract_resource_name(resource_type, resource_data)

        await self.log_action(
            session=session,
            organization_id=organization_id,
            action=AuditAction.DELETE,
            resource_type=resource_type,
            resource_id=resource_id,
            actor_id=actor_id,
            changes=changes,
            ip_address=ip_address,
            user_agent=user_agent,
            impersonated_by=impersonated_by,
            resource_name=resource_name,
            resource_context=resource_context,
        )


# Client IP resolution now lives in src/core/client_ip.py -- there must be
# exactly one answer to "who sent this request", because the same value keys
# the login/2FA lockout as well as audit metadata.
#
# The old implementation here read X-Forwarded-For[0] with no trusted-proxy
# check. X-Forwarded-For is APPENDED to by proxies, so its leftmost entry is
# whatever the client sent: anyone could forge their own audit trail, rotate
# the header to defeat the brute-force lockout entirely, or send a victim's
# address to get that victim locked out. See src/core/client_ip.py.
#
# Re-exported rather than moved so the ~30 modules that do
# ``from src.services.audit import get_client_ip`` keep working.


def get_user_agent(request) -> Optional[str]:
    """
    Extract user agent from request.

    Args:
        request: FastAPI Request object

    Returns:
        User agent string or None
    """
    return request.headers.get("User-Agent")


# Singleton instance
audit_service = AuditService()
