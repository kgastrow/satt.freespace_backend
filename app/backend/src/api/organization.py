"""
Organization management API endpoints.
Migrated to FastAPI with async/await patterns.
"""

import traceback
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import (
    CurrentUser,
    get_current_super_admin,
    get_current_user,
    get_session,
    require_permission,
)
from src.core.exceptions import create_http_exception
from src.core.response_codes import get_response_code
from src.crud.organization import (
    can_hard_delete_organization,
    cancel_organization_deletion_request,
    create_organization,
    delete_organization,
    get_organization_by_id,
    get_organization_deletion_request,
    get_organization_details,
    get_organizations,
    get_retention_days,
    hard_delete_organization,
    request_organization_deletion,
    update_organization,
    update_organization_details,
)
from src.crud.organization_member import (
    get_organization_member_count,
    get_organization_members,
    remove_user_from_organization,
)
from src.crud.user import get_user_by_id
from src.crud.user_role import user_has_role
from src.logger.logger import Logger
from src.models.organization import Organization
from src.serialisers.organization import (
    CancelDeletionResponse,
    CreateOrganizationRequest,
    CreateOrganizationResponse,
    DeleteOrganizationResponse,
    GetOrganizationDetailsResponse,
    GetOrganizationResponse,
    HardDeleteResponse,
    HardDeleteStatusResponse,
    ListOrganizationsResponse,
    MemberCountResponse,
    RemoveMemberResponse,
    RequestDeletionResponse,
    UpdateOrganizationAPIRequest,
    UpdateOrganizationDetailsRequest,
    UpdateOrganizationResponse,
)
from src.serialisers.organization_member import (
    ListOrganizationMembersResponse,
    OrganizationMemberResponse,
)
from src.services.audit import audit_service, get_client_ip, get_user_agent


router = APIRouter(prefix="/organizations", tags=["organizations"])


def _build_organization_response(
    org: Organization, deletion_request=None
) -> GetOrganizationResponse:
    """Helper to build GetOrganizationResponse with deletion status."""
    return GetOrganizationResponse(
        id=str(org.id),
        name=org.name,
        slug=org.slug,
        is_active=org.is_active,
        created_time=org.created_time.isoformat(),
        updated_time=org.updated_time.isoformat(),
        deletion_requested=deletion_request is not None,
        deletion_requested_time=(
            deletion_request.created_time.isoformat() if deletion_request else None
        ),
    )


@router.post("", response_model=CreateOrganizationResponse)
async def create_organization_endpoint(
    request: CreateOrganizationRequest,
    http_request: Request,
    current_user: Annotated[CurrentUser, Depends(get_current_super_admin)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """Create a new organization (super admin only)"""
    try:
        new_org = await create_organization(
            session=session, request=request.model_dump()
        )

        # Log audit event
        await audit_service.log_create(
            session=session,
            organization_id=current_user.organization_id,
            resource_type="Organization",
            resource_id=str(new_org.id),
            actor_id=current_user.id,
            ip_address=get_client_ip(http_request),
            user_agent=get_user_agent(http_request),
            resource_data={
                "name": new_org.name,
                "slug": new_org.slug,
                "is_active": new_org.is_active,
            },
        )

        Logger.info("Organization created: id=%s", new_org.id)

        return CreateOrganizationResponse(
            message="Organization created successfully",
            message_code=get_response_code("organization.created"),
            organization=_build_organization_response(new_org),
        )
    except ValueError as e:
        raise create_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
            detail_code="common.validation_error",
        )
    except Exception as e:
        error_tb = traceback.format_exc()
        Logger.error(f"Error creating organization: {e}\n{error_tb}")
        http_request.state.error_traceback = error_tb
        raise create_http_exception(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
            detail_code="common.internal_error",
        )


@router.get("", response_model=ListOrganizationsResponse)
async def list_organizations_endpoint(
    current_user: Annotated[CurrentUser, Depends(get_current_super_admin)],
    session: Annotated[AsyncSession, Depends(get_session)],
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    """List all organizations (super admin only)"""
    organizations, total = await get_organizations(
        session=session, limit=limit, offset=offset
    )

    # Fetch deletion requests for all organizations
    org_responses = []
    for org in organizations:
        deletion_request = await get_organization_deletion_request(
            session=session, org_id=str(org.id)
        )
        org_responses.append(_build_organization_response(org, deletion_request))

    return ListOrganizationsResponse(
        items=org_responses, total=total, limit=limit, offset=offset
    )


@router.get("/{org_id}", response_model=GetOrganizationResponse)
async def get_organization_endpoint(
    org_id: str,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """Get organization by ID"""
    try:
        organization_id = current_user.organization_id

        # Allow if user belongs to org OR is super admin
        if current_user.is_admin:
            # Super admin can view any organization
            organization = await get_organization_by_id(session=session, org_id=org_id)
        elif org_id == organization_id:
            # User can view their own organization
            organization = await get_organization_by_id(session=session, org_id=org_id)
        else:
            raise create_http_exception(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Unauthorized access",
                detail_code="common.forbidden",
            )

        if not organization:
            raise create_http_exception(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Organization not found",
                detail_code="organization.not_found",
            )

        # Get deletion request if exists
        deletion_request = await get_organization_deletion_request(
            session=session, org_id=org_id
        )

        return _build_organization_response(organization, deletion_request)
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
        Logger.error(f"Error getting organization: {e}\n{error_tb}")
        raise create_http_exception(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
            detail_code="common.internal_error",
        )


@router.put("/{org_id}", response_model=UpdateOrganizationResponse)
async def update_organization_endpoint(
    org_id: str,
    request: UpdateOrganizationAPIRequest,
    http_request: Request,
    current_user: Annotated[CurrentUser, Depends(get_current_super_admin)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """Update organization (super admin only)"""
    try:
        # Get current state for change tracking
        existing_org = await get_organization_by_id(session=session, org_id=org_id)
        if not existing_org:
            raise create_http_exception(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Organization not found",
                detail_code="organization.not_found",
            )
        old_values = {
            "name": existing_org.name,
            "slug": existing_org.slug,
            "is_active": existing_org.is_active,
        }

        update_data = request.model_dump(exclude_unset=True)
        update_data["id"] = org_id
        updated_org = await update_organization(session=session, request=update_data)

        # Log audit event
        new_values = {
            "name": updated_org.name,
            "slug": updated_org.slug,
            "is_active": updated_org.is_active,
        }
        await audit_service.log_update(
            session=session,
            organization_id=current_user.organization_id,
            resource_type="Organization",
            resource_id=str(updated_org.id),
            old_values=old_values,
            new_values=new_values,
            actor_id=current_user.id,
            ip_address=get_client_ip(http_request),
            user_agent=get_user_agent(http_request),
        )

        Logger.info("Organization updated: id=%s", updated_org.id)

        return UpdateOrganizationResponse(
            message="Organization updated successfully",
            message_code=get_response_code("organization.updated"),
            organization=_build_organization_response(updated_org),
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
        Logger.error(f"Error updating organization: {e}\n{error_tb}")
        http_request.state.error_traceback = error_tb
        raise create_http_exception(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
            detail_code="common.internal_error",
        )


@router.delete("/{org_id}", response_model=DeleteOrganizationResponse)
async def delete_organization_endpoint(
    org_id: str,
    http_request: Request,
    current_user: Annotated[CurrentUser, Depends(get_current_super_admin)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """Delete organization (super admin only)"""
    try:
        # Get org data before deletion for audit log
        existing_org = await get_organization_by_id(session=session, org_id=org_id)
        if not existing_org:
            raise create_http_exception(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Organization not found",
                detail_code="organization.not_found",
            )
        org_data = {"name": existing_org.name, "slug": existing_org.slug}

        deleted_org = await delete_organization(session=session, org_id=org_id)

        # Log audit event
        await audit_service.log_delete(
            session=session,
            organization_id=current_user.organization_id,
            resource_type="Organization",
            resource_id=str(deleted_org.id),
            actor_id=current_user.id,
            ip_address=get_client_ip(http_request),
            user_agent=get_user_agent(http_request),
            resource_data=org_data,
        )

        Logger.info("Organization deleted: id=%s", deleted_org.id)

        return DeleteOrganizationResponse(
            message="Organization deleted successfully",
            message_code=get_response_code("organization.deleted"),
            organization_id=str(deleted_org.id),
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
        Logger.error(f"Error deleting organization: {e}\n{error_tb}")
        http_request.state.error_traceback = error_tb
        raise create_http_exception(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
            detail_code="common.internal_error",
        )


# Organization Member Management Endpoints


@router.get("/{org_id}/members", response_model=ListOrganizationMembersResponse)
async def list_organization_members_endpoint(
    org_id: str,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    """List all members of an organization. Requires user_admin role or super admin."""
    try:
        organization_id = current_user.organization_id

        # Authorization: user must be in the org and have user_admin role, OR be super admin
        if current_user.is_admin:
            # Super admin can view any organization's members
            target_org_id = org_id
        elif org_id == organization_id:
            # User is in this organization, check if they have admin role (uses cached roles)
            if not (current_user.has_role("owner") or current_user.has_role("admin")):
                raise create_http_exception(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Admin access required",
                    detail_code="common.forbidden",
                )
            target_org_id = org_id
        else:
            raise create_http_exception(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Unauthorized access",
                detail_code="common.forbidden",
            )

        members, total = await get_organization_members(
            session, target_org_id, limit, offset
        )

        member_responses = [
            OrganizationMemberResponse(
                id=str(member.id),
                email=member.email,
                email_verified=member.email_verified,
                is_admin=member.is_admin,
                created_time=(
                    member.created_time.isoformat() if member.created_time else ""
                ),
            )
            for member in members
        ]

        return ListOrganizationMembersResponse(
            items=member_responses, total=total, limit=limit, offset=offset
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
        Logger.error(f"Error listing organization members: {e}\n{error_tb}")
        raise create_http_exception(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
            detail_code="common.internal_error",
        )


@router.delete("/{org_id}/members/{user_id}", response_model=RemoveMemberResponse)
async def remove_organization_member_endpoint(
    org_id: str,
    user_id: str,
    http_request: Request,
    current_user: Annotated[CurrentUser, Depends(require_permission("users:delete"))],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """Remove a member from an organization. Requires users:delete permission."""
    try:
        organization_id = current_user.organization_id

        # Authorization: must be removing from own org OR be super admin
        if current_user.is_admin:
            # Super admin can remove from any organization
            target_org_id = org_id
        elif org_id == organization_id:
            # User is in this organization and has users:delete permission (checked by decorator)
            target_org_id = org_id
        else:
            raise create_http_exception(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Unauthorized access",
                detail_code="common.forbidden",
            )

        # Prevent removing yourself
        if current_user.id == user_id:
            raise create_http_exception(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot remove yourself from organization",
                detail_code="common.bad_request",
            )

        # Prevent removing organization owners - they can only be removed when the organization is deleted
        is_owner = await user_has_role(session, user_id, "owner", target_org_id)
        if is_owner:
            raise create_http_exception(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Cannot remove organization owner. The owner can only be removed by deleting the organization.",
                detail_code="common.forbidden",
            )

        # Get user data before removal for audit log
        user_to_remove = await get_user_by_id(session, user_id, target_org_id)
        user_data = {"email": user_to_remove.email} if user_to_remove else {}

        removed_user = await remove_user_from_organization(
            session, user_id, target_org_id
        )

        # Log audit event
        await audit_service.log_delete(
            session=session,
            organization_id=target_org_id,
            resource_type="OrganizationMember",
            resource_id=str(removed_user.id),
            actor_id=current_user.id,
            ip_address=get_client_ip(http_request),
            user_agent=get_user_agent(http_request),
            resource_data=user_data,
        )

        Logger.info(
            "Organization member removed: user_id=%s, org_id=%s",
            removed_user.id,
            target_org_id,
        )

        return RemoveMemberResponse(
            message="User removed from organization successfully",
            message_code=get_response_code("user.deleted"),
            user_id=str(removed_user.id),
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
        Logger.error(f"Error removing organization member: {e}\n{error_tb}")
        http_request.state.error_traceback = error_tb
        raise create_http_exception(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
            detail_code="common.internal_error",
        )


@router.get("/{org_id}/members/count", response_model=MemberCountResponse)
async def get_organization_member_count_endpoint(
    org_id: str,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """Get the count of active members in an organization."""
    try:
        organization_id = current_user.organization_id

        # Authorization: user must belong to org OR be super admin
        if current_user.is_admin:
            # Super admin can view any organization
            target_org_id = org_id
        elif org_id == organization_id:
            # User can view their own organization
            target_org_id = org_id
        else:
            raise create_http_exception(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Unauthorized access",
                detail_code="common.forbidden",
            )

        count = await get_organization_member_count(session, target_org_id)

        return MemberCountResponse(organization_id=target_org_id, member_count=count)
    except HTTPException:
        raise
    except Exception as e:
        error_tb = traceback.format_exc()
        Logger.error(f"Error getting organization member count: {e}\n{error_tb}")
        raise create_http_exception(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
            detail_code="common.internal_error",
        )


# Organization Deletion Request Endpoints


@router.post("/{org_id}/request-deletion", response_model=RequestDeletionResponse)
async def request_organization_deletion_endpoint(
    org_id: str,
    http_request: Request,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """
    Request deletion of an organization. Only organization owners can request deletion.
    This creates a deletion request record that indicates deletion has been requested.
    A super admin must approve and execute the actual deletion.
    """
    try:
        organization_id = current_user.organization_id

        # Must be requesting deletion for own organization
        if org_id != organization_id:
            raise create_http_exception(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Can only request deletion for your own organization",
                detail_code="common.forbidden",
            )

        # Must be organization owner
        is_owner = await user_has_role(
            session, current_user.id, "owner", organization_id
        )
        if not is_owner:
            raise create_http_exception(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only organization owners can request deletion",
                detail_code="common.forbidden",
            )

        deletion_request = await request_organization_deletion(
            session=session, org_id=org_id, requested_by_user_id=current_user.id
        )

        # Log audit event
        await audit_service.log_create(
            session=session,
            organization_id=organization_id,
            resource_type="OrganizationDeletionRequest",
            resource_id=str(deletion_request.id),
            actor_id=current_user.id,
            ip_address=get_client_ip(http_request),
            user_agent=get_user_agent(http_request),
            resource_data={"organization_id": org_id},
        )

        return RequestDeletionResponse(
            message="Organization deletion request submitted. A super admin will review and process the request.",
            message_code=get_response_code("organization.deleted"),
            organization_id=org_id,
            deletion_requested_time=deletion_request.created_time.isoformat(),
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
        Logger.error(f"Error requesting organization deletion: {e}\n{error_tb}")
        http_request.state.error_traceback = error_tb
        raise create_http_exception(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
            detail_code="common.internal_error",
        )


@router.delete("/{org_id}/request-deletion", response_model=CancelDeletionResponse)
async def cancel_organization_deletion_request_endpoint(
    org_id: str,
    http_request: Request,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """
    Cancel a pending deletion request for an organization.
    Only organization owners or super admins can cancel a deletion request.
    """
    try:
        organization_id = current_user.organization_id

        # Must be canceling for own organization OR be super admin
        if org_id != organization_id and not current_user.is_admin:
            raise create_http_exception(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Can only cancel deletion request for your own organization",
                detail_code="common.forbidden",
            )

        # Must be organization owner (unless super admin)
        if not current_user.is_admin:
            is_owner = await user_has_role(
                session, current_user.id, "owner", organization_id
            )
            if not is_owner:
                raise create_http_exception(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Only organization owners can cancel deletion requests",
                    detail_code="common.forbidden",
                )

        # Get the deletion request before canceling for audit log
        deletion_request = await get_organization_deletion_request(
            session=session, org_id=org_id
        )
        deletion_request_id = str(deletion_request.id) if deletion_request else None

        org = await cancel_organization_deletion_request(session=session, org_id=org_id)

        # Log audit event
        if deletion_request_id:
            await audit_service.log_delete(
                session=session,
                organization_id=org_id,
                resource_type="OrganizationDeletionRequest",
                resource_id=deletion_request_id,
                actor_id=current_user.id,
                ip_address=get_client_ip(http_request),
                user_agent=get_user_agent(http_request),
                resource_data={"organization_id": org_id},
            )

        return CancelDeletionResponse(
            message="Organization deletion request has been cancelled",
            message_code=get_response_code("common.success"),
            organization_id=str(org.id),
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
        Logger.error(f"Error canceling organization deletion request: {e}\n{error_tb}")
        http_request.state.error_traceback = error_tb
        raise create_http_exception(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
            detail_code="common.internal_error",
        )


@router.get("/{org_id}/hard-delete-status", response_model=HardDeleteStatusResponse)
async def get_hard_delete_status_endpoint(
    org_id: str,
    current_user: Annotated[CurrentUser, Depends(get_current_super_admin)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """
    Check if an organization can be hard-deleted.
    Returns the status including days remaining in retention period.
    Super admin only.
    """
    try:
        can_delete, days_remaining, deleted_time = await can_hard_delete_organization(
            session=session, org_id=org_id
        )
        retention_days = await get_retention_days(session)

        return HardDeleteStatusResponse(
            organization_id=org_id,
            can_hard_delete=can_delete,
            days_remaining=days_remaining,
            retention_days=retention_days,
            deleted_time=deleted_time.isoformat() if deleted_time else None,
        )
    except ValueError as e:
        raise create_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
            detail_code="common.validation_error",
        )
    except Exception as e:
        error_tb = traceback.format_exc()
        Logger.error(f"Error getting hard delete status: {e}\n{error_tb}")
        raise create_http_exception(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
            detail_code="common.internal_error",
        )


@router.delete("/{org_id}/hard-delete", response_model=HardDeleteResponse)
async def hard_delete_organization_endpoint(
    org_id: str,
    http_request: Request,
    current_user: Annotated[CurrentUser, Depends(get_current_super_admin)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """
    Permanently delete an organization and all its related data.

    This action is irreversible and will:
    - Delete all S3 files belonging to the organization
    - Delete all database records (users, files, notifications, etc.)
    - Delete audit logs
    - Delete the organization record

    Requirements:
    - Super admin only
    - Retention period must have passed (configurable via system config)

    The organization must either:
    - Have an active deletion request, OR
    - Already be soft-deleted
    """
    try:
        # Get org data before deletion for audit log
        existing_org = await get_organization_by_id(session=session, org_id=org_id)
        # For hard delete, we also check soft-deleted orgs
        if not existing_org:
            from uuid import UUID

            from sqlalchemy import select

            from src.models.organization import Organization

            result = await session.execute(
                select(Organization).where(Organization.id == UUID(org_id))
            )
            existing_org = result.scalars().first()

        if not existing_org:
            raise create_http_exception(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Organization not found",
                detail_code="organization.not_found",
            )

        org_name = existing_org.name

        # Perform hard delete
        stats = await hard_delete_organization(session=session, org_id=org_id)

        # Log audit event (to super admin's org since target org is deleted)
        await audit_service.log_delete(
            session=session,
            organization_id=current_user.organization_id,
            resource_type="Organization",
            resource_id=org_id,
            actor_id=current_user.id,
            ip_address=get_client_ip(http_request),
            user_agent=get_user_agent(http_request),
            resource_data={
                "name": org_name,
                "hard_delete": True,
                "s3_files_deleted": stats["s3_files_deleted"],
                "records_deleted": stats["records_deleted"],
            },
        )

        return HardDeleteResponse(
            message="Organization and all related data permanently deleted",
            message_code=get_response_code("organization.deleted"),
            organization_id=org_id,
            organization_name=org_name,
            s3_files_deleted=stats["s3_files_deleted"],
            records_deleted=stats["records_deleted"],
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
        Logger.error(f"Error hard deleting organization: {e}\n{error_tb}")
        http_request.state.error_traceback = error_tb
        raise create_http_exception(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
            detail_code="common.internal_error",
        )


# Organization Details Endpoints


@router.get("/{org_id}/details", response_model=GetOrganizationDetailsResponse)
async def get_organization_details_endpoint(
    org_id: str,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """
    Get organization details including contact info, address, and logo.

    Authorization: super admin can access any org, org admin/owner can access their org only.
    """
    try:
        organization_id = current_user.organization_id

        # Authorization: super admin OR user belongs to org and has admin/owner role
        if current_user.is_admin:
            # Super admin can view any organization
            target_org_id = org_id
        elif org_id == organization_id:
            # User is in this organization, check if they have admin or owner role
            if not (current_user.has_role("owner") or current_user.has_role("admin")):
                raise create_http_exception(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Admin or owner access required",
                    detail_code="common.forbidden",
                )
            target_org_id = org_id
        else:
            raise create_http_exception(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Unauthorized access",
                detail_code="common.forbidden",
            )

        org = await get_organization_details(session=session, org_id=target_org_id)

        return GetOrganizationDetailsResponse(
            id=str(org.id),
            name=org.name,
            slug=org.slug,
            display_name=org.display_name,
            physical_address_line1=org.physical_address_line1,
            physical_address_line2=org.physical_address_line2,
            city=org.city,
            state_province=org.state_province,
            postal_code=org.postal_code,
            country=org.country,
            contact_email=org.contact_email,
            contact_phone=org.contact_phone,
            logo_file_id=str(org.logo_file_id) if org.logo_file_id else None,
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
        Logger.error(f"Error getting organization details: {e}\n{error_tb}")
        raise create_http_exception(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
            detail_code="common.internal_error",
        )


@router.patch("/{org_id}/details", response_model=GetOrganizationDetailsResponse)
async def update_organization_details_endpoint(
    org_id: str,
    request: UpdateOrganizationDetailsRequest,
    http_request: Request,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """
    Update organization details including contact info, address, and logo.

    Authorization: super admin can update any org, org admin/owner can update their org only.
    """
    try:
        organization_id = current_user.organization_id

        # Authorization: super admin OR user belongs to org and has admin/owner role
        if current_user.is_admin:
            # Super admin can update any organization
            target_org_id = org_id
        elif org_id == organization_id:
            # User is in this organization, check if they have admin or owner role
            if not (current_user.has_role("owner") or current_user.has_role("admin")):
                raise create_http_exception(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Admin or owner access required",
                    detail_code="common.forbidden",
                )
            target_org_id = org_id
        else:
            raise create_http_exception(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Unauthorized access",
                detail_code="common.forbidden",
            )

        # Get current state for audit logging
        existing_org = await get_organization_details(
            session=session, org_id=target_org_id
        )
        old_values = {
            "display_name": existing_org.display_name,
            "physical_address_line1": existing_org.physical_address_line1,
            "physical_address_line2": existing_org.physical_address_line2,
            "city": existing_org.city,
            "state_province": existing_org.state_province,
            "postal_code": existing_org.postal_code,
            "country": existing_org.country,
            "contact_email": existing_org.contact_email,
            "contact_phone": existing_org.contact_phone,
            "logo_file_id": (
                str(existing_org.logo_file_id) if existing_org.logo_file_id else None
            ),
        }

        # Update organization details
        updated_org = await update_organization_details(
            session=session,
            org_id=target_org_id,
            request=request.model_dump(exclude_unset=True),
        )

        # Log audit event
        new_values = {
            "display_name": updated_org.display_name,
            "physical_address_line1": updated_org.physical_address_line1,
            "physical_address_line2": updated_org.physical_address_line2,
            "city": updated_org.city,
            "state_province": updated_org.state_province,
            "postal_code": updated_org.postal_code,
            "country": updated_org.country,
            "contact_email": updated_org.contact_email,
            "contact_phone": updated_org.contact_phone,
            "logo_file_id": (
                str(updated_org.logo_file_id) if updated_org.logo_file_id else None
            ),
        }
        await audit_service.log_update(
            session=session,
            organization_id=target_org_id,
            resource_type="OrganizationDetails",
            resource_id=str(updated_org.id),
            old_values=old_values,
            new_values=new_values,
            actor_id=current_user.id,
            ip_address=get_client_ip(http_request),
            user_agent=get_user_agent(http_request),
        )

        Logger.info("Organization details updated: id=%s", updated_org.id)

        return GetOrganizationDetailsResponse(
            id=str(updated_org.id),
            name=updated_org.name,
            slug=updated_org.slug,
            display_name=updated_org.display_name,
            physical_address_line1=updated_org.physical_address_line1,
            physical_address_line2=updated_org.physical_address_line2,
            city=updated_org.city,
            state_province=updated_org.state_province,
            postal_code=updated_org.postal_code,
            country=updated_org.country,
            contact_email=updated_org.contact_email,
            contact_phone=updated_org.contact_phone,
            logo_file_id=(
                str(updated_org.logo_file_id) if updated_org.logo_file_id else None
            ),
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
        Logger.error(f"Error updating organization details: {e}\n{error_tb}")
        http_request.state.error_traceback = error_tb
        raise create_http_exception(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
            detail_code="common.internal_error",
        )
