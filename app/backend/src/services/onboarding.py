"""
Onboarding Service.

Manages user onboarding flows including step validation, progress tracking,
and automatic completion/review status transitions.
"""

from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.crud import onboarding_step as onboarding_step_crud
from src.crud import user_onboarding_progress as progress_crud
from src.crud import user_type as user_type_crud
from src.crud import user_user_type as user_user_type_crud
from src.logger.logger import Logger as logger
from src.models.user_user_type import OnboardingStatus


class OnboardingService:
    """
    Service for managing user onboarding workflows.

    Handles onboarding flow orchestration, step validation, progress tracking,
    and automatic status transitions based on completion and review requirements.
    """

    async def start_onboarding(
        self,
        session: AsyncSession,
        user_id: str,
        user_type_id: str,
        organization_id: str,
    ) -> dict[str, Any]:
        """
        Start the onboarding process for a user with a specific user type.

        Creates a UserUserType association with status 'in_progress' and
        returns the first step to complete.

        Args:
            session: Database session
            user_id: User UUID
            user_type_id: UserType UUID
            organization_id: Organization UUID

        Returns:
            Dict with user_user_type_id, status, and first step details

        Raises:
            ValueError: If user type not found or already assigned
        """
        user_type = await user_type_crud.get_by_id(session, user_type_id)
        if not user_type:
            raise ValueError(f"User type with id {user_type_id} not found")

        if not user_type.is_active:
            raise ValueError(f"User type '{user_type.name}' is not active")

        if not user_type.requires_onboarding:
            raise ValueError(
                f"User type '{user_type.name}' does not require onboarding"
            )

        # Check if already exists
        existing = await user_user_type_crud.get_by_user_and_type(
            session, user_id, user_type_id, organization_id
        )
        if existing:
            raise ValueError("User already has this user type assigned")

        # Create user-user type association
        user_user_type = await user_user_type_crud.create(
            session,
            {
                "user_id": user_id,
                "user_type_id": user_type_id,
            },
            organization_id,
        )

        # Update status to in_progress
        user_user_type = await user_user_type_crud.update_status(
            session,
            str(user_user_type.id),
            OnboardingStatus.IN_PROGRESS,
            organization_id,
        )

        # Get first step
        steps = await onboarding_step_crud.get_all_for_user_type(session, user_type_id)
        active_steps = [s for s in steps if s.is_active]

        if not active_steps:
            raise ValueError(
                f"No active onboarding steps found for user type '{user_type.name}'"
            )

        first_step = active_steps[0]

        return {
            "user_user_type_id": str(user_user_type.id),
            "status": user_user_type.onboarding_status.value,
            "current_step": {
                "id": str(first_step.id),
                "name": first_step.name,
                "code": first_step.code,
                "description": first_step.description,
                "step_order": first_step.step_order,
                "required_fields": first_step.required_fields,
                "validation_rules": first_step.validation_rules,
                "requires_verification": first_step.requires_verification,
            },
            "total_steps": len(active_steps),
        }

    async def get_current_step(
        self,
        session: AsyncSession,
        user_user_type_id: str,
        organization_id: str,
    ) -> Optional[dict[str, Any]]:
        """
        Get the current incomplete step for a user's onboarding.

        Returns the first step that hasn't been completed yet, or None if
        all steps are complete.

        Args:
            session: Database session
            user_user_type_id: UserUserType UUID
            organization_id: Organization UUID

        Returns:
            Dict with step details or None if all complete
        """
        # Get user_user_type record
        user_uuid = UUID(user_user_type_id)
        org_uuid = UUID(organization_id)

        from sqlalchemy import select

        from src.models.user_user_type import UserUserType

        result = await session.execute(
            select(UserUserType).where(
                UserUserType.id == user_uuid,
                UserUserType.organization_id == org_uuid,
                UserUserType.deleted_time.is_(None),
            )
        )
        user_user_type = result.scalars().first()

        if not user_user_type:
            raise ValueError(f"UserUserType with id {user_user_type_id} not found")

        # Get all steps for this user type
        steps = await onboarding_step_crud.get_all_for_user_type(
            session, str(user_user_type.user_type_id)
        )
        active_steps = [s for s in steps if s.is_active]

        if not active_steps:
            return None

        # Get completed progress
        progress_records = await progress_crud.get_progress_for_user_type(
            session, user_user_type_id, organization_id
        )
        completed_step_ids = {
            str(p.onboarding_step_id) for p in progress_records if p.completed_time
        }

        # Find first incomplete step
        for step in active_steps:
            if str(step.id) not in completed_step_ids:
                return {
                    "id": str(step.id),
                    "name": step.name,
                    "code": step.code,
                    "description": step.description,
                    "step_order": step.step_order,
                    "required_fields": step.required_fields,
                    "validation_rules": step.validation_rules,
                    "requires_verification": step.requires_verification,
                }

        return None

    async def submit_step(
        self,
        session: AsyncSession,
        user_id: str,
        user_user_type_id: str,
        step_id: str,
        submitted_data: dict[str, Any],
        organization_id: str,
    ) -> dict[str, Any]:
        """
        Submit data for an onboarding step.

        Validates the submitted data against the step's required_fields and
        validation_rules, creates/updates progress record, and checks if
        onboarding is complete.

        Args:
            session: Database session
            user_id: User UUID
            user_user_type_id: UserUserType UUID
            step_id: OnboardingStep UUID
            submitted_data: Dict of submitted field values
            organization_id: Organization UUID

        Returns:
            Dict with step completion status and next step info

        Raises:
            ValueError: If validation fails or step not found
        """
        # Get step
        step = await onboarding_step_crud.get_by_id(session, step_id)
        if not step:
            raise ValueError(f"Onboarding step with id {step_id} not found")

        # Validate submitted data
        validation_errors = self._validate_step_data(step, submitted_data)
        if validation_errors:
            raise ValueError(f"Validation failed: {', '.join(validation_errors)}")

        # Check if progress already exists
        existing_progress = await progress_crud.get_step_progress(
            session, user_user_type_id, step_id, organization_id
        )

        if existing_progress:
            # Update existing progress
            progress = await progress_crud.update(
                session,
                str(existing_progress.id),
                {
                    "submitted_data": submitted_data,
                    "completed_time": datetime.now(timezone.utc),
                },
                organization_id,
            )
        else:
            # Create new progress record
            progress = await progress_crud.create(
                session,
                {
                    "user_id": user_id,
                    "user_user_type_id": user_user_type_id,
                    "onboarding_step_id": step_id,
                    "submitted_data": submitted_data,
                    "completed_time": datetime.now(timezone.utc),
                },
                organization_id,
            )

        # Check if all steps are complete
        completion_result = await self.check_completion(
            session, user_user_type_id, organization_id
        )

        return {
            "step_completed": True,
            "progress_id": str(progress.id),
            "all_steps_complete": completion_result["all_complete"],
            "status": completion_result["status"],
            "next_step": completion_result.get("next_step"),
        }

    async def get_progress(
        self,
        session: AsyncSession,
        user_user_type_id: str,
        organization_id: str,
    ) -> dict[str, Any]:
        """
        Get the onboarding progress summary for a user.

        Returns overall status, completed steps count, and details of
        completed/incomplete steps.

        Args:
            session: Database session
            user_user_type_id: UserUserType UUID
            organization_id: Organization UUID

        Returns:
            Dict with progress summary
        """
        # Get user_user_type record
        user_uuid = UUID(user_user_type_id)
        org_uuid = UUID(organization_id)

        from sqlalchemy import select

        from src.models.user_user_type import UserUserType

        result = await session.execute(
            select(UserUserType).where(
                UserUserType.id == user_uuid,
                UserUserType.organization_id == org_uuid,
                UserUserType.deleted_time.is_(None),
            )
        )
        user_user_type = result.scalars().first()

        if not user_user_type:
            raise ValueError(f"UserUserType with id {user_user_type_id} not found")

        # Get all steps
        steps = await onboarding_step_crud.get_all_for_user_type(
            session, str(user_user_type.user_type_id)
        )
        active_steps = [s for s in steps if s.is_active]

        # Get progress records
        progress_records = await progress_crud.get_progress_for_user_type(
            session, user_user_type_id, organization_id
        )

        completed_steps = []
        incomplete_steps = []

        progress_map = {str(p.onboarding_step_id): p for p in progress_records}

        for step in active_steps:
            step_id = str(step.id)
            progress = progress_map.get(step_id)

            step_info = {
                "id": step_id,
                "name": step.name,
                "code": step.code,
                "step_order": step.step_order,
                "completed": False,
                "completed_time": None,
            }

            if progress and progress.completed_time:
                step_info["completed"] = True
                step_info["completed_time"] = progress.completed_time.isoformat()
                completed_steps.append(step_info)
            else:
                incomplete_steps.append(step_info)

        return {
            "user_user_type_id": user_user_type_id,
            "status": user_user_type.onboarding_status.value,
            "completed_steps_count": len(completed_steps),
            "total_steps": len(active_steps),
            "completed_steps": completed_steps,
            "incomplete_steps": incomplete_steps,
            "onboarded_at": (
                user_user_type.onboarded_at.isoformat()
                if user_user_type.onboarded_at
                else None
            ),
        }

    async def check_completion(
        self,
        session: AsyncSession,
        user_user_type_id: str,
        organization_id: str,
    ) -> dict[str, Any]:
        """
        Check if all onboarding steps are complete and update status accordingly.

        If all steps complete:
        - If user_type.requires_manual_review: set status to 'pending_review'
        - Otherwise: set status to 'approved' and set onboarded_at timestamp

        Args:
            session: Database session
            user_user_type_id: UserUserType UUID
            organization_id: Organization UUID

        Returns:
            Dict with completion status and next step if applicable
        """
        # Get user_user_type record
        user_uuid = UUID(user_user_type_id)
        org_uuid = UUID(organization_id)

        from sqlalchemy import select

        from src.models.user_user_type import UserUserType

        result = await session.execute(
            select(UserUserType).where(
                UserUserType.id == user_uuid,
                UserUserType.organization_id == org_uuid,
                UserUserType.deleted_time.is_(None),
            )
        )
        user_user_type = result.scalars().first()

        if not user_user_type:
            raise ValueError(f"UserUserType with id {user_user_type_id} not found")

        # Get user type to check requires_manual_review
        user_type = await user_type_crud.get_by_id(
            session, str(user_user_type.user_type_id)
        )
        if not user_type:
            raise ValueError("User type not found")

        # Get all steps
        steps = await onboarding_step_crud.get_all_for_user_type(
            session, str(user_user_type.user_type_id)
        )
        active_steps = [s for s in steps if s.is_active]

        if not active_steps:
            return {
                "all_complete": True,
                "status": user_user_type.onboarding_status.value,
            }

        # Get progress records
        progress_records = await progress_crud.get_progress_for_user_type(
            session, user_user_type_id, organization_id
        )
        completed_step_ids = {
            str(p.onboarding_step_id) for p in progress_records if p.completed_time
        }

        # Check if all steps complete
        all_complete = all(str(s.id) in completed_step_ids for s in active_steps)

        if not all_complete:
            # Find next incomplete step
            next_step = None
            for step in active_steps:
                if str(step.id) not in completed_step_ids:
                    next_step = {
                        "id": str(step.id),
                        "name": step.name,
                        "code": step.code,
                        "step_order": step.step_order,
                    }
                    break

            return {
                "all_complete": False,
                "status": user_user_type.onboarding_status.value,
                "next_step": next_step,
            }

        # All steps complete - update status based on review requirement
        if user_type.requires_manual_review:
            # Set to pending_review
            updated_user_type = await user_user_type_crud.update_status(
                session,
                str(user_user_type.id),
                OnboardingStatus.PENDING_REVIEW,
                organization_id,
            )
            if updated_user_type is None:
                raise ValueError(f"Failed to update user_user_type {user_user_type_id}")

            logger.info(
                f"Onboarding complete for user_user_type {user_user_type_id}, "
                f"set to pending_review"
            )

            # Trigger notifications
            from src.services.onboarding_notifications import (
                onboarding_notification_service,
            )

            # Notify user of submission
            await onboarding_notification_service.send_submission_notification(
                session,
                str(updated_user_type.user_id),
                organization_id,
                user_user_type_id,
            )

            # Notify org admins of new review required
            await onboarding_notification_service.send_new_review_required_notification(
                session,
                str(updated_user_type.user_id),
                organization_id,
                user_user_type_id,
            )
        else:
            # Auto-approve
            updated_user_type = await user_user_type_crud.update_status(
                session,
                str(user_user_type.id),
                OnboardingStatus.APPROVED,
                organization_id,
                onboarded_at=datetime.now(timezone.utc),
            )
            if updated_user_type is None:
                raise ValueError(f"Failed to update user_user_type {user_user_type_id}")

            logger.info(
                f"Onboarding complete and auto-approved for user_user_type {user_user_type_id}"
            )

        return {
            "all_complete": True,
            "status": updated_user_type.onboarding_status.value,
        }

    def _validate_step_data(
        self,
        step,
        submitted_data: dict[str, Any],
    ) -> list[str]:
        """
        Validate submitted data against step requirements.

        Checks:
        1. All required_fields are present
        2. Field types match validation_rules (if specified)

        Args:
            step: OnboardingStep model instance
            submitted_data: Dict of submitted field values

        Returns:
            List of error messages (empty if valid)
        """
        errors = []

        # Check required fields
        if step.required_fields:
            for field_name in step.required_fields:
                if field_name not in submitted_data:
                    errors.append(f"Missing required field: {field_name}")
                elif (
                    submitted_data[field_name] is None
                    or submitted_data[field_name] == ""
                ):
                    errors.append(f"Field '{field_name}' cannot be empty")

        # Apply validation rules if present
        if step.validation_rules:
            for field_name, rules in step.validation_rules.items():
                if field_name not in submitted_data:
                    continue

                value = submitted_data[field_name]

                # Type validation
                if "type" in rules:
                    expected_type = rules["type"]
                    if expected_type == "string" and not isinstance(value, str):
                        errors.append(f"Field '{field_name}' must be a string")
                    elif expected_type == "number" and not isinstance(
                        value, (int, float)
                    ):
                        errors.append(f"Field '{field_name}' must be a number")
                    elif expected_type == "boolean" and not isinstance(value, bool):
                        errors.append(f"Field '{field_name}' must be a boolean")

                # Min/max length for strings
                if isinstance(value, str):
                    if "min_length" in rules and len(value) < rules["min_length"]:
                        errors.append(
                            f"Field '{field_name}' must be at least {rules['min_length']} characters"
                        )
                    if "max_length" in rules and len(value) > rules["max_length"]:
                        errors.append(
                            f"Field '{field_name}' must be at most {rules['max_length']} characters"
                        )

                # Min/max value for numbers
                if isinstance(value, (int, float)):
                    if "min_value" in rules and value < rules["min_value"]:
                        errors.append(
                            f"Field '{field_name}' must be at least {rules['min_value']}"
                        )
                    if "max_value" in rules and value > rules["max_value"]:
                        errors.append(
                            f"Field '{field_name}' must be at most {rules['max_value']}"
                        )

                # Pattern validation for strings
                if isinstance(value, str) and "pattern" in rules:
                    import re

                    if not re.match(rules["pattern"], value):
                        errors.append(
                            f"Field '{field_name}' does not match required pattern"
                        )

        return errors


# Singleton instance
onboarding_service = OnboardingService()
