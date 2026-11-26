"""
API tests for user-facing onboarding endpoints.

Tests verify:
- Onboarding status
- Starting onboarding
- Step submission
- Phone verification in onboarding
- Progress tracking
- Tenant isolation
"""

from unittest.mock import AsyncMock, patch
from uuid import uuid4

from httpx import AsyncClient
import pytest


# ─────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────


@pytest.fixture
def mock_onboarding_enabled():
    """Mock onboarding feature flag as enabled."""
    return patch(
        "src.api.onboarding.check_onboarding_enabled",
        new_callable=AsyncMock,
        return_value=True,
    )


@pytest.fixture
def mock_onboarding_disabled():
    """Mock onboarding feature flag as disabled."""
    return patch(
        "src.api.onboarding.check_onboarding_enabled",
        new_callable=AsyncMock,
        return_value=False,
    )


# ─────────────────────────────────────────────────────────────
# Get Status Tests
# ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_onboarding_status_requires_auth(client: AsyncClient):
    """Test that getting onboarding status requires authentication."""
    response = await client.get("/api/v1/onboarding/status")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_get_onboarding_status_not_started(
    client: AsyncClient,
    test_jwt_token,
    mock_onboarding_enabled,
):
    """Test onboarding status when not started."""
    with mock_onboarding_enabled:
        response = await client.get(
            "/api/v1/onboarding/status",
            headers={"Authorization": test_jwt_token},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "not_started"
    assert data["current_step"] is None
    assert data["progress"] == []
    assert data["steps"] == []
    assert data["user_type"] is None


@pytest.mark.asyncio
async def test_get_onboarding_status_disabled_org(
    client: AsyncClient,
    test_jwt_token,
    mock_onboarding_disabled,
):
    """Test onboarding status when disabled for org."""
    with mock_onboarding_disabled:
        response = await client.get(
            "/api/v1/onboarding/status",
            headers={"Authorization": test_jwt_token},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["onboarding_enabled"] is False
    assert data["status"] == "not_started"


@pytest.mark.asyncio
async def test_get_onboarding_status_in_progress(
    client: AsyncClient,
    test_jwt_token,
    test_user_user_type,
    test_onboarding_step,
    mock_onboarding_enabled,
):
    """Test onboarding status when in progress."""
    with mock_onboarding_enabled:
        response = await client.get(
            "/api/v1/onboarding/status",
            headers={"Authorization": test_jwt_token},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "in_progress"
    assert data["user_type"] is not None
    assert data["total_steps_count"] >= 1


# ─────────────────────────────────────────────────────────────
# Get My User Types Tests
# ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_my_user_types_requires_auth(client: AsyncClient):
    """Test that getting my user types requires authentication."""
    response = await client.get("/api/v1/onboarding/my-user-types")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_get_my_user_types_empty(
    client: AsyncClient,
    test_jwt_token,
    mock_onboarding_enabled,
):
    """Test getting user types when none assigned."""
    with mock_onboarding_enabled:
        response = await client.get(
            "/api/v1/onboarding/my-user-types",
            headers={"Authorization": test_jwt_token},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["user_types"] == []
    assert data["total"] == 0


@pytest.mark.asyncio
async def test_get_my_user_types_with_assignment(
    client: AsyncClient,
    test_jwt_token,
    test_user_user_type,
    mock_onboarding_enabled,
):
    """Test getting user types when assigned."""
    with mock_onboarding_enabled:
        response = await client.get(
            "/api/v1/onboarding/my-user-types",
            headers={"Authorization": test_jwt_token},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["total"] >= 1
    assert len(data["user_types"]) >= 1


# ─────────────────────────────────────────────────────────────
# Start Onboarding Tests
# ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_start_onboarding_requires_auth(client: AsyncClient):
    """Test that starting onboarding requires authentication."""
    response = await client.post(f"/api/v1/onboarding/start/{uuid4()}")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_start_onboarding_feature_disabled(
    client: AsyncClient,
    test_jwt_token,
    test_user_type,
    mock_onboarding_disabled,
):
    """Test starting onboarding when feature is disabled."""
    with mock_onboarding_disabled:
        response = await client.post(
            f"/api/v1/onboarding/start/{test_user_type.id}",
            headers={"Authorization": test_jwt_token},
        )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_start_onboarding_invalid_user_type(
    client: AsyncClient,
    test_jwt_token,
    mock_onboarding_enabled,
):
    """Test starting onboarding with invalid user type."""
    with mock_onboarding_enabled:
        response = await client.post(
            f"/api/v1/onboarding/start/{uuid4()}",
            headers={"Authorization": test_jwt_token},
        )

    assert response.status_code in [400, 404]


@pytest.mark.asyncio
async def test_start_onboarding_success(
    client: AsyncClient,
    test_jwt_token,
    test_user_type,
    test_onboarding_step,
    mock_onboarding_enabled,
):
    """Test successfully starting onboarding."""
    with mock_onboarding_enabled:
        response = await client.post(
            f"/api/v1/onboarding/start/{test_user_type.id}",
            headers={"Authorization": test_jwt_token},
        )

    assert response.status_code in [200, 201]
    data = response.json()
    assert "user_user_type_id" in data or "id" in data


@pytest.mark.asyncio
async def test_start_onboarding_already_started(
    client: AsyncClient,
    test_jwt_token,
    test_user_user_type,
    test_user_type,
    mock_onboarding_enabled,
):
    """Test starting onboarding when already started for this user type."""
    with mock_onboarding_enabled:
        response = await client.post(
            f"/api/v1/onboarding/start/{test_user_type.id}",
            headers={"Authorization": test_jwt_token},
        )

    # Should fail because user already has this user type
    assert response.status_code == 400


# ─────────────────────────────────────────────────────────────
# Submit Step Tests
# ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_submit_step_requires_auth(client: AsyncClient):
    """Test that submitting a step requires authentication."""
    response = await client.post(
        f"/api/v1/onboarding/steps/{uuid4()}/submit",
        json={"submitted_data": {}},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_submit_step_feature_disabled(
    client: AsyncClient,
    test_jwt_token,
    test_onboarding_step,
    mock_onboarding_disabled,
):
    """Test submitting step when feature is disabled."""
    with mock_onboarding_disabled:
        response = await client.post(
            f"/api/v1/onboarding/steps/{test_onboarding_step.id}/submit",
            json={"submitted_data": {"name": "Test"}},
            headers={"Authorization": test_jwt_token},
        )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_submit_step_invalid_step_id(
    client: AsyncClient,
    test_jwt_token,
    mock_onboarding_enabled,
):
    """Test submitting to invalid step."""
    with mock_onboarding_enabled:
        response = await client.post(
            f"/api/v1/onboarding/steps/{uuid4()}/submit",
            json={"submitted_data": {"name": "Test"}},
            headers={"Authorization": test_jwt_token},
        )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_submit_step_not_started(
    client: AsyncClient,
    test_jwt_token,
    test_onboarding_step,
    mock_onboarding_enabled,
):
    """Test submitting step without starting onboarding first."""
    with mock_onboarding_enabled:
        response = await client.post(
            f"/api/v1/onboarding/steps/{test_onboarding_step.id}/submit",
            json={"submitted_data": {"name": "Test"}},
            headers={"Authorization": test_jwt_token},
        )

    assert response.status_code == 400


@pytest.mark.asyncio
async def test_submit_step_success(
    client: AsyncClient,
    test_jwt_token,
    test_user_user_type,
    test_onboarding_step,
    mock_onboarding_enabled,
):
    """Test successful step submission."""
    with mock_onboarding_enabled:
        response = await client.post(
            f"/api/v1/onboarding/steps/{test_onboarding_step.id}/submit",
            json={"submitted_data": {"name": "Test Name"}},
            headers={"Authorization": test_jwt_token},
        )

    assert response.status_code == 200
    data = response.json()
    assert "message" in data or "status" in data


@pytest.mark.asyncio
async def test_submit_step_data_too_large(
    client: AsyncClient,
    test_jwt_token,
    test_user_user_type,
    test_onboarding_step,
    mock_onboarding_enabled,
):
    """Test that submitted_data size is validated (max 100KB)."""
    # Create data larger than 100KB
    large_data = {"name": "x" * 150000}

    with mock_onboarding_enabled:
        response = await client.post(
            f"/api/v1/onboarding/steps/{test_onboarding_step.id}/submit",
            json={"submitted_data": large_data},
            headers={"Authorization": test_jwt_token},
        )

    assert response.status_code == 422


# ─────────────────────────────────────────────────────────────
# Phone Verification Tests
# ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_send_phone_otp_requires_auth(client: AsyncClient):
    """Test that sending phone OTP requires authentication."""
    response = await client.post(
        "/api/v1/onboarding/phone/send-otp",
        json={"phone": "+27123456789"},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_send_phone_otp_feature_disabled(
    client: AsyncClient,
    test_jwt_token,
    mock_onboarding_disabled,
):
    """Test sending phone OTP when onboarding is disabled."""
    with mock_onboarding_disabled:
        response = await client.post(
            "/api/v1/onboarding/phone/send-otp",
            json={"phone": "+27123456789"},
            headers={"Authorization": test_jwt_token},
        )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_send_phone_otp_invalid_phone(
    client: AsyncClient,
    test_jwt_token,
    mock_onboarding_enabled,
):
    """Test sending phone OTP with invalid phone number."""
    with mock_onboarding_enabled:
        response = await client.post(
            "/api/v1/onboarding/phone/send-otp",
            json={"phone": "123"},  # Too short
            headers={"Authorization": test_jwt_token},
        )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_send_phone_otp_success(
    client: AsyncClient,
    test_jwt_token,
    mock_onboarding_enabled,
):
    """Test successfully sending phone OTP."""
    with mock_onboarding_enabled, patch(
        "src.api.onboarding.phone_verification_service.send_otp",
        new_callable=AsyncMock,
        return_value={"message": "OTP sent"},
    ):
        response = await client.post(
            "/api/v1/onboarding/phone/send-otp",
            json={"phone": "+27123456789"},
            headers={"Authorization": test_jwt_token},
        )

    assert response.status_code == 200


@pytest.mark.asyncio
async def test_verify_phone_otp_requires_auth(client: AsyncClient):
    """Test that verifying phone OTP requires authentication."""
    response = await client.post(
        "/api/v1/onboarding/phone/verify",
        json={"phone": "+27123456789", "otp": "123456"},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_verify_phone_otp_invalid_format(
    client: AsyncClient,
    test_jwt_token,
    mock_onboarding_enabled,
):
    """Test verifying phone OTP with invalid OTP format."""
    with mock_onboarding_enabled:
        response = await client.post(
            "/api/v1/onboarding/phone/verify",
            json={"phone": "+27123456789", "otp": "12345"},  # Too short
            headers={"Authorization": test_jwt_token},
        )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_verify_phone_otp_success(
    client: AsyncClient,
    test_jwt_token,
    mock_onboarding_enabled,
):
    """Test successfully verifying phone OTP."""
    with mock_onboarding_enabled, patch(
        "src.api.onboarding.phone_verification_service.verify_otp",
        new_callable=AsyncMock,
        return_value={"verified": True, "phone": "+27123456789"},
    ):
        response = await client.post(
            "/api/v1/onboarding/phone/verify",
            json={"phone": "+27123456789", "otp": "123456"},
            headers={"Authorization": test_jwt_token},
        )

    assert response.status_code == 200


# ─────────────────────────────────────────────────────────────
# Respond to Change Request Tests
# ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_respond_to_change_request_requires_auth(client: AsyncClient):
    """Test that responding to change request requires authentication."""
    response = await client.post(
        f"/api/v1/onboarding/submissions/{uuid4()}/respond",
        json={"comment": "My response"},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_respond_to_change_request_not_found(
    client: AsyncClient,
    test_jwt_token,
    mock_onboarding_enabled,
):
    """Test responding to non-existent submission."""
    with mock_onboarding_enabled:
        response = await client.post(
            f"/api/v1/onboarding/submissions/{uuid4()}/respond",
            json={"comment": "My response"},
            headers={"Authorization": test_jwt_token},
        )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_respond_to_change_request_wrong_status(
    client: AsyncClient,
    async_session,
    test_jwt_token,
    test_user_user_type,
    mock_onboarding_enabled,
):
    """Test responding when status is not change_requested."""
    # test_user_user_type has status IN_PROGRESS, not CHANGE_REQUESTED
    with mock_onboarding_enabled:
        response = await client.post(
            f"/api/v1/onboarding/submissions/{test_user_user_type.id}/respond",
            json={"comment": "My response"},
            headers={"Authorization": test_jwt_token},
        )

    assert response.status_code == 400


@pytest.mark.asyncio
async def test_respond_to_change_request_success(
    client: AsyncClient,
    async_session,
    test_jwt_token,
    test_user_user_type,
    mock_onboarding_enabled,
):
    """Test successfully responding to change request."""
    from src.models.user_user_type import OnboardingStatus

    # Update status to CHANGE_REQUESTED
    test_user_user_type.onboarding_status = OnboardingStatus.CHANGE_REQUESTED
    await async_session.commit()

    with mock_onboarding_enabled, patch(
        "src.api.onboarding.onboarding_notification_service.send_user_responded_notification",
        new_callable=AsyncMock,
    ):
        response = await client.post(
            f"/api/v1/onboarding/submissions/{test_user_user_type.id}/respond",
            json={"comment": "I have addressed the concerns"},
            headers={"Authorization": test_jwt_token},
        )

    assert response.status_code == 200
    data = response.json()
    assert "message" in data


# ─────────────────────────────────────────────────────────────
# Resubmit for Review Tests
# ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_resubmit_for_review_requires_auth(client: AsyncClient):
    """Test that resubmitting requires authentication."""
    response = await client.post(f"/api/v1/onboarding/submissions/{uuid4()}/resubmit")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_resubmit_for_review_not_found(
    client: AsyncClient,
    test_jwt_token,
    mock_onboarding_enabled,
):
    """Test resubmitting non-existent submission."""
    with mock_onboarding_enabled:
        response = await client.post(
            f"/api/v1/onboarding/submissions/{uuid4()}/resubmit",
            headers={"Authorization": test_jwt_token},
        )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_resubmit_for_review_wrong_status(
    client: AsyncClient,
    test_jwt_token,
    test_user_user_type,
    mock_onboarding_enabled,
):
    """Test resubmitting when status is not change_requested."""
    with mock_onboarding_enabled:
        response = await client.post(
            f"/api/v1/onboarding/submissions/{test_user_user_type.id}/resubmit",
            headers={"Authorization": test_jwt_token},
        )

    assert response.status_code == 400


@pytest.mark.asyncio
async def test_resubmit_for_review_success(
    client: AsyncClient,
    async_session,
    test_jwt_token,
    test_user_user_type,
    mock_onboarding_enabled,
):
    """Test successfully resubmitting for review."""
    from src.models.user_user_type import OnboardingStatus

    # Update status to CHANGE_REQUESTED
    test_user_user_type.onboarding_status = OnboardingStatus.CHANGE_REQUESTED
    await async_session.commit()

    with mock_onboarding_enabled, patch(
        "src.api.onboarding.onboarding_notification_service.send_user_resubmitted_notification",
        new_callable=AsyncMock,
    ):
        response = await client.post(
            f"/api/v1/onboarding/submissions/{test_user_user_type.id}/resubmit",
            headers={"Authorization": test_jwt_token},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "pending_review"


# ─────────────────────────────────────────────────────────────
# Get My Review Comments Tests
# ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_my_review_comments_requires_auth(client: AsyncClient):
    """Test that getting comments requires authentication."""
    response = await client.get(f"/api/v1/onboarding/submissions/{uuid4()}/comments")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_get_my_review_comments_not_found(
    client: AsyncClient,
    test_jwt_token,
    mock_onboarding_enabled,
):
    """Test getting comments for non-existent submission."""
    with mock_onboarding_enabled:
        response = await client.get(
            f"/api/v1/onboarding/submissions/{uuid4()}/comments",
            headers={"Authorization": test_jwt_token},
        )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_my_review_comments_success(
    client: AsyncClient,
    test_jwt_token,
    test_user_user_type,
    test_review_comment,
    mock_onboarding_enabled,
):
    """Test successfully getting review comments."""
    with mock_onboarding_enabled:
        response = await client.get(
            f"/api/v1/onboarding/submissions/{test_user_user_type.id}/comments",
            headers={"Authorization": test_jwt_token},
        )

    assert response.status_code == 200
    data = response.json()
    assert "comments" in data


# ─────────────────────────────────────────────────────────────
# Tenant Isolation Tests
# ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_cannot_access_other_org_submission(
    client: AsyncClient,
    test_jwt_token,
    second_org_user_user_type,
    mock_onboarding_enabled,
):
    """Test that user cannot access submission from another org."""
    with mock_onboarding_enabled:
        response = await client.get(
            f"/api/v1/onboarding/submissions/{second_org_user_user_type.id}/comments",
            headers={"Authorization": test_jwt_token},
        )

    assert response.status_code in [403, 404]


@pytest.mark.asyncio
async def test_cannot_respond_to_other_org_submission(
    client: AsyncClient,
    test_jwt_token,
    second_org_user_user_type,
    mock_onboarding_enabled,
):
    """Test that user cannot respond to submission from another org."""
    with mock_onboarding_enabled:
        response = await client.post(
            f"/api/v1/onboarding/submissions/{second_org_user_user_type.id}/respond",
            json={"comment": "Sneaky response"},
            headers={"Authorization": test_jwt_token},
        )

    assert response.status_code in [403, 404]


@pytest.mark.asyncio
async def test_cannot_resubmit_other_org_submission(
    client: AsyncClient,
    test_jwt_token,
    second_org_user_user_type,
    mock_onboarding_enabled,
):
    """Test that user cannot resubmit submission from another org."""
    with mock_onboarding_enabled:
        response = await client.post(
            f"/api/v1/onboarding/submissions/{second_org_user_user_type.id}/resubmit",
            headers={"Authorization": test_jwt_token},
        )

    assert response.status_code in [403, 404]


# ─────────────────────────────────────────────────────────────
# Withdraw Onboarding Tests
# ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_withdraw_onboarding_requires_auth(client: AsyncClient):
    """Withdrawing requires authentication."""
    response = await client.delete(f"/api/v1/onboarding/submissions/{uuid4()}")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_withdraw_onboarding_feature_disabled(
    client: AsyncClient,
    test_jwt_token,
    test_user_user_type,
    mock_onboarding_disabled,
):
    """Withdraw is blocked when the onboarding feature flag is off."""
    with mock_onboarding_disabled:
        response = await client.delete(
            f"/api/v1/onboarding/submissions/{test_user_user_type.id}",
            headers={"Authorization": test_jwt_token},
        )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_withdraw_onboarding_not_found(
    client: AsyncClient,
    test_jwt_token,
    mock_onboarding_enabled,
):
    """Withdrawing a non-existent submission returns 404."""
    with mock_onboarding_enabled:
        response = await client.delete(
            f"/api/v1/onboarding/submissions/{uuid4()}",
            headers={"Authorization": test_jwt_token},
        )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_withdraw_onboarding_in_progress_success(
    client: AsyncClient,
    async_session,
    test_jwt_token,
    test_user_user_type,
    mock_onboarding_enabled,
):
    """In-progress withdrawal soft-deletes the row and does not notify admins."""
    from src.models.user_user_type import UserUserType

    uut_id = str(test_user_user_type.id)

    with mock_onboarding_enabled, patch(
        "src.api.onboarding.onboarding_notification_service.send_user_withdrew_notification",
        new_callable=AsyncMock,
    ) as mock_notify:
        response = await client.delete(
            f"/api/v1/onboarding/submissions/{uut_id}",
            headers={"Authorization": test_jwt_token},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["prior_status"] == "in_progress"
    mock_notify.assert_not_called()

    await async_session.refresh(test_user_user_type)
    fetched = await async_session.get(UserUserType, test_user_user_type.id)
    assert fetched is not None
    assert fetched.deleted_time is not None


@pytest.mark.asyncio
async def test_withdraw_onboarding_pending_review_notifies_admins(
    client: AsyncClient,
    async_session,
    test_jwt_token,
    test_user_user_type,
    mock_onboarding_enabled,
):
    """Withdrawing while pending_review sends a notification to admins."""
    from src.models.user_user_type import OnboardingStatus

    test_user_user_type.onboarding_status = OnboardingStatus.PENDING_REVIEW
    await async_session.commit()

    with mock_onboarding_enabled, patch(
        "src.api.onboarding.onboarding_notification_service.send_user_withdrew_notification",
        new_callable=AsyncMock,
    ) as mock_notify:
        response = await client.delete(
            f"/api/v1/onboarding/submissions/{test_user_user_type.id}",
            headers={"Authorization": test_jwt_token},
        )

    assert response.status_code == 200
    assert response.json()["prior_status"] == "pending_review"
    mock_notify.assert_awaited_once()


@pytest.mark.asyncio
async def test_withdraw_onboarding_blocked_when_approved(
    client: AsyncClient,
    async_session,
    test_jwt_token,
    test_user_user_type,
    mock_onboarding_enabled,
):
    """Approved onboarding cannot be self-withdrawn."""
    from src.models.user_user_type import OnboardingStatus

    test_user_user_type.onboarding_status = OnboardingStatus.APPROVED
    await async_session.commit()

    with mock_onboarding_enabled:
        response = await client.delete(
            f"/api/v1/onboarding/submissions/{test_user_user_type.id}",
            headers={"Authorization": test_jwt_token},
        )

    assert response.status_code == 400


@pytest.mark.asyncio
async def test_withdraw_onboarding_blocked_when_rejected(
    client: AsyncClient,
    async_session,
    test_jwt_token,
    test_user_user_type,
    mock_onboarding_enabled,
):
    """Rejected onboarding cannot be self-withdrawn (terminal state)."""
    from src.models.user_user_type import OnboardingStatus

    test_user_user_type.onboarding_status = OnboardingStatus.REJECTED
    await async_session.commit()

    with mock_onboarding_enabled:
        response = await client.delete(
            f"/api/v1/onboarding/submissions/{test_user_user_type.id}",
            headers={"Authorization": test_jwt_token},
        )

    assert response.status_code == 400


@pytest.mark.asyncio
async def test_cannot_withdraw_other_org_submission(
    client: AsyncClient,
    test_jwt_token,
    second_org_user_user_type,
    mock_onboarding_enabled,
):
    """User cannot withdraw a submission belonging to another org."""
    with mock_onboarding_enabled:
        response = await client.delete(
            f"/api/v1/onboarding/submissions/{second_org_user_user_type.id}",
            headers={"Authorization": test_jwt_token},
        )

    assert response.status_code in [403, 404]


@pytest.mark.asyncio
async def test_withdraw_then_restart_same_user_type(
    client: AsyncClient,
    test_jwt_token,
    test_user_user_type,
    test_user_type,
    test_onboarding_step,
    mock_onboarding_enabled,
):
    """After withdrawing, the user can start a fresh onboarding for the same user type."""
    with mock_onboarding_enabled, patch(
        "src.api.onboarding.onboarding_notification_service.send_user_withdrew_notification",
        new_callable=AsyncMock,
    ):
        withdraw_resp = await client.delete(
            f"/api/v1/onboarding/submissions/{test_user_user_type.id}",
            headers={"Authorization": test_jwt_token},
        )
        assert withdraw_resp.status_code == 200

        restart_resp = await client.post(
            f"/api/v1/onboarding/start/{test_user_type.id}",
            headers={"Authorization": test_jwt_token},
        )

    assert restart_resp.status_code in [200, 201]
    data = restart_resp.json()
    assert data["user_user_type_id"] != str(test_user_user_type.id)
