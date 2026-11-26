"""
SystemConfig API endpoints.

Super admin only endpoints for managing global system configuration.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from fastapi.requests import Request
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import CurrentUser, get_current_super_admin, get_session
from src.core.encryption import encrypt_field, mask_credential
from src.core.exceptions import create_http_exception
from src.core.response_codes import get_response_code
from src.crud.system_config import (
    delete_system_config,
    get_all_system_configs,
    get_system_config_by_key,
    update_system_config,
)
from src.serialisers.system_config import (
    CreateSystemConfigRequest,
    DeleteSystemConfigResponse,
    SystemConfigListResponse,
    SystemConfigResponse,
    UpdateSystemConfigRequest,
)
from src.services.audit import audit_service, get_client_ip, get_user_agent


# Keys that should be encrypted when stored
# These patterns are checked against lowercase key names using substring matching
ENCRYPTED_KEY_PATTERNS = [
    ".api_key",
    ".apikey",
    ".password",
    ".pass",
    ".secret",
    ".token",
    ".credential",
    ".private_key",
    ".privatekey",
    ".auth_key",
    ".authkey",
    ".encryption_key",
    ".client_secret",
    ".access_key",
    ".secret_key",
    ".license_key",
]


def _is_sensitive_key(key: str) -> bool:
    """Check if a config key should be encrypted."""
    key_lower = key.lower()
    return any(pattern in key_lower for pattern in ENCRYPTED_KEY_PATTERNS)


def _mask_sensitive_value(key: str, value: str) -> str:
    """Mask sensitive values for display."""
    if not value or not _is_sensitive_key(key):
        return value
    # Show masked value for encrypted fields
    masked = mask_credential(value, visible_chars=4) if len(value) > 8 else "********"
    return masked if masked else "********"


router = APIRouter(prefix="/admin/system-config", tags=["System Config"])


@router.get("", response_model=SystemConfigListResponse)
async def list_system_configs(
    current_user: Annotated[CurrentUser, Depends(get_current_super_admin)],
    session: Annotated[AsyncSession, Depends(get_session)],
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
):
    """
    List all system configuration entries (super admin only).
    """
    configs, total = await get_all_system_configs(session, limit=limit, offset=offset)

    config_responses = []
    for config in configs:
        updated_by_email = None
        if config.updated_by:
            updated_by_email = config.updated_by.email

        # Mask sensitive values in list view
        display_value = _mask_sensitive_value(config.key, config.value)

        config_responses.append(
            SystemConfigResponse(
                id=config.id,
                key=config.key,
                value=display_value,
                description=config.description,
                created_time=config.created_time,
                updated_time=config.updated_time,
                updated_by_user_id=config.updated_by_user_id,
                updated_by_email=updated_by_email,
                is_sensitive=_is_sensitive_key(config.key),
            )
        )

    return SystemConfigListResponse(
        items=config_responses,
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{key}", response_model=SystemConfigResponse)
async def get_system_config(
    key: str,
    current_user: Annotated[CurrentUser, Depends(get_current_super_admin)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """
    Get a single system config by key (super admin only).
    """
    config = await get_system_config_by_key(session, key, load_updated_by=True)

    if not config:
        raise create_http_exception(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="System config not found",
            detail_code="system_config.not_found",
        )

    updated_by_email = None
    if config.updated_by:
        updated_by_email = config.updated_by.email

    # Mask sensitive values
    display_value = _mask_sensitive_value(config.key, config.value)

    return SystemConfigResponse(
        id=config.id,
        key=config.key,
        value=display_value,
        description=config.description,
        created_time=config.created_time,
        updated_time=config.updated_time,
        updated_by_user_id=config.updated_by_user_id,
        updated_by_email=updated_by_email,
        is_sensitive=_is_sensitive_key(config.key),
    )


@router.post(
    "", response_model=SystemConfigResponse, status_code=status.HTTP_201_CREATED
)
async def create_system_config_endpoint(
    request_body: CreateSystemConfigRequest,
    http_request: Request,
    current_user: Annotated[CurrentUser, Depends(get_current_super_admin)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """
    Create a new system config (super admin only).
    """
    # Check if key already exists
    existing = await get_system_config_by_key(session, request_body.key)
    if existing:
        raise create_http_exception(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"System config with key '{request_body.key}' already exists",
            detail_code="system_config.already_exists",
        )

    # Encrypt sensitive values before storing
    value_to_store = request_body.value
    if _is_sensitive_key(request_body.key) and value_to_store:
        value_to_store = encrypt_field(value_to_store)

    config = await update_system_config(
        session=session,
        key=request_body.key,
        value=value_to_store,
        description=request_body.description,
        updated_by_user_id=str(current_user.id),
    )

    # Log audit event (mask sensitive values in audit log)
    audit_value = (
        _mask_sensitive_value(config.key, config.value)
        if _is_sensitive_key(config.key)
        else config.value
    )
    await audit_service.log_create(
        session=session,
        organization_id=current_user.organization_id,
        resource_type="SystemConfig",
        resource_id=str(config.id),
        resource_data={
            "key": config.key,
            "value": audit_value,
            "description": config.description,
        },
        actor_id=current_user.id,
        ip_address=get_client_ip(http_request),
        user_agent=get_user_agent(http_request),
    )

    # Return masked value for sensitive keys
    display_value = _mask_sensitive_value(config.key, config.value)

    return SystemConfigResponse(
        id=config.id,
        key=config.key,
        value=display_value,
        description=config.description,
        created_time=config.created_time,
        updated_time=config.updated_time,
        updated_by_user_id=config.updated_by_user_id,
        updated_by_email=current_user.email,
        is_sensitive=_is_sensitive_key(config.key),
    )


@router.put("/{key}", response_model=SystemConfigResponse)
async def update_system_config_endpoint(
    key: str,
    request_body: UpdateSystemConfigRequest,
    http_request: Request,
    current_user: Annotated[CurrentUser, Depends(get_current_super_admin)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """
    Update a system config by key (super admin only).
    Creates the config if it doesn't exist.
    """
    # Get old value for audit
    old_config = await get_system_config_by_key(session, key)
    old_values = None
    is_sensitive = _is_sensitive_key(key)
    if old_config:
        old_values = {
            "value": (
                _mask_sensitive_value(key, old_config.value)
                if is_sensitive
                else old_config.value
            ),
            "description": old_config.description,
        }

    # Encrypt sensitive values before storing
    value_to_store = request_body.value
    if is_sensitive and value_to_store:
        value_to_store = encrypt_field(value_to_store)

    config = await update_system_config(
        session=session,
        key=key,
        value=value_to_store,
        description=request_body.description,
        updated_by_user_id=str(current_user.id),
    )

    # Log audit event (mask sensitive values)
    audit_value = (
        _mask_sensitive_value(key, config.value) if is_sensitive else config.value
    )
    if old_values:
        await audit_service.log_update(
            session=session,
            organization_id=current_user.organization_id,
            resource_type="SystemConfig",
            resource_id=str(config.id),
            old_values=old_values,
            new_values={
                "value": audit_value,
                "description": config.description,
            },
            actor_id=current_user.id,
            ip_address=get_client_ip(http_request),
            user_agent=get_user_agent(http_request),
        )
    else:
        await audit_service.log_create(
            session=session,
            organization_id=current_user.organization_id,
            resource_type="SystemConfig",
            resource_id=str(config.id),
            resource_data={
                "key": config.key,
                "value": audit_value,
                "description": config.description,
            },
            actor_id=current_user.id,
            ip_address=get_client_ip(http_request),
            user_agent=get_user_agent(http_request),
        )

    # Return masked value
    display_value = _mask_sensitive_value(key, config.value)

    return SystemConfigResponse(
        id=config.id,
        key=config.key,
        value=display_value,
        description=config.description,
        created_time=config.created_time,
        updated_time=config.updated_time,
        updated_by_user_id=config.updated_by_user_id,
        updated_by_email=current_user.email,
        is_sensitive=is_sensitive,
    )


@router.delete("/{key}", response_model=DeleteSystemConfigResponse)
async def delete_system_config_endpoint(
    key: str,
    http_request: Request,
    current_user: Annotated[CurrentUser, Depends(get_current_super_admin)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """
    Delete a system config by key (super admin only).
    """
    # Get config for audit
    config = await get_system_config_by_key(session, key)
    if not config:
        raise create_http_exception(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="System config not found",
            detail_code="system_config.not_found",
        )

    config_id = str(config.id)
    is_sensitive = _is_sensitive_key(config.key)
    old_values = {
        "key": config.key,
        "value": (
            _mask_sensitive_value(config.key, config.value)
            if is_sensitive
            else config.value
        ),
        "description": config.description,
    }

    deleted = await delete_system_config(session, key)

    if not deleted:
        raise create_http_exception(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="System config not found",
            detail_code="system_config.not_found",
        )

    # Log audit event
    await audit_service.log_delete(
        session=session,
        organization_id=current_user.organization_id,
        resource_type="SystemConfig",
        resource_id=config_id,
        resource_data=old_values,
        actor_id=current_user.id,
        ip_address=get_client_ip(http_request),
        user_agent=get_user_agent(http_request),
    )

    return DeleteSystemConfigResponse(
        message="System config deleted successfully",
        message_code=get_response_code("system_config.deleted"),
    )
