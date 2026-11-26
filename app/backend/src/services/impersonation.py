"""
Impersonation service for super admin user impersonation.
Handles starting, ending, and managing impersonation sessions.
"""

from typing import Optional
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.security import create_impersonation_token
from src.crud.impersonation_session import (
    create_session,
    get_active_session_by_impersonator,
)
from src.crud.impersonation_session import (
    end_session as crud_end_session,
)
from src.crud.organization import get_organization_by_id
from src.models.impersonation_session import ImpersonationSession
from src.models.user import User
from src.services.cache import cache_service


class ImpersonationService:
    """Service for managing impersonation sessions"""

    @staticmethod
    async def start_impersonation(
        session: AsyncSession,
        impersonator_id: str,
        target_user_id: str,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> tuple[str, ImpersonationSession]:
        """
        Start an impersonation session.

        Args:
            session: Database session
            impersonator_id: ID of the super admin initiating impersonation
            target_user_id: ID of the user to impersonate
            ip_address: Optional IP address of the request
            user_agent: Optional user agent of the request

        Returns:
            Tuple of (impersonation_token, impersonation_session)

        Raises:
            HTTPException: If validation fails
        """
        # Validate impersonator is a super admin
        # Query directly since super admins don't require organization context
        impersonator_uuid = UUID(impersonator_id)
        result = await session.execute(
            select(User).where(
                User.id == impersonator_uuid, User.deleted_time.is_(None)
            )
        )
        impersonator = result.scalars().first()

        if not impersonator:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Impersonator not found",
            )

        if not impersonator.is_admin:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only super admins can impersonate users",
            )

        # Auto-end any existing active session (handles orphaned sessions from logout/browser close)
        existing_session = await get_active_session_by_impersonator(
            session, impersonator_id
        )
        if existing_session:
            await crud_end_session(session, str(existing_session.id))
            # SECURITY: Evict any cached JWT claims for the previously
            # impersonated target so the orphaned impersonation token can no
            # longer be served from the claims cache (matches the cache key
            # used in get_current_user, which caches under the target user id).
            await cache_service.invalidate_jwt_for_user(
                str(existing_session.target_user_id)
            )

        # Validate target user exists
        # Query directly since super admins can impersonate users across all organizations
        target_user_uuid = UUID(target_user_id)
        result = await session.execute(select(User).where(User.id == target_user_uuid))
        target_user = result.scalars().first()

        if not target_user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Target user not found",
            )

        # Validate user is not soft-deleted
        if target_user.deleted_time:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot impersonate deleted user",
            )

        # Cannot impersonate yourself
        if impersonator_id == target_user_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot impersonate yourself",
            )

        # Cannot impersonate another super admin
        if target_user.is_admin:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot impersonate another super admin",
            )

        # Validate user has email verified
        if not target_user.email_verified:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot impersonate user with unverified email",
            )

        # Get target user's organization
        target_organization = await get_organization_by_id(
            session, str(target_user.organization_id)
        )
        if not target_organization:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Target user's organization not found",
            )

        # Cannot impersonate users in inactive organizations
        if not target_organization.is_active:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot impersonate user in inactive organization",
            )

        # Create impersonation session
        impersonation_session = await create_session(
            session=session,
            impersonator_id=impersonator_id,
            target_user_id=target_user_id,
            target_organization_id=str(target_user.organization_id),
            ip_address=ip_address,
            user_agent=user_agent,
        )

        # Create impersonation token
        impersonation_token = create_impersonation_token(
            user_id=target_user_id,
            organization_id=str(target_user.organization_id),
            impersonator_id=impersonator_id,
            impersonation_session_id=str(impersonation_session.id),
        )

        return impersonation_token, impersonation_session

    @staticmethod
    async def end_impersonation(
        session: AsyncSession,
        impersonation_session_id: str,
    ) -> Optional[ImpersonationSession]:
        """
        End an active impersonation session.

        Args:
            session: Database session
            impersonation_session_id: ID of the session to end

        Returns:
            The ended impersonation session, or None if not found

        Raises:
            HTTPException: If session not found or already ended
        """
        ended_session = await crud_end_session(session, impersonation_session_id)

        if not ended_session:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Active impersonation session not found",
            )

        # SECURITY: Evict any cached JWT claims for the impersonated target
        # user. Without this, get_current_user's cached path would keep
        # serving the (now-ended) impersonation token until the cache TTL
        # expires, because that path does not re-check the session state.
        # The claims cache keys by the target user id (claims["user_id"]),
        # so invalidating by target_user_id evicts the right entries.
        await cache_service.invalidate_jwt_for_user(str(ended_session.target_user_id))

        return ended_session

    @staticmethod
    async def get_active_session(
        session: AsyncSession,
        impersonator_id: str,
    ) -> Optional[ImpersonationSession]:
        """
        Get the active impersonation session for an impersonator.

        Args:
            session: Database session
            impersonator_id: ID of the impersonator

        Returns:
            Active impersonation session or None
        """
        return await get_active_session_by_impersonator(session, impersonator_id)
