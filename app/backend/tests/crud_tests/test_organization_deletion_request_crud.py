"""
CRUD tests for organization deletion requests.

Cancelling a deletion request soft-deletes it. Lookups must therefore ignore
cancelled requests, otherwise the organization stays "pending deletion" forever
and can never request deletion again.
"""

import pytest
from sqlalchemy import select

from src.crud.organization import (
    cancel_organization_deletion_request,
    get_organization_deletion_request,
    request_organization_deletion,
)


class TestOrganizationDeletionRequestLifecycle:
    """request -> cancel -> request again must work."""

    @pytest.mark.asyncio
    async def test_request_cancel_request_again(
        self, async_session, test_organization, test_user
    ):
        """A cancelled deletion request must not block a new request."""
        org_id = str(test_organization.id)

        first = await request_organization_deletion(
            async_session, org_id, str(test_user.id)
        )
        assert first is not None
        assert first.deleted_time is None

        active = await get_organization_deletion_request(async_session, org_id)
        assert active is not None
        assert active.id == first.id

        # Cancel -> no active request remains
        await cancel_organization_deletion_request(async_session, org_id)
        assert await get_organization_deletion_request(async_session, org_id) is None

        # Re-requesting must succeed and produce an ACTIVE request again
        second = await request_organization_deletion(
            async_session, org_id, str(test_user.id)
        )
        assert second.deleted_time is None

        active_again = await get_organization_deletion_request(async_session, org_id)
        assert active_again is not None
        assert active_again.id == second.id

    @pytest.mark.asyncio
    async def test_cancel_soft_deletes_and_preserves_history(
        self, async_session, test_organization, test_user
    ):
        """Cancelling sets deleted_time rather than hard deleting the row."""
        from src.models.organization_deletion_request import (
            OrganizationDeletionRequest,
        )

        org_id = str(test_organization.id)
        created = await request_organization_deletion(
            async_session, org_id, str(test_user.id)
        )

        await cancel_organization_deletion_request(async_session, org_id)

        result = await async_session.execute(
            select(OrganizationDeletionRequest).where(
                OrganizationDeletionRequest.id == created.id
            )
        )
        row = result.scalars().first()
        assert row is not None, "cancelled request must be soft deleted, not removed"
        assert row.deleted_time is not None

    @pytest.mark.asyncio
    async def test_duplicate_active_request_still_rejected(
        self, async_session, test_organization, test_user
    ):
        """Two active requests for the same organization are not allowed."""
        org_id = str(test_organization.id)
        await request_organization_deletion(async_session, org_id, str(test_user.id))

        with pytest.raises(ValueError, match="already been requested"):
            await request_organization_deletion(
                async_session, org_id, str(test_user.id)
            )

    @pytest.mark.asyncio
    async def test_cancel_without_active_request_raises(
        self, async_session, test_organization, test_user
    ):
        """Cancelling twice raises because there is no active request left."""
        org_id = str(test_organization.id)
        await request_organization_deletion(async_session, org_id, str(test_user.id))
        await cancel_organization_deletion_request(async_session, org_id)

        with pytest.raises(ValueError, match="No deletion request"):
            await cancel_organization_deletion_request(async_session, org_id)


class TestOrganizationDeletionRequestTenantIsolation:
    """Deletion requests are scoped to a single organization."""

    @pytest.mark.asyncio
    async def test_cancel_does_not_affect_other_organization(
        self,
        async_session,
        test_organization,
        second_organization,
        test_user,
        second_org_user,
    ):
        """Cancelling org A's request leaves org B's request active."""
        org_a = str(test_organization.id)
        org_b = str(second_organization.id)

        await request_organization_deletion(async_session, org_a, str(test_user.id))
        request_b = await request_organization_deletion(
            async_session, org_b, str(second_org_user.id)
        )

        await cancel_organization_deletion_request(async_session, org_a)

        assert await get_organization_deletion_request(async_session, org_a) is None
        still_active = await get_organization_deletion_request(async_session, org_b)
        assert still_active is not None
        assert still_active.id == request_b.id
