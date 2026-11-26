"""File cleanup cron handlers."""

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.logger.logger import Logger as logger


async def cleanup_deleted_files_handler(
    session: AsyncSession, parameters: dict[str, Any]
) -> dict[str, Any]:
    """
    Hard delete files that have been soft-deleted past retention period.
    Removes files from S3 storage and database.

    Parameters:
        default_retention_days (int): Default retention period (default: 30)

    Returns:
        dict with total_deleted and by_organization counts
    """
    from src.models.file import File
    from src.models.organization_file_settings import OrganizationFileSettings
    from src.services.files.s3_storage import s3_storage

    default_retention_days = parameters.get("default_retention_days", 30)
    now = datetime.now(timezone.utc)
    total_deleted = 0
    org_deleted: dict[str, int] = {}

    try:
        # Get all organization file settings
        result = await session.execute(
            select(OrganizationFileSettings).where(
                OrganizationFileSettings.deleted_file_retention_days.isnot(None)
            )
        )
        org_settings = result.scalars().all()

        for settings in org_settings:
            retention_days = (
                settings.deleted_file_retention_days or default_retention_days
            )
            cutoff_date = now - timedelta(days=retention_days)

            # Find soft-deleted files past retention
            file_result = await session.execute(
                select(File).where(
                    File.organization_id == settings.organization_id,
                    File.deleted_time.isnot(None),
                    File.deleted_time < cutoff_date,
                )
            )
            files_to_delete = file_result.scalars().all()

            count = 0
            for file_record in files_to_delete:
                try:
                    # Delete from S3
                    if s3_storage:
                        await s3_storage.delete(file_record.storage_key)

                    # Hard delete from database
                    await session.delete(file_record)
                    count += 1
                except Exception as e:
                    logger.warning(f"Failed to hard delete file {file_record.id}: {e}")

            if count > 0:
                org_deleted[str(settings.organization_id)] = count
                total_deleted += count

        # Handle files without organization-specific settings
        default_cutoff = now - timedelta(days=default_retention_days)
        default_conditions = [
            File.deleted_time.isnot(None),
            File.deleted_time < default_cutoff,
        ]
        if org_settings:
            default_conditions.append(
                ~File.organization_id.in_([s.organization_id for s in org_settings])
            )
        default_result = await session.execute(select(File).where(*default_conditions))
        default_files = default_result.scalars().all()

        default_count = 0
        for file_record in default_files:
            try:
                if s3_storage:
                    await s3_storage.delete(file_record.storage_key)
                await session.delete(file_record)
                default_count += 1
            except Exception as e:
                logger.warning(f"Failed to hard delete file {file_record.id}: {e}")

        if default_count > 0:
            org_deleted["default"] = default_count
            total_deleted += default_count

        await session.commit()

        logger.info(f"Hard deleted {total_deleted} old files from storage")
        return {
            "status": "completed",
            "total_deleted": total_deleted,
            "by_organization": org_deleted,
        }

    except Exception as exc:
        await session.rollback()
        logger.error(f"Failed to cleanup deleted files: {exc}")
        return {
            "status": "error",
            "reason": str(exc),
            "total_deleted": total_deleted,
            "by_organization": org_deleted,
        }


async def cleanup_expired_exports_handler(
    session: AsyncSession, parameters: dict[str, Any]
) -> dict[str, Any]:
    """
    Clean up expired data export files.

    Parameters:
        batch_size (int): Number of records to process per batch (default: 100)

    Returns:
        dict with deleted_count
    """
    from src.models.data_export_request import DataExportRequest, ExportStatus
    from src.services.files.s3_storage import s3_storage

    batch_size = parameters.get("batch_size", 100)
    total_deleted = 0
    now = datetime.now(timezone.utc)

    try:
        # Find expired exports
        result = await session.execute(
            select(DataExportRequest)
            .where(
                DataExportRequest.expires_at < now,
                DataExportRequest.status == ExportStatus.COMPLETED,
                DataExportRequest.deleted_time.is_(None),
            )
            .limit(batch_size)
        )
        expired_exports = result.scalars().all()

        for export_request in expired_exports:
            try:
                # Delete from storage
                if export_request.file_path:
                    if export_request.file_path.startswith("local:"):
                        # Local file
                        import os

                        local_path = export_request.file_path[
                            6:
                        ]  # Remove "local:" prefix
                        if os.path.exists(local_path):
                            os.remove(local_path)
                    elif s3_storage:
                        await s3_storage.delete(export_request.file_path)

                # Soft delete the export request
                export_request.deleted_time = now
                total_deleted += 1
            except Exception as e:
                logger.warning(f"Failed to delete export {export_request.id}: {e}")

        await session.commit()

        logger.info(f"Cleaned up {total_deleted} expired exports")
        return {"status": "completed", "deleted_count": total_deleted}

    except Exception as exc:
        await session.rollback()
        logger.error(f"Failed to cleanup expired exports: {exc}")
        return {"status": "error", "reason": str(exc), "deleted_count": total_deleted}


__all__ = [
    "cleanup_deleted_files_handler",
    "cleanup_expired_exports_handler",
]
