"""
Pydantic model serialization micro-benchmarks.
"""

import uuid

import pytest

from src.serialisers.user import (
    UserDetailResponse,
    UserListItemResponse,
    UserResponse,
)


@pytest.fixture
def sample_user_response_data():
    """Data dict matching UserResponse fields."""
    return {
        "id": str(uuid.uuid4()),
        "email": "bench@test.com",
        "email_deliverable": True,
    }


@pytest.fixture
def sample_user_detail_data():
    """Data dict matching UserDetailResponse fields."""
    return {
        "id": str(uuid.uuid4()),
        "email": "detail@test.com",
        "email_verified": True,
        "email_deliverable": True,
        "phone": "+27737442554",
        "phone_verified": True,
        "first_name": "Bench",
        "last_name": "User",
        "is_admin": False,
        "created_time": "2025-01-01T00:00:00Z",
        "updated_time": "2025-01-02T00:00:00Z",
        "suspension_status": "active",
        "roles": [{"id": str(uuid.uuid4()), "name": "admin"}],
    }


@pytest.fixture
def sample_user_list_item_data():
    """Data dict matching UserListItemResponse fields."""
    return {
        "id": str(uuid.uuid4()),
        "email": "listitem@test.com",
        "email_verified": True,
        "email_deliverable": True,
        "phone": None,
        "phone_verified": False,
        "first_name": "List",
        "last_name": "Item",
        "is_admin": False,
        "created_time": "2025-01-01T00:00:00Z",
        "updated_time": None,
        "suspension_status": "active",
        "created_via": "email",
        "roles": [],
        "user_types": None,
        "avatar_url": None,
        "total_storage_bytes": None,
        "last_login": None,
    }


@pytest.mark.benchmark(group="serialization")
def test_user_response_serialization(benchmark, sample_user_response_data):
    """Pydantic v2 serialization of UserResponse."""
    benchmark(UserResponse.model_validate, sample_user_response_data)


@pytest.mark.benchmark(group="serialization")
def test_user_detail_response_serialization(benchmark, sample_user_detail_data):
    """Pydantic v2 serialization of UserDetailResponse."""
    benchmark(UserDetailResponse.model_validate, sample_user_detail_data)


@pytest.mark.benchmark(group="serialization")
def test_user_list_item_serialization(benchmark, sample_user_list_item_data):
    """Pydantic v2 serialization of UserListItemResponse."""
    benchmark(UserListItemResponse.model_validate, sample_user_list_item_data)


@pytest.mark.benchmark(group="serialization")
def test_user_response_json_output(benchmark, sample_user_response_data):
    """Pydantic v2 model_validate + model_dump_json round-trip."""
    obj = UserResponse.model_validate(sample_user_response_data)

    benchmark(obj.model_dump_json)


@pytest.mark.benchmark(group="serialization")
def test_batch_user_detail_serialization(benchmark, sample_user_detail_data):
    """Serialize 50 UserDetailResponse instances (simulating a page of results)."""

    def run():
        return [
            UserDetailResponse.model_validate(sample_user_detail_data)
            for _ in range(50)
        ]

    benchmark(run)
