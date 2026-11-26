"""
Report Service.

Orchestrates report generation: creates report record, generates content,
uploads to storage, and updates the record with results.
"""

from datetime import datetime, timezone
import io
from typing import Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from src.crud.report import create_report, update_report_status
from src.logger.logger import Logger as logger
from src.models.report import Report, ReportStatus
from src.services.files import get_file_manager
from src.services.reports import get_generator, is_valid_report_type


class ReportService:
    """
    Service for orchestrating report generation.

    Handles the full lifecycle: creation, generation, upload, and status updates.
    """

    async def generate_report(
        self,
        session: AsyncSession,
        organization_id: str,
        report_type: str,
        name: str,
        generated_by_user_id: Optional[str] = None,
        description: Optional[str] = None,
        parameters: Optional[dict[str, Any]] = None,
        schedule_id: Optional[str] = None,
    ) -> Report:
        """
        Generate a report.

        This method:
        1. Validates the report type
        2. Creates a report record in pending status
        3. Generates the report content
        4. Uploads the content to file storage
        5. Updates the report record with results

        Args:
            session: Database session
            organization_id: Organization UUID string
            report_type: Type of report (e.g., "users_report")
            name: Report name
            generated_by_user_id: User ID who initiated the report
            description: Optional description
            parameters: Report-specific parameters/filters
            schedule_id: Optional schedule ID if generated from a schedule

        Returns:
            The Report record (with status indicating success or failure)

        Raises:
            ValueError: If report type is not valid
        """
        # Validate report type
        if not is_valid_report_type(report_type):
            raise ValueError(f"Unknown report type: {report_type}")

        # Create report record
        report = await create_report(
            session=session,
            organization_id=organization_id,
            report_type=report_type,
            name=name,
            generated_by_user_id=generated_by_user_id,
            description=description,
            parameters=parameters,
            schedule_id=schedule_id,
        )

        # Start processing
        started_at = datetime.now(timezone.utc)
        await update_report_status(
            session=session,
            report_id=str(report.id),
            organization_id=organization_id,
            status=ReportStatus.PROCESSING.value,
            started_at=started_at,
        )

        try:
            # Get the generator
            generator = get_generator(report_type)
            if not generator:
                raise ValueError(f"No generator found for report type: {report_type}")

            # Generate the report
            file_bytes, content_type, row_count = await generator(
                session, organization_id, parameters
            )

            # Upload to file storage
            fm = get_file_manager()
            if not fm:
                raise RuntimeError("File manager not initialized")

            # Generate filename
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            safe_name = "".join(c for c in name if c.isalnum() or c in " -_")[:50]
            filename = f"{safe_name}_{timestamp}.csv"

            # Upload the file
            file_io = io.BytesIO(file_bytes)
            upload_result = await fm.upload_direct(
                session=session,
                organization_id=organization_id,
                user_id=generated_by_user_id
                or organization_id,  # Use org as fallback for system-generated
                filename=filename,
                file_data=file_io,
                content_type=content_type,
                generate_thumbnail=False,
            )

            if not upload_result.success:
                raise RuntimeError(
                    f"Failed to upload report file: {upload_result.error_message}"
                )

            # Update report with success
            completed_at = datetime.now(timezone.utc)
            report = await update_report_status(
                session=session,
                report_id=str(report.id),
                organization_id=organization_id,
                status=ReportStatus.COMPLETED.value,
                file_id=str(upload_result.file.id) if upload_result.file else None,
                row_count=row_count,
                completed_at=completed_at,
            )

            logger.info(
                f"Report generated successfully: {report.id} "
                f"({report_type}, {row_count} rows)"
            )

        except Exception as e:
            # Update report with failure
            logger.error(f"Report generation failed for {report.id}: {e}")
            completed_at = datetime.now(timezone.utc)
            report = await update_report_status(
                session=session,
                report_id=str(report.id),
                organization_id=organization_id,
                status=ReportStatus.FAILED.value,
                error_message=str(e),
                completed_at=completed_at,
            )

        return report


# Global service instance
report_service = ReportService()


__all__ = ["ReportService", "report_service"]
