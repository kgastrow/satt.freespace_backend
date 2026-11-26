"""
Unit tests for announcement models and CRUD operations.
Tests Announcement and AnnouncementDismissal model creation, field constraints, relationships,
and CRUD operations with multi-tenancy support.
"""

from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio

from src.crud import announcement as announcement_crud
from src.crud import announcement_dismissal as dismissal_crud
from src.models.announcement import Announcement
from src.models.announcement_dismissal import AnnouncementDismissal
from src.models.permission import Permission
from src.models.role_permission import RolePermission


# ============================================================================
# ANNOUNCEMENT PERMISSION FIXTURES
# ============================================================================


@pytest_asyncio.fixture(scope="function")
async def announcement_permissions(async_session, admin_role, test_user):
    """Create announcement permissions and assign them to admin_role."""
    permissions_data = [
        ("announcements:read", "Read Announcements", "announcements", "read"),
        ("announcements:write", "Write Announcements", "announcements", "write"),
        ("announcements:delete", "Delete Announcements", "announcements", "delete"),
    ]

    for code, name, resource, action in permissions_data:
        permission = Permission(
            code=code,
            name=name,
            description=f"{name} permission",
            resource=resource,
            action=action,
            display_order=0,
        )
        async_session.add(permission)
        await async_session.commit()
        await async_session.refresh(permission)

        # Assign to admin_role
        role_permission = RolePermission(
            role_id=admin_role.id,
            permission_id=permission.id,
            granted_by=test_user.id,
        )
        async_session.add(role_permission)
        await async_session.commit()

    return True


class TestAnnouncementModel:
    """Tests for Announcement model."""

    @pytest.mark.asyncio
    async def test_create_org_announcement(
        self, async_session, test_organization, test_user
    ):
        """Test creating an organization-scoped announcement."""
        announcement = Announcement(
            organization_id=test_organization.id,
            title="Scheduled Maintenance",
            body="System maintenance scheduled for tonight at 10 PM.",
            priority="high",
            created_by_id=test_user.id,
        )
        async_session.add(announcement)
        await async_session.commit()
        await async_session.refresh(announcement)

        assert announcement.id is not None
        assert announcement.organization_id == test_organization.id
        assert announcement.title == "Scheduled Maintenance"
        assert announcement.body == "System maintenance scheduled for tonight at 10 PM."
        assert announcement.priority == "high"
        assert announcement.created_by_id == test_user.id
        assert announcement.is_dismissible is True
        assert announcement.cta_dismisses is True
        assert announcement.created_time is not None
        assert announcement.deleted_time is None

    @pytest.mark.asyncio
    async def test_create_platform_wide_announcement(
        self, async_session, test_admin_user
    ):
        """Test creating a platform-wide announcement (NULL organization_id)."""
        announcement = Announcement(
            organization_id=None,  # Platform-wide
            title="Terms of Service Update",
            body="Our Terms of Service have been updated. Please review.",
            priority="critical",
            created_by_id=test_admin_user.id,
            is_dismissible=False,  # Non-dismissible
        )
        async_session.add(announcement)
        await async_session.commit()
        await async_session.refresh(announcement)

        assert announcement.id is not None
        assert announcement.organization_id is None
        assert announcement.priority == "critical"
        assert announcement.is_dismissible is False

    @pytest.mark.asyncio
    async def test_announcement_with_scheduling(
        self, async_session, test_organization, test_user
    ):
        """Test announcement with start and end times."""
        start_time = datetime.now(timezone.utc) + timedelta(hours=1)
        end_time = datetime.now(timezone.utc) + timedelta(days=7)

        announcement = Announcement(
            organization_id=test_organization.id,
            title="New Feature Launch",
            body="Check out our new dashboard!",
            priority="normal",
            created_by_id=test_user.id,
            start_time=start_time,
            end_time=end_time,
        )
        async_session.add(announcement)
        await async_session.commit()
        await async_session.refresh(announcement)

        # Compare times accounting for potential DB timezone handling
        assert announcement.start_time is not None
        assert announcement.end_time is not None
        # Verify the times are close (within 1 second to handle microsecond precision)
        assert (
            abs(
                (
                    announcement.start_time - start_time.replace(tzinfo=None)
                ).total_seconds()
            )
            < 1
        )
        assert (
            abs((announcement.end_time - end_time.replace(tzinfo=None)).total_seconds())
            < 1
        )

    @pytest.mark.asyncio
    async def test_announcement_with_styling(
        self, async_session, test_organization, test_user
    ):
        """Test announcement with custom styling options."""
        announcement = Announcement(
            organization_id=test_organization.id,
            title="Special Offer",
            body="50% off premium plans this week!",
            priority="high",
            created_by_id=test_user.id,
            background_color="#FF5733",
            featured_image_url="https://example.com/banner.jpg",
        )
        async_session.add(announcement)
        await async_session.commit()
        await async_session.refresh(announcement)

        assert announcement.background_color == "#FF5733"
        assert announcement.featured_image_url == "https://example.com/banner.jpg"

    @pytest.mark.asyncio
    async def test_announcement_with_cta(
        self, async_session, test_organization, test_user
    ):
        """Test announcement with call-to-action button."""
        announcement = Announcement(
            organization_id=test_organization.id,
            title="Update Required",
            body="Please update your profile information.",
            priority="normal",
            created_by_id=test_user.id,
            cta_text="Update Profile",
            cta_url="/profile/edit",
            cta_dismisses=True,
            cta_button_color="#007BFF",
            cta_button_variant="solid",
        )
        async_session.add(announcement)
        await async_session.commit()
        await async_session.refresh(announcement)

        assert announcement.cta_text == "Update Profile"
        assert announcement.cta_url == "/profile/edit"
        assert announcement.cta_dismisses is True
        assert announcement.cta_button_color == "#007BFF"
        assert announcement.cta_button_variant == "solid"

    @pytest.mark.asyncio
    async def test_announcement_priority_levels(
        self, async_session, test_organization, test_user
    ):
        """Test all priority levels are valid."""
        priorities = ["critical", "high", "normal", "low"]

        for priority in priorities:
            announcement = Announcement(
                organization_id=test_organization.id,
                title=f"{priority.title()} Priority",
                body=f"This is a {priority} priority announcement.",
                priority=priority,
                created_by_id=test_user.id,
            )
            async_session.add(announcement)
            await async_session.commit()
            await async_session.refresh(announcement)

            assert announcement.priority == priority

    @pytest.mark.asyncio
    async def test_announcement_organization_relationship(
        self, async_session, test_organization, test_user
    ):
        """Test announcement has proper relationship to organization."""
        announcement = Announcement(
            organization_id=test_organization.id,
            title="Test Relationship",
            body="Testing organization relationship.",
            priority="normal",
            created_by_id=test_user.id,
        )
        async_session.add(announcement)
        await async_session.commit()
        await async_session.refresh(announcement)

        # Load relationship
        await async_session.refresh(announcement, ["organization"])
        assert announcement.organization is not None
        assert announcement.organization.id == test_organization.id


class TestAnnouncementDismissalModel:
    """Tests for AnnouncementDismissal model."""

    @pytest.mark.asyncio
    async def test_create_dismissal(self, async_session, test_organization, test_user):
        """Test creating an announcement dismissal."""
        # First create an announcement
        announcement = Announcement(
            organization_id=test_organization.id,
            title="Dismissible Announcement",
            body="You can dismiss this.",
            priority="normal",
            created_by_id=test_user.id,
        )
        async_session.add(announcement)
        await async_session.commit()
        await async_session.refresh(announcement)

        # Create dismissal
        dismissal = AnnouncementDismissal(
            announcement_id=announcement.id,
            user_id=test_user.id,
        )
        async_session.add(dismissal)
        await async_session.commit()
        await async_session.refresh(dismissal)

        assert dismissal.id is not None
        assert dismissal.announcement_id == announcement.id
        assert dismissal.user_id == test_user.id
        assert dismissal.dismissed_time is not None

    @pytest.mark.asyncio
    async def test_dismissal_unique_constraint(
        self, async_session, test_organization, test_user
    ):
        """Test unique constraint on (announcement_id, user_id)."""
        # Create announcement
        announcement = Announcement(
            organization_id=test_organization.id,
            title="Unique Test",
            body="Testing unique constraint.",
            priority="normal",
            created_by_id=test_user.id,
        )
        async_session.add(announcement)
        await async_session.commit()
        await async_session.refresh(announcement)

        # Create first dismissal
        dismissal1 = AnnouncementDismissal(
            announcement_id=announcement.id,
            user_id=test_user.id,
        )
        async_session.add(dismissal1)
        await async_session.commit()

        # Try to create duplicate dismissal - should raise error
        dismissal2 = AnnouncementDismissal(
            announcement_id=announcement.id,
            user_id=test_user.id,
        )
        async_session.add(dismissal2)

        with pytest.raises(Exception):  # SQLAlchemy will raise IntegrityError
            await async_session.commit()

    @pytest.mark.asyncio
    async def test_dismissal_relationship(
        self, async_session, test_organization, test_user
    ):
        """Test dismissal has proper relationship to announcement."""
        # Create announcement
        announcement = Announcement(
            organization_id=test_organization.id,
            title="Relationship Test",
            body="Testing relationships.",
            priority="normal",
            created_by_id=test_user.id,
        )
        async_session.add(announcement)
        await async_session.commit()
        await async_session.refresh(announcement)

        # Create dismissal
        dismissal = AnnouncementDismissal(
            announcement_id=announcement.id,
            user_id=test_user.id,
        )
        async_session.add(dismissal)
        await async_session.commit()
        await async_session.refresh(dismissal)

        # Load relationship
        await async_session.refresh(dismissal, ["announcement"])
        assert dismissal.announcement is not None
        assert dismissal.announcement.id == announcement.id
        assert dismissal.announcement.title == "Relationship Test"

    @pytest.mark.asyncio
    async def test_multiple_users_dismiss_same_announcement(
        self, async_session, test_organization, test_user, admin_user
    ):
        """Test multiple users can dismiss the same announcement."""
        # Create announcement
        announcement = Announcement(
            organization_id=test_organization.id,
            title="Multi-User Dismiss",
            body="Multiple users can dismiss this.",
            priority="normal",
            created_by_id=test_user.id,
        )
        async_session.add(announcement)
        await async_session.commit()
        await async_session.refresh(announcement)

        # User 1 dismisses
        dismissal1 = AnnouncementDismissal(
            announcement_id=announcement.id,
            user_id=test_user.id,
        )
        async_session.add(dismissal1)
        await async_session.commit()

        # User 2 dismisses (different user, same announcement - should succeed)
        dismissal2 = AnnouncementDismissal(
            announcement_id=announcement.id,
            user_id=admin_user.id,
        )
        async_session.add(dismissal2)
        await async_session.commit()
        await async_session.refresh(dismissal2)

        assert dismissal1.user_id == test_user.id
        assert dismissal2.user_id == admin_user.id
        assert dismissal1.announcement_id == dismissal2.announcement_id


class TestAnnouncementCRUD:
    """Tests for Announcement CRUD operations."""

    @pytest.mark.asyncio
    async def test_create_org_announcement_crud(
        self, async_session, test_organization, test_user
    ):
        """Test creating an organization-scoped announcement via CRUD."""
        announcement_data = {
            "title": "System Maintenance",
            "body": "Scheduled maintenance tonight at 10 PM.",
            "priority": "high",
        }

        announcement = await announcement_crud.create_announcement(
            session=async_session,
            announcement_data=announcement_data,
            organization_id=str(test_organization.id),
            created_by_id=str(test_user.id),
        )

        assert announcement.id is not None
        assert announcement.organization_id == test_organization.id
        assert announcement.title == "System Maintenance"
        assert announcement.priority == "high"
        assert announcement.is_dismissible is True

    @pytest.mark.asyncio
    async def test_create_platform_wide_announcement_crud(
        self, async_session, test_admin_user
    ):
        """Test creating a platform-wide announcement via CRUD."""
        announcement_data = {
            "title": "Platform Update",
            "body": "New features available!",
            "priority": "critical",
            "is_dismissible": False,
        }

        announcement = await announcement_crud.create_announcement(
            session=async_session,
            announcement_data=announcement_data,
            organization_id=None,  # Platform-wide
            created_by_id=str(test_admin_user.id),
        )

        assert announcement.id is not None
        assert announcement.organization_id is None
        assert announcement.is_dismissible is False

    @pytest.mark.asyncio
    async def test_get_announcement_by_id(
        self, async_session, test_organization, test_user
    ):
        """Test retrieving announcement by ID."""
        announcement_data = {
            "title": "Test Announcement",
            "body": "Test body",
            "priority": "normal",
        }

        created = await announcement_crud.create_announcement(
            session=async_session,
            announcement_data=announcement_data,
            organization_id=str(test_organization.id),
            created_by_id=str(test_user.id),
        )

        retrieved = await announcement_crud.get_announcement_by_id(
            session=async_session,
            announcement_id=str(created.id),
            organization_id=str(test_organization.id),
        )

        assert retrieved is not None
        assert retrieved.id == created.id
        assert retrieved.title == "Test Announcement"

    @pytest.mark.asyncio
    async def test_get_announcement_tenant_isolation(
        self, async_session, test_organization, second_organization, test_user
    ):
        """Test tenant isolation: cannot access other org's announcements."""
        announcement_data = {
            "title": "Org 1 Announcement",
            "body": "Only for org 1",
            "priority": "normal",
        }

        created = await announcement_crud.create_announcement(
            session=async_session,
            announcement_data=announcement_data,
            organization_id=str(test_organization.id),
            created_by_id=str(test_user.id),
        )

        # Try to access from different organization
        retrieved = await announcement_crud.get_announcement_by_id(
            session=async_session,
            announcement_id=str(created.id),
            organization_id=str(second_organization.id),
        )

        assert retrieved is None

    @pytest.mark.asyncio
    async def test_get_active_announcements_time_filtering(
        self, async_session, test_organization, test_user
    ):
        """Test active announcements filtered by time window."""
        now = datetime.now(timezone.utc)

        # Active (no time constraints)
        ann1_data = {
            "title": "Active 1",
            "body": "No time constraints",
            "priority": "normal",
        }
        ann1 = await announcement_crud.create_announcement(
            async_session, ann1_data, str(test_organization.id), str(test_user.id)
        )

        # Active (within time window)
        ann2_data = {
            "title": "Active 2",
            "body": "Within time window",
            "priority": "normal",
            "start_time": now - timedelta(hours=1),
            "end_time": now + timedelta(hours=1),
        }
        ann2 = await announcement_crud.create_announcement(
            async_session, ann2_data, str(test_organization.id), str(test_user.id)
        )

        # Not yet active
        ann3_data = {
            "title": "Future",
            "body": "Not yet active",
            "priority": "normal",
            "start_time": now + timedelta(hours=2),
            "end_time": now + timedelta(hours=3),
        }
        await announcement_crud.create_announcement(
            async_session, ann3_data, str(test_organization.id), str(test_user.id)
        )

        # Expired
        ann4_data = {
            "title": "Expired",
            "body": "Already expired",
            "priority": "normal",
            "start_time": now - timedelta(hours=3),
            "end_time": now - timedelta(hours=2),
        }
        await announcement_crud.create_announcement(
            async_session, ann4_data, str(test_organization.id), str(test_user.id)
        )

        active = await announcement_crud.get_active_announcements(
            session=async_session,
            organization_id=str(test_organization.id),
            exclude_dismissed=False,
        )

        assert len(active) == 2
        active_ids = {str(a.id) for a in active}
        assert str(ann1.id) in active_ids
        assert str(ann2.id) in active_ids

    @pytest.mark.asyncio
    async def test_get_active_announcements_sorting(
        self, async_session, test_organization, test_user
    ):
        """Test active announcements sorted correctly: non-dismissible first, then priority, then date."""
        # Create announcements in reverse order
        ann1 = await announcement_crud.create_announcement(
            async_session,
            {"title": "Low Priority", "body": "Low", "priority": "low"},
            str(test_organization.id),
            str(test_user.id),
        )

        ann2 = await announcement_crud.create_announcement(
            async_session,
            {
                "title": "Critical Non-Dismissible",
                "body": "Critical",
                "priority": "critical",
                "is_dismissible": False,
            },
            str(test_organization.id),
            str(test_user.id),
        )

        ann3 = await announcement_crud.create_announcement(
            async_session,
            {"title": "High Priority", "body": "High", "priority": "high"},
            str(test_organization.id),
            str(test_user.id),
        )

        active = await announcement_crud.get_active_announcements(
            session=async_session,
            organization_id=str(test_organization.id),
            exclude_dismissed=False,
        )

        # Non-dismissible (ann2) should be first, then high (ann3), then low (ann1)
        assert len(active) == 3
        assert active[0].id == ann2.id
        assert active[1].id == ann3.id
        assert active[2].id == ann1.id

    @pytest.mark.asyncio
    async def test_get_active_announcements_mixed_scope(
        self, async_session, test_organization, test_user, test_admin_user
    ):
        """Test active announcements includes both org-specific and platform-wide."""
        # Org-specific
        org_ann = await announcement_crud.create_announcement(
            async_session,
            {"title": "Org Announcement", "body": "Org only", "priority": "normal"},
            str(test_organization.id),
            str(test_user.id),
        )

        # Platform-wide
        platform_ann = await announcement_crud.create_announcement(
            async_session,
            {
                "title": "Platform Announcement",
                "body": "For everyone",
                "priority": "high",
            },
            None,  # Platform-wide
            str(test_admin_user.id),
        )

        active = await announcement_crud.get_active_announcements(
            session=async_session,
            organization_id=str(test_organization.id),
            exclude_dismissed=False,
        )

        assert len(active) == 2
        active_ids = {str(a.id) for a in active}
        assert str(org_ann.id) in active_ids
        assert str(platform_ann.id) in active_ids

    @pytest.mark.asyncio
    async def test_get_active_announcements_exclude_dismissed(
        self, async_session, test_organization, test_user
    ):
        """Test active announcements excludes dismissed announcements for user."""
        ann1 = await announcement_crud.create_announcement(
            async_session,
            {"title": "Announcement 1", "body": "First", "priority": "normal"},
            str(test_organization.id),
            str(test_user.id),
        )

        ann2 = await announcement_crud.create_announcement(
            async_session,
            {"title": "Announcement 2", "body": "Second", "priority": "normal"},
            str(test_organization.id),
            str(test_user.id),
        )

        # Dismiss ann1
        await dismissal_crud.create_dismissal(
            async_session, str(ann1.id), str(test_user.id)
        )

        # Get active announcements (exclude dismissed)
        active = await announcement_crud.get_active_announcements(
            session=async_session,
            organization_id=str(test_organization.id),
            user_id=str(test_user.id),
            exclude_dismissed=True,
        )

        assert len(active) == 1
        assert active[0].id == ann2.id

    @pytest.mark.asyncio
    async def test_update_announcement(
        self, async_session, test_organization, test_user
    ):
        """Test updating an announcement."""
        created = await announcement_crud.create_announcement(
            async_session,
            {"title": "Original Title", "body": "Original body", "priority": "normal"},
            str(test_organization.id),
            str(test_user.id),
        )

        updated = await announcement_crud.update_announcement(
            session=async_session,
            announcement_id=str(created.id),
            organization_id=str(test_organization.id),
            announcement_data={"title": "Updated Title", "priority": "high"},
        )

        assert updated is not None
        assert updated.title == "Updated Title"
        assert updated.priority == "high"
        assert updated.body == "Original body"  # Unchanged

    @pytest.mark.asyncio
    async def test_update_announcement_tenant_isolation(
        self, async_session, test_organization, second_organization, test_user
    ):
        """Test cannot update another org's announcement."""
        created = await announcement_crud.create_announcement(
            async_session,
            {"title": "Org 1 Ann", "body": "Test", "priority": "normal"},
            str(test_organization.id),
            str(test_user.id),
        )

        # Try to update from different org
        updated = await announcement_crud.update_announcement(
            session=async_session,
            announcement_id=str(created.id),
            organization_id=str(second_organization.id),
            announcement_data={"title": "Hacked"},
        )

        assert updated is None

    @pytest.mark.asyncio
    async def test_soft_delete_announcement(
        self, async_session, test_organization, test_user
    ):
        """Test soft deleting an announcement."""
        created = await announcement_crud.create_announcement(
            async_session,
            {"title": "To Delete", "body": "Will be deleted", "priority": "normal"},
            str(test_organization.id),
            str(test_user.id),
        )

        deleted = await announcement_crud.soft_delete_announcement(
            session=async_session,
            announcement_id=str(created.id),
            organization_id=str(test_organization.id),
        )

        assert deleted is not None
        assert deleted.deleted_time is not None

        # Should not appear in active announcements
        active = await announcement_crud.get_active_announcements(
            session=async_session,
            organization_id=str(test_organization.id),
            exclude_dismissed=False,
        )

        assert len(active) == 0

    @pytest.mark.asyncio
    async def test_soft_delete_tenant_isolation(
        self, async_session, test_organization, second_organization, test_user
    ):
        """Test cannot delete another org's announcement."""
        created = await announcement_crud.create_announcement(
            async_session,
            {"title": "Org 1 Ann", "body": "Test", "priority": "normal"},
            str(test_organization.id),
            str(test_user.id),
        )

        # Try to delete from different org
        deleted = await announcement_crud.soft_delete_announcement(
            session=async_session,
            announcement_id=str(created.id),
            organization_id=str(second_organization.id),
        )

        assert deleted is None


class TestAnnouncementDismissalCRUD:
    """Tests for AnnouncementDismissal CRUD operations."""

    @pytest.mark.asyncio
    async def test_create_dismissal_crud(
        self, async_session, test_organization, test_user
    ):
        """Test creating a dismissal via CRUD."""
        announcement = await announcement_crud.create_announcement(
            async_session,
            {"title": "Test", "body": "Test", "priority": "normal"},
            str(test_organization.id),
            str(test_user.id),
        )

        dismissal = await dismissal_crud.create_dismissal(
            session=async_session,
            announcement_id=str(announcement.id),
            user_id=str(test_user.id),
        )

        assert dismissal.id is not None
        assert dismissal.announcement_id == announcement.id
        assert dismissal.user_id == test_user.id

    @pytest.mark.asyncio
    async def test_create_dismissal_duplicate_prevention(
        self, async_session, test_organization, test_user
    ):
        """Test cannot create duplicate dismissal."""
        announcement = await announcement_crud.create_announcement(
            async_session,
            {"title": "Test", "body": "Test", "priority": "normal"},
            str(test_organization.id),
            str(test_user.id),
        )

        # First dismissal
        await dismissal_crud.create_dismissal(
            async_session, str(announcement.id), str(test_user.id)
        )

        # Try duplicate - should raise error
        with pytest.raises(ValueError):
            await dismissal_crud.create_dismissal(
                async_session, str(announcement.id), str(test_user.id)
            )

    @pytest.mark.asyncio
    async def test_get_user_dismissals(
        self, async_session, test_organization, test_user
    ):
        """Test getting all dismissals for a user."""
        ann1 = await announcement_crud.create_announcement(
            async_session,
            {"title": "Ann 1", "body": "Test", "priority": "normal"},
            str(test_organization.id),
            str(test_user.id),
        )

        ann2 = await announcement_crud.create_announcement(
            async_session,
            {"title": "Ann 2", "body": "Test", "priority": "normal"},
            str(test_organization.id),
            str(test_user.id),
        )

        # Dismiss both
        await dismissal_crud.create_dismissal(
            async_session, str(ann1.id), str(test_user.id)
        )
        await dismissal_crud.create_dismissal(
            async_session, str(ann2.id), str(test_user.id)
        )

        dismissals = await dismissal_crud.get_user_dismissals(
            session=async_session, user_id=str(test_user.id)
        )

        assert len(dismissals) == 2
        assert str(ann1.id) in dismissals
        assert str(ann2.id) in dismissals

    @pytest.mark.asyncio
    async def test_is_dismissed(self, async_session, test_organization, test_user):
        """Test checking if announcement is dismissed."""
        announcement = await announcement_crud.create_announcement(
            async_session,
            {"title": "Test", "body": "Test", "priority": "normal"},
            str(test_organization.id),
            str(test_user.id),
        )

        # Not dismissed yet
        is_dismissed = await dismissal_crud.is_dismissed(
            async_session, str(announcement.id), str(test_user.id)
        )
        assert is_dismissed is False

        # Dismiss
        await dismissal_crud.create_dismissal(
            async_session, str(announcement.id), str(test_user.id)
        )

        # Now dismissed
        is_dismissed = await dismissal_crud.is_dismissed(
            async_session, str(announcement.id), str(test_user.id)
        )
        assert is_dismissed is True

    @pytest.mark.asyncio
    async def test_get_dismissals_for_announcement(
        self, async_session, test_organization, test_user, admin_user
    ):
        """Test getting all dismissals for a specific announcement."""
        announcement = await announcement_crud.create_announcement(
            async_session,
            {"title": "Test", "body": "Test", "priority": "normal"},
            str(test_organization.id),
            str(test_user.id),
        )

        # Two users dismiss
        await dismissal_crud.create_dismissal(
            async_session, str(announcement.id), str(test_user.id)
        )
        await dismissal_crud.create_dismissal(
            async_session, str(announcement.id), str(admin_user.id)
        )

        dismissals = await dismissal_crud.get_dismissals_for_announcement(
            session=async_session, announcement_id=str(announcement.id)
        )

        assert len(dismissals) == 2
        user_ids = {d.user_id for d in dismissals}
        assert test_user.id in user_ids
        assert admin_user.id in user_ids


class TestAnnouncementAPI:
    """Tests for Announcement API endpoints."""

    @pytest.mark.asyncio
    async def test_get_active_announcements(
        self, client, async_session, test_organization, test_user, test_jwt_token
    ):
        """Test GET /announcements/active endpoint."""
        # Create an active announcement
        announcement = Announcement(
            organization_id=test_organization.id,
            title="Active Announcement",
            body="This is active",
            priority="normal",
            created_by_id=test_user.id,
        )
        async_session.add(announcement)
        await async_session.commit()

        response = await client.get(
            "/api/v1/announcements/active",
            headers={"Authorization": test_jwt_token},
        )

        assert response.status_code == 200
        data = response.json()
        assert "announcements" in data
        assert len(data["announcements"]) == 1
        assert data["announcements"][0]["title"] == "Active Announcement"

    @pytest.mark.asyncio
    async def test_create_announcement_org_admin(
        self,
        client,
        test_organization,
        admin_user,
        admin_token,
        announcement_permissions,
    ):
        """Test POST /announcements endpoint with org admin permissions."""
        request_data = {
            "title": "New Announcement",
            "body": "This is a new announcement",
            "priority": "high",
            "is_platform_wide": False,
        }

        response = await client.post(
            "/api/v1/announcements",
            headers={"Authorization": admin_token},
            json=request_data,
        )

        assert response.status_code == 201
        data = response.json()
        assert data["title"] == "New Announcement"
        assert data["priority"] == "high"
        assert data["organization_id"] is not None
        assert data["is_platform_wide"] is False

    @pytest.mark.asyncio
    async def test_create_announcement_platform_wide_super_admin(
        self, client, test_admin_user, test_super_admin_token
    ):
        """Test POST /announcements endpoint with platform-wide flag (super admin only)."""
        request_data = {
            "title": "Platform Announcement",
            "body": "This is platform-wide",
            "priority": "critical",
            "is_platform_wide": True,
            "is_dismissible": False,
        }

        response = await client.post(
            "/api/v1/announcements",
            headers={"Authorization": test_super_admin_token},
            json=request_data,
        )

        assert response.status_code == 201
        data = response.json()
        assert data["title"] == "Platform Announcement"
        assert data["organization_id"] is None
        assert data["is_platform_wide"] is True
        assert data["is_dismissible"] is False

    @pytest.mark.asyncio
    async def test_create_announcement_platform_wide_forbidden_regular_admin(
        self, client, admin_user, admin_token, announcement_permissions
    ):
        """Test POST /announcements with platform-wide flag fails for non-super admins."""
        request_data = {
            "title": "Platform Announcement",
            "body": "Trying platform-wide",
            "priority": "critical",
            "is_platform_wide": True,
        }

        response = await client.post(
            "/api/v1/announcements",
            headers={"Authorization": admin_token},
            json=request_data,
        )

        assert response.status_code == 403
        assert "super admins" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_get_announcement_by_id(
        self,
        client,
        async_session,
        test_organization,
        test_user,
        admin_user,
        admin_token,
        announcement_permissions,
    ):
        """Test GET /announcements/{id} endpoint."""
        announcement = Announcement(
            organization_id=test_organization.id,
            title="Test Announcement",
            body="Test body",
            priority="normal",
            created_by_id=test_user.id,
        )
        async_session.add(announcement)
        await async_session.commit()
        await async_session.refresh(announcement)

        response = await client.get(
            f"/api/v1/announcements/{announcement.id}",
            headers={"Authorization": admin_token},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["title"] == "Test Announcement"
        assert data["id"] == str(announcement.id)

    @pytest.mark.asyncio
    async def test_list_announcements(
        self,
        client,
        async_session,
        test_organization,
        test_user,
        admin_token,
        announcement_permissions,
    ):
        """Test GET /announcements endpoint (admin list view)."""
        # Create multiple announcements
        for i in range(3):
            ann = Announcement(
                organization_id=test_organization.id,
                title=f"Announcement {i}",
                body=f"Body {i}",
                priority="normal",
                created_by_id=test_user.id,
            )
            async_session.add(ann)
        await async_session.commit()

        response = await client.get(
            "/api/v1/announcements",
            headers={"Authorization": admin_token},
        )

        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert data["total"] == 3
        assert len(data["items"]) == 3

    @pytest.mark.asyncio
    async def test_update_announcement(
        self,
        client,
        async_session,
        test_organization,
        test_user,
        admin_token,
        announcement_permissions,
    ):
        """Test PUT /announcements/{id} endpoint."""
        announcement = Announcement(
            organization_id=test_organization.id,
            title="Original Title",
            body="Original body",
            priority="normal",
            created_by_id=test_user.id,
        )
        async_session.add(announcement)
        await async_session.commit()
        await async_session.refresh(announcement)

        update_data = {
            "title": "Updated Title",
            "priority": "high",
        }

        response = await client.put(
            f"/api/v1/announcements/{announcement.id}",
            headers={"Authorization": admin_token},
            json=update_data,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["title"] == "Updated Title"
        assert data["priority"] == "high"
        assert data["body"] == "Original body"

    @pytest.mark.asyncio
    async def test_delete_announcement(
        self,
        client,
        async_session,
        test_organization,
        test_user,
        admin_token,
        announcement_permissions,
    ):
        """Test DELETE /announcements/{id} endpoint (soft delete)."""
        announcement = Announcement(
            organization_id=test_organization.id,
            title="To Delete",
            body="Will be deleted",
            priority="normal",
            created_by_id=test_user.id,
        )
        async_session.add(announcement)
        await async_session.commit()
        await async_session.refresh(announcement)

        response = await client.delete(
            f"/api/v1/announcements/{announcement.id}",
            headers={"Authorization": admin_token},
        )

        assert response.status_code == 204

        # Verify it's soft deleted
        await async_session.refresh(announcement)
        assert announcement.deleted_time is not None

    @pytest.mark.asyncio
    async def test_dismiss_announcement(
        self, client, async_session, test_organization, test_user, test_jwt_token
    ):
        """Test POST /announcements/{id}/dismiss endpoint."""
        announcement = Announcement(
            organization_id=test_organization.id,
            title="Dismissible",
            body="You can dismiss this",
            priority="normal",
            created_by_id=test_user.id,
            is_dismissible=True,
        )
        async_session.add(announcement)
        await async_session.commit()
        await async_session.refresh(announcement)

        response = await client.post(
            f"/api/v1/announcements/{announcement.id}/dismiss",
            headers={"Authorization": test_jwt_token},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["message"] == "Announcement dismissed successfully"
        assert data["announcement_id"] == str(announcement.id)

    @pytest.mark.asyncio
    async def test_dismiss_non_dismissible_announcement_forbidden(
        self, client, async_session, test_organization, test_user, test_jwt_token
    ):
        """Test dismissing non-dismissible announcement returns 400."""
        announcement = Announcement(
            organization_id=test_organization.id,
            title="Non-Dismissible",
            body="You cannot dismiss this",
            priority="critical",
            created_by_id=test_user.id,
            is_dismissible=False,
        )
        async_session.add(announcement)
        await async_session.commit()
        await async_session.refresh(announcement)

        response = await client.post(
            f"/api/v1/announcements/{announcement.id}/dismiss",
            headers={"Authorization": test_jwt_token},
        )

        assert response.status_code == 400
        assert "not dismissible" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_dismiss_announcement_twice_conflict(
        self, client, async_session, test_organization, test_user, test_jwt_token
    ):
        """Test dismissing same announcement twice returns 409."""
        announcement = Announcement(
            organization_id=test_organization.id,
            title="Dismissible",
            body="You can dismiss this",
            priority="normal",
            created_by_id=test_user.id,
            is_dismissible=True,
        )
        async_session.add(announcement)
        await async_session.commit()
        await async_session.refresh(announcement)

        # First dismissal - success
        response1 = await client.post(
            f"/api/v1/announcements/{announcement.id}/dismiss",
            headers={"Authorization": test_jwt_token},
        )
        assert response1.status_code == 200

        # Second dismissal - conflict
        response2 = await client.post(
            f"/api/v1/announcements/{announcement.id}/dismiss",
            headers={"Authorization": test_jwt_token},
        )
        assert response2.status_code == 409

    @pytest.mark.asyncio
    async def test_create_announcement_requires_permission(
        self, client, test_organization, test_user, test_jwt_token
    ):
        """Test creating announcement without permission returns 403."""
        request_data = {
            "title": "New Announcement",
            "body": "Test",
            "priority": "normal",
            "is_platform_wide": False,
        }

        response = await client.post(
            "/api/v1/announcements",
            headers={"Authorization": test_jwt_token},
            json=request_data,
        )

        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_announcement_tenant_isolation(
        self,
        client,
        async_session,
        test_organization,
        second_organization,
        test_user,
        admin_token,
        announcement_permissions,
    ):
        """Test users cannot access announcements from other organizations."""
        # Create announcement in second_organization
        announcement = Announcement(
            organization_id=second_organization.id,
            title="Other Org Announcement",
            body="From another org",
            priority="normal",
            created_by_id=test_user.id,
        )
        async_session.add(announcement)
        await async_session.commit()
        await async_session.refresh(announcement)

        # Try to access with admin_token (from test_organization)
        response = await client.get(
            f"/api/v1/announcements/{announcement.id}",
            headers={"Authorization": admin_token},
        )

        assert response.status_code == 404
