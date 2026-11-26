"""
API Key Rate Limit management endpoints.
Super-admin-only endpoints for configuring rate limits per permission type.
"""

import traceback
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import CurrentUser, get_current_super_admin, get_session
from src.core.exceptions import create_http_exception
from src.core.response_codes import get_response_code
from src.crud.api_key_rate_limit import (
    create_rate_limit,
    delete_rate_limit,
    get_all_rate_limits,
    update_rate_limit,
)
from src.logger.logger import Logger
from src.serialisers.api_key_rate_limit import (
    CreateRateLimitRequest,
    CreateRateLimitResponse,
    DeleteRateLimitResponse,
    RateLimitListResponse,
    RateLimitResponse,
    UpdateRateLimitRequest,
    UpdateRateLimitResponse,
)
from src.services.audit import audit_service, get_client_ip, get_user_agent


router = APIRouter(prefix="/admin/api-key-rate-limits", tags=["admin", "api-keys"])


@router.post("", response_model=CreateRateLimitResponse)
async def create_rate_limit_endpoint(
    request_body: CreateRateLimitRequest,
    http_request: Request,
    current_user: Annotated[CurrentUser, Depends(get_current_super_admin)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """Create a new rate limit configuration for a permission type."""
    try:
        new_rate_limit = await create_rate_limit(
            session=session,
            permission_code=request_body.permission_code,
            requests_per_minute=request_body.requests_per_minute,
            burst_limit=request_body.burst_limit,
        )

        # Log audit event
        await audit_service.log_create(
            session=session,
            organization_id=current_user.organization_id,
            resource_type="ApiKeyRateLimit",
            resource_id=str(new_rate_limit.id),
            actor_id=current_user.id,
            ip_address=get_client_ip(http_request),
            user_agent=get_user_agent(http_request),
            resource_data={
                "permission_code": new_rate_limit.permission_code,
                "requests_per_minute": new_rate_limit.requests_per_minute,
                "burst_limit": new_rate_limit.burst_limit,
            },
        )

        response = RateLimitResponse(
            id=new_rate_limit.id,
            permission_code=new_rate_limit.permission_code,
            requests_per_minute=new_rate_limit.requests_per_minute,
            burst_limit=new_rate_limit.burst_limit,
            created_time=(
                new_rate_limit.created_time.isoformat()
                if new_rate_limit.created_time
                else ""
            ),
            updated_time=(
                new_rate_limit.updated_time.isoformat()
                if new_rate_limit.updated_time
                else ""
            ),
        )
        return CreateRateLimitResponse(
            message="Rate limit created successfully",
            message_code=get_response_code("rate_limit.created"),
            rate_limit=response,
        )
    except ValueError as e:
        raise create_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
            detail_code="common.validation_error",
        )
    except Exception as e:
        error_tb = traceback.format_exc()
        Logger.error(f"Failed to create rate limit: {e}\n{error_tb}")
        http_request.state.error_traceback = error_tb
        raise create_http_exception(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
            detail_code="common.internal_error",
        )


@router.get("", response_model=RateLimitListResponse)
async def list_rate_limits_endpoint(
    http_request: Request,
    current_user: Annotated[CurrentUser, Depends(get_current_super_admin)],
    session: Annotated[AsyncSession, Depends(get_session)],
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
):
    """List all rate limit configurations."""
    try:
        rate_limits, total = await get_all_rate_limits(
            session=session, limit=limit, offset=offset
        )
        rate_limit_responses = [
            RateLimitResponse(
                id=rl.id,
                permission_code=rl.permission_code,
                requests_per_minute=rl.requests_per_minute,
                burst_limit=rl.burst_limit,
                created_time=rl.created_time.isoformat() if rl.created_time else "",
                updated_time=rl.updated_time.isoformat() if rl.updated_time else "",
            )
            for rl in rate_limits
        ]
        return RateLimitListResponse(
            items=rate_limit_responses, total=total, limit=limit, offset=offset
        )
    except Exception as e:
        error_tb = traceback.format_exc()
        Logger.error(f"Failed to list rate limits: {e}\n{error_tb}")
        http_request.state.error_traceback = error_tb
        raise create_http_exception(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
            detail_code="common.internal_error",
        )


@router.patch("/{rate_limit_id}", response_model=UpdateRateLimitResponse)
async def update_rate_limit_endpoint(
    rate_limit_id: str,
    request_body: UpdateRateLimitRequest,
    http_request: Request,
    current_user: Annotated[CurrentUser, Depends(get_current_super_admin)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """Update a rate limit configuration."""
    try:
        updated_rate_limit = await update_rate_limit(
            session=session,
            rate_limit_id=rate_limit_id,
            requests_per_minute=request_body.requests_per_minute,
            burst_limit=request_body.burst_limit,
        )

        # Log audit event
        new_values = {}
        if request_body.requests_per_minute is not None:
            new_values["requests_per_minute"] = updated_rate_limit.requests_per_minute
        if request_body.burst_limit is not None:
            new_values["burst_limit"] = updated_rate_limit.burst_limit

        await audit_service.log_update(
            session=session,
            organization_id=current_user.organization_id,
            resource_type="ApiKeyRateLimit",
            resource_id=str(updated_rate_limit.id),
            old_values={},
            new_values=new_values,
            actor_id=current_user.id,
            ip_address=get_client_ip(http_request),
            user_agent=get_user_agent(http_request),
        )

        response = RateLimitResponse(
            id=updated_rate_limit.id,
            permission_code=updated_rate_limit.permission_code,
            requests_per_minute=updated_rate_limit.requests_per_minute,
            burst_limit=updated_rate_limit.burst_limit,
            created_time=(
                updated_rate_limit.created_time.isoformat()
                if updated_rate_limit.created_time
                else ""
            ),
            updated_time=(
                updated_rate_limit.updated_time.isoformat()
                if updated_rate_limit.updated_time
                else ""
            ),
        )
        return UpdateRateLimitResponse(
            message="Rate limit updated successfully",
            message_code=get_response_code("rate_limit.updated"),
            rate_limit=response,
        )
    except ValueError as e:
        raise create_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
            detail_code="common.validation_error",
        )
    except HTTPException:
        raise
    except Exception as e:
        error_tb = traceback.format_exc()
        Logger.error(f"Failed to update rate limit: {e}\n{error_tb}")
        http_request.state.error_traceback = error_tb
        raise create_http_exception(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
            detail_code="common.internal_error",
        )


@router.delete("/{rate_limit_id}", response_model=DeleteRateLimitResponse)
async def delete_rate_limit_endpoint(
    rate_limit_id: str,
    http_request: Request,
    current_user: Annotated[CurrentUser, Depends(get_current_super_admin)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """Delete a rate limit configuration."""
    try:
        deleted_rate_limit = await delete_rate_limit(
            session=session, rate_limit_id=rate_limit_id
        )

        # Log audit event
        await audit_service.log_delete(
            session=session,
            organization_id=current_user.organization_id,
            resource_type="ApiKeyRateLimit",
            resource_id=str(deleted_rate_limit.id),
            actor_id=current_user.id,
            ip_address=get_client_ip(http_request),
            user_agent=get_user_agent(http_request),
            resource_data={
                "permission_code": deleted_rate_limit.permission_code,
                "requests_per_minute": deleted_rate_limit.requests_per_minute,
                "burst_limit": deleted_rate_limit.burst_limit,
            },
        )

        return DeleteRateLimitResponse(
            message="Rate limit deleted successfully",
            message_code=get_response_code("rate_limit.deleted"),
            rate_limit_id=str(deleted_rate_limit.id),
        )
    except ValueError as e:
        raise create_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
            detail_code="common.validation_error",
        )
    except HTTPException:
        raise
    except Exception as e:
        error_tb = traceback.format_exc()
        Logger.error(f"Failed to delete rate limit: {e}\n{error_tb}")
        http_request.state.error_traceback = error_tb
        raise create_http_exception(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
            detail_code="common.internal_error",
        )
