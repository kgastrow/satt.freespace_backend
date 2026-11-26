"""
User Data Export Service

Collects and packages user data into a ZIP file for GDPR compliance.
Includes user profile, organization memberships, audit logs, and file metadata.
"""

from datetime import datetime, timezone
import io
import json
from typing import Any
import zipfile

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.audit_log import AuditLog
from src.models.file import File
from src.models.organization import Organization
from src.models.role import Role
from src.models.user import User
from src.models.user_role import UserRole


class UserDataExportService:
    """Service for collecting and packaging user data exports."""

    async def collect_user_data(
        self, session: AsyncSession, user_id: str, organization_id: str
    ) -> dict[str, Any]:
        """
        Collect all user data for export.

        Args:
            session: Database session
            user_id: User ID
            organization_id: Organization ID for tenant isolation

        Returns:
            Dictionary with collected data sections
        """
        from uuid import UUID

        user_uuid = UUID(user_id)
        org_uuid = UUID(organization_id)

        # Collect user profile
        user_result = await session.execute(
            select(User).where(
                User.id == user_uuid,
                User.organization_id == org_uuid,
                User.deleted_time.is_(None),
            )
        )
        user = user_result.scalar_one_or_none()

        if not user:
            raise ValueError(f"User {user_id} not found")

        profile_data = {
            "id": str(user.id),
            "email": user.email,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "phone": user.phone,
            "email_verified": user.email_verified,
            "phone_verified": user.phone_verified,
            "created_time": (
                user.created_time.isoformat() if user.created_time else None
            ),
            "updated_time": (
                user.updated_time.isoformat() if user.updated_time else None
            ),
        }

        # Collect organization memberships with roles
        user_roles_result = await session.execute(
            select(UserRole, Role)
            .join(Role, UserRole.role_id == Role.id)
            .where(
                UserRole.user_id == user_uuid,
                UserRole.organization_id == org_uuid,
                UserRole.deleted_time.is_(None),
            )
        )
        user_roles = user_roles_result.all()

        org_result = await session.execute(
            select(Organization).where(Organization.id == org_uuid)
        )
        org = org_result.scalar_one_or_none()

        organizations_data = []
        if org:
            organizations_data.append(
                {
                    "organization_id": str(org.id),
                    "organization_name": org.name,
                    "organization_slug": org.slug,
                    "roles": [
                        {
                            "role_id": str(role.id),
                            "role_name": role.name,
                            "assigned_at": (
                                user_role.created_time.isoformat()
                                if user_role.created_time
                                else None
                            ),
                        }
                        for user_role, role in user_roles
                    ],
                }
            )

        # Collect audit logs (last 1000 entries for the user)
        audit_result = await session.execute(
            select(AuditLog)
            .where(
                AuditLog.actor_id == user_uuid,
                AuditLog.organization_id == org_uuid,
            )
            .order_by(AuditLog.created_time.desc())
            .limit(1000)
        )
        audit_logs = audit_result.scalars().all()

        activity_data = [
            {
                "timestamp": log.created_time.isoformat() if log.created_time else None,
                "action": str(log.action),
                "resource_type": log.resource_type,
                "resource_id": str(log.resource_id) if log.resource_id else None,
                "changes": log.changes,
            }
            for log in audit_logs
        ]

        # Collect file metadata (uploaded by user)
        files_result = await session.execute(
            select(File)
            .where(
                File.uploaded_by_user_id == user_uuid,
                File.organization_id == org_uuid,
                File.deleted_time.is_(None),
            )
            .order_by(File.created_time.desc())
        )
        files = files_result.scalars().all()

        files_data = [
            {
                "id": str(file.id),
                "original_filename": file.original_filename,
                "content_type": file.content_type,
                "size_bytes": file.size_bytes,
                "category": file.category,
                "status": file.status,
                "upload_time": (
                    file.created_time.isoformat() if file.created_time else None
                ),
                "download_count": file.download_count,
            }
            for file in files
        ]

        return {
            "profile": profile_data,
            "organizations": organizations_data,
            "activity": activity_data,
            "files": files_data,
        }

    async def estimate_size(
        self, session: AsyncSession, user_id: str, organization_id: str
    ) -> int:
        """
        Estimate the size of the export ZIP file in bytes.

        Args:
            session: Database session
            user_id: User ID
            organization_id: Organization ID for tenant isolation

        Returns:
            Estimated size in bytes
        """
        # Rough estimate: profile ~5KB, each activity ~1KB, each file record ~0.5KB, README ~2KB
        from uuid import UUID

        user_uuid = UUID(user_id)
        org_uuid = UUID(organization_id)

        # Count audit logs
        audit_result = await session.execute(
            select(AuditLog)
            .where(
                AuditLog.actor_id == user_uuid,
                AuditLog.organization_id == org_uuid,
            )
            .limit(1000)
        )
        audit_count = len(audit_result.scalars().all())

        # Count files
        files_result = await session.execute(
            select(File).where(
                File.uploaded_by_user_id == user_uuid,
                File.organization_id == org_uuid,
                File.deleted_time.is_(None),
            )
        )
        files_count = len(files_result.scalars().all())

        # Estimate
        estimated_size = (
            5 * 1024  # profile.json
            + 2 * 1024  # organizations.json
            + (audit_count * 1024)  # activity.json
            + (files_count * 512)  # files metadata
            + 2 * 1024  # README.txt
        )

        return estimated_size

    async def generate_export_zip(
        self, session: AsyncSession, user_id: str, organization_id: str
    ) -> bytes:
        """
        Generate a ZIP file containing all user data.

        Args:
            session: Database session
            user_id: User ID
            organization_id: Organization ID for tenant isolation

        Returns:
            ZIP file contents as bytes
        """
        # Collect data
        data = await self.collect_user_data(session, user_id, organization_id)

        # Create ZIP file in memory
        zip_buffer = io.BytesIO()

        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
            # Add profile.json
            profile_json = json.dumps(data["profile"], indent=2, ensure_ascii=False)
            zip_file.writestr("profile.json", profile_json)

            # Add organizations.json
            organizations_json = json.dumps(
                data["organizations"], indent=2, ensure_ascii=False
            )
            zip_file.writestr("organizations.json", organizations_json)

            # Add activity.json
            activity_json = json.dumps(data["activity"], indent=2, ensure_ascii=False)
            zip_file.writestr("activity.json", activity_json)

            # Add files/metadata.json
            files_json = json.dumps(data["files"], indent=2, ensure_ascii=False)
            zip_file.writestr("files/metadata.json", files_json)

            # Add README.txt
            readme_content = self._generate_readme(data)
            zip_file.writestr("README.txt", readme_content)

        zip_buffer.seek(0)
        return zip_buffer.read()

    def _generate_readme(self, data: dict[str, Any]) -> str:
        """
        Generate README.txt content explaining the export.

        Args:
            data: Collected user data

        Returns:
            README content as string
        """
        profile = data["profile"]
        activity_count = len(data["activity"])
        files_count = len(data["files"])

        readme = f"""Personal Data Export - GDPR Compliance
======================================

Generated: {datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")}
User: {profile.get("email", "N/A")}
User ID: {profile.get("id", "N/A")}

This archive contains all your personal data stored in our system,
as required by GDPR Article 15 (Right of Access) and Article 20 (Right to Data Portability).

Contents:
---------

1. profile.json
   Your user profile information including email, name, phone, and verification status.

2. organizations.json
   Your organization memberships and assigned roles.

3. activity.json
   Your activity history (last 1000 entries) including actions performed and changes made.
   Total activity records: {activity_count}

4. files/metadata.json
   Metadata for files you uploaded, including filenames, sizes, and upload dates.
   Total files: {files_count}
   Note: This contains metadata only. Actual file contents are stored separately.

Data Format:
-----------
All data is provided in JSON format for easy parsing and portability.
Timestamps are in ISO 8601 format (UTC timezone).

Questions or Concerns:
---------------------
If you have questions about this export or wish to exercise your data rights
(correction, deletion, restriction of processing), please contact us.

This export is valid for 30 days from the generation date, after which it will
automatically expire and be removed from our storage.
"""
        return readme


# Singleton service instance
user_data_export_service = UserDataExportService()
