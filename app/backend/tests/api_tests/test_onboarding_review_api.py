"""
API tests for onboarding review admin endpoints.

Tests verify:
- List submissions
- Approve/reject/request changes
- Comments
- Tenant isolation
"""

from unittest.mock import AsyncMock, patch
from uuid import uuid4

from httpx import AsyncClient
import pytest


# ─────────────────────────────────────────────────────────────
# Access Control Tests
# ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_pending_requires_admin(
    client: AsyncClient,
    test_jwt_token,
):
    """Test that listing pending reviews requires admin role."""
    response = await client.get(
        "/api/v1/onboarding/review/pending",
        headers={"Authorization": test_jwt_token},
    )
    assert response.status_code in [401, 403]


@pytest.mark.asyncio
async def test_list_submissions_requires_admin(
    client: AsyncClient,
    test_jwt_token,
):
    """Test that listing submissions requires admin role."""
    response = await client.get(
        "/api/v1/onboarding/review/submissions",
        headers={"Authorization": test_jwt_token},
    )
    assert response.status_code in [401, 403]


@pytest.mark.asyncio
async def test_get_submission_details_requires_admin(
    client: AsyncClient,
    test_jwt_token,
    test_user_user_type,
):
    """Test that getting submission details requires admin role."""
    response = await client.get(
        f"/api/v1/onboarding/review/{test_user_user_type.id}",
        headers={"Authorization": test_jwt_token},
    )
    assert response.status_code in [401, 403]


@pytest.mark.asyncio
async def test_approve_requires_admin(
    client: AsyncClient,
    test_jwt_token,
    test_user_user_type,
):
    """Test that approving requires admin role."""
    response = await client.post(
        f"/api/v1/onboarding/review/{test_user_user_type.id}/approve",
        headers={"Authorization": test_jwt_token},
    )
    assert response.status_code in [401, 403]


@pytest.mark.asyncio
async def test_reject_requires_admin(
    client: AsyncClient,
    test_jwt_token,
    test_user_user_type,
):
    """Test that rejecting requires admin role."""
    response = await client.post(
        f"/api/v1/onboarding/review/{test_user_user_type.id}/reject",
        json={"reason": "Test rejection"},
        headers={"Authorization": test_jwt_token},
    )
    assert response.status_code in [401, 403]


@pytest.mark.asyncio
async def test_request_change_requires_admin(
    client: AsyncClient,
    test_jwt_token,
    test_user_user_type,
):
    """Test that requesting changes requires admin role."""
    response = await client.post(
        f"/api/v1/onboarding/review/{test_user_user_type.id}/request-change",
        json={"comment": "Please fix this"},
        headers={"Authorization": test_jwt_token},
    )
    assert response.status_code in [401, 403]


# ─────────────────────────────────────────────────────────────
# List Pending Reviews Tests
# ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_pending_as_admin(
    client: AsyncClient,
    admin_token,
):
    """Test listing pending reviews as admin."""
    response = await client.get(
        "/api/v1/onboarding/review/pending",
        headers={"Authorization": admin_token},
    )
    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    assert "total" in data
    assert "limit" in data
    assert "offset" in data


@pytest.mark.asyncio
async def test_list_pending_with_search(
    client: AsyncClient,
    admin_token,
):
    """Test listing pending reviews with search filter."""
    response = await client.get(
        "/api/v1/onboarding/review/pending",
        params={"search": "test"},
        headers={"Authorization": admin_token},
    )
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_list_pending_with_user_type_filter(
    client: AsyncClient,
    admin_token,
    test_user_type,
):
    """Test listing pending reviews filtered by user type."""
    response = await client.get(
        "/api/v1/onboarding/review/pending",
        params={"user_type_id": str(test_user_type.id)},
        headers={"Authorization": admin_token},
    )
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_list_pending_invalid_user_type_format(
    client: AsyncClient,
    admin_token,
):
    """Test listing pending reviews with invalid user type ID format."""
    response = await client.get(
        "/api/v1/onboarding/review/pending",
        params={"user_type_id": "not-a-uuid"},
        headers={"Authorization": admin_token},
    )
    assert response.status_code == 400


# ─────────────────────────────────────────────────────────────
# List Submissions Tests
# ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_submissions_as_admin(
    client: AsyncClient,
    admin_token,
):
    """Test listing all submissions as admin."""
    response = await client.get(
        "/api/v1/onboarding/review/submissions",
        headers={"Authorization": admin_token},
    )
    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    assert "total" in data


@pytest.mark.asyncio
async def test_list_submissions_with_status_filter(
    client: AsyncClient,
    admin_token,
):
    """Test listing submissions filtered by status."""
    response = await client.get(
        "/api/v1/onboarding/review/submissions",
        params={"status": "pending_review"},
        headers={"Authorization": admin_token},
    )
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_list_submissions_with_attention_filter(
    client: AsyncClient,
    admin_token,
):
    """Test listing submissions filtered by requires_attention flag."""
    response = await client.get(
        "/api/v1/onboarding/review/submissions",
        params={"requires_attention": True},
        headers={"Authorization": admin_token},
    )
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_list_submissions_pagination(
    client: AsyncClient,
    admin_token,
):
    """Test listing submissions with pagination."""
    response = await client.get(
        "/api/v1/onboarding/review/submissions",
        params={"limit": 10, "offset": 0},
        headers={"Authorization": admin_token},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["limit"] == 10
    assert data["offset"] == 0


# ─────────────────────────────────────────────────────────────
# Get Submission Details Tests
# ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_submission_details(
    client: AsyncClient,
    admin_token,
    test_user_user_type,
):
    """Test getting submission details."""
    response = await client.get(
        f"/api/v1/onboarding/review/{test_user_user_type.id}",
        headers={"Authorization": admin_token},
    )
    assert response.status_code == 200
    data = response.json()
    assert "id" in data
    assert "user_id" in data
    assert "user_first_name" in data
    assert "user_last_name" in data
    assert "user_email" in data
    assert "user_type_id" in data
    assert "user_type_name" in data
    assert "onboarding_status" in data
    assert "steps_data" in data


@pytest.mark.asyncio
async def test_get_submission_details_not_found(
    client: AsyncClient,
    admin_token,
):
    """Test getting non-existent submission."""
    response = await client.get(
        f"/api/v1/onboarding/review/{uuid4()}",
        headers={"Authorization": admin_token},
    )
    assert response.status_code == 404


# ─────────────────────────────────────────────────────────────
# Approve Submission Tests
# ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_approve_submission(
    client: AsyncClient,
    async_session,
    admin_token,
    test_user_user_type,
):
    """Test approving an onboarding submission."""
    from src.models.user_user_type import OnboardingStatus

    test_user_user_type.onboarding_status = OnboardingStatus.PENDING_REVIEW
    await async_session.commit()

    with patch(
        "src.api.onboarding_review.onboarding_notification_service.send_approved_notification",
        new_callable=AsyncMock,
    ):
        response = await client.post(
            f"/api/v1/onboarding/review/{test_user_user_type.id}/approve",
            headers={"Authorization": admin_token},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "approved"
    assert "onboarded_at" in data


@pytest.mark.asyncio
async def test_approve_submission_with_expiry(
    client: AsyncClient,
    async_session,
    admin_token,
    test_user_user_type,
):
    """Test approving submission with expiry date."""
    from datetime import datetime, timedelta, timezone

    from src.models.user_user_type import OnboardingStatus

    test_user_user_type.onboarding_status = OnboardingStatus.PENDING_REVIEW
    await async_session.commit()

    expires_at = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()

    with patch(
        "src.api.onboarding_review.onboarding_notification_service.send_approved_notification",
        new_callable=AsyncMock,
    ):
        response = await client.post(
            f"/api/v1/onboarding/review/{test_user_user_type.id}/approve",
            json={"expires_at": expires_at},
            headers={"Authorization": admin_token},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["expires_at"] is not None


@pytest.mark.asyncio
async def test_approve_submission_not_found(
    client: AsyncClient,
    admin_token,
):
    """Test approving non-existent submission."""
    response = await client.post(
        f"/api/v1/onboarding/review/{uuid4()}/approve",
        headers={"Authorization": admin_token},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_approve_submission_wrong_status(
    client: AsyncClient,
    admin_token,
    test_user_user_type,
):
    """Test approving submission with wrong status."""
    # test_user_user_type has status IN_PROGRESS
    response = await client.post(
        f"/api/v1/onboarding/review/{test_user_user_type.id}/approve",
        headers={"Authorization": admin_token},
    )
    assert response.status_code == 400


# ─────────────────────────────────────────────────────────────
# Reject Submission Tests
# ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_reject_submission(
    client: AsyncClient,
    async_session,
    admin_token,
    test_user_user_type,
):
    """Test rejecting an onboarding submission."""
    from src.models.user_user_type import OnboardingStatus

    test_user_user_type.onboarding_status = OnboardingStatus.PENDING_REVIEW
    await async_session.commit()

    with patch(
        "src.api.onboarding_review.onboarding_notification_service.send_rejected_notification",
        new_callable=AsyncMock,
    ):
        response = await client.post(
            f"/api/v1/onboarding/review/{test_user_user_type.id}/reject",
            json={"reason": "Test rejection reason"},
            headers={"Authorization": admin_token},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "rejected"
    assert data["reason"] == "Test rejection reason"


@pytest.mark.asyncio
async def test_reject_submission_missing_reason(
    client: AsyncClient,
    async_session,
    admin_token,
    test_user_user_type,
):
    """Test rejecting submission without reason."""
    from src.models.user_user_type import OnboardingStatus

    test_user_user_type.onboarding_status = OnboardingStatus.PENDING_REVIEW
    await async_session.commit()

    response = await client.post(
        f"/api/v1/onboarding/review/{test_user_user_type.id}/reject",
        json={},
        headers={"Authorization": admin_token},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_reject_submission_not_found(
    client: AsyncClient,
    admin_token,
):
    """Test rejecting non-existent submission."""
    response = await client.post(
        f"/api/v1/onboarding/review/{uuid4()}/reject",
        json={"reason": "Test rejection"},
        headers={"Authorization": admin_token},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_reject_submission_wrong_status(
    client: AsyncClient,
    admin_token,
    test_user_user_type,
):
    """Test rejecting submission with wrong status."""
    # test_user_user_type has status IN_PROGRESS
    response = await client.post(
        f"/api/v1/onboarding/review/{test_user_user_type.id}/reject",
        json={"reason": "Test rejection"},
        headers={"Authorization": admin_token},
    )
    assert response.status_code == 400


# ─────────────────────────────────────────────────────────────
# Request Change Tests
# ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_request_change(
    client: AsyncClient,
    async_session,
    admin_token,
    test_user_user_type,
):
    """Test requesting changes on an onboarding submission."""
    from src.models.user_user_type import OnboardingStatus

    test_user_user_type.onboarding_status = OnboardingStatus.PENDING_REVIEW
    await async_session.commit()

    with patch(
        "src.api.onboarding_review.onboarding_notification_service.send_change_requested_notification",
        new_callable=AsyncMock,
    ):
        response = await client.post(
            f"/api/v1/onboarding/review/{test_user_user_type.id}/request-change",
            json={"comment": "Please update your information"},
            headers={"Authorization": admin_token},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "change_requested"


@pytest.mark.asyncio
async def test_request_change_missing_comment(
    client: AsyncClient,
    async_session,
    admin_token,
    test_user_user_type,
):
    """Test requesting changes without comment."""
    from src.models.user_user_type import OnboardingStatus

    test_user_user_type.onboarding_status = OnboardingStatus.PENDING_REVIEW
    await async_session.commit()

    response = await client.post(
        f"/api/v1/onboarding/review/{test_user_user_type.id}/request-change",
        json={},
        headers={"Authorization": admin_token},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_request_change_not_found(
    client: AsyncClient,
    admin_token,
):
    """Test requesting changes on non-existent submission."""
    response = await client.post(
        f"/api/v1/onboarding/review/{uuid4()}/request-change",
        json={"comment": "Test comment"},
        headers={"Authorization": admin_token},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_request_change_wrong_status(
    client: AsyncClient,
    admin_token,
    test_user_user_type,
):
    """Test requesting changes on submission with wrong status."""
    # test_user_user_type has status IN_PROGRESS (not PENDING_REVIEW)
    response = await client.post(
        f"/api/v1/onboarding/review/{test_user_user_type.id}/request-change",
        json={"comment": "Test comment"},
        headers={"Authorization": admin_token},
    )
    assert response.status_code == 400


# ─────────────────────────────────────────────────────────────
# Comments Tests
# ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_review_comments(
    client: AsyncClient,
    admin_token,
    test_user_user_type,
    test_review_comment,
):
    """Test getting comments for a submission."""
    response = await client.get(
        f"/api/v1/onboarding/review/{test_user_user_type.id}/comments",
        headers={"Authorization": admin_token},
    )
    assert response.status_code == 200
    data = response.json()
    assert "comments" in data
    assert len(data["comments"]) >= 1


@pytest.mark.asyncio
async def test_get_review_comments_not_found(
    client: AsyncClient,
    admin_token,
):
    """Test getting comments for non-existent submission."""
    response = await client.get(
        f"/api/v1/onboarding/review/{uuid4()}/comments",
        headers={"Authorization": admin_token},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_add_review_comment(
    client: AsyncClient,
    admin_token,
    test_user_user_type,
):
    """Test adding a comment to a submission."""
    response = await client.post(
        f"/api/v1/onboarding/review/{test_user_user_type.id}/comments",
        json={"comment": "Test admin comment"},
        headers={"Authorization": admin_token},
    )
    assert response.status_code == 200
    data = response.json()
    assert "message" in data


@pytest.mark.asyncio
async def test_add_review_comment_empty(
    client: AsyncClient,
    admin_token,
    test_user_user_type,
):
    """Test adding an empty comment."""
    response = await client.post(
        f"/api/v1/onboarding/review/{test_user_user_type.id}/comments",
        json={"comment": ""},
        headers={"Authorization": admin_token},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_add_review_comment_too_long(
    client: AsyncClient,
    admin_token,
    test_user_user_type,
):
    """Test adding a comment that exceeds max length."""
    response = await client.post(
        f"/api/v1/onboarding/review/{test_user_user_type.id}/comments",
        json={"comment": "x" * 2001},  # Max is 2000
        headers={"Authorization": admin_token},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_add_review_comment_not_found(
    client: AsyncClient,
    admin_token,
):
    """Test adding comment to non-existent submission."""
    response = await client.post(
        f"/api/v1/onboarding/review/{uuid4()}/comments",
        json={"comment": "Test comment"},
        headers={"Authorization": admin_token},
    )
    assert response.status_code == 404


# ─────────────────────────────────────────────────────────────
# Tenant Isolation Tests
# ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_cannot_view_other_org_submission(
    client: AsyncClient,
    admin_token,
    second_org_user_user_type,
):
    """Test that admin cannot view submission from another org."""
    response = await client.get(
        f"/api/v1/onboarding/review/{second_org_user_user_type.id}",
        headers={"Authorization": admin_token},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_cannot_approve_other_org_submission(
    client: AsyncClient,
    admin_token,
    second_org_user_user_type,
):
    """Test that admin cannot approve submission from another org."""
    response = await client.post(
        f"/api/v1/onboarding/review/{second_org_user_user_type.id}/approve",
        headers={"Authorization": admin_token},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_cannot_reject_other_org_submission(
    client: AsyncClient,
    admin_token,
    second_org_user_user_type,
):
    """Test that admin cannot reject submission from another org."""
    response = await client.post(
        f"/api/v1/onboarding/review/{second_org_user_user_type.id}/reject",
        json={"reason": "Test rejection"},
        headers={"Authorization": admin_token},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_cannot_request_change_other_org_submission(
    client: AsyncClient,
    admin_token,
    second_org_user_user_type,
):
    """Test that admin cannot request changes on submission from another org."""
    response = await client.post(
        f"/api/v1/onboarding/review/{second_org_user_user_type.id}/request-change",
        json={"comment": "Test comment"},
        headers={"Authorization": admin_token},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_cannot_view_other_org_comments(
    client: AsyncClient,
    admin_token,
    second_org_user_user_type,
):
    """Test that admin cannot view comments from another org's submission."""
    response = await client.get(
        f"/api/v1/onboarding/review/{second_org_user_user_type.id}/comments",
        headers={"Authorization": admin_token},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_cannot_add_comment_other_org_submission(
    client: AsyncClient,
    admin_token,
    second_org_user_user_type,
):
    """Test that admin cannot add comment to another org's submission."""
    response = await client.post(
        f"/api/v1/onboarding/review/{second_org_user_user_type.id}/comments",
        json={"comment": "Sneaky comment"},
        headers={"Authorization": admin_token},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_submissions_list_excludes_other_orgs(
    client: AsyncClient,
    async_session,
    admin_token,
    test_user_user_type,
    second_org_user_user_type,
):
    """Test that submissions list excludes other orgs."""
    from src.models.user_user_type import OnboardingStatus

    # Set both to PENDING_REVIEW so they should appear in the list
    test_user_user_type.onboarding_status = OnboardingStatus.PENDING_REVIEW
    second_org_user_user_type.onboarding_status = OnboardingStatus.PENDING_REVIEW
    await async_session.commit()

    response = await client.get(
        "/api/v1/onboarding/review/submissions",
        params={"status": "pending_review"},
        headers={"Authorization": admin_token},
    )
    assert response.status_code == 200
    data = response.json()

    # Verify second org's submission is not in the list
    submission_ids = [item["id"] for item in data.get("items", [])]
    assert str(second_org_user_user_type.id) not in submission_ids
