"""
Bulk notification processor service.
Handles processing of bulk notifications in batches with rate limiting.
"""

import asyncio
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import ColumnElement, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.logger.logger import Logger as logger
from src.models.user import User
from src.serialisers.notification import (
    LEGACY_VERIFIED_CONTACT_KEY,
    VERIFIED_CONTACT_KEY,
)

# Import models (will be created per spec)
# from src.models.bulk_notification import BulkNotification
# from src.models.notification import Notification
# Import services (will be created per spec)
# from src.services.notifications.dispatcher import dispatcher
# from src.services.notifications.preference_checker import preference_checker
# Import task queue for enqueueing next batch
from src.services.tasks import TaskQueue


# Configuration constants - will be loaded from config when available
# Read the settings that actually exist. These were `getattr(settings,
# "NOTIFICATION_BULK_BATCH_SIZE"/"NOTIFICATION_BULK_RATE_LIMIT", ...)` - names
# no Settings field ever had - so both getattrs always took their default and
# the documented config.json knobs (notifications.bulk_batch_size /
# bulk_rate_limit_per_second) were inert. An operator lowering the send rate
# to protect a provider quota changed nothing.
#
# Named directly rather than via getattr: a typo is now an AttributeError at
# import, which is the whole reason the previous form hid this for so long.
NOTIFICATION_BULK_BATCH_SIZE = settings.BULK_BATCH_SIZE
NOTIFICATION_BULK_RATE_LIMIT = settings.BULK_RATE_LIMIT_PER_SECOND


# Which User column proves the recipient is reachable ON A GIVEN CHANNEL.
# verified_contact_only used to mean "User.email_verified" on every channel, so
# an SMS or WhatsApp blast silently dropped everyone who had verified a phone
# but not an email - the count and the send agreed with each other, so the
# under-send was invisible.
CHANNEL_VERIFICATION_COLUMN: dict[str, Any] = {
    "email": User.email_verified,
    "sms": User.phone_verified,
    "whatsapp": User.phone_verified,
}

# Channels that deliver to no external address, so there is nothing to verify.
# Filtering these on any verification column would drop recipients for a
# property irrelevant to how they are reached.
CHANNELS_WITHOUT_VERIFIABLE_CONTACT = frozenset({"in_app"})


def _resolve_verified_contact_only(filters: dict[str, Any]) -> bool:
    """Read the verification flag out of a filter dict, legacy key included.

    Filter dicts reach the processor from two places: a freshly validated
    RecipientFilter, and BulkNotification.extra_data["recipient_filters"] - a
    JSON side-car that may have been written by an older build and therefore
    still carries the pre-rename key. Both must resolve identically.

    An ABSENT key means "no verification filter" (the serialiser supplies the
    True default for API callers); this only affects direct service callers,
    for whom it is the long-standing behaviour.
    """
    if VERIFIED_CONTACT_KEY in filters:
        return bool(filters[VERIFIED_CONTACT_KEY])
    if LEGACY_VERIFIED_CONTACT_KEY in filters:
        logger.warning(
            f"Recipient filters carry deprecated '{LEGACY_VERIFIED_CONTACT_KEY}'; "
            f"treating it as '{VERIFIED_CONTACT_KEY}'. Stored bulk rows written "
            "before the rename keep working, but the check is now channel-aware."
        )
        return bool(filters[LEGACY_VERIFIED_CONTACT_KEY])
    return False


class BulkProcessor:
    """
    Bulk notification processor.

    Handles processing bulk notifications in batches with:
    - Rate limiting to prevent overwhelming providers
    - Preference checking for each recipient
    - Progress tracking and status updates
    - Automatic enqueueing of next batch jobs
    """

    async def process_bulk_notification(
        self, session: AsyncSession, bulk_id: str, batch_offset: int = 0
    ) -> dict[str, Any]:
        """
        Process a bulk notification batch.

        Args:
            session: Async database session
            bulk_id: UUID of the BulkNotification record
            batch_offset: Offset for batch processing (which batch to start from)

        Returns:
            dict: Progress stats including:
                - bulk_id: str
                - batch_offset: int
                - processed: int (recipients processed in this batch)
                - sent: int (successful sends in this batch)
                - failed: int (failed sends in this batch)
                - skipped: int (skipped due to preferences)
                - total_sent: int (cumulative sent count)
                - total_failed: int (cumulative failed count)
                - status: str (current status)
                - has_more: bool (whether more batches remain)
        """
        from src.models.bulk_notification import BulkNotification
        from src.services.notifications.dispatcher import notification_dispatcher
        from src.services.notifications.preference_checker import preference_checker

        bulk_uuid = UUID(bulk_id)

        # Load BulkNotification record
        result = await session.execute(
            select(BulkNotification).where(
                BulkNotification.id == bulk_uuid,
                BulkNotification.deleted_time.is_(None),
            )
        )
        bulk_notification = result.scalar_one_or_none()

        if not bulk_notification:
            logger.error(f"BulkNotification {bulk_id} not found")
            raise ValueError(f"BulkNotification {bulk_id} not found")

        # Check if cancelled
        if bulk_notification.status == "cancelled":
            logger.info(
                f"BulkNotification {bulk_id} was cancelled, skipping processing"
            )
            return {
                "bulk_id": bulk_id,
                "batch_offset": batch_offset,
                "processed": 0,
                "sent": 0,
                "failed": 0,
                "skipped": 0,
                "total_sent": bulk_notification.sent_count,
                "total_failed": bulk_notification.failed_count,
                "status": "cancelled",
                "has_more": False,
            }

        # Update status to processing if first batch
        if batch_offset == 0:
            bulk_notification.status = "processing"
            bulk_notification.started_time = datetime.now(timezone.utc)
            await session.commit()
            logger.info(f"Started processing BulkNotification {bulk_id}")

        # Get organization_id (can be None for system-wide notifications)
        org_id = (
            str(bulk_notification.organization_id)
            if bulk_notification.organization_id
            else None
        )

        # Parse filters from bulk notification extra_data or use defaults
        # BulkNotification.extra_data is a JSON field that may contain:
        # - recipient_filters: dict with filter criteria
        # - category_code: str for notification category
        # - is_urgent: bool to bypass quiet hours
        filters = {}
        extra_data = bulk_notification.extra_data or {}
        if isinstance(extra_data, dict):
            filters = extra_data.get("recipient_filters", {})

        # Get recipients for this batch.
        #
        # The channel comes off the record, which is exactly what the create
        # endpoint counted against (it passes request.channel, and persists
        # that same value as BulkNotification.channel). Count and send read the
        # channel from one place for the same reason they share
        # _build_recipient_conditions: they must not be able to disagree.
        recipients = await self.get_recipients(
            session=session,
            org_id=org_id,
            filters=filters,
            channel=bulk_notification.channel,
            limit=NOTIFICATION_BULK_BATCH_SIZE,
            offset=batch_offset * NOTIFICATION_BULK_BATCH_SIZE,
        )

        logger.info(
            f"Processing batch {batch_offset} for BulkNotification {bulk_id}: "
            f"{len(recipients)} recipients"
        )

        # Track batch stats
        batch_sent = 0
        batch_failed = 0
        batch_skipped = 0

        # Batch load preferences for all recipients to avoid N+1 queries
        recipient_ids = [str(r.id) for r in recipients]
        effective_org_id = org_id or (
            str(recipients[0].organization_id) if recipients else None
        )
        prefs_map = {}
        if effective_org_id and recipient_ids:
            prefs_map = await preference_checker.batch_load_preferences(
                session=session,
                user_ids=recipient_ids,
                organization_id=effective_org_id,
            )

        # Check if category is mandatory (one-time lookup)
        category_is_mandatory = False
        category_code = extra_data.get("category_code") if extra_data else None
        if category_code and effective_org_id:
            category = await preference_checker._get_category(
                session, UUID(effective_org_id), category_code
            )
            if category and not category.user_configurable:
                category_is_mandatory = True

        is_urgent = extra_data.get("is_urgent", False) if extra_data else False

        # Process each recipient
        for recipient in recipients:
            # Apply rate limiting
            await self._apply_rate_limit()

            try:
                # Check user preferences using cached data
                pref_data = prefs_map.get(str(recipient.id))
                if pref_data:
                    preference_result = (
                        preference_checker.check_can_send_with_cached_prefs(
                            channel=bulk_notification.channel,
                            pref_data=pref_data,
                            category_is_mandatory=category_is_mandatory,
                            is_urgent=is_urgent,
                        )
                    )
                else:
                    # Fallback to per-user query if no cached data
                    preference_result = await preference_checker.check_can_send(
                        session=session,
                        user_id=str(recipient.id),
                        organization_id=org_id or str(recipient.organization_id),
                        channel=bulk_notification.channel,
                        category_code=category_code,
                        is_urgent=is_urgent,
                    )

                if not preference_result.allowed:
                    batch_skipped += 1
                    logger.debug(
                        f"Skipped notification for user {recipient.id}: "
                        f"{preference_result.skip_reason}"
                    )
                    continue

                # Get recipient address based on channel
                recipient_address = await self._get_recipient_address(
                    recipient=recipient,
                    channel=bulk_notification.channel,
                    preference_result=preference_result,
                )

                if not recipient_address:
                    batch_skipped += 1
                    logger.debug(
                        f"No valid address for user {recipient.id} on channel {bulk_notification.channel}"
                    )
                    continue

                # Prepare notification content
                notification_data = {
                    "channel": bulk_notification.channel,
                    "recipient": recipient_address,
                    "user_id": str(recipient.id),
                    "organization_id": org_id,
                    "template_id": (
                        str(bulk_notification.template_id)
                        if bulk_notification.template_id
                        else None
                    ),
                    "subject": bulk_notification.subject,
                    "body_text": bulk_notification.body_text,
                    "body_html": bulk_notification.body_html,
                    "bulk_notification_id": bulk_id,
                    "metadata": {
                        "bulk_batch": batch_offset,
                        "recipient_name": f"{recipient.first_name or ''} {recipient.last_name or ''}".strip(),
                    },
                }

                # Send via dispatcher
                send_result = await notification_dispatcher.send_notification(
                    session=session, **notification_data  # type: ignore[arg-type]
                )

                if send_result and send_result.success:  # type: ignore[union-attr, attr-defined]
                    batch_sent += 1
                else:
                    batch_failed += 1
                    error_msg = getattr(send_result, "error_message", "Unknown error")
                    logger.warning(
                        f"Failed to send notification to {recipient.id}: "
                        f"{error_msg}"
                    )

            except Exception as e:
                batch_failed += 1
                logger.error(f"Error processing recipient {recipient.id}: {str(e)}")

        # Update bulk notification counts
        bulk_notification.sent_count += batch_sent
        bulk_notification.failed_count += batch_failed

        # Check if more batches remain
        total_processed = (batch_offset + 1) * NOTIFICATION_BULK_BATCH_SIZE
        has_more = (
            total_processed < bulk_notification.total_recipients
            and len(recipients) == NOTIFICATION_BULK_BATCH_SIZE
        )

        if has_more:
            # Enqueue next batch job
            next_batch_offset = batch_offset + 1
            await self._enqueue_next_batch(bulk_id, next_batch_offset)
            logger.info(
                f"Enqueued next batch {next_batch_offset} for BulkNotification {bulk_id}"
            )
        else:
            # Mark as completed
            bulk_notification.status = "completed"
            bulk_notification.completed_time = datetime.now(timezone.utc)
            logger.info(
                f"Completed BulkNotification {bulk_id}: "
                f"sent={bulk_notification.sent_count}, failed={bulk_notification.failed_count}"
            )

        await session.commit()

        return {
            "bulk_id": bulk_id,
            "batch_offset": batch_offset,
            "processed": len(recipients),
            "sent": batch_sent,
            "failed": batch_failed,
            "skipped": batch_skipped,
            "total_sent": bulk_notification.sent_count,
            "total_failed": bulk_notification.failed_count,
            "status": bulk_notification.status,
            "has_more": has_more,
        }

    def _build_recipient_conditions(
        self,
        org_id: Optional[str],
        filters: dict[str, Any],
        channel: str,
    ) -> Optional[list[ColumnElement[bool]]]:
        """Translate a RecipientFilter dict into SQL conditions on User.

        This is the SINGLE definition of "who does this bulk go to". Both
        get_recipients (what is actually sent) and count_recipients (the
        total_recipients the admin is shown and the progress bar is measured
        against) call it, so the two cannot diverge - previously each built its
        own query, both ignored every declared filter, and both therefore
        selected the whole organisation while claiming to honour a segment.

        Filters combine with AND; each one only narrows. The keys are the
        RecipientFilter field names (see src/serialisers/notification.py):

            - user_ids: List[str] - narrow to these users
            - role_ids: List[str] - narrow to holders of these roles
            - exclude_user_ids: List[str] - remove these users
            - verified_contact_only: bool - require that the contact address
              THIS CHANNEL uses is verified

        Legacy keys are still accepted so that direct callers of this service
        (and any bulk row queued before the contract was reconciled) keep
        working: "specific_user_ids" is an alias of user_ids, "email_verified_only"
        is an alias of verified_contact_only, "role" filters by a single role
        NAME, and "all_users" explicitly set to False with no positive selector
        means "nobody".

        Args:
            org_id: Tenant scope (None for system-wide sends)
            filters: RecipientFilter criteria
            channel: The bulk's channel. Decides WHICH verification column
                verified_contact_only checks - see CHANNEL_VERIFICATION_COLUMN.

        Returns:
            The list of conditions, or None if the filters select nobody at all
            (which the caller must treat as an empty audience rather than as
            "no filters").
        """
        from src.models.role import Role
        from src.models.user_role import UserRole

        conditions: list[ColumnElement[bool]] = [User.deleted_time.is_(None)]

        # Tenant scope. Always first: no filter below may widen past it.
        if org_id:
            conditions.append(User.organization_id == UUID(org_id))

        # --- user_ids (alias: legacy specific_user_ids) -------------------
        raw_user_ids = filters.get("user_ids") or filters.get("specific_user_ids")
        has_user_ids = bool(raw_user_ids)
        if raw_user_ids:
            conditions.append(User.id.in_([UUID(str(uid)) for uid in raw_user_ids]))

        # --- role_ids ------------------------------------------------------
        raw_role_ids = filters.get("role_ids")
        has_role_filter = bool(raw_role_ids)
        if raw_role_ids:
            role_subquery = select(UserRole.user_id).where(
                UserRole.role_id.in_([UUID(str(rid)) for rid in raw_role_ids]),
                UserRole.deleted_time.is_(None),
            )
            # Roles themselves are global in this schema; the assignment is what
            # is tenant-scoped. Scope the subquery too so a role id belonging to
            # another tenant's assignment can never widen the audience.
            if org_id:
                role_subquery = role_subquery.where(
                    UserRole.organization_id == UUID(org_id)  # type: ignore[attr-defined]
                )
            conditions.append(User.id.in_(role_subquery))

        # --- legacy "role" (a role NAME) ------------------------------------
        if filters.get("role"):
            has_role_filter = True
            legacy_role_subquery = (
                select(UserRole.user_id)
                .join(Role, UserRole.role_id == Role.id)
                .where(
                    Role.name == filters["role"],
                    Role.deleted_time.is_(None),
                    UserRole.deleted_time.is_(None),
                )
            )
            if org_id:
                legacy_role_subquery = legacy_role_subquery.where(
                    Role.organization_id == UUID(org_id)  # type: ignore[attr-defined]
                )
            conditions.append(User.id.in_(legacy_role_subquery))

        # --- verified_contact_only (alias: legacy email_verified_only) ------
        # Checked against the contact method the CHANNEL actually uses, not
        # always against email. Applied identically on both paths.
        if _resolve_verified_contact_only(filters):
            verification_column = CHANNEL_VERIFICATION_COLUMN.get(channel)
            if verification_column is not None:
                conditions.append(verification_column.is_(True))
            elif channel in CHANNELS_WITHOUT_VERIFIABLE_CONTACT:
                # Nothing to verify: in_app delivers to no external address, so
                # a verification filter here would drop reachable recipients
                # for an irrelevant property.
                pass
            else:
                # Unknown / future channel: apply NO verification filter and say
                # so, rather than silently guessing a column. Deliberately
                # permissive, matching preference_checker's "unknown channels
                # default to enabled" convention, and safe because it cannot
                # cause an unverified send: _get_recipient_address is the real
                # gate and returns None for a channel it does not know, so the
                # recipient is skipped at send time either way. Refusing here
                # would instead crash the worker on a stored row whose channel
                # a fork has since added.
                logger.warning(
                    f"verified_contact_only requested for unknown channel "
                    f"'{channel}'; no verification filter applied. Register the "
                    "channel in CHANNEL_VERIFICATION_COLUMN (or in "
                    "CHANNELS_WITHOUT_VERIFIABLE_CONTACT if it has no external "
                    "address) to have it filtered."
                )

        # --- exclude_user_ids ----------------------------------------------
        # Applied last and always wins, including over an explicit user_ids.
        raw_exclude_ids = filters.get("exclude_user_ids")
        if raw_exclude_ids:
            conditions.append(
                User.id.notin_([UUID(str(uid)) for uid in raw_exclude_ids])
            )

        # Legacy explicit "select nobody" guard.
        if (
            filters.get("all_users") is False
            and not has_user_ids
            and not has_role_filter
        ):
            return None

        return conditions

    async def get_recipients(
        self,
        session: AsyncSession,
        org_id: Optional[str],
        filters: dict[str, Any],
        channel: str,
        limit: int = 100,
        offset: int = 0,
    ) -> list[User]:
        """
        Get notification recipients based on filters.

        Args:
            session: Async database session
            org_id: Organization ID (None for system-wide notifications)
            filters: RecipientFilter criteria - see _build_recipient_conditions
            channel: The bulk's channel. Required, not defaulted: the audience
                genuinely depends on it, and a forgotten argument must be a
                type error rather than a silent fallback to email semantics.
            limit: Maximum number of users to return
            offset: Offset for pagination

        Returns:
            List[User]: List of user recipients
        """
        conditions = self._build_recipient_conditions(org_id, filters, channel)
        if conditions is None:
            return []

        query = (
            select(User)
            .where(*conditions)
            .order_by(User.created_time, User.id)
            .offset(offset)
            .limit(limit)
        )

        result = await session.execute(query)
        users = result.scalars().all()

        return list(users)

    async def count_recipients(
        self,
        session: AsyncSession,
        org_id: Optional[str],
        filters: dict[str, Any],
        channel: str,
    ) -> int:
        """
        Count notification recipients based on filters without fetching all records.

        This is more efficient than get_recipients for large recipient sets as it
        only returns the count instead of loading all user objects into memory.

        It builds its conditions from the same _build_recipient_conditions call
        get_recipients uses, so the number the admin approves at create time is
        by construction the number of people the job will walk.

        Args:
            session: Async database session
            org_id: Organization ID (None for system-wide notifications)
            filters: RecipientFilter criteria - see _build_recipient_conditions
            channel: The bulk's channel - the SAME value that will be persisted
                as BulkNotification.channel and read back by the send path, so
                the two queries cannot resolve a different verification column.

        Returns:
            int: Count of matching recipients
        """
        conditions = self._build_recipient_conditions(org_id, filters, channel)
        if conditions is None:
            return 0

        query = select(func.count()).select_from(User).where(*conditions)

        result = await session.execute(query)
        count = result.scalar_one()

        return count

    async def _apply_rate_limit(self) -> None:
        """
        Apply rate limiting to prevent overwhelming notification providers.

        Uses asyncio.sleep to throttle to NOTIFICATION_BULK_RATE_LIMIT per second.
        """
        if NOTIFICATION_BULK_RATE_LIMIT > 0:
            # Calculate delay: 1 second / rate_limit = delay between each notification
            delay = 1.0 / NOTIFICATION_BULK_RATE_LIMIT
            await asyncio.sleep(delay)

    async def _get_recipient_address(
        self, recipient: User, channel: str, preference_result: Any
    ) -> Optional[str]:
        """
        Get the recipient's address for the specified channel.

        Args:
            recipient: User model instance
            channel: Notification channel (email, sms, whatsapp)
            preference_result: PreferenceCheckResult with potential custom address

        Returns:
            str or None: Recipient address (email or phone) or None if not available
        """
        # Check if preference result has a preferred address
        if (
            hasattr(preference_result, "preferred_address")
            and preference_result.preferred_address
        ):
            return preference_result.preferred_address

        if channel == "email":
            return recipient.email if recipient.email_deliverable else None
        elif channel in ("sms", "whatsapp"):
            return recipient.phone if recipient.phone_verified else None

        return None

    async def _enqueue_next_batch(self, bulk_id: str, batch_offset: int) -> None:
        """
        Enqueue the next batch processing job.

        Args:
            bulk_id: UUID of the BulkNotification
            batch_offset: Offset for the next batch
        """
        try:
            await TaskQueue.enqueue_job(
                "process_bulk_notification_task", bulk_id, batch_offset
            )
        except Exception as e:
            logger.error(f"Failed to enqueue next batch for {bulk_id}: {str(e)}")
            raise

    async def cancel_bulk(self, session: AsyncSession, bulk_id: str, org_id: str):
        """
        Cancel a pending or processing bulk notification.

        Args:
            session: Async database session
            bulk_id: UUID of the BulkNotification
            org_id: Organization ID for tenant isolation

        Returns:
            BulkNotification: Updated bulk notification record

        Raises:
            ValueError: If bulk notification not found or cannot be cancelled
        """
        from src.models.bulk_notification import BulkNotification

        bulk_uuid = UUID(bulk_id)
        org_uuid = UUID(org_id)

        # Query with organization filter for tenant isolation
        result = await session.execute(
            select(BulkNotification).where(
                BulkNotification.id == bulk_uuid,
                BulkNotification.organization_id == org_uuid,
                BulkNotification.deleted_time.is_(None),
            )
        )
        bulk_notification = result.scalar_one_or_none()

        if not bulk_notification:
            raise ValueError(f"BulkNotification {bulk_id} not found")

        # Check if can be cancelled
        if bulk_notification.status in ("completed", "cancelled"):
            raise ValueError(
                f"BulkNotification {bulk_id} cannot be cancelled - "
                f"current status: {bulk_notification.status}"
            )

        # Update status to cancelled
        bulk_notification.status = "cancelled"
        bulk_notification.completed_time = datetime.now(timezone.utc)

        try:
            await session.commit()
            await session.refresh(bulk_notification)
            logger.info(
                f"Cancelled BulkNotification {bulk_id}: "
                f"sent={bulk_notification.sent_count}, failed={bulk_notification.failed_count}"
            )
        except Exception as e:
            await session.rollback()
            logger.error(f"Failed to cancel BulkNotification {bulk_id}: {str(e)}")
            raise

        return bulk_notification

    async def get_progress(
        self, session: AsyncSession, bulk_id: str, org_id: str
    ) -> dict[str, Any]:
        """
        Get current progress of a bulk notification.

        Args:
            session: Async database session
            bulk_id: UUID of the BulkNotification
            org_id: Organization ID for tenant isolation

        Returns:
            dict: Progress stats
        """
        from src.models.bulk_notification import BulkNotification

        bulk_uuid = UUID(bulk_id)
        org_uuid = UUID(org_id)

        result = await session.execute(
            select(BulkNotification).where(
                BulkNotification.id == bulk_uuid,
                BulkNotification.organization_id == org_uuid,
                BulkNotification.deleted_time.is_(None),
            )
        )
        bulk_notification = result.scalar_one_or_none()

        if not bulk_notification:
            raise ValueError(f"BulkNotification {bulk_id} not found")

        total = bulk_notification.total_recipients
        sent = bulk_notification.sent_count
        failed = bulk_notification.failed_count
        processed = sent + failed

        return {
            "bulk_id": bulk_id,
            "name": bulk_notification.name,
            "status": bulk_notification.status,
            "total_recipients": total,
            "sent_count": sent,
            "failed_count": failed,
            "processed_count": processed,
            "progress_percent": round((processed / total * 100), 2) if total > 0 else 0,
            "started_time": (
                bulk_notification.started_time.isoformat()
                if bulk_notification.started_time
                else None
            ),
            "completed_time": (
                bulk_notification.completed_time.isoformat()
                if bulk_notification.completed_time
                else None
            ),
        }


# Singleton instance
bulk_processor = BulkProcessor()
