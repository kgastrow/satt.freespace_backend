"""
User management API endpoints.
Migrated to FastAPI with async/await patterns.
"""

import io
import traceback
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import CurrentUser, get_current_user, get_session
from src.core.exceptions import create_http_exception
from src.core.response_codes import get_response_code
from src.core.security import verify_password
from src.crud.file import soft_delete_file
from src.crud.organization import get_organization_by_slug
from src.crud.role import get_default_registration_roles
from src.crud.role_permission import get_user_permissions
from src.crud.user import (
    create_user,
    get_user_by_email,
    get_user_by_id,
    get_user_by_phone,
    update_user,
    update_user_avatar,
)
from src.crud.user_otp import create_otp
from src.crud.user_role import assign_role, get_user_roles
from src.logger.logger import Logger
from src.models.file import MediaUse
from src.serialisers.user import (
    AvatarUploadResponse,
    ChangePasswordRequest,
    ChangePasswordResponse,
    DeleteAvatarResponse,
    RegisterRequest,
    RegisterResponse,
    UpdateUserProfileRequest,
    UpdateUserProfileResponse,
    UserPermissionsResponse,
    UserProfileOrganizationInfo,
    UserProfileResponse,
    UserProfileRoleInfo,
    UserResponse,
)
from src.services.audit import audit_service, get_client_ip, get_user_agent
from src.services.files.file_manager import get_file_manager
from src.services.notifications import notification_dispatcher


router = APIRouter(prefix="/user", tags=["user"])


@router.post("/register", response_model=RegisterResponse)
async def register_endpoint(
    request: RegisterRequest,
    http_request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """Register a new user"""
    try:
        # Get organization from slug
        organization = await get_organization_by_slug(
            session, request.organization_slug
        )
        if not organization:
            raise create_http_exception(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Organization not found",
                detail_code="user.organization_not_found",
            )

        if not organization.is_active:
            raise create_http_exception(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Organization is not active",
                detail_code="auth.organization_not_active",
            )

        organization_id = str(organization.id)

        # Check if user already exists
        existing_user = await get_user_by_email(session, request.email, organization_id)
        if existing_user:
            # Block registration if email is undeliverable
            if (
                hasattr(existing_user, "email_deliverable")
                and existing_user.email_deliverable is False
            ):
                raise create_http_exception(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="This email address is marked as undeliverable and cannot be registered.",
                    detail_code="user.email_undeliverable",
                )

            # If user exists but email is not verified, resend verification
            if not existing_user.email_verified:
                # Generate new OTP and send verification email
                otp_code = await create_otp(session, existing_user.id, organization_id)
                await notification_dispatcher.send_to_user(
                    session=session,
                    user_id=str(existing_user.id),
                    organization_id=organization_id,
                    channel="email",
                    content=f"Your verification code is: {otp_code[:3]}-{otp_code[3:]}\n\nThis code will expire in 10 minutes.",
                    subject="Your Verification Code",
                    is_urgent=True,  # Bypass quiet hours for transactional emails
                )

                return RegisterResponse(
                    message="User exists but email not verified. New verification email sent.",
                    message_code=get_response_code("user.verification_email_sent"),
                    user=UserResponse(
                        id=str(existing_user.id),
                        email=existing_user.email,
                        email_deliverable=getattr(
                            existing_user, "email_deliverable", True
                        ),
                    ),
                    requires_verification=True,
                )
            else:
                raise create_http_exception(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Unable to process registration. Please try again or contact support.",
                    detail_code="user.registration_failed",
                )

        # Check for invitation token
        invitation = None
        if request.invite_token:
            from src.crud.user_invitation import (
                accept_invitation,
                get_invitation_by_token,
                parse_invitation_ids,
            )

            pending_invitation = await get_invitation_by_token(
                session, request.invite_token
            )
            if pending_invitation:
                # Verify invitation is for this organization
                if str(pending_invitation.organization_id) == organization_id:
                    invitation = pending_invitation

        # Create new user; invited users skip email verification
        email_verified = invitation is not None
        user_data = {
            "email": request.email,
            "password": request.password,
            "phone": request.phone,
            "first_name": request.first_name,
            "last_name": request.last_name,
            "email_verified": email_verified,
            "is_admin": False,
        }

        new_user = await create_user(
            session=session, request=user_data, organization_id=organization_id
        )

        # Assign default roles to the new user
        default_roles = await get_default_registration_roles(session)
        for role in default_roles:
            try:
                await assign_role(
                    session=session,
                    request={"user_id": str(new_user.id), "role_id": str(role.id)},
                    assigned_by_user_id=str(new_user.id),
                    organization_id=organization_id,
                )
            except ValueError:
                pass  # Skip if role assignment fails (e.g., already assigned)

        # Apply invitation pre-assignments (roles and user types)
        if invitation:
            from datetime import datetime, timezone

            from src.crud.user_invitation import (
                accept_invitation,
                parse_invitation_ids,
            )
            from src.models.user_user_type import OnboardingStatus, UserUserType

            role_ids, user_type_ids = parse_invitation_ids(invitation)

            # Assign pre-selected roles
            for role_id in role_ids:
                try:
                    await assign_role(
                        session=session,
                        request={"user_id": str(new_user.id), "role_id": role_id},
                        assigned_by_user_id=str(new_user.id),
                        organization_id=organization_id,
                    )
                except ValueError:
                    pass  # Skip duplicates

            # Assign pre-selected user types, bypassing onboarding wizard
            for user_type_id in user_type_ids:
                try:
                    uut = UserUserType(
                        user_id=new_user.id,
                        user_type_id=__import__("uuid").UUID(user_type_id),
                        organization_id=organization.id,
                        onboarding_status=OnboardingStatus.APPROVED,
                        onboarded_at=datetime.now(timezone.utc),
                    )
                    session.add(uut)
                except Exception:
                    pass  # Skip on error

            # Mark invitation as accepted
            await accept_invitation(session, invitation.token)

        requires_verification = not email_verified

        if requires_verification:
            # Generate OTP and send verification email
            otp_code = await create_otp(session, new_user.id, organization_id)
            await notification_dispatcher.send_to_user(
                session=session,
                user_id=str(new_user.id),
                organization_id=organization_id,
                channel="email",
                content=f"Your verification code is: {otp_code[:3]}-{otp_code[3:]}\n\nThis code will expire in 10 minutes.",
                subject="Your Verification Code",
                is_urgent=True,  # Bypass quiet hours for transactional emails
            )

        return RegisterResponse(
            message=(
                "User created. Please verify your email."
                if requires_verification
                else "Registration complete."
            ),
            message_code=get_response_code("user.created"),
            user=UserResponse(
                id=str(new_user.id),
                email=new_user.email,
                email_deliverable=getattr(new_user, "email_deliverable", True),
            ),
            requires_verification=requires_verification,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        error_tb = traceback.format_exc()
        Logger.error(f"Registration failed: {e}\n{error_tb}")
        http_request.state.error_traceback = error_tb
        raise create_http_exception(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred during registration",
            detail_code="common.internal_error",
        )


@router.get("/me", response_model=UserProfileResponse)
async def get_me_endpoint(
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """Get current user profile"""
    # Get full user object from database
    user = await get_user_by_id(session, current_user.id, current_user.organization_id)
    if not user:
        raise create_http_exception(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
            detail_code="user.not_found",
        )

    # Fetch user's active roles
    user_roles, _ = await get_user_roles(
        session, current_user.id, current_user.organization_id
    )
    roles = [
        UserProfileRoleInfo(id=str(ur.role.id), name=ur.role.name)
        for ur in user_roles
        if ur.role is not None
    ]

    # Build organization info if available
    organization_info = None
    if user.organization:
        organization_info = UserProfileOrganizationInfo(
            id=str(user.organization.id),
            name=user.organization.name,
            slug=user.organization.slug,
        )

    # Get avatar URLs if user has avatar
    avatar_url = None
    full_avatar_url = None
    if user.avatar:
        try:
            fm = get_file_manager()
            if fm:
                # Get full avatar URL (original image)
                full_avatar_result = await fm.get_download_url(
                    session=session,
                    file_id=str(user.avatar.id),
                    organization_id=current_user.organization_id,
                )
                if full_avatar_result:
                    full_avatar_url = full_avatar_result.url

                # Get thumbnail URL for efficient display, fallback to full image
                thumbnail_result = await fm.get_thumbnail_url(
                    session=session,
                    file_id=str(user.avatar.id),
                    organization_id=current_user.organization_id,
                )
                if thumbnail_result:
                    avatar_url = thumbnail_result.url
                else:
                    avatar_url = full_avatar_url
        except Exception as e:
            # Log error but don't fail the request
            Logger.warning(f"Failed to get avatar download URLs: {str(e)}")

    return UserProfileResponse(
        id=str(user.id),
        email=user.email,
        email_verified=user.email_verified,
        email_deliverable=getattr(user, "email_deliverable", True),
        phone=user.phone,
        phone_verified=getattr(user, "phone_verified", False),
        first_name=user.first_name,
        last_name=user.last_name,
        is_admin=user.is_admin,
        organization_id=current_user.organization_id,
        organization=organization_info,
        roles=roles,
        avatar_url=avatar_url,
        full_avatar_url=full_avatar_url,
    )


@router.get("/permissions", response_model=UserPermissionsResponse)
async def get_my_permissions_endpoint(
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """Get current user's effective permissions based on their roles."""
    permission_codes = await get_user_permissions(
        session, current_user.id, current_user.organization_id
    )
    return UserPermissionsResponse(permissions=permission_codes)


@router.put("/me", response_model=UpdateUserProfileResponse)
async def update_me_endpoint(
    request: UpdateUserProfileRequest,
    http_request: Request,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """Update current user profile"""
    organization_id = current_user.organization_id

    # Get current state for change tracking
    existing_user = await get_user_by_id(session, current_user.id, organization_id)
    if not existing_user:
        raise create_http_exception(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
            detail_code="user.not_found",
        )
    old_values = {
        "email": existing_user.email,
        "phone": existing_user.phone,
        "first_name": existing_user.first_name,
        "last_name": existing_user.last_name,
    }

    # Initialize update request with user id
    update_user_request = {"id": current_user.id}

    # Only include fields that are present in the request data
    if request.email is not None:
        update_user_request["email"] = request.email
    if request.password is not None:
        update_user_request["password"] = request.password
    if request.phone is not None:
        update_user_request["phone"] = request.phone
    if request.first_name is not None:
        update_user_request["first_name"] = request.first_name
    if request.last_name is not None:
        update_user_request["last_name"] = request.last_name

    # Check phone uniqueness if phone is being updated to a different value
    if request.phone is not None and request.phone != existing_user.phone:
        existing_phone_user = await get_user_by_phone(
            session,
            request.phone,
            organization_id,
            exclude_user_id=str(current_user.id),
        )
        if existing_phone_user:
            raise create_http_exception(
                status_code=status.HTTP_409_CONFLICT,
                detail="Phone number is already in use",
                detail_code="user.phone_already_exists",
            )

    updated_user = await update_user(
        session=session, request=update_user_request, organization_id=organization_id
    )

    # Log audit event
    new_values = {
        "email": updated_user.email,
        "phone": updated_user.phone,
        "first_name": updated_user.first_name,
        "last_name": updated_user.last_name,
    }
    # Add password change indicator if password was updated
    if request.password is not None:
        old_values["password"] = "[PREVIOUS]"
        new_values["password"] = "[CHANGED]"

    await audit_service.log_update(
        session=session,
        organization_id=organization_id,
        resource_type="User",
        resource_id=str(updated_user.id),
        old_values=old_values,
        new_values=new_values,
        actor_id=current_user.id,
        ip_address=get_client_ip(http_request),
        user_agent=get_user_agent(http_request),
    )

    return UpdateUserProfileResponse(
        message="User updated",
        message_code=get_response_code("user.profile_updated"),
        user={
            "id": str(updated_user.id),
            "email": updated_user.email,
            "email_deliverable": getattr(updated_user, "email_deliverable", True),
            "phone": updated_user.phone,
            "first_name": updated_user.first_name,
            "last_name": updated_user.last_name,
        },
    )


@router.post("/me/change-password", response_model=ChangePasswordResponse)
async def change_password_endpoint(
    request: ChangePasswordRequest,
    http_request: Request,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """
    Change current user's password.
    Requires current password verification for security.
    """
    organization_id = current_user.organization_id

    # Get user with password hash
    user = await get_user_by_id(session, current_user.id, organization_id)
    if not user:
        raise create_http_exception(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
            detail_code="user.not_found",
        )

    # Verify current password
    # SECURITY: Use generic error message to not reveal password validity
    if not verify_password(request.current_password, user.password):
        raise create_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unable to change password. Please verify your input and try again.",
            detail_code="user.password_incorrect",
        )

    # Prevent setting same password
    if verify_password(request.new_password, user.password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="New password must be different from current password",
        )

    # Update password
    update_request = {"id": current_user.id, "password": request.new_password}
    await update_user(
        session=session, request=update_request, organization_id=organization_id
    )

    # Log audit event
    await audit_service.log_update(
        session=session,
        organization_id=organization_id,
        resource_type="User",
        resource_id=str(current_user.id),
        old_values={"password": "[PREVIOUS]"},
        new_values={"password": "[CHANGED]"},
        actor_id=current_user.id,
        ip_address=get_client_ip(http_request),
        user_agent=get_user_agent(http_request),
    )

    return ChangePasswordResponse(
        message="Password changed successfully",
        message_code=get_response_code("user.password_changed"),
    )


@router.post(
    "/me/avatar",
    response_model=AvatarUploadResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_avatar_endpoint(
    file: Annotated[UploadFile, File(...)],
    http_request: Request,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """
    Upload avatar image for current user.

    Accepts image files (JPEG, PNG, GIF, WEBP).
    Creates File record with media_use=AVATAR and updates user.avatar_file_id.
    Automatically generates a thumbnail for efficient display.
    """
    organization_id = current_user.organization_id

    if not file.filename:
        raise create_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Filename is required",
            detail_code="avatar.filename_required",
        )

    if not file.content_type:
        raise create_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Content type is required",
            detail_code="avatar.content_type_required",
        )

    # Validate file is an image
    allowed_types = ["image/jpeg", "image/png", "image/gif", "image/webp"]
    if file.content_type not in allowed_types:
        raise create_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid file type. Allowed types: {', '.join(allowed_types)}",
            detail_code="avatar.invalid_file_type",
        )

    # Read file data
    file_data = await file.read()
    size_bytes = len(file_data)

    if size_bytes == 0:
        raise create_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File is empty",
            detail_code="avatar.file_empty",
        )

    # Get file manager
    fm = get_file_manager()
    if fm is None:
        raise create_http_exception(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="File storage service unavailable",
            detail_code="file.service_unavailable",
        )

    # Upload file with media_use=AVATAR
    upload_result = await fm.upload_direct(
        session=session,
        organization_id=str(organization_id),
        user_id=str(current_user.id),
        filename=file.filename,
        file_data=io.BytesIO(file_data),
        content_type=file.content_type,
        media_use=MediaUse.AVATAR,
    )

    if not upload_result.success or upload_result.file is None:
        raise create_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=upload_result.error_message or "Failed to upload avatar",
            detail_code="avatar.upload_failed",
        )

    # Update user's avatar_file_id
    try:
        await update_user_avatar(
            session=session,
            user_id=str(current_user.id),
            organization_id=str(organization_id),
            avatar_file_id=str(upload_result.file.id),
        )
    except ValueError as e:
        raise create_http_exception(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
            detail_code="user.not_found",
        )

    # Get avatar URLs
    avatar_url = None
    full_avatar_url = None
    try:
        # Get full avatar URL (original image)
        full_avatar_result = await fm.get_download_url(
            session=session,
            file_id=str(upload_result.file.id),
            organization_id=str(organization_id),
        )
        if full_avatar_result:
            full_avatar_url = full_avatar_result.url

        # Get thumbnail URL for efficient display, fallback to full image
        thumbnail_result = await fm.get_thumbnail_url(
            session=session,
            file_id=str(upload_result.file.id),
            organization_id=str(organization_id),
        )
        if thumbnail_result:
            avatar_url = thumbnail_result.url
        else:
            avatar_url = full_avatar_url
    except Exception:
        pass

    # Log audit event
    await audit_service.log_create(
        session=session,
        organization_id=str(organization_id),
        resource_type="UserAvatar",
        resource_id=str(upload_result.file.id),
        resource_data={"filename": file.filename, "size_bytes": size_bytes},
        actor_id=current_user.id,
        ip_address=get_client_ip(http_request),
        user_agent=get_user_agent(http_request),
    )

    return AvatarUploadResponse(
        message="Avatar uploaded successfully",
        message_code=get_response_code("avatar.uploaded"),
        avatar_url=avatar_url,
        full_avatar_url=full_avatar_url,
    )


@router.delete("/me/avatar", response_model=DeleteAvatarResponse)
async def delete_avatar_endpoint(
    http_request: Request,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """
    Delete avatar for current user.

    Soft-deletes the avatar file record and sets user.avatar_file_id to null.
    """
    organization_id = current_user.organization_id

    # Get current user with avatar
    user = await get_user_by_id(session, current_user.id, str(organization_id))
    if not user:
        raise create_http_exception(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
            detail_code="user.not_found",
        )

    if not user.avatar_file_id:
        raise create_http_exception(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User has no avatar to delete",
            detail_code="avatar.not_found",
        )

    avatar_file_id = str(user.avatar_file_id)

    # Soft delete the avatar file
    try:
        await soft_delete_file(
            session=session,
            file_id=avatar_file_id,
            organization_id=str(organization_id),
        )
    except ValueError as e:
        raise create_http_exception(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
            detail_code="avatar.not_found",
        )

    # Update user's avatar_file_id to null
    await update_user_avatar(
        session=session,
        user_id=str(current_user.id),
        organization_id=str(organization_id),
        avatar_file_id=None,
    )

    # Log audit event
    await audit_service.log_delete(
        session=session,
        organization_id=str(organization_id),
        resource_type="UserAvatar",
        resource_id=avatar_file_id,
        resource_data={},
        actor_id=current_user.id,
        ip_address=get_client_ip(http_request),
        user_agent=get_user_agent(http_request),
    )

    return DeleteAvatarResponse(
        message="Avatar deleted successfully",
        message_code=get_response_code("avatar.deleted"),
    )
