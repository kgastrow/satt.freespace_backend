"""
Unit tests for feedback models and CRUD operations.
Tests Feedback and FeedbackAttachment model creation, field constraints, relationships,
and CRUD operations with multi-tenancy support.
"""

from datetime import datetime, timedelta, timezone

import pytest

from src.core.query_params import FilterOperator, FilterSpec
from src.crud.feedback import (
    create_feedback,
    create_feedback_attachment,
    delete_attachment,
    get_attachments_by_feedback_id,
    get_feedback_by_id,
    get_feedbacks_list,
    get_user_feedbacks,
    soft_delete_feedback,
    update_feedback,
)
from src.models.feedback import Feedback, FeedbackAttachment


# ============================================================================
# FEEDBACK MODEL TESTS
# ============================================================================


class TestFeedbackModel:
    """Tests for Feedback model."""

    @pytest.mark.asyncio
    async def test_create_feedback_bug_report(
        self, async_session, test_organization, test_user
    ):
        """Test creating a bug report feedback."""
        feedback = Feedback(
            organization_id=test_organization.id,
            user_id=test_user.id,
            type="bug",
            rating=2,
            subject="Button not working",
            message="The submit button on the form doesn't respond when clicked.",
            page_url="https://example.com/form",
            user_agent="Mozilla/5.0...",
            screen_resolution="1920x1080",
            status="new",
        )
        async_session.add(feedback)
        await async_session.commit()
        await async_session.refresh(feedback)

        assert feedback.id is not None
        assert feedback.organization_id == test_organization.id
        assert feedback.user_id == test_user.id
        assert feedback.type == "bug"
        assert feedback.rating == 2
        assert feedback.subject == "Button not working"
        assert (
            feedback.message
            == "The submit button on the form doesn't respond when clicked."
        )
        assert feedback.page_url == "https://example.com/form"
        assert feedback.user_agent == "Mozilla/5.0..."
        assert feedback.screen_resolution == "1920x1080"
        assert feedback.status == "new"
        assert feedback.created_time is not None
        assert feedback.deleted_time is None
        assert feedback.admin_notes is None
        assert feedback.admin_response is None

    @pytest.mark.asyncio
    async def test_create_feedback_suggestion(
        self, async_session, test_organization, test_user
    ):
        """Test creating a suggestion feedback."""
        feedback = Feedback(
            organization_id=test_organization.id,
            user_id=test_user.id,
            type="suggestion",
            rating=4,
            subject="Add dark mode",
            message="It would be great to have a dark mode option for the interface.",
            status="new",
        )
        async_session.add(feedback)
        await async_session.commit()
        await async_session.refresh(feedback)

        assert feedback.type == "suggestion"
        assert feedback.rating == 4
        assert feedback.subject == "Add dark mode"

    @pytest.mark.asyncio
    async def test_create_feedback_complaint(
        self, async_session, test_organization, test_user
    ):
        """Test creating a complaint feedback."""
        feedback = Feedback(
            organization_id=test_organization.id,
            user_id=test_user.id,
            type="complaint",
            rating=1,
            subject="Slow performance",
            message="The application is very slow and takes forever to load.",
            status="new",
        )
        async_session.add(feedback)
        await async_session.commit()
        await async_session.refresh(feedback)

        assert feedback.type == "complaint"
        assert feedback.rating == 1

    @pytest.mark.asyncio
    async def test_create_feedback_praise(
        self, async_session, test_organization, test_user
    ):
        """Test creating a praise feedback."""
        feedback = Feedback(
            organization_id=test_organization.id,
            user_id=test_user.id,
            type="praise",
            rating=5,
            subject="Excellent feature!",
            message="The new reporting feature is amazing and very intuitive.",
            status="new",
        )
        async_session.add(feedback)
        await async_session.commit()
        await async_session.refresh(feedback)

        assert feedback.type == "praise"
        assert feedback.rating == 5

    @pytest.mark.asyncio
    async def test_create_feedback_other(
        self, async_session, test_organization, test_user
    ):
        """Test creating an 'other' type feedback."""
        feedback = Feedback(
            organization_id=test_organization.id,
            user_id=test_user.id,
            type="other",
            subject="General question",
            message="How do I export my data?",
            status="new",
        )
        async_session.add(feedback)
        await async_session.commit()
        await async_session.refresh(feedback)

        assert feedback.type == "other"
        assert feedback.rating is None

    @pytest.mark.asyncio
    async def test_feedback_status_values(
        self, async_session, test_organization, test_user
    ):
        """Test all valid feedback status values."""
        statuses = ["new", "in_review", "resolved", "dismissed"]

        for status in statuses:
            feedback = Feedback(
                organization_id=test_organization.id,
                user_id=test_user.id,
                type="bug",
                subject=f"Test {status}",
                message="Test message",
                status=status,
            )
            async_session.add(feedback)
            await async_session.commit()
            await async_session.refresh(feedback)

            assert feedback.status == status

    @pytest.mark.asyncio
    async def test_feedback_with_admin_fields(
        self, async_session, test_organization, test_user, admin_user
    ):
        """Test feedback with admin notes and response."""
        feedback = Feedback(
            organization_id=test_organization.id,
            user_id=test_user.id,
            type="bug",
            subject="Test bug",
            message="Test message",
            status="in_review",
            admin_notes="Internal note: investigating",
            admin_response="We are looking into this issue.",
            responded_by=admin_user.id,
        )
        async_session.add(feedback)
        await async_session.commit()
        await async_session.refresh(feedback)

        assert feedback.admin_notes == "Internal note: investigating"
        assert feedback.admin_response == "We are looking into this issue."
        assert feedback.responded_by == admin_user.id
        assert feedback.responded_at is None

    @pytest.mark.asyncio
    async def test_feedback_organization_relationship(
        self, async_session, test_organization, test_user
    ):
        """Test feedback has proper relationship to organization."""
        feedback = Feedback(
            organization_id=test_organization.id,
            user_id=test_user.id,
            type="bug",
            subject="Test",
            message="Test",
            status="new",
        )
        async_session.add(feedback)
        await async_session.commit()
        await async_session.refresh(feedback)

        # Load relationship
        await async_session.refresh(feedback, ["organization"])
        assert feedback.organization is not None
        assert feedback.organization.id == test_organization.id

    @pytest.mark.asyncio
    async def test_feedback_user_relationship(
        self, async_session, test_organization, test_user
    ):
        """Test feedback has proper relationship to user."""
        feedback = Feedback(
            organization_id=test_organization.id,
            user_id=test_user.id,
            type="bug",
            subject="Test",
            message="Test",
            status="new",
        )
        async_session.add(feedback)
        await async_session.commit()
        await async_session.refresh(feedback)

        # Load relationship
        await async_session.refresh(feedback, ["user"])
        assert feedback.user is not None
        assert feedback.user.id == test_user.id


# ============================================================================
# FEEDBACK ATTACHMENT MODEL TESTS
# ============================================================================


class TestFeedbackAttachmentModel:
    """Tests for FeedbackAttachment model."""

    @pytest.mark.asyncio
    async def test_create_feedback_attachment(
        self, async_session, test_organization, test_user
    ):
        """Test creating a feedback attachment."""
        # First create feedback
        feedback = Feedback(
            organization_id=test_organization.id,
            user_id=test_user.id,
            type="bug",
            subject="Test",
            message="Test",
            status="new",
        )
        async_session.add(feedback)
        await async_session.commit()
        await async_session.refresh(feedback)

        # Create attachment
        attachment = FeedbackAttachment(
            feedback_id=feedback.id,
            file_path="feedback/screenshots/abc123.png",
            file_type="image/png",
            file_size_bytes=1024000,
        )
        async_session.add(attachment)
        await async_session.commit()
        await async_session.refresh(attachment)

        assert attachment.id is not None
        assert attachment.feedback_id == feedback.id
        assert attachment.file_path == "feedback/screenshots/abc123.png"
        assert attachment.file_type == "image/png"
        assert attachment.file_size_bytes == 1024000
        assert attachment.created_time is not None
        assert attachment.deleted_time is None

    @pytest.mark.asyncio
    async def test_feedback_attachment_relationship(
        self, async_session, test_organization, test_user
    ):
        """Test attachment has proper relationship to feedback."""
        # Create feedback
        feedback = Feedback(
            organization_id=test_organization.id,
            user_id=test_user.id,
            type="bug",
            subject="Test",
            message="Test",
            status="new",
        )
        async_session.add(feedback)
        await async_session.commit()
        await async_session.refresh(feedback)

        # Create attachment
        attachment = FeedbackAttachment(
            feedback_id=feedback.id,
            file_path="test.png",
            file_type="image/png",
            file_size_bytes=1000,
        )
        async_session.add(attachment)
        await async_session.commit()
        await async_session.refresh(attachment)

        # Load relationship
        await async_session.refresh(attachment, ["feedback"])
        assert attachment.feedback is not None
        assert attachment.feedback.id == feedback.id

    @pytest.mark.asyncio
    async def test_feedback_with_multiple_attachments(
        self, async_session, test_organization, test_user
    ):
        """Test feedback can have multiple attachments."""
        # Create feedback
        feedback = Feedback(
            organization_id=test_organization.id,
            user_id=test_user.id,
            type="bug",
            subject="Test with attachments",
            message="Test",
            status="new",
        )
        async_session.add(feedback)
        await async_session.commit()
        await async_session.refresh(feedback)

        # Create multiple attachments
        attachment1 = FeedbackAttachment(
            feedback_id=feedback.id,
            file_path="screenshot1.png",
            file_type="image/png",
            file_size_bytes=1000,
        )
        attachment2 = FeedbackAttachment(
            feedback_id=feedback.id,
            file_path="screenshot2.png",
            file_type="image/png",
            file_size_bytes=2000,
        )
        attachment3 = FeedbackAttachment(
            feedback_id=feedback.id,
            file_path="document.pdf",
            file_type="application/pdf",
            file_size_bytes=50000,
        )
        async_session.add_all([attachment1, attachment2, attachment3])
        await async_session.commit()

        # Load attachments relationship
        await async_session.refresh(feedback, ["attachments"])
        assert len(feedback.attachments) == 3
        assert any(a.file_path == "screenshot1.png" for a in feedback.attachments)
        assert any(a.file_path == "screenshot2.png" for a in feedback.attachments)
        assert any(a.file_path == "document.pdf" for a in feedback.attachments)

    @pytest.mark.asyncio
    async def test_attachment_file_types(
        self, async_session, test_organization, test_user
    ):
        """Test various attachment file types."""
        feedback = Feedback(
            organization_id=test_organization.id,
            user_id=test_user.id,
            type="bug",
            subject="Test",
            message="Test",
            status="new",
        )
        async_session.add(feedback)
        await async_session.commit()
        await async_session.refresh(feedback)

        file_types = [
            ("image/png", 1000),
            ("image/jpeg", 2000),
            ("image/gif", 1500),
            ("application/pdf", 50000),
            ("video/mp4", 5000000),
        ]

        for file_type, size in file_types:
            attachment = FeedbackAttachment(
                feedback_id=feedback.id,
                file_path=f"test.{file_type.split('/')[-1]}",
                file_type=file_type,
                file_size_bytes=size,
            )
            async_session.add(attachment)
            await async_session.commit()
            await async_session.refresh(attachment)

            assert attachment.file_type == file_type
            assert attachment.file_size_bytes == size


# ============================================================================
# FEEDBACK CRUD TESTS
# ============================================================================


class TestFeedbackCRUD:
    """Tests for Feedback CRUD operations."""

    @pytest.mark.asyncio
    async def test_create_feedback(self, async_session, test_organization, test_user):
        """Test creating feedback via CRUD."""
        feedback_data = {
            "type": "bug",
            "rating": 3,
            "subject": "Login issue",
            "message": "Cannot log in with Google OAuth",
            "page_url": "https://example.com/login",
            "user_agent": "Mozilla/5.0",
            "screen_resolution": "1920x1080",
        }

        feedback = await create_feedback(
            async_session,
            feedback_data,
            str(test_organization.id),
            str(test_user.id),
        )

        assert feedback.id is not None
        assert feedback.organization_id == test_organization.id
        assert feedback.user_id == test_user.id
        assert feedback.type == "bug"
        assert feedback.rating == 3
        assert feedback.subject == "Login issue"
        assert feedback.message == "Cannot log in with Google OAuth"
        assert feedback.status == "new"

    @pytest.mark.asyncio
    async def test_get_feedback_by_id(
        self, async_session, test_organization, test_user
    ):
        """Test getting feedback by ID."""
        feedback_data = {
            "type": "suggestion",
            "subject": "Feature request",
            "message": "Add export functionality",
        }

        created = await create_feedback(
            async_session,
            feedback_data,
            str(test_organization.id),
            str(test_user.id),
        )

        fetched = await get_feedback_by_id(
            async_session, str(created.id), str(test_organization.id)
        )

        assert fetched is not None
        assert fetched.id == created.id
        assert fetched.subject == "Feature request"

    @pytest.mark.asyncio
    async def test_get_feedback_by_id_wrong_org(
        self, async_session, test_organization, second_organization, test_user
    ):
        """Test cannot get feedback from another organization."""
        feedback_data = {
            "type": "bug",
            "subject": "Test",
            "message": "Test message",
        }

        created = await create_feedback(
            async_session,
            feedback_data,
            str(test_organization.id),
            str(test_user.id),
        )

        fetched = await get_feedback_by_id(
            async_session, str(created.id), str(second_organization.id)
        )

        assert fetched is None

    @pytest.mark.asyncio
    async def test_get_feedbacks_list(
        self, async_session, test_organization, test_user
    ):
        """Test getting paginated feedback list."""
        # Create multiple feedback items
        for i in range(5):
            await create_feedback(
                async_session,
                {
                    "type": "bug",
                    "subject": f"Bug {i}",
                    "message": f"Message {i}",
                },
                str(test_organization.id),
                str(test_user.id),
            )

        feedbacks, total = await get_feedbacks_list(
            async_session, str(test_organization.id), limit=10, offset=0
        )

        assert total == 5
        assert len(feedbacks) == 5

    @pytest.mark.asyncio
    async def test_get_feedbacks_list_with_type_filter(
        self, async_session, test_organization, test_user
    ):
        """Test filtering feedback by type."""
        await create_feedback(
            async_session,
            {"type": "bug", "subject": "Bug 1", "message": "Message"},
            str(test_organization.id),
            str(test_user.id),
        )
        await create_feedback(
            async_session,
            {"type": "suggestion", "subject": "Suggestion 1", "message": "Message"},
            str(test_organization.id),
            str(test_user.id),
        )
        await create_feedback(
            async_session,
            {"type": "bug", "subject": "Bug 2", "message": "Message"},
            str(test_organization.id),
            str(test_user.id),
        )

        filters = [FilterSpec(field="type", operator=FilterOperator.EQ, value="bug")]
        feedbacks, total = await get_feedbacks_list(
            async_session, str(test_organization.id), filters=filters
        )

        assert total == 2
        assert all(f.type == "bug" for f in feedbacks)

    @pytest.mark.asyncio
    async def test_get_feedbacks_list_with_status_filter(
        self, async_session, test_organization, test_user
    ):
        """Test filtering feedback by status."""
        fb1 = await create_feedback(
            async_session,
            {"type": "bug", "subject": "Bug 1", "message": "Message"},
            str(test_organization.id),
            str(test_user.id),
        )
        fb2 = await create_feedback(
            async_session,
            {"type": "bug", "subject": "Bug 2", "message": "Message"},
            str(test_organization.id),
            str(test_user.id),
        )

        # Update one to resolved
        await update_feedback(
            async_session,
            str(fb2.id),
            str(test_organization.id),
            {"status": "resolved"},
        )

        filters = [FilterSpec(field="status", operator=FilterOperator.EQ, value="new")]
        feedbacks, total = await get_feedbacks_list(
            async_session, str(test_organization.id), filters=filters
        )

        assert total == 1
        assert feedbacks[0].id == fb1.id

    @pytest.mark.asyncio
    async def test_get_feedbacks_list_with_rating_filter(
        self, async_session, test_organization, test_user
    ):
        """Test filtering feedback by rating range."""
        await create_feedback(
            async_session,
            {
                "type": "complaint",
                "rating": 1,
                "subject": "Bad",
                "message": "Message",
            },
            str(test_organization.id),
            str(test_user.id),
        )
        await create_feedback(
            async_session,
            {"type": "bug", "rating": 3, "subject": "OK", "message": "Message"},
            str(test_organization.id),
            str(test_user.id),
        )
        await create_feedback(
            async_session,
            {
                "type": "praise",
                "rating": 5,
                "subject": "Great",
                "message": "Message",
            },
            str(test_organization.id),
            str(test_user.id),
        )

        filters = [FilterSpec(field="rating", operator=FilterOperator.GTE, value=4)]
        feedbacks, total = await get_feedbacks_list(
            async_session, str(test_organization.id), filters=filters
        )

        assert total == 1
        assert feedbacks[0].rating == 5

    @pytest.mark.asyncio
    async def test_get_feedbacks_list_with_date_filter(
        self, async_session, test_organization, test_user
    ):
        """Test filtering feedback by date range."""
        now = datetime.now(timezone.utc)
        yesterday = now - timedelta(days=1)

        # Create feedback with different dates
        fb_old = await create_feedback(
            async_session,
            {"type": "bug", "subject": "Old", "message": "Message"},
            str(test_organization.id),
            str(test_user.id),
        )
        fb_old.created_time = yesterday
        await async_session.commit()

        fb_new = await create_feedback(
            async_session,
            {"type": "bug", "subject": "New", "message": "Message"},
            str(test_organization.id),
            str(test_user.id),
        )

        date_from = now - timedelta(hours=1)
        filters = [
            FilterSpec(
                field="created_time", operator=FilterOperator.GTE, value=date_from
            )
        ]
        feedbacks, total = await get_feedbacks_list(
            async_session,
            str(test_organization.id),
            filters=filters,
        )

        assert total == 1
        assert feedbacks[0].id == fb_new.id

    @pytest.mark.asyncio
    async def test_get_feedbacks_list_pagination(
        self, async_session, test_organization, test_user
    ):
        """Test pagination of feedback list."""
        # Create 10 feedback items
        for i in range(10):
            await create_feedback(
                async_session,
                {"type": "bug", "subject": f"Bug {i}", "message": "Message"},
                str(test_organization.id),
                str(test_user.id),
            )

        # Get first page
        feedbacks_page1, total = await get_feedbacks_list(
            async_session, str(test_organization.id), limit=5, offset=0
        )

        assert total == 10
        assert len(feedbacks_page1) == 5

        # Get second page
        feedbacks_page2, _ = await get_feedbacks_list(
            async_session, str(test_organization.id), limit=5, offset=5
        )

        assert len(feedbacks_page2) == 5
        assert feedbacks_page1[0].id != feedbacks_page2[0].id

    @pytest.mark.asyncio
    async def test_get_feedbacks_list_tenant_isolation(
        self,
        async_session,
        test_organization,
        second_organization,
        test_user,
        second_org_user,
    ):
        """Test feedback list is tenant-isolated."""
        await create_feedback(
            async_session,
            {"type": "bug", "subject": "Org 1", "message": "Message"},
            str(test_organization.id),
            str(test_user.id),
        )
        await create_feedback(
            async_session,
            {"type": "bug", "subject": "Org 2", "message": "Message"},
            str(second_organization.id),
            str(second_org_user.id),
        )

        feedbacks, total = await get_feedbacks_list(
            async_session, str(test_organization.id)
        )

        assert total == 1
        assert feedbacks[0].subject == "Org 1"

    @pytest.mark.asyncio
    async def test_get_user_feedbacks(
        self, async_session, test_organization, test_user, admin_user
    ):
        """Test getting feedback for a specific user."""
        await create_feedback(
            async_session,
            {"type": "bug", "subject": "User feedback", "message": "Message"},
            str(test_organization.id),
            str(test_user.id),
        )
        await create_feedback(
            async_session,
            {"type": "bug", "subject": "Admin feedback", "message": "Message"},
            str(test_organization.id),
            str(admin_user.id),
        )

        feedbacks, total = await get_user_feedbacks(
            async_session, str(test_organization.id), str(test_user.id)
        )

        assert total == 1
        assert feedbacks[0].user_id == test_user.id

    @pytest.mark.asyncio
    async def test_update_feedback_status(
        self, async_session, test_organization, test_user, admin_user
    ):
        """Test updating feedback status."""
        feedback = await create_feedback(
            async_session,
            {"type": "bug", "subject": "Test", "message": "Message"},
            str(test_organization.id),
            str(test_user.id),
        )

        updated = await update_feedback(
            async_session,
            str(feedback.id),
            str(test_organization.id),
            {"status": "in_review"},
            str(admin_user.id),
        )

        assert updated.status == "in_review"
        assert updated.resolved_at is None

    @pytest.mark.asyncio
    async def test_update_feedback_to_resolved(
        self, async_session, test_organization, test_user, admin_user
    ):
        """Test updating feedback to resolved tracks resolution time."""
        feedback = await create_feedback(
            async_session,
            {"type": "bug", "subject": "Test", "message": "Message"},
            str(test_organization.id),
            str(test_user.id),
        )

        updated = await update_feedback(
            async_session,
            str(feedback.id),
            str(test_organization.id),
            {"status": "resolved"},
            str(admin_user.id),
        )

        assert updated.status == "resolved"
        assert updated.resolved_at is not None
        assert updated.resolved_by == admin_user.id

    @pytest.mark.asyncio
    async def test_update_feedback_admin_response(
        self, async_session, test_organization, test_user, admin_user
    ):
        """Test adding admin response to feedback."""
        feedback = await create_feedback(
            async_session,
            {"type": "bug", "subject": "Test", "message": "Message"},
            str(test_organization.id),
            str(test_user.id),
        )

        updated = await update_feedback(
            async_session,
            str(feedback.id),
            str(test_organization.id),
            {"admin_response": "We're working on this issue."},
            str(admin_user.id),
        )

        assert updated.admin_response == "We're working on this issue."
        assert updated.responded_at is not None
        assert updated.responded_by == admin_user.id

    @pytest.mark.asyncio
    async def test_update_feedback_admin_notes(
        self, async_session, test_organization, test_user, admin_user
    ):
        """Test adding admin notes to feedback."""
        feedback = await create_feedback(
            async_session,
            {"type": "bug", "subject": "Test", "message": "Message"},
            str(test_organization.id),
            str(test_user.id),
        )

        updated = await update_feedback(
            async_session,
            str(feedback.id),
            str(test_organization.id),
            {"admin_notes": "Internal investigation notes"},
            str(admin_user.id),
        )

        assert updated.admin_notes == "Internal investigation notes"

    @pytest.mark.asyncio
    async def test_update_feedback_wrong_org(
        self, async_session, test_organization, second_organization, test_user
    ):
        """Test cannot update feedback from another organization."""
        feedback = await create_feedback(
            async_session,
            {"type": "bug", "subject": "Test", "message": "Message"},
            str(test_organization.id),
            str(test_user.id),
        )

        updated = await update_feedback(
            async_session,
            str(feedback.id),
            str(second_organization.id),
            {"status": "resolved"},
        )

        assert updated is None

    @pytest.mark.asyncio
    async def test_soft_delete_feedback(
        self, async_session, test_organization, test_user
    ):
        """Test soft deleting feedback."""
        feedback = await create_feedback(
            async_session,
            {"type": "bug", "subject": "Test", "message": "Message"},
            str(test_organization.id),
            str(test_user.id),
        )

        deleted = await soft_delete_feedback(
            async_session, str(feedback.id), str(test_organization.id)
        )

        assert deleted is not None
        assert deleted.deleted_time is not None

        # Verify cannot fetch after deletion
        fetched = await get_feedback_by_id(
            async_session, str(feedback.id), str(test_organization.id)
        )
        assert fetched is None

    @pytest.mark.asyncio
    async def test_soft_delete_feedback_wrong_org(
        self, async_session, test_organization, second_organization, test_user
    ):
        """Test cannot delete feedback from another organization."""
        feedback = await create_feedback(
            async_session,
            {"type": "bug", "subject": "Test", "message": "Message"},
            str(test_organization.id),
            str(test_user.id),
        )

        deleted = await soft_delete_feedback(
            async_session, str(feedback.id), str(second_organization.id)
        )

        assert deleted is None


# ============================================================================
# FEEDBACK ATTACHMENT CRUD TESTS
# ============================================================================


class TestFeedbackAttachmentCRUD:
    """Tests for FeedbackAttachment CRUD operations."""

    @pytest.mark.asyncio
    async def test_create_feedback_attachment(
        self, async_session, test_organization, test_user
    ):
        """Test creating feedback attachment via CRUD."""
        feedback = await create_feedback(
            async_session,
            {"type": "bug", "subject": "Test", "message": "Message"},
            str(test_organization.id),
            str(test_user.id),
        )

        attachment = await create_feedback_attachment(
            async_session,
            str(feedback.id),
            str(test_organization.id),
            "feedback/screenshots/test.png",
            "image/png",
            1024000,
        )

        assert attachment.id is not None
        assert attachment.feedback_id == feedback.id
        assert attachment.file_path == "feedback/screenshots/test.png"
        assert attachment.file_type == "image/png"
        assert attachment.file_size_bytes == 1024000

    @pytest.mark.asyncio
    async def test_create_attachment_feedback_not_found(
        self, async_session, test_organization
    ):
        """Test creating attachment for non-existent feedback fails."""
        with pytest.raises(ValueError, match="not found"):
            await create_feedback_attachment(
                async_session,
                "00000000-0000-0000-0000-000000000000",
                str(test_organization.id),
                "test.png",
                "image/png",
                1000,
            )

    @pytest.mark.asyncio
    async def test_create_attachment_wrong_org(
        self, async_session, test_organization, second_organization, test_user
    ):
        """Test creating attachment for feedback in another org fails."""
        feedback = await create_feedback(
            async_session,
            {"type": "bug", "subject": "Test", "message": "Message"},
            str(test_organization.id),
            str(test_user.id),
        )

        with pytest.raises(ValueError, match="not found"):
            await create_feedback_attachment(
                async_session,
                str(feedback.id),
                str(second_organization.id),
                "test.png",
                "image/png",
                1000,
            )

    @pytest.mark.asyncio
    async def test_get_attachments_by_feedback_id(
        self, async_session, test_organization, test_user
    ):
        """Test getting all attachments for a feedback."""
        feedback = await create_feedback(
            async_session,
            {"type": "bug", "subject": "Test", "message": "Message"},
            str(test_organization.id),
            str(test_user.id),
        )

        # Create multiple attachments
        await create_feedback_attachment(
            async_session,
            str(feedback.id),
            str(test_organization.id),
            "screenshot1.png",
            "image/png",
            1000,
        )
        await create_feedback_attachment(
            async_session,
            str(feedback.id),
            str(test_organization.id),
            "screenshot2.png",
            "image/png",
            2000,
        )

        attachments = await get_attachments_by_feedback_id(
            async_session, str(feedback.id), str(test_organization.id)
        )

        assert len(attachments) == 2
        assert any(a.file_path == "screenshot1.png" for a in attachments)
        assert any(a.file_path == "screenshot2.png" for a in attachments)

    @pytest.mark.asyncio
    async def test_get_attachments_wrong_org(
        self, async_session, test_organization, second_organization, test_user
    ):
        """Test cannot get attachments for feedback in another org."""
        feedback = await create_feedback(
            async_session,
            {"type": "bug", "subject": "Test", "message": "Message"},
            str(test_organization.id),
            str(test_user.id),
        )

        await create_feedback_attachment(
            async_session,
            str(feedback.id),
            str(test_organization.id),
            "test.png",
            "image/png",
            1000,
        )

        attachments = await get_attachments_by_feedback_id(
            async_session, str(feedback.id), str(second_organization.id)
        )

        assert len(attachments) == 0

    @pytest.mark.asyncio
    async def test_delete_attachment(self, async_session, test_organization, test_user):
        """Test soft deleting an attachment."""
        feedback = await create_feedback(
            async_session,
            {"type": "bug", "subject": "Test", "message": "Message"},
            str(test_organization.id),
            str(test_user.id),
        )

        attachment = await create_feedback_attachment(
            async_session,
            str(feedback.id),
            str(test_organization.id),
            "test.png",
            "image/png",
            1000,
        )

        deleted = await delete_attachment(
            async_session, str(attachment.id), str(test_organization.id)
        )

        assert deleted is not None
        assert deleted.deleted_time is not None

        # Verify cannot fetch after deletion
        attachments = await get_attachments_by_feedback_id(
            async_session, str(feedback.id), str(test_organization.id)
        )
        assert len(attachments) == 0

    @pytest.mark.asyncio
    async def test_delete_attachment_wrong_org(
        self, async_session, test_organization, second_organization, test_user
    ):
        """Test cannot delete attachment for feedback in another org."""
        feedback = await create_feedback(
            async_session,
            {"type": "bug", "subject": "Test", "message": "Message"},
            str(test_organization.id),
            str(test_user.id),
        )

        attachment = await create_feedback_attachment(
            async_session,
            str(feedback.id),
            str(test_organization.id),
            "test.png",
            "image/png",
            1000,
        )

        deleted = await delete_attachment(
            async_session, str(attachment.id), str(second_organization.id)
        )

        assert deleted is None


# ============================================================================
# FEEDBACK SERIALIZER TESTS
# ============================================================================


class TestFeedbackSerializers:
    """Tests for Feedback Pydantic serializers."""

    def test_create_feedback_request_valid(self):
        """Test CreateFeedbackRequest with valid data."""
        from src.serialisers.feedback import CreateFeedbackRequest

        data = {
            "type": "bug",
            "rating": 3,
            "subject": "Test subject",
            "message": "Test message",
            "page_url": "https://example.com/page",
            "user_agent": "Mozilla/5.0",
            "screen_resolution": "1920x1080",
        }

        request = CreateFeedbackRequest(**data)
        assert request.type == "bug"
        assert request.rating == 3
        assert request.subject == "Test subject"
        assert request.message == "Test message"

    def test_create_feedback_request_type_validation(self):
        """Test CreateFeedbackRequest type field validation."""
        from pydantic import ValidationError

        from src.serialisers.feedback import CreateFeedbackRequest

        # Test invalid type
        with pytest.raises(ValidationError):
            CreateFeedbackRequest(type="invalid_type", subject="Test", message="Test")

    def test_create_feedback_request_rating_validation(self):
        """Test CreateFeedbackRequest rating field validation."""
        from pydantic import ValidationError

        from src.serialisers.feedback import CreateFeedbackRequest

        # Test rating too low
        with pytest.raises(ValidationError):
            CreateFeedbackRequest(type="bug", rating=0, subject="Test", message="Test")

        # Test rating too high
        with pytest.raises(ValidationError):
            CreateFeedbackRequest(type="bug", rating=6, subject="Test", message="Test")

        # Test valid ratings
        for rating in [1, 2, 3, 4, 5]:
            request = CreateFeedbackRequest(
                type="bug", rating=rating, subject="Test", message="Test"
            )
            assert request.rating == rating

    def test_create_feedback_request_subject_validation(self):
        """Test CreateFeedbackRequest subject field validation."""
        from pydantic import ValidationError

        from src.serialisers.feedback import CreateFeedbackRequest

        # Test subject too short
        with pytest.raises(ValidationError):
            CreateFeedbackRequest(type="bug", subject="", message="Test")

        # Test subject too long
        with pytest.raises(ValidationError):
            CreateFeedbackRequest(type="bug", subject="x" * 101, message="Test")

        # Test valid subject at boundary
        request = CreateFeedbackRequest(type="bug", subject="x" * 100, message="Test")
        assert len(request.subject) == 100

    def test_create_feedback_request_message_validation(self):
        """Test CreateFeedbackRequest message field validation."""
        from pydantic import ValidationError

        from src.serialisers.feedback import CreateFeedbackRequest

        # Test message too short
        with pytest.raises(ValidationError):
            CreateFeedbackRequest(type="bug", subject="Test", message="")

        # Test message too long
        with pytest.raises(ValidationError):
            CreateFeedbackRequest(type="bug", subject="Test", message="x" * 2001)

        # Test valid message at boundary
        request = CreateFeedbackRequest(type="bug", subject="Test", message="x" * 2000)
        assert len(request.message) == 2000

    def test_create_feedback_request_optional_fields(self):
        """Test CreateFeedbackRequest optional fields."""
        from src.serialisers.feedback import CreateFeedbackRequest

        # Test minimal request
        request = CreateFeedbackRequest(
            type="suggestion", subject="Test", message="Test message"
        )
        assert request.rating is None
        assert request.page_url is None
        assert request.user_agent is None
        assert request.screen_resolution is None

    def test_update_feedback_request_valid(self):
        """Test UpdateFeedbackRequest with valid data."""
        from src.serialisers.feedback import UpdateFeedbackRequest

        data = {
            "status": "in_review",
            "admin_notes": "Investigating this issue",
            "admin_response": "We are looking into this problem.",
        }

        request = UpdateFeedbackRequest(**data)
        assert request.status == "in_review"
        assert request.admin_notes == "Investigating this issue"
        assert request.admin_response == "We are looking into this problem."

    def test_update_feedback_request_status_validation(self):
        """Test UpdateFeedbackRequest status validation."""
        from src.serialisers.feedback import UpdateFeedbackRequest

        # Test all valid statuses
        for status in ["new", "in_review", "resolved", "dismissed"]:
            request = UpdateFeedbackRequest(status=status)
            assert request.status == status

    def test_update_feedback_request_optional_fields(self):
        """Test UpdateFeedbackRequest all fields optional."""
        from src.serialisers.feedback import UpdateFeedbackRequest

        # Test empty request
        request = UpdateFeedbackRequest()
        assert request.status is None
        assert request.admin_notes is None
        assert request.admin_response is None

    def test_feedback_attachment_request_valid(self):
        """Test FeedbackAttachmentRequest with valid data."""
        from src.serialisers.feedback import FeedbackAttachmentRequest

        data = {
            "file_path": "feedback/screenshots/abc123.png",
            "file_type": "image/png",
            "file_size_bytes": 1024000,
        }

        request = FeedbackAttachmentRequest(**data)
        assert request.file_path == "feedback/screenshots/abc123.png"
        assert request.file_type == "image/png"
        assert request.file_size_bytes == 1024000

    def test_feedback_attachment_request_file_size_validation(self):
        """Test FeedbackAttachmentRequest file size validation."""
        from pydantic import ValidationError

        from src.serialisers.feedback import FeedbackAttachmentRequest

        # Test file size must be greater than 0
        with pytest.raises(ValidationError):
            FeedbackAttachmentRequest(
                file_path="test.png", file_type="image/png", file_size_bytes=0
            )

        with pytest.raises(ValidationError):
            FeedbackAttachmentRequest(
                file_path="test.png", file_type="image/png", file_size_bytes=-1
            )

    @pytest.mark.asyncio
    async def test_feedback_response_from_orm(
        self, async_session, test_organization, test_user
    ):
        """Test FeedbackResponse.from_orm_feedback conversion."""
        from src.serialisers.feedback import FeedbackResponse

        # Create feedback
        feedback = Feedback(
            organization_id=test_organization.id,
            user_id=test_user.id,
            type="bug",
            rating=3,
            subject="Test bug",
            message="Test message",
            page_url="https://example.com",
            status="new",
        )
        async_session.add(feedback)
        await async_session.commit()
        await async_session.refresh(feedback)

        # Convert to response
        response = FeedbackResponse.from_orm_feedback(feedback)

        assert response.id == feedback.id
        assert response.organization_id == feedback.organization_id
        assert response.user_id == feedback.user_id
        assert response.type == "bug"
        assert response.rating == 3
        assert response.subject == "Test bug"
        assert response.message == "Test message"
        assert response.status == "new"
        assert response.attachments == []

    @pytest.mark.asyncio
    async def test_feedback_response_with_attachments(
        self, async_session, test_organization, test_user
    ):
        """Test FeedbackResponse includes attachments."""
        from src.serialisers.feedback import FeedbackResponse

        # Create feedback
        feedback = Feedback(
            organization_id=test_organization.id,
            user_id=test_user.id,
            type="bug",
            subject="Test",
            message="Test",
            status="new",
        )
        async_session.add(feedback)
        await async_session.commit()
        await async_session.refresh(feedback)

        # Create attachment
        attachment = FeedbackAttachment(
            feedback_id=feedback.id,
            file_path="test.png",
            file_type="image/png",
            file_size_bytes=1000,
        )
        async_session.add(attachment)
        await async_session.commit()

        # Refresh with attachments
        await async_session.refresh(feedback, ["attachments"])

        # Convert to response
        response = FeedbackResponse.from_orm_feedback(feedback)

        assert len(response.attachments) == 1
        assert response.attachments[0].file_path == "test.png"
        assert response.attachments[0].file_type == "image/png"
        assert response.attachments[0].file_size_bytes == 1000

    def test_feedback_list_response_structure(self):
        """Test FeedbackListResponse structure."""
        from uuid import uuid4

        from src.serialisers.feedback import FeedbackListResponse, FeedbackResponse

        feedbacks = [
            FeedbackResponse(
                id=uuid4(),
                organization_id=uuid4(),
                user_id=uuid4(),
                type="bug",
                rating=3,
                subject="Test 1",
                message="Message 1",
                status="new",
                admin_notes=None,
                admin_response=None,
                responded_by=None,
                responded_at=None,
                resolved_by=None,
                resolved_at=None,
                created_time=datetime.now(timezone.utc),
                updated_time=datetime.now(timezone.utc),
                page_url=None,
                user_agent=None,
                screen_resolution=None,
                attachments=[],
            )
        ]

        response = FeedbackListResponse(items=feedbacks, total=1, limit=10, offset=0)

        assert len(response.items) == 1
        assert response.total == 1
        assert response.limit == 10
        assert response.offset == 0


# ============================================================================
# FEEDBACK API TESTS
# ============================================================================


class TestFeedbackAPI:
    """Tests for Feedback API endpoints."""

    @pytest.mark.asyncio
    async def test_submit_feedback(self, client, test_jwt_token):
        """Test submitting feedback via API."""
        response = await client.post(
            "/api/v1/feedback",
            headers={"Authorization": test_jwt_token},
            json={
                "type": "bug",
                "rating": 3,
                "subject": "Login button broken",
                "message": "The login button doesn't work on mobile",
                "page_url": "https://example.com/login",
                "user_agent": "Mozilla/5.0",
                "screen_resolution": "375x667",
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert data["message_code"] == "feedback.created"
        assert data["feedback"]["type"] == "bug"
        assert data["feedback"]["subject"] == "Login button broken"
        assert data["feedback"]["status"] == "new"

    @pytest.mark.asyncio
    async def test_submit_feedback_minimal(self, client, test_jwt_token):
        """Test submitting feedback with minimal fields."""
        response = await client.post(
            "/api/v1/feedback",
            headers={"Authorization": test_jwt_token},
            json={
                "type": "suggestion",
                "subject": "Feature request",
                "message": "Add dark mode please",
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert data["feedback"]["type"] == "suggestion"
        assert data["feedback"]["rating"] is None

    @pytest.mark.asyncio
    async def test_submit_feedback_unauthenticated(self, client):
        """Test submitting feedback without authentication."""
        response = await client.post(
            "/api/v1/feedback",
            json={
                "type": "bug",
                "subject": "Test",
                "message": "Test message",
            },
        )

        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_submit_feedback_invalid_type(self, client, test_jwt_token):
        """Test submitting feedback with invalid type."""
        response = await client.post(
            "/api/v1/feedback",
            headers={"Authorization": test_jwt_token},
            json={
                "type": "invalid_type",
                "subject": "Test",
                "message": "Test message",
            },
        )

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_submit_feedback_invalid_rating(self, client, test_jwt_token):
        """Test submitting feedback with invalid rating."""
        response = await client.post(
            "/api/v1/feedback",
            headers={"Authorization": test_jwt_token},
            json={
                "type": "bug",
                "rating": 6,
                "subject": "Test",
                "message": "Test message",
            },
        )

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_submit_feedback_subject_too_long(self, client, test_jwt_token):
        """Test submitting feedback with subject exceeding max length."""
        response = await client.post(
            "/api/v1/feedback",
            headers={"Authorization": test_jwt_token},
            json={
                "type": "bug",
                "subject": "x" * 101,
                "message": "Test message",
            },
        )

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_submit_feedback_message_too_long(self, client, test_jwt_token):
        """Test submitting feedback with message exceeding max length."""
        response = await client.post(
            "/api/v1/feedback",
            headers={"Authorization": test_jwt_token},
            json={
                "type": "bug",
                "subject": "Test",
                "message": "x" * 2001,
            },
        )

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_get_my_feedback(
        self, client, async_session, test_organization, test_user, test_jwt_token
    ):
        """Test getting user's own feedback."""
        # Create some feedback for the user
        await create_feedback(
            async_session,
            {"type": "bug", "subject": "Bug 1", "message": "Message 1"},
            str(test_organization.id),
            str(test_user.id),
        )
        await create_feedback(
            async_session,
            {"type": "suggestion", "subject": "Suggestion 1", "message": "Message 1"},
            str(test_organization.id),
            str(test_user.id),
        )

        response = await client.get(
            "/api/v1/feedback/me",
            headers={"Authorization": test_jwt_token},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 2
        assert len(data["items"]) == 2

    @pytest.mark.asyncio
    async def test_get_my_feedback_empty(self, client, test_jwt_token):
        """Test getting user's own feedback when none exist."""
        response = await client.get(
            "/api/v1/feedback/me",
            headers={"Authorization": test_jwt_token},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 0
        assert len(data["items"]) == 0

    @pytest.mark.asyncio
    async def test_get_my_feedback_pagination(
        self, client, async_session, test_organization, test_user, test_jwt_token
    ):
        """Test pagination of user's own feedback."""
        # Create 5 feedback items
        for i in range(5):
            await create_feedback(
                async_session,
                {"type": "bug", "subject": f"Bug {i}", "message": "Message"},
                str(test_organization.id),
                str(test_user.id),
            )

        response = await client.get(
            "/api/v1/feedback/me?limit=2&offset=0",
            headers={"Authorization": test_jwt_token},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 5
        assert len(data["items"]) == 2

    @pytest.mark.asyncio
    async def test_list_feedback_with_permission(
        self,
        client,
        async_session,
        test_organization,
        test_user,
        admin_user,
        test_role,
    ):
        """Test listing all feedback with feedback:view permission."""
        from src.crud.role_permission import grant_permission_to_role
        from src.crud.user_role import assign_role
        from src.models.permission import Permission

        # Create feedback:view permission
        permission = Permission(
            code="feedback:view",
            name="View Feedback",
            resource="feedback",
            action="view",
        )
        async_session.add(permission)
        await async_session.commit()
        await async_session.refresh(permission)

        # Assign permission to test_role
        await grant_permission_to_role(
            async_session, str(test_role.id), str(permission.id), str(test_user.id)
        )

        # Assign role to test_user
        await assign_role(
            async_session,
            {"user_id": str(test_user.id), "role_id": str(test_role.id)},
            str(test_user.id),
            str(test_organization.id),
        )

        # Create some feedback
        await create_feedback(
            async_session,
            {"type": "bug", "subject": "Bug 1", "message": "Message"},
            str(test_organization.id),
            str(test_user.id),
        )
        await create_feedback(
            async_session,
            {"type": "suggestion", "subject": "Suggestion 1", "message": "Message"},
            str(test_organization.id),
            str(admin_user.id),
        )

        # Get token for test_user with role
        import jwt

        from src.core.config import settings

        token = jwt.encode(
            {
                "user_id": str(test_user.id),
                "organization_id": str(test_organization.id),
                "type": "access",
            },
            settings.JWT_SECRET,
            algorithm="HS256",
        )

        response = await client.get(
            "/api/v1/feedback",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 2

    @pytest.mark.asyncio
    async def test_list_feedback_without_permission(self, client, test_jwt_token):
        """Test listing feedback without feedback:view permission."""
        response = await client.get(
            "/api/v1/feedback",
            headers={"Authorization": test_jwt_token},
        )

        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_list_feedback_with_filters(
        self,
        client,
        async_session,
        test_organization,
        test_user,
        test_role,
    ):
        """Test listing feedback with filters."""
        from src.crud.role_permission import grant_permission_to_role
        from src.crud.user_role import assign_role
        from src.models.permission import Permission

        # Setup permission
        permission = Permission(
            code="feedback:view",
            name="View Feedback",
            resource="feedback",
            action="view",
        )
        async_session.add(permission)
        await async_session.commit()
        await async_session.refresh(permission)

        await grant_permission_to_role(
            async_session, str(test_role.id), str(permission.id), str(test_user.id)
        )
        await assign_role(
            async_session,
            {"user_id": str(test_user.id), "role_id": str(test_role.id)},
            str(test_user.id),
            str(test_organization.id),
        )

        # Create feedback with different types and ratings
        await create_feedback(
            async_session,
            {"type": "bug", "rating": 1, "subject": "Bug 1", "message": "Message"},
            str(test_organization.id),
            str(test_user.id),
        )
        await create_feedback(
            async_session,
            {
                "type": "suggestion",
                "rating": 5,
                "subject": "Suggestion 1",
                "message": "Message",
            },
            str(test_organization.id),
            str(test_user.id),
        )

        import jwt

        from src.core.config import settings

        token = jwt.encode(
            {
                "user_id": str(test_user.id),
                "organization_id": str(test_organization.id),
                "type": "access",
            },
            settings.JWT_SECRET,
            algorithm="HS256",
        )

        # Filter by type using SDL filter format
        response = await client.get(
            "/api/v1/feedback?filter[type]=bug",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["items"][0]["type"] == "bug"

    @pytest.mark.asyncio
    async def test_get_feedback_by_id_own(
        self, client, async_session, test_organization, test_user, test_jwt_token
    ):
        """Test getting feedback by ID (own feedback)."""
        feedback = await create_feedback(
            async_session,
            {"type": "bug", "subject": "Test", "message": "Message"},
            str(test_organization.id),
            str(test_user.id),
        )

        response = await client.get(
            f"/api/v1/feedback/{feedback.id}",
            headers={"Authorization": test_jwt_token},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == str(feedback.id)
        assert data["subject"] == "Test"

    @pytest.mark.asyncio
    async def test_get_feedback_by_id_not_own_without_permission(
        self,
        client,
        async_session,
        test_organization,
        test_user,
        admin_user,
        test_jwt_token,
    ):
        """Test getting feedback by ID (not own, without permission)."""
        feedback = await create_feedback(
            async_session,
            {"type": "bug", "subject": "Admin feedback", "message": "Message"},
            str(test_organization.id),
            str(admin_user.id),
        )

        response = await client.get(
            f"/api/v1/feedback/{feedback.id}",
            headers={"Authorization": test_jwt_token},
        )

        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_get_feedback_by_id_not_found(self, client, test_jwt_token):
        """Test getting feedback by ID that doesn't exist."""
        response = await client.get(
            "/api/v1/feedback/00000000-0000-0000-0000-000000000000",
            headers={"Authorization": test_jwt_token},
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_get_feedback_wrong_org(
        self,
        client,
        async_session,
        test_organization,
        second_organization,
        test_user,
        second_org_user,
    ):
        """Test cannot get feedback from another organization."""
        feedback = await create_feedback(
            async_session,
            {"type": "bug", "subject": "Test", "message": "Message"},
            str(second_organization.id),
            str(second_org_user.id),
        )

        import jwt

        from src.core.config import settings

        token = jwt.encode(
            {
                "user_id": str(test_user.id),
                "organization_id": str(test_organization.id),
                "type": "access",
            },
            settings.JWT_SECRET,
            algorithm="HS256",
        )

        response = await client.get(
            f"/api/v1/feedback/{feedback.id}",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_update_feedback_with_permission(
        self,
        client,
        async_session,
        test_organization,
        test_user,
        test_role,
    ):
        """Test updating feedback with feedback:respond permission."""
        from src.crud.role_permission import grant_permission_to_role
        from src.crud.user_role import assign_role
        from src.models.permission import Permission

        # Create permission
        permission = Permission(
            code="feedback:respond",
            name="Respond to Feedback",
            resource="feedback",
            action="respond",
        )
        async_session.add(permission)
        await async_session.commit()
        await async_session.refresh(permission)

        await grant_permission_to_role(
            async_session, str(test_role.id), str(permission.id), str(test_user.id)
        )
        await assign_role(
            async_session,
            {"user_id": str(test_user.id), "role_id": str(test_role.id)},
            str(test_user.id),
            str(test_organization.id),
        )

        # Create feedback
        feedback = await create_feedback(
            async_session,
            {"type": "bug", "subject": "Test", "message": "Message"},
            str(test_organization.id),
            str(test_user.id),
        )

        import jwt

        from src.core.config import settings

        token = jwt.encode(
            {
                "user_id": str(test_user.id),
                "organization_id": str(test_organization.id),
                "type": "access",
            },
            settings.JWT_SECRET,
            algorithm="HS256",
        )

        response = await client.patch(
            f"/api/v1/feedback/{feedback.id}",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "status": "in_review",
                "admin_response": "We are investigating this issue.",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["message_code"] == "feedback.updated"
        assert data["feedback"]["status"] == "in_review"
        assert data["feedback"]["admin_response"] == "We are investigating this issue."

    @pytest.mark.asyncio
    async def test_update_feedback_without_permission(
        self, client, async_session, test_organization, test_user, test_jwt_token
    ):
        """Test updating feedback without permission."""
        feedback = await create_feedback(
            async_session,
            {"type": "bug", "subject": "Test", "message": "Message"},
            str(test_organization.id),
            str(test_user.id),
        )

        response = await client.patch(
            f"/api/v1/feedback/{feedback.id}",
            headers={"Authorization": test_jwt_token},
            json={"status": "resolved"},
        )

        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_update_feedback_tracks_resolution(
        self,
        client,
        async_session,
        test_organization,
        test_user,
        test_role,
    ):
        """Test updating feedback to resolved tracks resolution time."""
        from src.crud.role_permission import grant_permission_to_role
        from src.crud.user_role import assign_role
        from src.models.permission import Permission

        permission = Permission(
            code="feedback:respond",
            name="Respond to Feedback",
            resource="feedback",
            action="respond",
        )
        async_session.add(permission)
        await async_session.commit()
        await async_session.refresh(permission)

        await grant_permission_to_role(
            async_session, str(test_role.id), str(permission.id), str(test_user.id)
        )
        await assign_role(
            async_session,
            {"user_id": str(test_user.id), "role_id": str(test_role.id)},
            str(test_user.id),
            str(test_organization.id),
        )

        feedback = await create_feedback(
            async_session,
            {"type": "bug", "subject": "Test", "message": "Message"},
            str(test_organization.id),
            str(test_user.id),
        )

        import jwt

        from src.core.config import settings

        token = jwt.encode(
            {
                "user_id": str(test_user.id),
                "organization_id": str(test_organization.id),
                "type": "access",
            },
            settings.JWT_SECRET,
            algorithm="HS256",
        )

        response = await client.patch(
            f"/api/v1/feedback/{feedback.id}",
            headers={"Authorization": f"Bearer {token}"},
            json={"status": "resolved"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["feedback"]["status"] == "resolved"
        assert data["feedback"]["resolved_at"] is not None
        assert data["feedback"]["resolved_by"] == str(test_user.id)

    @pytest.mark.asyncio
    async def test_delete_feedback_with_permission(
        self,
        client,
        async_session,
        test_organization,
        test_user,
        test_role,
    ):
        """Test deleting feedback with feedback:delete permission."""
        from src.crud.role_permission import grant_permission_to_role
        from src.crud.user_role import assign_role
        from src.models.permission import Permission

        permission = Permission(
            code="feedback:delete",
            name="Delete Feedback",
            resource="feedback",
            action="delete",
        )
        async_session.add(permission)
        await async_session.commit()
        await async_session.refresh(permission)

        await grant_permission_to_role(
            async_session, str(test_role.id), str(permission.id), str(test_user.id)
        )
        await assign_role(
            async_session,
            {"user_id": str(test_user.id), "role_id": str(test_role.id)},
            str(test_user.id),
            str(test_organization.id),
        )

        feedback = await create_feedback(
            async_session,
            {"type": "bug", "subject": "Test", "message": "Message"},
            str(test_organization.id),
            str(test_user.id),
        )

        import jwt

        from src.core.config import settings

        token = jwt.encode(
            {
                "user_id": str(test_user.id),
                "organization_id": str(test_organization.id),
                "type": "access",
            },
            settings.JWT_SECRET,
            algorithm="HS256",
        )

        response = await client.delete(
            f"/api/v1/feedback/{feedback.id}",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["message_code"] == "feedback.deleted"

    @pytest.mark.asyncio
    async def test_delete_feedback_without_permission(
        self, client, async_session, test_organization, test_user, test_jwt_token
    ):
        """Test deleting feedback without permission."""
        feedback = await create_feedback(
            async_session,
            {"type": "bug", "subject": "Test", "message": "Message"},
            str(test_organization.id),
            str(test_user.id),
        )

        response = await client.delete(
            f"/api/v1/feedback/{feedback.id}",
            headers={"Authorization": test_jwt_token},
        )

        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_create_feedback_attachment(
        self, client, async_session, test_organization, test_user, test_jwt_token
    ):
        """Test creating feedback attachment."""
        feedback = await create_feedback(
            async_session,
            {"type": "bug", "subject": "Test", "message": "Message"},
            str(test_organization.id),
            str(test_user.id),
        )

        response = await client.post(
            f"/api/v1/feedback/{feedback.id}/attachments",
            headers={"Authorization": test_jwt_token},
            json={
                "file_path": "feedback/screenshots/test.png",
                "file_type": "image/png",
                "file_size_bytes": 1024000,
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert data["feedback_id"] == str(feedback.id)
        assert data["file_path"] == "feedback/screenshots/test.png"

    @pytest.mark.asyncio
    async def test_create_attachment_feedback_not_found(self, client, test_jwt_token):
        """Test creating attachment for non-existent feedback."""
        response = await client.post(
            "/api/v1/feedback/00000000-0000-0000-0000-000000000000/attachments",
            headers={"Authorization": test_jwt_token},
            json={
                "file_path": "test.png",
                "file_type": "image/png",
                "file_size_bytes": 1000,
            },
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_create_attachment_not_own_feedback(
        self,
        client,
        async_session,
        test_organization,
        test_user,
        admin_user,
        test_jwt_token,
    ):
        """Test creating attachment for someone else's feedback without permission."""
        feedback = await create_feedback(
            async_session,
            {"type": "bug", "subject": "Admin feedback", "message": "Message"},
            str(test_organization.id),
            str(admin_user.id),
        )

        response = await client.post(
            f"/api/v1/feedback/{feedback.id}/attachments",
            headers={"Authorization": test_jwt_token},
            json={
                "file_path": "test.png",
                "file_type": "image/png",
                "file_size_bytes": 1000,
            },
        )

        assert response.status_code == 403


# ============================================================================
# FEEDBACK PERMISSIONS AND FEATURE FLAG TESTS
# ============================================================================


class TestFeedbackPermissionsAndFeatureFlag:
    """Tests for feedback permissions and feature flag seed data."""

    def test_feedback_permissions_defined(self):
        """Test that feedback permissions are defined in seed data."""
        from scripts.seed_first_tenant import load_yaml

        # Load permissions from YAML
        permissions = load_yaml("permissions.yaml")

        # Filter to just feedback permissions
        feedback_permissions = [
            p for p in permissions if p["code"].startswith("feedback:")
        ]
        assert len(feedback_permissions) == 4

        permission_codes = [p["code"] for p in feedback_permissions]
        assert "feedback:submit" in permission_codes
        assert "feedback:view" in permission_codes
        assert "feedback:respond" in permission_codes
        assert "feedback:delete" in permission_codes

    def test_feedback_role_permissions_defined(self):
        """Test that feedback role permissions are mapped correctly."""
        from scripts.seed_first_tenant import load_yaml

        # Load role permissions from YAML
        role_permissions = load_yaml("role_permissions.yaml")

        # Owner should have all feedback permissions
        assert "feedback:submit" in role_permissions["owner"]
        assert "feedback:view" in role_permissions["owner"]
        assert "feedback:respond" in role_permissions["owner"]
        assert "feedback:delete" in role_permissions["owner"]

        # Admin should have view, respond, and submit
        assert "feedback:submit" in role_permissions["admin"]
        assert "feedback:view" in role_permissions["admin"]
        assert "feedback:respond" in role_permissions["admin"]
        assert "feedback:delete" not in role_permissions["admin"]

        # Member should have submit permission
        assert "feedback:submit" in role_permissions["member"]
        assert "feedback:view" not in role_permissions["member"]

        # Viewer should have submit permission
        assert "feedback:submit" in role_permissions["viewer"]
        assert "feedback:view" not in role_permissions["viewer"]

    async def test_feedback_widget_feature_flag_defined(self, async_session):
        """Test that feedback_widget feature flag is seeded correctly."""
        from scripts.seed_first_tenant import seed_feature_flags
        from src.crud.feature_flag import get_feature_flag_by_key

        # Seed the feature flags
        await seed_feature_flags(async_session)

        # Verify feedback_widget was created
        feedback_flag = await get_feature_flag_by_key(async_session, "feedback_widget")

        assert feedback_flag is not None
        assert feedback_flag.key == "feedback_widget"
        assert feedback_flag.name == "Feedback Widget"
        # Feature flags are disabled by default; orgs can enable via overrides
        assert feedback_flag.default_enabled is False
        assert feedback_flag.description is not None

    def test_feedback_permissions_structure(self):
        """Test that feedback permissions have correct structure."""
        from scripts.seed_first_tenant import load_yaml

        # Load permissions from YAML
        permissions = load_yaml("permissions.yaml")

        # Filter to just feedback permissions
        feedback_permissions = [
            p for p in permissions if p["code"].startswith("feedback:")
        ]

        for permission in feedback_permissions:
            assert "code" in permission
            assert "name" in permission
            assert "description" in permission
            assert "display_order" in permission

            # Verify code format
            assert permission["code"].startswith("feedback:")

            # Verify display_order is integer
            assert isinstance(permission["display_order"], int)

    async def test_feature_flags_structure(self, async_session):
        """Test that feature flags are seeded with correct structure."""
        from scripts.seed_first_tenant import seed_feature_flags
        from src.crud.feature_flag import get_feature_flag_by_key

        # Seed the feature flags
        await seed_feature_flags(async_session)

        # Verify feedback_widget flag has correct structure
        flag = await get_feature_flag_by_key(async_session, "feedback_widget")

        assert flag is not None
        assert hasattr(flag, "key")
        assert hasattr(flag, "name")
        assert hasattr(flag, "description")
        assert hasattr(flag, "default_enabled")

        # Verify default_enabled is boolean
        assert isinstance(flag.default_enabled, bool)
