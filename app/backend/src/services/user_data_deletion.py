"""
User data deletion service for GDPR-compliant account deletion.

Handles soft-delete cascade and hard deletion of user data after grace period.
"""

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import delete as sql_delete
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.logger.logger import Logger as logger


class UserDataDeletionService:
    """Service for managing user data deletion (soft and hard delete)."""

    async def soft_delete_user_cascade(
        self, session: AsyncSession, user_id: str, organization_id: str
    ) -> None:
        """
        Soft-delete a user and all their related data.

        Sets deleted_time on user and all related records:
        - User
        - UserRole
        - RefreshToken
        - UserOTP
        - UserTwoFactor
        - UserNotification
        - UserNotificationPreference
        - File (user uploads)

        Args:
            session: SQLAlchemy async session
            user_id: UUID of the user
            organization_id: UUID of the organization

        Raises:
            ValueError: If user not found
        """
        from src.models.file import File
        from src.models.notification import Notification
        from src.models.refresh_token import RefreshToken
        from src.models.user import User
        from src.models.user_notification_preference import UserNotificationPreference
        from src.models.user_otp import UserOTP
        from src.models.user_role import UserRole
        from src.models.user_two_factor import UserTwoFactor

        user_uuid = UUID(user_id)
        org_uuid = UUID(organization_id)
        now = datetime.now(timezone.utc)

        # Verify user exists
        result = await session.execute(
            select(User).where(
                User.id == user_uuid,
                User.organization_id == org_uuid,
                User.deleted_time.is_(None),
            )
        )
        user = result.scalar_one_or_none()
        if not user:
            raise ValueError(
                f"User {user_id} not found in organization {organization_id}"
            )

        logger.info(f"Soft-deleting user {user_id} and related data")

        # Soft-delete the user
        await session.execute(
            update(User)
            .where(User.id == user_uuid, User.deleted_time.is_(None))
            .values(deleted_time=now)
        )

        # UserRole
        await session.execute(
            update(UserRole)
            .where(
                UserRole.user_id == user_uuid,
                UserRole.organization_id == org_uuid,
                UserRole.deleted_time.is_(None),
            )
            .values(deleted_time=now)
        )

        # RefreshToken
        await session.execute(
            update(RefreshToken)
            .where(
                RefreshToken.user_id == user_uuid,
                RefreshToken.organization_id == org_uuid,
                RefreshToken.deleted_time.is_(None),
            )
            .values(deleted_time=now)
        )

        # UserOTP
        await session.execute(
            update(UserOTP)
            .where(
                UserOTP.user_id == user_uuid,
                UserOTP.organization_id == org_uuid,
                UserOTP.deleted_time.is_(None),
            )
            .values(deleted_time=now)
        )

        # UserTwoFactor
        await session.execute(
            update(UserTwoFactor)
            .where(
                UserTwoFactor.user_id == user_uuid,
                UserTwoFactor.organization_id == org_uuid,
                UserTwoFactor.deleted_time.is_(None),
            )
            .values(deleted_time=now)
        )

        # Notification (user-specific notifications)
        await session.execute(
            update(Notification)
            .where(
                Notification.user_id == user_uuid,
                Notification.organization_id == org_uuid,
                Notification.deleted_time.is_(None),
            )
            .values(deleted_time=now)
        )

        # UserNotificationPreference
        await session.execute(
            update(UserNotificationPreference)
            .where(
                UserNotificationPreference.user_id == user_uuid,
                UserNotificationPreference.organization_id == org_uuid,
                UserNotificationPreference.deleted_time.is_(None),
            )
            .values(deleted_time=now)
        )

        # File (uploaded by user)
        await session.execute(
            update(File)
            .where(
                File.uploaded_by_user_id == user_uuid,
                File.organization_id == org_uuid,
                File.deleted_time.is_(None),
            )
            .values(deleted_time=now)
        )

        await session.commit()
        logger.info(f"Soft-delete cascade completed for user {user_id}")

    async def invalidate_sessions(
        self, session: AsyncSession, user_id: str, organization_id: str
    ) -> int:
        """
        Invalidate all user sessions by deleting refresh tokens.

        Args:
            session: SQLAlchemy async session
            user_id: UUID of the user
            organization_id: UUID of the organization

        Returns:
            Number of tokens deleted
        """
        from src.models.refresh_token import RefreshToken

        user_uuid = UUID(user_id)
        org_uuid = UUID(organization_id)

        # Hard delete refresh tokens to immediately invalidate sessions
        result = await session.execute(
            sql_delete(RefreshToken).where(
                RefreshToken.user_id == user_uuid,
                RefreshToken.organization_id == org_uuid,
            )
        )

        count = result.rowcount
        await session.commit()

        logger.info(f"Invalidated {count} sessions for user {user_id}")
        return count

    async def hard_delete_user(
        self, session: AsyncSession, user_id: str, organization_id: str
    ) -> None:
        """
        Permanently delete a user and all their data from the database.

        This includes:
        - User record
        - UserRole
        - RefreshToken
        - UserOTP
        - UserTwoFactor
        - Notification (user-specific)
        - UserNotificationPreference
        - File records and S3 objects (uploaded by user)
        - DataExportRequest
        - DataDeletionRequest

        Args:
            session: SQLAlchemy async session
            user_id: UUID of the user
            organization_id: UUID of the organization

        Raises:
            ValueError: If user not found
        """
        from src.models.data_deletion_request import DataDeletionRequest
        from src.models.data_export_request import DataExportRequest
        from src.models.file import File
        from src.models.notification import Notification
        from src.models.refresh_token import RefreshToken
        from src.models.user import User
        from src.models.user_notification_preference import UserNotificationPreference
        from src.models.user_otp import UserOTP
        from src.models.user_role import UserRole
        from src.models.user_two_factor import UserTwoFactor
        from src.services.files.s3_storage import s3_storage

        user_uuid = UUID(user_id)
        org_uuid = UUID(organization_id)

        # Verify user exists (check soft-deleted users too)
        result = await session.execute(
            select(User).where(
                User.id == user_uuid,
                User.organization_id == org_uuid,
            )
        )
        user = result.scalar_one_or_none()
        if not user:
            raise ValueError(
                f"User {user_id} not found in organization {organization_id}"
            )

        logger.info(f"Hard-deleting user {user_id} and all related data")

        # Delete files from S3 first
        if s3_storage and s3_storage.is_available():
            file_result = await session.execute(
                select(File).where(
                    File.uploaded_by_user_id == user_uuid,
                    File.organization_id == org_uuid,
                )
            )
            files = file_result.scalars().all()

            for file_record in files:
                try:
                    await s3_storage.delete(file_record.storage_key)
                    logger.info(f"Deleted file from S3: {file_record.storage_key}")
                except Exception as e:
                    logger.warning(
                        f"Failed to delete file {file_record.id} from S3: {e}"
                    )

        # Hard delete related records (order matters for foreign keys)
        await session.execute(
            sql_delete(UserRole).where(
                UserRole.user_id == user_uuid,
                UserRole.organization_id == org_uuid,
            )
        )

        await session.execute(
            sql_delete(RefreshToken).where(
                RefreshToken.user_id == user_uuid,
                RefreshToken.organization_id == org_uuid,
            )
        )

        await session.execute(
            sql_delete(UserOTP).where(
                UserOTP.user_id == user_uuid,
                UserOTP.organization_id == org_uuid,
            )
        )

        await session.execute(
            sql_delete(UserTwoFactor).where(
                UserTwoFactor.user_id == user_uuid,
                UserTwoFactor.organization_id == org_uuid,
            )
        )

        await session.execute(
            sql_delete(Notification).where(
                Notification.user_id == user_uuid,
                Notification.organization_id == org_uuid,
            )
        )

        await session.execute(
            sql_delete(UserNotificationPreference).where(
                UserNotificationPreference.user_id == user_uuid,
                UserNotificationPreference.organization_id == org_uuid,
            )
        )

        await session.execute(
            sql_delete(File).where(
                File.uploaded_by_user_id == user_uuid,
                File.organization_id == org_uuid,
            )
        )

        # Delete export requests
        await session.execute(
            sql_delete(DataExportRequest).where(
                DataExportRequest.user_id == user_uuid,
                DataExportRequest.organization_id == org_uuid,
            )
        )

        # Delete deletion request
        await session.execute(
            sql_delete(DataDeletionRequest).where(
                DataDeletionRequest.user_id == user_uuid,
                DataDeletionRequest.organization_id == org_uuid,
            )
        )

        # Finally, delete the user
        await session.execute(
            sql_delete(User).where(
                User.id == user_uuid,
                User.organization_id == org_uuid,
            )
        )

        await session.commit()
        logger.info(f"Hard-delete completed for user {user_id}")


# Singleton instance
user_data_deletion_service = UserDataDeletionService()
