"""
Tests for bulk notification recipient filtering and template resolution.

Covers the N5 defect: recipient_filters were built at create time but never
persisted, the processor understood a different set of keys than the serialiser
declared, count and send used separate queries that both selected the whole
organisation, and template_code was never resolved to a template_id (so a
template-based bulk mailed an empty body to everyone and reported success).

Also covers the channel-aware verification filter: verified_contact_only (was
email_verified_only) checks the contact method the CHOSEN CHANNEL uses, so an
SMS or WhatsApp blast no longer silently skips users who verified their phone
but not their email.
"""

import logging
from unittest.mock import AsyncMock, patch
from uuid import UUID, uuid4

from httpx import AsyncClient
from pydantic import ValidationError
import pytest

from src.core.security import hash_password
from src.models.bulk_notification import BulkNotification
from src.models.notification_template import NotificationTemplate
from src.models.role import Role
from src.models.user import User
from src.models.user_role import UserRole
from src.serialisers.notification import RecipientFilter
from src.services.notifications.bulk_processor import bulk_processor


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
async def verified_users(async_session, test_organization):
    """Three verified users in the test organization."""
    users = []
    for i in range(3):
        user = User(
            email=f"verified{i}@test.com",
            password=hash_password("Password123!"),
            email_verified=True,
            organization_id=test_organization.id,
        )
        async_session.add(user)
        users.append(user)
    await async_session.commit()
    for user in users:
        await async_session.refresh(user)
    return users


@pytest.fixture
async def unverified_user(async_session, test_organization):
    """A user in the test organization who has not verified their email."""
    user = User(
        email="unverified@test.com",
        password=hash_password("Password123!"),
        email_verified=False,
        organization_id=test_organization.id,
    )
    async_session.add(user)
    await async_session.commit()
    await async_session.refresh(user)
    return user


@pytest.fixture
async def other_org_user(async_session, second_organization):
    """A verified user belonging to a DIFFERENT organization."""
    user = User(
        email="outsider@other.com",
        password=hash_password("Password123!"),
        email_verified=True,
        organization_id=second_organization.id,
    )
    async_session.add(user)
    await async_session.commit()
    await async_session.refresh(user)
    return user


@pytest.fixture
async def phone_verified_user(async_session, test_organization):
    """Verified PHONE, unverified email.

    Reachable by SMS/WhatsApp, and precisely the user the old email-only filter
    silently dropped from every phone-channel blast.
    """
    user = User(
        email="phoneverified@test.com",
        password=hash_password("Password123!"),
        email_verified=False,
        phone="+15550000001",
        phone_verified=True,
        organization_id=test_organization.id,
    )
    async_session.add(user)
    await async_session.commit()
    await async_session.refresh(user)
    return user


@pytest.fixture
async def phone_unverified_user(async_session, test_organization):
    """Verified email, unverified phone - the mirror image."""
    user = User(
        email="phoneunverified@test.com",
        password=hash_password("Password123!"),
        email_verified=True,
        phone="+15550000002",
        phone_verified=False,
        organization_id=test_organization.id,
    )
    async_session.add(user)
    await async_session.commit()
    await async_session.refresh(user)
    return user


@pytest.fixture
async def other_org_phone_user(async_session, second_organization):
    """A phone-verified user in a DIFFERENT organization."""
    user = User(
        email="outsider-phone@other.com",
        password=hash_password("Password123!"),
        email_verified=False,
        phone="+15550000003",
        phone_verified=True,
        organization_id=second_organization.id,
    )
    async_session.add(user)
    await async_session.commit()
    await async_session.refresh(user)
    return user


@pytest.fixture
async def editor_role(async_session, test_organization, verified_users):
    """A role held by the first verified user only."""
    role = Role(
        name=f"editors_{uuid4().hex[:8]}",
        description="Editors",
    )
    async_session.add(role)
    await async_session.commit()
    await async_session.refresh(role)

    async_session.add(
        UserRole(
            user_id=verified_users[0].id,
            role_id=role.id,
            organization_id=test_organization.id,
        )
    )
    await async_session.commit()
    return role


@pytest.fixture
async def email_template(async_session, test_organization):
    """An active email template for the test organization."""
    template = NotificationTemplate(
        organization_id=test_organization.id,
        code="bulk_promo",
        name="Bulk Promo",
        channel="email",
        subject="Promo",
        body_text="Hello {{name}}",
        body_html="<p>Hello {{name}}</p>",
        is_active=True,
    )
    async_session.add(template)
    await async_session.commit()
    await async_session.refresh(template)
    return template


@pytest.fixture
async def sms_template(async_session, test_organization):
    """An active SMS template for the test organization."""
    template = NotificationTemplate(
        organization_id=test_organization.id,
        code="bulk_sms",
        name="Bulk SMS",
        channel="sms",
        body_text="Hello {{name}}",
        is_active=True,
    )
    async_session.add(template)
    await async_session.commit()
    await async_session.refresh(template)
    return template


def _ids(users):
    return {str(u.id) for u in users}


# ============================================================================
# The filter contract: count path and send path must agree
# ============================================================================


class TestRecipientFilters:
    """Every filter the serialiser declares must be honoured on BOTH paths."""

    @pytest.mark.asyncio
    async def test_user_ids_reaches_only_those_users(
        self, async_session, test_organization, verified_users
    ):
        target = verified_users[1]
        filters = {"user_ids": [str(target.id)], "verified_contact_only": True}

        recipients = await bulk_processor.get_recipients(
            session=async_session,
            org_id=str(test_organization.id),
            filters=filters,
            channel="email",
        )

        assert _ids(recipients) == {str(target.id)}

    @pytest.mark.asyncio
    async def test_legacy_specific_user_ids_key_still_works(
        self, async_session, test_organization, verified_users
    ):
        """Direct service callers predating the reconciled contract keep working."""
        target = verified_users[2]

        recipients = await bulk_processor.get_recipients(
            session=async_session,
            org_id=str(test_organization.id),
            filters={"specific_user_ids": [str(target.id)]},
            channel="email",
        )

        assert _ids(recipients) == {str(target.id)}

    @pytest.mark.asyncio
    async def test_verified_contact_only_excludes_email_unverified(
        self,
        async_session,
        test_organization,
        verified_users,
        unverified_user,
    ):
        recipients = await bulk_processor.get_recipients(
            session=async_session,
            org_id=str(test_organization.id),
            filters={"verified_contact_only": True},
            channel="email",
        )

        assert str(unverified_user.id) not in _ids(recipients)
        assert _ids(verified_users).issubset(_ids(recipients))

    @pytest.mark.asyncio
    async def test_verified_contact_only_false_includes_unverified(
        self,
        async_session,
        test_organization,
        verified_users,
        unverified_user,
    ):
        recipients = await bulk_processor.get_recipients(
            session=async_session,
            org_id=str(test_organization.id),
            filters={"verified_contact_only": False},
            channel="email",
        )

        assert str(unverified_user.id) in _ids(recipients)

    @pytest.mark.asyncio
    async def test_exclude_user_ids_removes_them(
        self, async_session, test_organization, verified_users
    ):
        excluded = verified_users[0]

        recipients = await bulk_processor.get_recipients(
            session=async_session,
            org_id=str(test_organization.id),
            filters={
                "verified_contact_only": True,
                "exclude_user_ids": [str(excluded.id)],
            },
            channel="email",
        )

        assert str(excluded.id) not in _ids(recipients)
        assert str(verified_users[1].id) in _ids(recipients)

    @pytest.mark.asyncio
    async def test_exclude_beats_an_explicit_include(
        self, async_session, test_organization, verified_users
    ):
        """exclude_user_ids is applied last and always wins."""
        user = verified_users[0]

        recipients = await bulk_processor.get_recipients(
            session=async_session,
            org_id=str(test_organization.id),
            filters={
                "user_ids": [str(user.id)],
                "exclude_user_ids": [str(user.id)],
            },
            channel="email",
        )

        assert recipients == []

    @pytest.mark.asyncio
    async def test_role_ids_narrows_to_role_holders(
        self, async_session, test_organization, verified_users, editor_role
    ):
        recipients = await bulk_processor.get_recipients(
            session=async_session,
            org_id=str(test_organization.id),
            filters={"role_ids": [str(editor_role.id)], "verified_contact_only": True},
            channel="email",
        )

        assert _ids(recipients) == {str(verified_users[0].id)}

    @pytest.mark.asyncio
    async def test_filters_combine_with_and_never_widening(
        self, async_session, test_organization, verified_users, editor_role
    ):
        """user_ids AND role_ids intersect - a filter can only ever narrow."""
        non_editor = verified_users[1]

        recipients = await bulk_processor.get_recipients(
            session=async_session,
            org_id=str(test_organization.id),
            filters={
                "role_ids": [str(editor_role.id)],
                "user_ids": [str(non_editor.id)],
            },
            channel="email",
        )

        assert recipients == []

    @pytest.mark.asyncio
    async def test_no_filters_selects_the_whole_verified_org(
        self,
        async_session,
        test_organization,
        verified_users,
        unverified_user,
    ):
        recipients = await bulk_processor.get_recipients(
            session=async_session,
            org_id=str(test_organization.id),
            filters={"verified_contact_only": True},
            channel="email",
        )

        assert _ids(verified_users).issubset(_ids(recipients))
        assert str(unverified_user.id) not in _ids(recipients)

    @pytest.mark.asyncio
    async def test_all_users_false_with_no_selector_selects_nobody(
        self, async_session, test_organization, verified_users
    ):
        """Legacy explicit opt-out guard is preserved on both paths."""
        filters = {"all_users": False}

        assert (
            await bulk_processor.get_recipients(
                session=async_session,
                org_id=str(test_organization.id),
                filters=filters,
                channel="email",
            )
            == []
        )
        assert (
            await bulk_processor.count_recipients(
                session=async_session,
                org_id=str(test_organization.id),
                filters=filters,
                channel="email",
            )
            == 0
        )


class TestCountAndSendAgree:
    """total_recipients must be the number of people the job will walk.

    Both numbers come from _build_recipient_conditions, and now both must also
    come from the same CHANNEL - a count taken on one channel's verification
    column and a send taken on another's would reintroduce exactly the silent
    divergence this function exists to prevent.
    """

    @pytest.mark.parametrize("channel", ["email", "sms", "whatsapp", "in_app"])
    @pytest.mark.parametrize(
        "filter_name",
        [
            "verified_only",
            "unverified_included",
            "single_user",
            "role_scoped",
            "excluded",
            "legacy_key",
        ],
    )
    @pytest.mark.asyncio
    async def test_count_matches_send_audience(
        self,
        async_session,
        test_organization,
        verified_users,
        unverified_user,
        phone_verified_user,
        phone_unverified_user,
        editor_role,
        other_org_user,
        filter_name,
        channel,
    ):
        filters = {
            "verified_only": {"verified_contact_only": True},
            "unverified_included": {"verified_contact_only": False},
            "single_user": {"user_ids": [str(verified_users[0].id)]},
            "role_scoped": {"role_ids": [str(editor_role.id)]},
            "excluded": {
                "verified_contact_only": True,
                "exclude_user_ids": [str(verified_users[0].id)],
            },
            "legacy_key": {"email_verified_only": True},
        }[filter_name]

        count = await bulk_processor.count_recipients(
            session=async_session,
            org_id=str(test_organization.id),
            filters=filters,
            channel=channel,
        )
        recipients = await bulk_processor.get_recipients(
            session=async_session,
            org_id=str(test_organization.id),
            filters=filters,
            limit=1000,
            channel=channel,
        )

        assert count == len(recipients)


class TestChannelAwareVerification:
    """verified_contact_only checks the address the CHANNEL actually uses.

    Before this, it was hardcoded to User.email_verified on every channel, so
    an SMS or WhatsApp blast silently skipped users who had verified their
    phone but not their email - the count and the send agreed, so the admin
    never learned they had under-sent.
    """

    @pytest.mark.parametrize("channel", ["sms", "whatsapp"])
    @pytest.mark.asyncio
    async def test_phone_channels_check_phone_verified(
        self,
        async_session,
        test_organization,
        phone_verified_user,
        phone_unverified_user,
        channel,
    ):
        recipients = await bulk_processor.get_recipients(
            session=async_session,
            org_id=str(test_organization.id),
            filters={"verified_contact_only": True},
            channel=channel,
            limit=1000,
        )

        # Phone verified, email NOT verified: reachable on this channel, and
        # the old email-only filter would have dropped them.
        assert str(phone_verified_user.id) in _ids(recipients)
        # Email verified, phone NOT verified: unreachable on this channel.
        assert str(phone_unverified_user.id) not in _ids(recipients)

    @pytest.mark.asyncio
    async def test_email_channel_still_checks_email_verified(
        self,
        async_session,
        test_organization,
        phone_verified_user,
        phone_unverified_user,
    ):
        recipients = await bulk_processor.get_recipients(
            session=async_session,
            org_id=str(test_organization.id),
            filters={"verified_contact_only": True},
            channel="email",
            limit=1000,
        )

        assert str(phone_unverified_user.id) in _ids(recipients)
        assert str(phone_verified_user.id) not in _ids(recipients)

    @pytest.mark.asyncio
    async def test_in_app_applies_no_verification_filter(
        self,
        async_session,
        test_organization,
        verified_users,
        unverified_user,
        phone_verified_user,
        phone_unverified_user,
    ):
        """in_app delivers to no external address, so there is nothing to verify."""
        recipients = await bulk_processor.get_recipients(
            session=async_session,
            org_id=str(test_organization.id),
            filters={"verified_contact_only": True},
            channel="in_app",
            limit=1000,
        )

        recipient_ids = _ids(recipients)
        assert _ids(verified_users).issubset(recipient_ids)
        assert str(unverified_user.id) in recipient_ids
        assert str(phone_verified_user.id) in recipient_ids
        assert str(phone_unverified_user.id) in recipient_ids

    @pytest.mark.asyncio
    async def test_unknown_channel_is_permissive_not_a_crash(
        self,
        async_session,
        test_organization,
        verified_users,
        unverified_user,
    ):
        """A fork's new channel must not crash the worker or guess a column."""
        recipients = await bulk_processor.get_recipients(
            session=async_session,
            org_id=str(test_organization.id),
            filters={"verified_contact_only": True},
            channel="web_push",
            limit=1000,
        )

        assert str(unverified_user.id) in _ids(recipients)
        assert _ids(verified_users).issubset(_ids(recipients))

    @pytest.mark.parametrize(
        "channel", ["email", "sms", "whatsapp", "in_app", "web_push"]
    )
    @pytest.mark.asyncio
    async def test_false_applies_no_verification_filter_on_any_channel(
        self,
        async_session,
        test_organization,
        verified_users,
        unverified_user,
        phone_verified_user,
        phone_unverified_user,
        channel,
    ):
        recipients = await bulk_processor.get_recipients(
            session=async_session,
            org_id=str(test_organization.id),
            filters={"verified_contact_only": False},
            channel=channel,
            limit=1000,
        )

        recipient_ids = _ids(recipients)
        assert str(unverified_user.id) in recipient_ids
        assert str(phone_verified_user.id) in recipient_ids
        assert str(phone_unverified_user.id) in recipient_ids

    @pytest.mark.parametrize("channel", ["email", "sms", "whatsapp", "in_app"])
    @pytest.mark.asyncio
    async def test_channel_aware_filter_never_crosses_the_tenant_boundary(
        self,
        async_session,
        test_organization,
        other_org_user,
        other_org_phone_user,
        channel,
    ):
        """Every channel's verification filter narrows WITHIN the org scope."""
        recipients = await bulk_processor.get_recipients(
            session=async_session,
            org_id=str(test_organization.id),
            filters={"verified_contact_only": True},
            channel=channel,
            limit=1000,
        )

        recipient_ids = _ids(recipients)
        assert str(other_org_user.id) not in recipient_ids
        assert str(other_org_phone_user.id) not in recipient_ids


class TestLegacyVerifiedContactKey:
    """email_verified_only is a deprecated alias that must keep working.

    RecipientFilter forbids extra keys, so an unmigrated caller would otherwise
    get a 422 on a payload that worked yesterday. Filters are also PERSISTED
    into BulkNotification.extra_data, so a bulk created before the rename can
    have the legacy key sitting in the database - that row must still resolve,
    and now resolve channel-aware.
    """

    def test_serialiser_accepts_the_legacy_key_and_warns(self, caplog):
        with caplog.at_level(logging.WARNING):
            parsed = RecipientFilter(email_verified_only=False)

        assert parsed.verified_contact_only is False
        assert "email_verified_only" in caplog.text

    def test_serialiser_defaults_to_true_when_neither_key_is_given(self):
        assert RecipientFilter().verified_contact_only is True

    def test_new_key_wins_when_both_are_present(self):
        parsed = RecipientFilter.model_validate(
            {"email_verified_only": True, "verified_contact_only": False}
        )

        assert parsed.verified_contact_only is False

    def test_unknown_keys_are_still_forbidden(self):
        """The alias is an exception, not a hole in extra="forbid"."""
        with pytest.raises(ValidationError):
            RecipientFilter.model_validate({"not_a_filter": True})

    @pytest.mark.parametrize("channel", ["sms", "whatsapp"])
    @pytest.mark.asyncio
    async def test_persisted_legacy_key_resolves_channel_aware(
        self,
        async_session,
        test_organization,
        phone_verified_user,
        phone_unverified_user,
        caplog,
        channel,
    ):
        """The most likely breakage: a row written BEFORE the rename.

        Simulates BulkNotification.extra_data["recipient_filters"] as an older
        build stored it, read straight back by the processor.
        """
        stored_filters = {"email_verified_only": True}

        with caplog.at_level(logging.WARNING):
            recipients = await bulk_processor.get_recipients(
                session=async_session,
                org_id=str(test_organization.id),
                filters=stored_filters,
                channel=channel,
                limit=1000,
            )
            count = await bulk_processor.count_recipients(
                session=async_session,
                org_id=str(test_organization.id),
                filters=stored_filters,
                channel=channel,
            )

        assert str(phone_verified_user.id) in _ids(recipients)
        assert str(phone_unverified_user.id) not in _ids(recipients)
        assert count == len(recipients)
        assert "email_verified_only" in caplog.text

    @pytest.mark.asyncio
    async def test_persisted_legacy_key_on_email_is_unchanged(
        self,
        async_session,
        test_organization,
        phone_verified_user,
        phone_unverified_user,
    ):
        recipients = await bulk_processor.get_recipients(
            session=async_session,
            org_id=str(test_organization.id),
            filters={"email_verified_only": True},
            channel="email",
            limit=1000,
        )

        assert str(phone_unverified_user.id) in _ids(recipients)
        assert str(phone_verified_user.id) not in _ids(recipients)

    @pytest.mark.asyncio
    async def test_legacy_request_payload_is_accepted_and_normalised(
        self,
        client: AsyncClient,
        async_session,
        test_admin_token,
        verified_users,
    ):
        """A fork upgrading mid-flight must not get a 422 on yesterday's payload."""
        with patch(
            "src.services.tasks.TaskQueue.enqueue_job", new_callable=AsyncMock
        ) as enqueue:
            enqueue.return_value = "job"
            response = await client.post(
                "/api/v1/notifications/bulk",
                json={
                    "name": "Legacy payload",
                    "channel": "email",
                    "subject": "Hi",
                    "body_text": "Hello",
                    "recipient_filters": {"email_verified_only": True},
                },
                headers={"Authorization": test_admin_token},
            )

        assert response.status_code == 201
        bulk = await async_session.get(
            BulkNotification, UUID(response.json()["bulk_notification"]["id"])
        )
        stored = bulk.extra_data["recipient_filters"]

        # Normalised on the way in, so nothing new is written with the old key.
        assert stored["verified_contact_only"] is True
        assert "email_verified_only" not in stored

    @pytest.mark.asyncio
    async def test_legacy_sms_bulk_reaches_phone_verified_users(
        self,
        client: AsyncClient,
        async_session,
        test_admin_token,
        phone_verified_user,
        phone_unverified_user,
        sms_template,
    ):
        """End to end on the channel the old behaviour under-sent on."""
        with patch(
            "src.services.tasks.TaskQueue.enqueue_job", new_callable=AsyncMock
        ) as enqueue:
            enqueue.return_value = "job"
            response = await client.post(
                "/api/v1/notifications/bulk",
                json={
                    "name": "SMS blast",
                    "channel": "sms",
                    "template_code": sms_template.code,
                    "recipient_filters": {"email_verified_only": True},
                },
                headers={"Authorization": test_admin_token},
            )

        assert response.status_code == 201
        bulk = await async_session.get(
            BulkNotification, UUID(response.json()["bulk_notification"]["id"])
        )

        recipients = await bulk_processor.get_recipients(
            session=async_session,
            org_id=str(bulk.organization_id),
            filters=bulk.extra_data["recipient_filters"],
            channel=bulk.channel,
            limit=1000,
        )

        assert str(phone_verified_user.id) in _ids(recipients)
        assert str(phone_unverified_user.id) not in _ids(recipients)
        assert len(recipients) == bulk.total_recipients


class TestBulkTenantIsolation:
    """A bulk in org A must never reach a user in org B."""

    @pytest.mark.asyncio
    async def test_org_scope_excludes_other_org_users(
        self, async_session, test_organization, verified_users, other_org_user
    ):
        recipients = await bulk_processor.get_recipients(
            session=async_session,
            org_id=str(test_organization.id),
            filters={"verified_contact_only": True},
            limit=1000,
            channel="email",
        )

        assert str(other_org_user.id) not in _ids(recipients)

    @pytest.mark.asyncio
    async def test_user_ids_cannot_reach_across_the_tenant_boundary(
        self, async_session, test_organization, other_org_user
    ):
        """Naming a foreign user id explicitly must still select nobody."""
        filters = {"user_ids": [str(other_org_user.id)]}

        recipients = await bulk_processor.get_recipients(
            session=async_session,
            org_id=str(test_organization.id),
            filters=filters,
            channel="email",
        )
        count = await bulk_processor.count_recipients(
            session=async_session,
            org_id=str(test_organization.id),
            filters=filters,
            channel="email",
        )

        assert recipients == []
        assert count == 0


# ============================================================================
# Create endpoint: persistence and template resolution
# ============================================================================


class TestCreateBulkNotification:
    """POST /notifications/bulk must persist what it counted."""

    @pytest.mark.asyncio
    async def test_persists_recipient_filters_into_extra_data(
        self,
        client: AsyncClient,
        async_session,
        test_admin_token,
        verified_users,
    ):
        target = verified_users[0]
        request_data = {
            "name": "Segment send",
            "channel": "email",
            "subject": "Hi",
            "body_text": "Hello",
            "recipient_filters": {
                "user_ids": [str(target.id)],
                "verified_contact_only": True,
            },
        }

        with patch(
            "src.services.tasks.TaskQueue.enqueue_job", new_callable=AsyncMock
        ) as enqueue:
            enqueue.return_value = "job"
            response = await client.post(
                "/api/v1/notifications/bulk",
                json=request_data,
                headers={"Authorization": test_admin_token},
            )

        assert response.status_code == 201
        body = response.json()["bulk_notification"]
        assert body["total_recipients"] == 1

        bulk = await async_session.get(BulkNotification, UUID(body["id"]))
        assert bulk is not None
        assert bulk.extra_data is not None
        stored = bulk.extra_data["recipient_filters"]
        assert stored["user_ids"] == [str(target.id)]
        assert stored["verified_contact_only"] is True

    @pytest.mark.asyncio
    async def test_persisted_filters_drive_the_processor(
        self,
        client: AsyncClient,
        async_session,
        test_admin_token,
        verified_users,
        unverified_user,
    ):
        """End to end: what the admin chose is what the worker would send to."""
        target = verified_users[1]

        with patch(
            "src.services.tasks.TaskQueue.enqueue_job", new_callable=AsyncMock
        ) as enqueue:
            enqueue.return_value = "job"
            response = await client.post(
                "/api/v1/notifications/bulk",
                json={
                    "name": "Segment send",
                    "channel": "email",
                    "subject": "Hi",
                    "body_text": "Hello",
                    "recipient_filters": {"user_ids": [str(target.id)]},
                },
                headers={"Authorization": test_admin_token},
            )

        assert response.status_code == 201
        bulk = await async_session.get(
            BulkNotification, UUID(response.json()["bulk_notification"]["id"])
        )

        recipients = await bulk_processor.get_recipients(
            session=async_session,
            org_id=str(bulk.organization_id),
            filters=bulk.extra_data["recipient_filters"],
            limit=1000,
            channel="email",
        )

        assert _ids(recipients) == {str(target.id)}

    @pytest.mark.asyncio
    async def test_total_recipients_zero_is_rejected(
        self, client: AsyncClient, test_admin_token
    ):
        """The guard can now actually fire - previously the count was org-wide."""
        with patch(
            "src.services.tasks.TaskQueue.enqueue_job", new_callable=AsyncMock
        ) as enqueue:
            enqueue.return_value = "job"
            response = await client.post(
                "/api/v1/notifications/bulk",
                json={
                    "name": "Nobody",
                    "channel": "email",
                    "body_text": "Hello",
                    "recipient_filters": {"user_ids": [str(uuid4())]},
                },
                headers={"Authorization": test_admin_token},
            )

        assert response.status_code == 400
        assert response.json()["detail_code"] == "common.validation_error"

    @pytest.mark.asyncio
    async def test_template_code_resolves_to_template_id(
        self,
        client: AsyncClient,
        async_session,
        test_admin_token,
        verified_users,
        email_template,
    ):
        with patch(
            "src.services.tasks.TaskQueue.enqueue_job", new_callable=AsyncMock
        ) as enqueue:
            enqueue.return_value = "job"
            response = await client.post(
                "/api/v1/notifications/bulk",
                json={
                    "name": "Template send",
                    "channel": "email",
                    "template_code": email_template.code,
                    "recipient_filters": {"verified_contact_only": True},
                },
                headers={"Authorization": test_admin_token},
            )

        assert response.status_code == 201
        bulk = await async_session.get(
            BulkNotification, UUID(response.json()["bulk_notification"]["id"])
        )
        assert bulk.template_id == email_template.id
        assert bulk.extra_data["template_code"] == email_template.code

    @pytest.mark.asyncio
    async def test_unresolvable_template_code_is_rejected_at_create(
        self, client: AsyncClient, test_admin_token, verified_users
    ):
        """Otherwise the job mails an empty body to everyone and reports success."""
        with patch(
            "src.services.tasks.TaskQueue.enqueue_job", new_callable=AsyncMock
        ) as enqueue:
            enqueue.return_value = "job"
            response = await client.post(
                "/api/v1/notifications/bulk",
                json={
                    "name": "Broken template",
                    "channel": "email",
                    "template_code": "no_such_template",
                    "recipient_filters": {"verified_contact_only": True},
                },
                headers={"Authorization": test_admin_token},
            )

        assert response.status_code == 400
        assert response.json()["detail_code"] == "notification.template_not_found"

    @pytest.mark.asyncio
    async def test_template_on_the_wrong_channel_is_rejected(
        self,
        client: AsyncClient,
        test_admin_token,
        verified_users,
        email_template,
    ):
        """An email template cannot back an SMS blast."""
        with patch(
            "src.services.tasks.TaskQueue.enqueue_job", new_callable=AsyncMock
        ) as enqueue:
            enqueue.return_value = "job"
            response = await client.post(
                "/api/v1/notifications/bulk",
                json={
                    "name": "Wrong channel",
                    "channel": "sms",
                    "template_code": email_template.code,
                    "recipient_filters": {"verified_contact_only": True},
                },
                headers={"Authorization": test_admin_token},
            )

        assert response.status_code == 400
        assert response.json()["detail_code"] == "notification.template_not_found"

    @pytest.mark.asyncio
    async def test_shipped_ui_payload_still_works(
        self, client: AsyncClient, test_admin_token, verified_users
    ):
        """BulkNotificationsPage.tsx sends only verified_contact_only - keep it valid."""
        with patch(
            "src.services.tasks.TaskQueue.enqueue_job", new_callable=AsyncMock
        ) as enqueue:
            enqueue.return_value = "job"
            response = await client.post(
                "/api/v1/notifications/bulk",
                json={
                    "name": "Test Bulk Campaign",
                    "channel": "email",
                    "subject": "Important Update",
                    "body_text": "Hello everyone!",
                    "recipient_filters": {"verified_contact_only": True},
                },
                headers={"Authorization": test_admin_token},
            )

        assert response.status_code == 201

    @pytest.mark.asyncio
    async def test_bulk_is_scoped_to_the_creators_organization(
        self,
        client: AsyncClient,
        async_session,
        test_admin_token,
        verified_users,
        other_org_user,
    ):
        """Tenant isolation: an org-wide bulk in org A never counts org B users."""
        with patch(
            "src.services.tasks.TaskQueue.enqueue_job", new_callable=AsyncMock
        ) as enqueue:
            enqueue.return_value = "job"
            response = await client.post(
                "/api/v1/notifications/bulk",
                json={
                    "name": "Org wide",
                    "channel": "email",
                    "subject": "Hi",
                    "body_text": "Hello",
                    "recipient_filters": {"verified_contact_only": True},
                },
                headers={"Authorization": test_admin_token},
            )

        assert response.status_code == 201
        bulk = await async_session.get(
            BulkNotification, UUID(response.json()["bulk_notification"]["id"])
        )

        recipients = await bulk_processor.get_recipients(
            session=async_session,
            org_id=str(bulk.organization_id),
            filters=bulk.extra_data["recipient_filters"],
            limit=1000,
            channel="email",
        )

        assert str(other_org_user.id) not in _ids(recipients)
        assert len(recipients) == bulk.total_recipients
