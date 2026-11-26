"""
API tests for feedback endpoints.

Tests verify:
- Submit feedback
- User view own feedback
- Admin view/respond/delete
- Replies and attachments
- Mark as viewed
- Tenant isolation
"""

from httpx import AsyncClient
import pytest

from src.models.feedback import Feedback, FeedbackReply
from src.models.permission import Permission
from src.models.role_permission import RolePermission
from src.models.user_role import UserRole


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
async def test_feedback(async_session, test_organization, test_user):
    """Create a test feedback entry."""
    feedback = Feedback(
        organization_id=test_organization.id,
        user_id=test_user.id,
        type="bug",
        subject="Test Feedback",
        message="This is test feedback",
        status="new",
    )
    async_session.add(feedback)
    await async_session.commit()
    await async_session.refresh(feedback)
    return feedback


@pytest.fixture
async def second_org_feedback(async_session, second_organization, second_org_user):
    """Create feedback in second org."""
    feedback = Feedback(
        organization_id=second_organization.id,
        user_id=second_org_user.id,
        type="suggestion",
        subject="Second Org Feedback",
        message="This is second org feedback",
        status="new",
    )
    async_session.add(feedback)
    await async_session.commit()
    await async_session.refresh(feedback)
    return feedback


@pytest.fixture
async def feedback_view_permission(async_session):
    """Create feedback:view permission."""
    permission = Permission(
        code="feedback:view",
        name="View Feedback",
        description="View all feedback in the organization",
        resource="feedback",
        action="view",
        display_order=0,
    )
    async_session.add(permission)
    await async_session.commit()
    await async_session.refresh(permission)
    return permission


@pytest.fixture
async def feedback_respond_permission(async_session):
    """Create feedback:respond permission."""
    permission = Permission(
        code="feedback:respond",
        name="Respond to Feedback",
        description="Respond to feedback in the organization",
        resource="feedback",
        action="respond",
        display_order=1,
    )
    async_session.add(permission)
    await async_session.commit()
    await async_session.refresh(permission)
    return permission


@pytest.fixture
async def feedback_delete_permission(async_session):
    """Create feedback:delete permission."""
    permission = Permission(
        code="feedback:delete",
        name="Delete Feedback",
        description="Delete feedback in the organization",
        resource="feedback",
        action="delete",
        display_order=2,
    )
    async_session.add(permission)
    await async_session.commit()
    await async_session.refresh(permission)
    return permission


@pytest.fixture
async def user_with_feedback_view(
    async_session,
    test_organization,
    test_role,
    feedback_view_permission,
    test_user,
):
    """Create a user with feedback:view permission."""
    from src.core.security import hash_password

    # Grant permission to the role
    role_permission = RolePermission(
        role_id=test_role.id,
        permission_id=feedback_view_permission.id,
        granted_by=test_user.id,
    )
    async_session.add(role_permission)
    await async_session.commit()

    # Create user with the role
    from src.models.user import User

    user = User(
        email="feedbackviewer@test.com",
        password=hash_password("FeedbackViewer123!"),
        email_verified=True,
        organization_id=test_organization.id,
    )
    async_session.add(user)
    await async_session.commit()
    await async_session.refresh(user)

    # Assign role to user
    user_role = UserRole(
        user_id=user.id, role_id=test_role.id, organization_id=test_organization.id
    )
    async_session.add(user_role)
    await async_session.commit()

    return user


@pytest.fixture
def user_with_feedback_view_token(user_with_feedback_view, test_organization) -> str:
    """Create a JWT token for user with feedback:view permission."""
    from src.core.security import create_access_token

    token = create_access_token(
        user_id=str(user_with_feedback_view.id),
        organization_id=str(test_organization.id),
    )
    return f"Bearer {token}"


@pytest.fixture
async def user_with_feedback_respond(
    async_session,
    test_organization,
    test_role,
    feedback_respond_permission,
    test_user,
):
    """Create a user with feedback:respond permission."""
    from src.core.security import hash_password

    # Grant permission to the role
    role_permission = RolePermission(
        role_id=test_role.id,
        permission_id=feedback_respond_permission.id,
        granted_by=test_user.id,
    )
    async_session.add(role_permission)
    await async_session.commit()

    # Create user with the role
    from src.models.user import User

    user = User(
        email="feedbackresponder@test.com",
        password=hash_password("FeedbackResponder123!"),
        email_verified=True,
        organization_id=test_organization.id,
    )
    async_session.add(user)
    await async_session.commit()
    await async_session.refresh(user)

    # Assign role to user
    user_role = UserRole(
        user_id=user.id, role_id=test_role.id, organization_id=test_organization.id
    )
    async_session.add(user_role)
    await async_session.commit()

    return user


@pytest.fixture
def user_with_feedback_respond_token(
    user_with_feedback_respond, test_organization
) -> str:
    """Create a JWT token for user with feedback:respond permission."""
    from src.core.security import create_access_token

    token = create_access_token(
        user_id=str(user_with_feedback_respond.id),
        organization_id=str(test_organization.id),
    )
    return f"Bearer {token}"


@pytest.fixture
async def user_with_feedback_delete(
    async_session,
    test_organization,
    test_role,
    feedback_delete_permission,
    test_user,
):
    """Create a user with feedback:delete permission."""
    from src.core.security import hash_password

    # Grant permission to the role
    role_permission = RolePermission(
        role_id=test_role.id,
        permission_id=feedback_delete_permission.id,
        granted_by=test_user.id,
    )
    async_session.add(role_permission)
    await async_session.commit()

    # Create user with the role
    from src.models.user import User

    user = User(
        email="feedbackdeleter@test.com",
        password=hash_password("FeedbackDeleter123!"),
        email_verified=True,
        organization_id=test_organization.id,
    )
    async_session.add(user)
    await async_session.commit()
    await async_session.refresh(user)

    # Assign role to user
    user_role = UserRole(
        user_id=user.id, role_id=test_role.id, organization_id=test_organization.id
    )
    async_session.add(user_role)
    await async_session.commit()

    return user


@pytest.fixture
def user_with_feedback_delete_token(
    user_with_feedback_delete, test_organization
) -> str:
    """Create a JWT token for user with feedback:delete permission."""
    from src.core.security import create_access_token

    token = create_access_token(
        user_id=str(user_with_feedback_delete.id),
        organization_id=str(test_organization.id),
    )
    return f"Bearer {token}"


@pytest.fixture
async def test_feedback_reply(async_session, test_feedback, test_user):
    """Create a reply on test feedback."""
    reply = FeedbackReply(
        feedback_id=test_feedback.id,
        user_id=test_user.id,
        message="This is a test reply",
        is_admin_reply=False,
    )
    async_session.add(reply)
    await async_session.commit()
    await async_session.refresh(reply)
    return reply


# ============================================================================
# Submit Feedback Tests
# ============================================================================


class TestSubmitFeedback:
    """Tests for POST /api/v1/feedback endpoint."""

    @pytest.mark.asyncio
    async def test_submit_feedback_requires_auth(self, client: AsyncClient):
        """Test that submitting feedback requires authentication."""
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
    async def test_submit_feedback_success(
        self,
        client: AsyncClient,
        test_jwt_token,
    ):
        """Test successful feedback submission."""
        response = await client.post(
            "/api/v1/feedback",
            json={
                "type": "bug",
                "subject": "Test Feedback",
                "message": "Detailed feedback message",
            },
            headers={"Authorization": test_jwt_token},
        )
        assert response.status_code == 201
        data = response.json()
        assert data["message"] == "Feedback submitted successfully"
        assert data["feedback"]["type"] == "bug"
        assert data["feedback"]["subject"] == "Test Feedback"

    @pytest.mark.asyncio
    async def test_submit_feedback_with_rating(
        self,
        client: AsyncClient,
        test_jwt_token,
    ):
        """Test feedback submission with rating."""
        response = await client.post(
            "/api/v1/feedback",
            json={
                "type": "praise",
                "subject": "Great app",
                "message": "Love this application",
                "rating": 5,
            },
            headers={"Authorization": test_jwt_token},
        )
        assert response.status_code == 201
        data = response.json()
        assert data["feedback"]["rating"] == 5

    @pytest.mark.asyncio
    async def test_submit_feedback_invalid_type(
        self,
        client: AsyncClient,
        test_jwt_token,
    ):
        """Test submitting feedback with invalid type."""
        response = await client.post(
            "/api/v1/feedback",
            json={
                "type": "invalid_type",
                "subject": "Test",
                "message": "Message",
            },
            headers={"Authorization": test_jwt_token},
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_submit_feedback_missing_fields(
        self,
        client: AsyncClient,
        test_jwt_token,
    ):
        """Test submitting feedback with missing required fields."""
        response = await client.post(
            "/api/v1/feedback",
            json={"type": "bug"},  # Missing subject and message
            headers={"Authorization": test_jwt_token},
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_submit_feedback_with_context(
        self,
        client: AsyncClient,
        test_jwt_token,
    ):
        """Test feedback submission with auto-captured context."""
        response = await client.post(
            "/api/v1/feedback",
            json={
                "type": "bug",
                "subject": "Test Bug",
                "message": "Bug description",
                "page_url": "https://example.com/dashboard",
                "user_agent": "Mozilla/5.0",
                "screen_resolution": "1920x1080",
            },
            headers={"Authorization": test_jwt_token},
        )
        assert response.status_code == 201
        data = response.json()
        assert data["feedback"]["page_url"] == "https://example.com/dashboard"


# ============================================================================
# User View Own Feedback Tests
# ============================================================================


class TestGetMyFeedback:
    """Tests for GET /api/v1/feedback/me endpoint."""

    @pytest.mark.asyncio
    async def test_get_my_feedback_requires_auth(self, client: AsyncClient):
        """Test that getting own feedback requires authentication."""
        response = await client.get("/api/v1/feedback/me")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_get_my_feedback_success(
        self,
        client: AsyncClient,
        test_jwt_token,
        test_feedback,
    ):
        """Test getting user's own feedback."""
        response = await client.get(
            "/api/v1/feedback/me",
            headers={"Authorization": test_jwt_token},
        )
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert "total" in data
        assert len(data["items"]) >= 1
        # Verify the test feedback is in the list
        feedback_ids = [item["id"] for item in data["items"]]
        assert str(test_feedback.id) in feedback_ids

    @pytest.mark.asyncio
    async def test_get_my_feedback_pagination(
        self,
        client: AsyncClient,
        test_jwt_token,
        test_feedback,
    ):
        """Test pagination parameters."""
        response = await client.get(
            "/api/v1/feedback/me?limit=1&offset=0",
            headers={"Authorization": test_jwt_token},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["limit"] == 1
        assert data["offset"] == 0


# ============================================================================
# Get Feedback By ID Tests
# ============================================================================


class TestGetFeedbackById:
    """Tests for GET /api/v1/feedback/{feedback_id} endpoint."""

    @pytest.mark.asyncio
    async def test_get_feedback_by_id_own(
        self,
        client: AsyncClient,
        test_jwt_token,
        test_feedback,
    ):
        """Test getting own feedback by ID."""
        response = await client.get(
            f"/api/v1/feedback/{test_feedback.id}",
            headers={"Authorization": test_jwt_token},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == str(test_feedback.id)

    @pytest.mark.asyncio
    async def test_get_feedback_by_id_with_view_permission(
        self,
        client: AsyncClient,
        user_with_feedback_view_token,
        test_feedback,
    ):
        """Test getting feedback by ID with feedback:view permission."""
        response = await client.get(
            f"/api/v1/feedback/{test_feedback.id}",
            headers={"Authorization": user_with_feedback_view_token},
        )
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_get_feedback_by_id_forbidden(
        self,
        client: AsyncClient,
        async_session,
        test_organization,
        test_jwt_token,
    ):
        """Test that users cannot view others' feedback without permission."""
        # Create feedback by another user
        from src.core.security import hash_password
        from src.models.user import User

        other_user = User(
            email="other@test.com",
            password=hash_password("OtherUser123!"),
            email_verified=True,
            organization_id=test_organization.id,
        )
        async_session.add(other_user)
        await async_session.commit()
        await async_session.refresh(other_user)

        other_feedback = Feedback(
            organization_id=test_organization.id,
            user_id=other_user.id,
            type="bug",
            subject="Other User Feedback",
            message="This is other user feedback",
            status="new",
        )
        async_session.add(other_feedback)
        await async_session.commit()
        await async_session.refresh(other_feedback)

        response = await client.get(
            f"/api/v1/feedback/{other_feedback.id}",
            headers={"Authorization": test_jwt_token},
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_get_feedback_not_found(
        self,
        client: AsyncClient,
        test_jwt_token,
    ):
        """Test getting non-existent feedback."""
        import uuid

        fake_id = str(uuid.uuid4())
        response = await client.get(
            f"/api/v1/feedback/{fake_id}",
            headers={"Authorization": test_jwt_token},
        )
        assert response.status_code == 404


# ============================================================================
# Admin List Feedback Tests
# ============================================================================


class TestListFeedback:
    """Tests for GET /api/v1/feedback endpoint (admin)."""

    @pytest.mark.asyncio
    async def test_list_feedback_requires_permission(
        self,
        client: AsyncClient,
        test_jwt_token,
    ):
        """Test that listing all feedback requires feedback:view permission."""
        response = await client.get(
            "/api/v1/feedback",
            headers={"Authorization": test_jwt_token},
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_list_feedback_with_permission(
        self,
        client: AsyncClient,
        user_with_feedback_view_token,
        test_feedback,
    ):
        """Test listing all feedback with permission."""
        response = await client.get(
            "/api/v1/feedback",
            headers={"Authorization": user_with_feedback_view_token},
        )
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert "total" in data

    @pytest.mark.asyncio
    async def test_list_feedback_as_admin(
        self,
        client: AsyncClient,
        test_admin_token,
        test_feedback,
    ):
        """Test listing all feedback as admin (is_admin=True)."""
        response = await client.get(
            "/api/v1/feedback",
            headers={"Authorization": test_admin_token},
        )
        assert response.status_code == 200
        data = response.json()
        assert "items" in data


# ============================================================================
# Update Feedback Tests
# ============================================================================


class TestUpdateFeedback:
    """Tests for PATCH /api/v1/feedback/{feedback_id} endpoint."""

    @pytest.mark.asyncio
    async def test_update_feedback_requires_permission(
        self,
        client: AsyncClient,
        test_jwt_token,
        test_feedback,
    ):
        """Test that updating feedback requires feedback:respond permission."""
        response = await client.patch(
            f"/api/v1/feedback/{test_feedback.id}",
            json={"status": "in_review"},
            headers={"Authorization": test_jwt_token},
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_update_feedback_status(
        self,
        client: AsyncClient,
        user_with_feedback_respond_token,
        test_feedback,
    ):
        """Test updating feedback status."""
        response = await client.patch(
            f"/api/v1/feedback/{test_feedback.id}",
            json={"status": "in_review"},
            headers={"Authorization": user_with_feedback_respond_token},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["feedback"]["status"] == "in_review"

    @pytest.mark.asyncio
    async def test_update_feedback_admin_response(
        self,
        client: AsyncClient,
        user_with_feedback_respond_token,
        test_feedback,
    ):
        """Test adding admin response to feedback."""
        response = await client.patch(
            f"/api/v1/feedback/{test_feedback.id}",
            json={"admin_response": "Thank you for your feedback!"},
            headers={"Authorization": user_with_feedback_respond_token},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["feedback"]["admin_response"] == "Thank you for your feedback!"

    @pytest.mark.asyncio
    async def test_update_feedback_admin_notes(
        self,
        client: AsyncClient,
        user_with_feedback_respond_token,
        test_feedback,
    ):
        """Test adding internal admin notes."""
        response = await client.patch(
            f"/api/v1/feedback/{test_feedback.id}",
            json={"admin_notes": "Internal note: needs follow-up"},
            headers={"Authorization": user_with_feedback_respond_token},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["feedback"]["admin_notes"] == "Internal note: needs follow-up"

    @pytest.mark.asyncio
    async def test_update_feedback_not_found(
        self,
        client: AsyncClient,
        user_with_feedback_respond_token,
    ):
        """Test updating non-existent feedback."""
        import uuid

        fake_id = str(uuid.uuid4())
        response = await client.patch(
            f"/api/v1/feedback/{fake_id}",
            json={"status": "in_review"},
            headers={"Authorization": user_with_feedback_respond_token},
        )
        assert response.status_code == 404


# ============================================================================
# Delete Feedback Tests
# ============================================================================


class TestDeleteFeedback:
    """Tests for DELETE /api/v1/feedback/{feedback_id} endpoint."""

    @pytest.mark.asyncio
    async def test_delete_feedback_requires_permission(
        self,
        client: AsyncClient,
        test_jwt_token,
        test_feedback,
    ):
        """Test that deleting feedback requires feedback:delete permission."""
        response = await client.delete(
            f"/api/v1/feedback/{test_feedback.id}",
            headers={"Authorization": test_jwt_token},
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_delete_feedback_success(
        self,
        client: AsyncClient,
        user_with_feedback_delete_token,
        test_feedback,
    ):
        """Test successful feedback deletion."""
        response = await client.delete(
            f"/api/v1/feedback/{test_feedback.id}",
            headers={"Authorization": user_with_feedback_delete_token},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["message"] == "Feedback deleted successfully"
        assert data["feedback_id"] == str(test_feedback.id)

    @pytest.mark.asyncio
    async def test_delete_feedback_not_found(
        self,
        client: AsyncClient,
        user_with_feedback_delete_token,
    ):
        """Test deleting non-existent feedback."""
        import uuid

        fake_id = str(uuid.uuid4())
        response = await client.delete(
            f"/api/v1/feedback/{fake_id}",
            headers={"Authorization": user_with_feedback_delete_token},
        )
        assert response.status_code == 404


# ============================================================================
# Feedback Reply Tests
# ============================================================================


class TestFeedbackReplies:
    """Tests for POST /api/v1/feedback/{feedback_id}/replies endpoint."""

    @pytest.mark.asyncio
    async def test_create_reply_requires_auth(
        self,
        client: AsyncClient,
        test_feedback,
    ):
        """Test that creating a reply requires authentication."""
        response = await client.post(
            f"/api/v1/feedback/{test_feedback.id}/replies",
            json={"message": "Test reply"},
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_create_reply_by_owner(
        self,
        client: AsyncClient,
        test_jwt_token,
        test_feedback,
    ):
        """Test feedback owner can create reply."""
        response = await client.post(
            f"/api/v1/feedback/{test_feedback.id}/replies",
            json={"message": "Additional information for my feedback"},
            headers={"Authorization": test_jwt_token},
        )
        assert response.status_code == 201
        data = response.json()
        assert data["message"] == "Reply created successfully"
        assert data["reply"]["is_admin_reply"] is False

    @pytest.mark.asyncio
    async def test_create_reply_by_admin(
        self,
        client: AsyncClient,
        user_with_feedback_respond_token,
        test_feedback,
    ):
        """Test admin can reply to feedback."""
        response = await client.post(
            f"/api/v1/feedback/{test_feedback.id}/replies",
            json={"message": "Admin response to your feedback"},
            headers={"Authorization": user_with_feedback_respond_token},
        )
        assert response.status_code == 201
        data = response.json()
        assert data["reply"]["is_admin_reply"] is True

    @pytest.mark.asyncio
    async def test_create_reply_not_authorized(
        self,
        client: AsyncClient,
        async_session,
        test_organization,
        test_feedback,
    ):
        """Test that users without permission cannot reply to others' feedback."""
        from src.core.security import create_access_token, hash_password
        from src.models.user import User

        # Create another user without permissions
        other_user = User(
            email="noperm@test.com",
            password=hash_password("NoPermUser123!"),
            email_verified=True,
            organization_id=test_organization.id,
        )
        async_session.add(other_user)
        await async_session.commit()
        await async_session.refresh(other_user)

        token = create_access_token(
            user_id=str(other_user.id),
            organization_id=str(test_organization.id),
        )

        response = await client.post(
            f"/api/v1/feedback/{test_feedback.id}/replies",
            json={"message": "Unauthorized reply"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 403


# ============================================================================
# Mark Feedback Viewed Tests
# ============================================================================


class TestMarkFeedbackViewed:
    """Tests for marking feedback as viewed."""

    @pytest.mark.asyncio
    async def test_mark_feedback_viewed_by_owner(
        self,
        client: AsyncClient,
        test_jwt_token,
        test_feedback,
    ):
        """Test owner can mark feedback as viewed."""
        response = await client.post(
            f"/api/v1/feedback/{test_feedback.id}/mark-viewed",
            headers={"Authorization": test_jwt_token},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["message"] == "Feedback marked as viewed"
        assert data["viewed_at"] is not None

    @pytest.mark.asyncio
    async def test_mark_feedback_viewed_by_admin(
        self,
        client: AsyncClient,
        user_with_feedback_view_token,
        test_feedback,
    ):
        """Test admin can mark feedback as viewed."""
        response = await client.post(
            f"/api/v1/feedback/{test_feedback.id}/mark-viewed-admin",
            headers={"Authorization": user_with_feedback_view_token},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["message"] == "Feedback marked as viewed by admin"


# ============================================================================
# Feedback Attachment Tests
# ============================================================================


class TestFeedbackAttachments:
    """Tests for POST /api/v1/feedback/{feedback_id}/attachments endpoint."""

    @pytest.mark.asyncio
    async def test_create_attachment_by_owner(
        self,
        client: AsyncClient,
        test_jwt_token,
        test_feedback,
    ):
        """Test feedback owner can add attachment."""
        response = await client.post(
            f"/api/v1/feedback/{test_feedback.id}/attachments",
            json={
                "file_path": "s3://bucket/feedback/screenshot.png",
                "file_type": "image/png",
                "file_size_bytes": 12345,
            },
            headers={"Authorization": test_jwt_token},
        )
        assert response.status_code == 201
        data = response.json()
        assert data["file_path"] == "s3://bucket/feedback/screenshot.png"
        assert data["file_type"] == "image/png"

    @pytest.mark.asyncio
    async def test_create_attachment_forbidden(
        self,
        client: AsyncClient,
        async_session,
        test_organization,
        test_feedback,
    ):
        """Test that users cannot attach to others' feedback without permission."""
        from src.core.security import create_access_token, hash_password
        from src.models.user import User

        # Create another user without permissions
        other_user = User(
            email="noattach@test.com",
            password=hash_password("NoAttach123!"),
            email_verified=True,
            organization_id=test_organization.id,
        )
        async_session.add(other_user)
        await async_session.commit()
        await async_session.refresh(other_user)

        token = create_access_token(
            user_id=str(other_user.id),
            organization_id=str(test_organization.id),
        )

        response = await client.post(
            f"/api/v1/feedback/{test_feedback.id}/attachments",
            json={
                "file_path": "s3://bucket/feedback/screenshot.png",
                "file_type": "image/png",
                "file_size_bytes": 12345,
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 403


# ============================================================================
# Tenant Isolation Tests
# ============================================================================


class TestFeedbackTenantIsolation:
    """Tests to ensure feedback is properly isolated between organizations."""

    @pytest.mark.asyncio
    async def test_cannot_view_other_org_feedback(
        self,
        client: AsyncClient,
        test_admin_token,
        second_org_feedback,
    ):
        """Test that admin cannot view other org's feedback."""
        response = await client.get(
            f"/api/v1/feedback/{second_org_feedback.id}",
            headers={"Authorization": test_admin_token},
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_feedback_list_excludes_other_orgs(
        self,
        client: AsyncClient,
        test_admin_token,
        test_feedback,
        second_org_feedback,
    ):
        """Test that feedback list excludes other org's feedback."""
        response = await client.get(
            "/api/v1/feedback",
            headers={"Authorization": test_admin_token},
        )
        assert response.status_code == 200
        data = response.json()
        feedback_ids = [item["id"] for item in data["items"]]
        assert str(second_org_feedback.id) not in feedback_ids

    @pytest.mark.asyncio
    async def test_cannot_update_other_org_feedback(
        self,
        client: AsyncClient,
        test_admin_token,
        second_org_feedback,
    ):
        """Test that admin cannot update other org's feedback."""
        response = await client.patch(
            f"/api/v1/feedback/{second_org_feedback.id}",
            json={"status": "in_review"},
            headers={"Authorization": test_admin_token},
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_cannot_delete_other_org_feedback(
        self,
        client: AsyncClient,
        test_admin_token,
        second_org_feedback,
    ):
        """Test that admin cannot delete other org's feedback."""
        response = await client.delete(
            f"/api/v1/feedback/{second_org_feedback.id}",
            headers={"Authorization": test_admin_token},
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_cannot_reply_to_other_org_feedback(
        self,
        client: AsyncClient,
        test_admin_token,
        second_org_feedback,
    ):
        """Test that admin cannot reply to other org's feedback."""
        response = await client.post(
            f"/api/v1/feedback/{second_org_feedback.id}/replies",
            json={"message": "Unauthorized reply"},
            headers={"Authorization": test_admin_token},
        )
        assert response.status_code == 404
