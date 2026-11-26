"""
Unit tests for FeatureFlag and FeatureFlagOverride CRUD operations.
Tests cover flag management, organization overrides, and resolution logic.
"""

from unittest.mock import AsyncMock, patch

import pytest

from src.crud.feature_flag import (
    create_feature_flag,
    create_override,
    delete_feature_flag,
    delete_override,
    get_all_feature_flags,
    get_feature_flag_by_id,
    get_feature_flag_by_key,
    get_override,
    get_overrides_for_flag,
    get_resolved_flags_for_organization,
    update_feature_flag,
)
from src.services.feature_flag_cache import feature_flag_cache


# FeatureFlag CRUD Tests


@pytest.mark.asyncio
async def test_create_feature_flag(async_session):
    """Test creating a global feature flag."""
    flag_data = {
        "key": "test_feature",
        "name": "Test Feature",
        "description": "A test feature flag",
        "default_enabled": False,
    }

    flag = await create_feature_flag(async_session, flag_data)

    assert flag.key == "test_feature"
    assert flag.name == "Test Feature"
    assert flag.description == "A test feature flag"
    assert flag.default_enabled is False
    assert flag.deleted_time is None


@pytest.mark.asyncio
async def test_create_feature_flag_minimal(async_session):
    """Test creating a feature flag with minimal data."""
    flag_data = {"key": "minimal_feature"}

    flag = await create_feature_flag(async_session, flag_data)

    assert flag.key == "minimal_feature"
    assert flag.name == "minimal_feature"
    assert flag.description is None
    assert flag.default_enabled is False


@pytest.mark.asyncio
async def test_create_duplicate_feature_flag(async_session):
    """Test creating a duplicate feature flag raises error."""
    flag_data = {"key": "duplicate_feature", "name": "Duplicate"}

    await create_feature_flag(async_session, flag_data)

    with pytest.raises(ValueError, match="already exists"):
        await create_feature_flag(async_session, flag_data)


@pytest.mark.asyncio
async def test_get_feature_flag_by_id(async_session):
    """Test getting a feature flag by ID."""
    flag_data = {"key": "test_by_id", "name": "Test By ID"}
    created_flag = await create_feature_flag(async_session, flag_data)

    flag = await get_feature_flag_by_id(async_session, str(created_flag.id))

    assert flag.id == created_flag.id
    assert flag.key == "test_by_id"


@pytest.mark.asyncio
async def test_get_feature_flag_by_key(async_session):
    """Test getting a feature flag by key."""
    flag_data = {"key": "test_by_key", "name": "Test By Key"}
    await create_feature_flag(async_session, flag_data)

    flag = await get_feature_flag_by_key(async_session, "test_by_key")

    assert flag.key == "test_by_key"
    assert flag.name == "Test By Key"


@pytest.mark.asyncio
async def test_get_all_feature_flags(async_session):
    """Test listing all feature flags."""
    await create_feature_flag(async_session, {"key": "flag1", "name": "Flag 1"})
    await create_feature_flag(async_session, {"key": "flag2", "name": "Flag 2"})

    flags, total = await get_all_feature_flags(async_session)

    assert total >= 2
    assert any(f.key == "flag1" for f in flags)
    assert any(f.key == "flag2" for f in flags)


@pytest.mark.asyncio
async def test_get_all_feature_flags_pagination(async_session):
    """Test pagination of feature flags."""
    for i in range(5):
        await create_feature_flag(
            async_session, {"key": f"flag_page_{i}", "name": f"Flag {i}"}
        )

    flags, total = await get_all_feature_flags(async_session, limit=2, offset=0)

    assert total >= 5
    assert len(flags) == 2


@pytest.mark.asyncio
async def test_update_feature_flag(async_session):
    """Test updating a feature flag."""
    flag_data = {
        "key": "test_update",
        "name": "Original Name",
        "default_enabled": False,
    }
    flag = await create_feature_flag(async_session, flag_data)

    update_data = {
        "name": "Updated Name",
        "description": "Updated description",
        "default_enabled": True,
    }
    updated_flag = await update_feature_flag(async_session, str(flag.id), update_data)

    assert updated_flag.name == "Updated Name"
    assert updated_flag.description == "Updated description"
    assert updated_flag.default_enabled is True


@pytest.mark.asyncio
async def test_update_feature_flag_key(async_session):
    """Test updating a feature flag's key."""
    flag_data = {"key": "old_key", "name": "Test Flag"}
    flag = await create_feature_flag(async_session, flag_data)

    update_data = {"key": "new_key"}
    updated_flag = await update_feature_flag(async_session, str(flag.id), update_data)

    assert updated_flag.key == "new_key"


@pytest.mark.asyncio
async def test_update_feature_flag_duplicate_key(async_session):
    """Test updating a feature flag to a duplicate key raises error."""
    await create_feature_flag(
        async_session, {"key": "existing_key", "name": "Existing"}
    )
    flag = await create_feature_flag(
        async_session, {"key": "other_key", "name": "Other"}
    )

    with pytest.raises(ValueError, match="already exists"):
        await update_feature_flag(async_session, str(flag.id), {"key": "existing_key"})


@pytest.mark.asyncio
async def test_delete_feature_flag(async_session):
    """Test soft deleting a feature flag."""
    flag_data = {"key": "test_delete", "name": "Test Delete"}
    flag = await create_feature_flag(async_session, flag_data)

    deleted_flag = await delete_feature_flag(async_session, str(flag.id))

    assert deleted_flag.deleted_time is not None

    flag_check = await get_feature_flag_by_id(async_session, str(flag.id))
    assert flag_check is None


@pytest.mark.asyncio
async def test_get_feature_flag_by_id_not_found(async_session):
    """Test getting a non-existent feature flag by ID."""
    import uuid

    flag = await get_feature_flag_by_id(async_session, str(uuid.uuid4()))

    assert flag is None


# FeatureFlagOverride CRUD Tests


@pytest.mark.asyncio
async def test_create_override(async_session, test_organization):
    """Test creating an organization override for a feature flag."""
    flag = await create_feature_flag(
        async_session,
        {"key": "test_override", "name": "Test Override", "default_enabled": False},
    )

    override = await create_override(
        async_session, str(flag.id), str(test_organization.id), True
    )

    assert override.feature_flag_id == flag.id
    assert override.organization_id == test_organization.id
    assert override.enabled is True
    assert override.deleted_time is None


@pytest.mark.asyncio
async def test_create_override_updates_existing(async_session, test_organization):
    """Test creating an override updates existing override instead of creating duplicate."""
    flag = await create_feature_flag(
        async_session,
        {"key": "test_update_override", "name": "Test", "default_enabled": False},
    )

    override1 = await create_override(
        async_session, str(flag.id), str(test_organization.id), True
    )

    override2 = await create_override(
        async_session, str(flag.id), str(test_organization.id), False
    )

    assert override1.id == override2.id
    assert override2.enabled is False


@pytest.mark.asyncio
async def test_create_override_nonexistent_flag(async_session, test_organization):
    """Test creating override for non-existent flag raises error."""
    import uuid

    with pytest.raises(ValueError, match="not found"):
        await create_override(
            async_session, str(uuid.uuid4()), str(test_organization.id), True
        )


@pytest.mark.asyncio
async def test_get_override(async_session, test_organization):
    """Test getting an organization's override."""
    flag = await create_feature_flag(
        async_session,
        {"key": "test_get_override", "name": "Test", "default_enabled": False},
    )
    await create_override(async_session, str(flag.id), str(test_organization.id), True)

    override = await get_override(
        async_session, str(flag.id), str(test_organization.id)
    )

    assert override is not None
    assert override.enabled is True


@pytest.mark.asyncio
async def test_get_override_not_found(async_session, test_organization):
    """Test getting non-existent override returns None."""
    flag = await create_feature_flag(
        async_session,
        {"key": "test_no_override", "name": "Test", "default_enabled": False},
    )

    override = await get_override(
        async_session, str(flag.id), str(test_organization.id)
    )

    assert override is None


@pytest.mark.asyncio
async def test_delete_override(async_session, test_organization):
    """Test soft deleting an organization's override."""
    flag = await create_feature_flag(
        async_session,
        {"key": "test_delete_override", "name": "Test", "default_enabled": False},
    )
    await create_override(async_session, str(flag.id), str(test_organization.id), True)

    deleted_override = await delete_override(
        async_session, str(flag.id), str(test_organization.id)
    )

    assert deleted_override.deleted_time is not None

    override_check = await get_override(
        async_session, str(flag.id), str(test_organization.id)
    )
    assert override_check is None


@pytest.mark.asyncio
async def test_delete_override_not_found(async_session, test_organization):
    """Test deleting non-existent override raises error."""
    flag = await create_feature_flag(
        async_session,
        {"key": "test_delete_missing", "name": "Test", "default_enabled": False},
    )

    with pytest.raises(ValueError, match="not found"):
        await delete_override(async_session, str(flag.id), str(test_organization.id))


@pytest.mark.asyncio
async def test_get_overrides_for_flag(
    async_session, test_organization, second_organization
):
    """Test getting all overrides for a feature flag."""
    flag = await create_feature_flag(
        async_session,
        {"key": "test_list_overrides", "name": "Test", "default_enabled": False},
    )
    await create_override(async_session, str(flag.id), str(test_organization.id), True)
    await create_override(
        async_session, str(flag.id), str(second_organization.id), False
    )

    overrides, total = await get_overrides_for_flag(async_session, str(flag.id))

    assert total == 2
    assert len(overrides) == 2
    org_ids = {o.organization_id for o in overrides}
    assert test_organization.id in org_ids
    assert second_organization.id in org_ids


# Resolution Logic Tests


@pytest.mark.asyncio
async def test_get_resolved_flags_default(async_session, test_organization):
    """Test resolved flags returns default_enabled when no override exists."""
    await create_feature_flag(
        async_session,
        {"key": "enabled_flag", "name": "Enabled", "default_enabled": True},
    )
    await create_feature_flag(
        async_session,
        {"key": "disabled_flag", "name": "Disabled", "default_enabled": False},
    )

    resolved = await get_resolved_flags_for_organization(
        async_session, str(test_organization.id)
    )

    assert resolved["enabled_flag"] is True
    assert resolved["disabled_flag"] is False


@pytest.mark.asyncio
async def test_get_resolved_flags_with_override(async_session, test_organization):
    """Test resolved flags uses override when it exists."""
    flag = await create_feature_flag(
        async_session,
        {"key": "override_flag", "name": "Override Test", "default_enabled": False},
    )
    await create_override(async_session, str(flag.id), str(test_organization.id), True)

    resolved = await get_resolved_flags_for_organization(
        async_session, str(test_organization.id)
    )

    assert resolved["override_flag"] is True


@pytest.mark.asyncio
async def test_get_resolved_flags_isolation(
    async_session, test_organization, second_organization
):
    """Test organization isolation for resolved flags."""
    flag = await create_feature_flag(
        async_session,
        {"key": "isolated_flag", "name": "Isolated", "default_enabled": False},
    )
    await create_override(async_session, str(flag.id), str(test_organization.id), True)

    resolved_org1 = await get_resolved_flags_for_organization(
        async_session, str(test_organization.id)
    )
    resolved_org2 = await get_resolved_flags_for_organization(
        async_session, str(second_organization.id)
    )

    assert resolved_org1["isolated_flag"] is True
    assert resolved_org2["isolated_flag"] is False


@pytest.mark.asyncio
async def test_get_resolved_flags_multiple_flags(async_session, test_organization):
    """Test resolving multiple flags at once."""
    flag1 = await create_feature_flag(
        async_session, {"key": "flag_a", "name": "Flag A", "default_enabled": True}
    )
    flag2 = await create_feature_flag(
        async_session, {"key": "flag_b", "name": "Flag B", "default_enabled": False}
    )
    await create_feature_flag(
        async_session, {"key": "flag_c", "name": "Flag C", "default_enabled": True}
    )

    await create_override(
        async_session, str(flag1.id), str(test_organization.id), False
    )
    await create_override(async_session, str(flag2.id), str(test_organization.id), True)

    resolved = await get_resolved_flags_for_organization(
        async_session, str(test_organization.id)
    )

    assert resolved["flag_a"] is False
    assert resolved["flag_b"] is True
    assert resolved["flag_c"] is True


@pytest.mark.asyncio
async def test_get_resolved_flags_empty(async_session, test_organization):
    """Test resolved flags returns empty dict when no flags exist."""
    resolved = await get_resolved_flags_for_organization(
        async_session, str(test_organization.id)
    )

    assert resolved == {}


# Feature Flag Cache Tests


@pytest.mark.asyncio
async def test_cache_set_and_get(test_organization):
    """Test caching and retrieving feature flags for an organization."""
    org_id = str(test_organization.id)
    test_flags = {"flag_a": True, "flag_b": False}

    with patch(
        "src.services.feature_flag_cache.cache_service._is_available", return_value=True
    ):
        mock_redis = AsyncMock()
        mock_redis.setex = AsyncMock()
        mock_redis.get = AsyncMock(return_value='{"flag_a": true, "flag_b": false}')

        with patch("src.services.feature_flag_cache.cache_service._redis", mock_redis):
            success = await feature_flag_cache.set_org_feature_flags(org_id, test_flags)
            assert success is True

            cached_flags = await feature_flag_cache.get_org_feature_flags(org_id)
            assert cached_flags == test_flags


@pytest.mark.asyncio
async def test_cache_miss_returns_none(test_organization):
    """Test cache miss returns None."""
    org_id = str(test_organization.id)

    cached_flags = await feature_flag_cache.get_org_feature_flags(org_id)
    assert cached_flags is None


@pytest.mark.asyncio
async def test_cache_invalidation(test_organization):
    """Test cache invalidation removes cached flags."""
    org_id = str(test_organization.id)
    test_flags = {"flag_a": True, "flag_b": False}

    with patch(
        "src.services.feature_flag_cache.cache_service._is_available", return_value=True
    ):
        mock_redis = AsyncMock()
        mock_redis.setex = AsyncMock()
        mock_redis.delete = AsyncMock()
        mock_redis.get = AsyncMock(
            side_effect=['{"flag_a": true, "flag_b": false}', None]
        )

        with patch("src.services.feature_flag_cache.cache_service._redis", mock_redis):
            await feature_flag_cache.set_org_feature_flags(org_id, test_flags)

            cached_flags = await feature_flag_cache.get_org_feature_flags(org_id)
            assert cached_flags == test_flags

            success = await feature_flag_cache.invalidate_org_feature_flags(org_id)
            assert success is True

            cached_flags = await feature_flag_cache.get_org_feature_flags(org_id)
            assert cached_flags is None


@pytest.mark.asyncio
async def test_cache_ttl_60_seconds(test_organization):
    """Test cache uses 60-second TTL."""
    assert feature_flag_cache.FEATURE_FLAG_TTL == 60


@pytest.mark.asyncio
async def test_cache_isolation_between_orgs(test_organization, second_organization):
    """Test cache isolation between different organizations."""
    org1_id = str(test_organization.id)
    org2_id = str(second_organization.id)

    flags_org1 = {"flag_a": True}
    flags_org2 = {"flag_a": False}

    with patch(
        "src.services.feature_flag_cache.cache_service._is_available", return_value=True
    ):
        mock_redis = AsyncMock()
        mock_redis.setex = AsyncMock()
        mock_redis.get = AsyncMock(
            side_effect=['{"flag_a": true}', '{"flag_a": false}']
        )

        with patch("src.services.feature_flag_cache.cache_service._redis", mock_redis):
            await feature_flag_cache.set_org_feature_flags(org1_id, flags_org1)
            await feature_flag_cache.set_org_feature_flags(org2_id, flags_org2)

            cached_org1 = await feature_flag_cache.get_org_feature_flags(org1_id)
            cached_org2 = await feature_flag_cache.get_org_feature_flags(org2_id)

            assert cached_org1 == flags_org1
            assert cached_org2 == flags_org2
            assert cached_org1 != cached_org2


@pytest.mark.asyncio
async def test_cache_graceful_degradation_unavailable():
    """Test graceful degradation when Redis is unavailable."""
    with patch(
        "src.services.feature_flag_cache.cache_service._is_available",
        return_value=False,
    ):
        result = await feature_flag_cache.get_org_feature_flags("test-org-id")
        assert result is None

        result = await feature_flag_cache.set_org_feature_flags(
            "test-org-id", {"flag": True}
        )
        assert result is False

        result = await feature_flag_cache.invalidate_org_feature_flags("test-org-id")
        assert result is False


@pytest.mark.asyncio
async def test_cache_handles_redis_errors(test_organization):
    """Test cache handles Redis errors gracefully."""
    org_id = str(test_organization.id)

    with patch("src.services.feature_flag_cache.cache_service._redis") as mock_redis:
        mock_redis.get = AsyncMock(side_effect=Exception("Redis error"))

        result = await feature_flag_cache.get_org_feature_flags(org_id)
        assert result is None

    with patch("src.services.feature_flag_cache.cache_service._redis") as mock_redis:
        mock_redis.setex = AsyncMock(side_effect=Exception("Redis error"))

        result = await feature_flag_cache.set_org_feature_flags(org_id, {"flag": True})
        assert result is False

    with patch("src.services.feature_flag_cache.cache_service._redis") as mock_redis:
        mock_redis.delete = AsyncMock(side_effect=Exception("Redis error"))

        result = await feature_flag_cache.invalidate_org_feature_flags(org_id)
        assert result is False


@pytest.mark.asyncio
async def test_cache_key_pattern(test_organization):
    """Test cache key follows the pattern feature_flags:{org_id}."""
    org_id = str(test_organization.id)
    expected_key = f"feature_flags:{org_id}"

    actual_key = feature_flag_cache._get_cache_key(org_id)
    assert actual_key == expected_key


# Cache Invalidation Integration Tests


@pytest.mark.asyncio
async def test_create_override_invalidates_cache(async_session, test_organization):
    """Test creating an override invalidates the organization's cache."""
    flag = await create_feature_flag(
        async_session,
        {"key": "test_cache_invalidate", "name": "Test", "default_enabled": False},
    )

    with patch.object(
        feature_flag_cache, "invalidate_org_feature_flags"
    ) as mock_invalidate:
        mock_invalidate.return_value = True
        await create_override(
            async_session, str(flag.id), str(test_organization.id), True
        )
        mock_invalidate.assert_called_once_with(str(test_organization.id))


@pytest.mark.asyncio
async def test_delete_override_invalidates_cache(async_session, test_organization):
    """Test deleting an override invalidates the organization's cache."""
    flag = await create_feature_flag(
        async_session,
        {"key": "test_delete_cache", "name": "Test", "default_enabled": False},
    )
    await create_override(async_session, str(flag.id), str(test_organization.id), True)

    with patch.object(
        feature_flag_cache, "invalidate_org_feature_flags"
    ) as mock_invalidate:
        mock_invalidate.return_value = True
        await delete_override(async_session, str(flag.id), str(test_organization.id))
        mock_invalidate.assert_called_once_with(str(test_organization.id))


@pytest.mark.asyncio
async def test_update_flag_invalidates_all_caches(async_session):
    """Test updating a flag's default_enabled invalidates all organization caches."""
    flag = await create_feature_flag(
        async_session,
        {"key": "test_update_cache", "name": "Test", "default_enabled": False},
    )

    with patch.object(
        feature_flag_cache, "invalidate_all_feature_flags"
    ) as mock_invalidate:
        mock_invalidate.return_value = True
        await update_feature_flag(
            async_session, str(flag.id), {"default_enabled": True}
        )
        mock_invalidate.assert_called_once()


@pytest.mark.asyncio
async def test_delete_flag_invalidates_all_caches(async_session):
    """Test deleting a flag invalidates all organization caches."""
    flag = await create_feature_flag(
        async_session,
        {"key": "test_delete_flag_cache", "name": "Test", "default_enabled": False},
    )

    with patch.object(
        feature_flag_cache, "invalidate_all_feature_flags"
    ) as mock_invalidate:
        mock_invalidate.return_value = True
        await delete_feature_flag(async_session, str(flag.id))
        mock_invalidate.assert_called_once()


@pytest.mark.asyncio
async def test_invalidate_all_feature_flags():
    """Test invalidate_all_feature_flags scans and deletes all feature_flags:* keys."""
    with patch(
        "src.services.feature_flag_cache.cache_service._is_available", return_value=True
    ):
        mock_redis = AsyncMock()
        mock_redis.scan = AsyncMock(
            side_effect=[
                (100, ["feature_flags:org1", "feature_flags:org2"]),
                (0, ["feature_flags:org3"]),
            ]
        )
        mock_redis.delete = AsyncMock()

        with patch("src.services.feature_flag_cache.cache_service._redis", mock_redis):
            result = await feature_flag_cache.invalidate_all_feature_flags()
            assert result is True

            assert mock_redis.scan.call_count == 2
            assert mock_redis.delete.call_count == 2

            first_delete_call = mock_redis.delete.call_args_list[0]
            assert "feature_flags:org1" in first_delete_call[0]
            assert "feature_flags:org2" in first_delete_call[0]

            second_delete_call = mock_redis.delete.call_args_list[1]
            assert "feature_flags:org3" in second_delete_call[0]


# API Endpoint Tests


@pytest.mark.asyncio
async def test_api_create_feature_flag(client, test_admin_token):
    """Test creating a feature flag via API (super admin only)."""
    response = await client.post(
        "/api/v1/admin/feature-flags",
        headers={"Authorization": test_admin_token},
        json={
            "key": "api_test_flag",
            "name": "API Test Flag",
            "description": "Test via API",
            "default_enabled": True,
        },
    )

    assert response.status_code == 201
    data = response.json()
    assert data["flag"]["key"] == "api_test_flag"
    assert data["flag"]["name"] == "API Test Flag"
    assert data["flag"]["default_enabled"] is True
    assert "message_code" in data


@pytest.mark.asyncio
async def test_api_create_feature_flag_requires_super_admin(client, test_jwt_token):
    """Test creating a feature flag requires super admin access."""
    response = await client.post(
        "/api/v1/admin/feature-flags",
        headers={"Authorization": test_jwt_token},
        json={"key": "test", "name": "Test"},
    )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_api_list_feature_flags(client, test_admin_token, async_session):
    """Test listing feature flags via API."""
    await create_feature_flag(async_session, {"key": "list_flag_1", "name": "Flag 1"})
    await create_feature_flag(async_session, {"key": "list_flag_2", "name": "Flag 2"})

    response = await client.get(
        "/api/v1/admin/feature-flags", headers={"Authorization": test_admin_token}
    )

    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    assert "total" in data
    assert data["total"] >= 2


@pytest.mark.asyncio
async def test_api_list_feature_flags_pagination(
    client, test_admin_token, async_session
):
    """Test feature flags pagination via API."""
    for i in range(5):
        await create_feature_flag(
            async_session, {"key": f"page_flag_{i}", "name": f"Flag {i}"}
        )

    response = await client.get(
        "/api/v1/admin/feature-flags?limit=2&offset=0",
        headers={"Authorization": test_admin_token},
    )

    assert response.status_code == 200
    data = response.json()
    assert len(data["items"]) == 2
    assert data["limit"] == 2
    assert data["offset"] == 0


@pytest.mark.asyncio
async def test_api_get_feature_flag(client, test_admin_token, async_session):
    """Test getting a specific feature flag via API."""
    flag = await create_feature_flag(
        async_session, {"key": "get_flag", "name": "Get Flag"}
    )

    response = await client.get(
        f"/api/v1/admin/feature-flags/{flag.id}",
        headers={"Authorization": test_admin_token},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["key"] == "get_flag"
    assert data["name"] == "Get Flag"


@pytest.mark.asyncio
async def test_api_get_feature_flag_not_found(client, test_admin_token):
    """Test getting non-existent feature flag returns 404."""
    import uuid

    response = await client.get(
        f"/api/v1/admin/feature-flags/{uuid.uuid4()}",
        headers={"Authorization": test_admin_token},
    )

    assert response.status_code == 404


@pytest.mark.asyncio
@pytest.mark.skip(
    reason="fakeredis scan operation issues in test environment - CRUD update test covers functionality"
)
async def test_api_update_feature_flag(client, test_admin_token, async_session):
    """Test updating a feature flag via API."""
    flag = await create_feature_flag(
        async_session,
        {"key": "update_flag", "name": "Original", "default_enabled": False},
    )

    response = await client.put(
        f"/api/v1/admin/feature-flags/{flag.id}",
        headers={"Authorization": test_admin_token},
        json={"name": "Updated", "default_enabled": True},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["flag"]["name"] == "Updated"
    assert data["flag"]["default_enabled"] is True


@pytest.mark.asyncio
async def test_api_delete_feature_flag(client, test_admin_token, async_session):
    """Test deleting a feature flag via API."""
    flag = await create_feature_flag(
        async_session, {"key": "delete_flag", "name": "Delete Flag"}
    )

    response = await client.delete(
        f"/api/v1/admin/feature-flags/{flag.id}",
        headers={"Authorization": test_admin_token},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["flag_id"] == str(flag.id)

    flag_check = await get_feature_flag_by_id(async_session, str(flag.id))
    assert flag_check is None


@pytest.mark.asyncio
async def test_api_create_override(
    client, test_admin_token, async_session, test_organization
):
    """Test creating an organization override via API."""
    flag = await create_feature_flag(
        async_session,
        {"key": "override_flag", "name": "Override", "default_enabled": False},
    )

    response = await client.post(
        f"/api/v1/admin/feature-flags/{flag.id}/overrides",
        headers={"Authorization": test_admin_token},
        json={"organization_id": str(test_organization.id), "enabled": True},
    )

    assert response.status_code == 201
    data = response.json()
    assert data["override"]["enabled"] is True
    assert str(data["override"]["organization_id"]) == str(test_organization.id)


@pytest.mark.asyncio
async def test_api_delete_override(
    client, test_admin_token, async_session, test_organization
):
    """Test deleting an organization override via API."""
    flag = await create_feature_flag(
        async_session, {"key": "delete_override_flag", "name": "Test"}
    )
    await create_override(async_session, str(flag.id), str(test_organization.id), True)

    response = await client.delete(
        f"/api/v1/admin/feature-flags/{flag.id}/overrides/{test_organization.id}",
        headers={"Authorization": test_admin_token},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["flag_id"] == str(flag.id)
    assert data["organization_id"] == str(test_organization.id)


@pytest.mark.asyncio
async def test_api_list_overrides(
    client, test_admin_token, async_session, test_organization, second_organization
):
    """Test listing overrides for a flag via API."""
    flag = await create_feature_flag(
        async_session, {"key": "list_overrides_flag", "name": "Test"}
    )
    await create_override(async_session, str(flag.id), str(test_organization.id), True)
    await create_override(
        async_session, str(flag.id), str(second_organization.id), False
    )

    response = await client.get(
        f"/api/v1/admin/feature-flags/{flag.id}/overrides",
        headers={"Authorization": test_admin_token},
    )

    assert response.status_code == 200
    data = response.json()
    assert len(data["items"]) == 2
    assert data["total"] == 2


@pytest.mark.asyncio
async def test_api_get_resolved_flags(
    client, test_jwt_token, async_session, test_organization
):
    """Test getting resolved flags for current organization via API."""
    await create_feature_flag(
        async_session, {"key": "resolved_1", "name": "Flag 1", "default_enabled": True}
    )
    flag2 = await create_feature_flag(
        async_session, {"key": "resolved_2", "name": "Flag 2", "default_enabled": False}
    )
    await create_override(async_session, str(flag2.id), str(test_organization.id), True)

    response = await client.get(
        "/api/v1/feature-flags", headers={"Authorization": test_jwt_token}
    )

    assert response.status_code == 200
    data = response.json()
    assert data["flags"]["resolved_1"] is True
    assert data["flags"]["resolved_2"] is True


@pytest.mark.asyncio
async def test_api_get_resolved_flags_uses_cache(
    client, test_jwt_token, async_session, test_organization
):
    """Test resolved flags endpoint uses caching."""
    await create_feature_flag(
        async_session, {"key": "cached_flag", "name": "Cached", "default_enabled": True}
    )

    with patch.object(feature_flag_cache, "get_org_feature_flags") as mock_get:
        with patch.object(feature_flag_cache, "set_org_feature_flags") as mock_set:
            mock_get.return_value = None
            mock_set.return_value = True

            response = await client.get(
                "/api/v1/feature-flags", headers={"Authorization": test_jwt_token}
            )

            assert response.status_code == 200
            mock_get.assert_called_once()
            mock_set.assert_called_once()


@pytest.mark.asyncio
async def test_api_get_resolved_flags_isolation(
    client, async_session, test_organization, second_organization, second_org_user
):
    """Test resolved flags isolation between organizations."""
    from src.core.security import create_access_token

    flag = await create_feature_flag(
        async_session, {"key": "isolated", "name": "Isolated", "default_enabled": False}
    )
    await create_override(async_session, str(flag.id), str(test_organization.id), True)

    org2_token = create_access_token(
        user_id=str(second_org_user.id), organization_id=str(second_organization.id)
    )

    response_org2 = await client.get(
        "/api/v1/feature-flags", headers={"Authorization": f"Bearer {org2_token}"}
    )

    assert response_org2.status_code == 200
    data_org2 = response_org2.json()
    assert data_org2["flags"]["isolated"] is False


@pytest.mark.asyncio
async def test_require_feature_flag_dependency_logic(
    async_session, test_organization, test_user, test_admin_user
):
    """Test require_feature_flag dependency logic directly."""
    from src.api.deps import CurrentUser, require_feature_flag

    flag = await create_feature_flag(
        async_session, {"key": "test_access", "name": "Test", "default_enabled": False}
    )

    # Test 1: Regular user with flag enabled via override
    await create_override(async_session, str(flag.id), str(test_organization.id), True)

    regular_user = CurrentUser(
        id=str(test_user.id),
        email=test_user.email,
        organization_id=str(test_organization.id),
        is_admin=False,
        email_verified=True,
        roles=[],
        org_is_active=True,
        org_name="Test Org",
    )

    dependency = require_feature_flag("test_access")
    result = await dependency(regular_user, async_session)
    assert result == regular_user

    # Test 2: Regular user with flag disabled
    await create_feature_flag(
        async_session, {"key": "test_blocked", "name": "Test", "default_enabled": False}
    )

    dependency2 = require_feature_flag("test_blocked")

    try:
        await dependency2(regular_user, async_session)
        assert False, "Should have raised HTTPException"
    except Exception as e:
        assert e.status_code == 403

    # Test 3: Super admin bypasses flag check
    admin_user = CurrentUser(
        id=str(test_admin_user.id),
        email=test_admin_user.email,
        organization_id=str(test_organization.id),
        is_admin=True,
        email_verified=True,
        roles=[],
        org_is_active=True,
        org_name="Test Org",
    )

    result = await dependency2(admin_user, async_session)
    assert result == admin_user


@pytest.mark.asyncio
async def test_require_feature_flag_bypass_permission(
    async_session, test_organization, test_user, test_role
):
    """Test that users with feature_flags:bypass permission can access disabled flags."""
    from src.api.deps import CurrentUser, require_feature_flag
    from src.models.permission import Permission
    from src.models.role_permission import RolePermission
    from src.models.user_role import UserRole

    # Create a feature flag that is disabled by default
    await create_feature_flag(
        async_session,
        {"key": "bypass_test_flag", "name": "Bypass Test", "default_enabled": False},
    )

    # Create the feature_flags:bypass permission
    bypass_permission = Permission(
        code="feature_flags:bypass",
        name="Bypass Feature Flags",
        description="Allows bypassing feature flag restrictions",
        resource="feature_flags",
        action="bypass",
        display_order=0,
    )
    async_session.add(bypass_permission)
    await async_session.commit()
    await async_session.refresh(bypass_permission)

    # Grant bypass permission to test_role
    role_permission = RolePermission(
        role_id=test_role.id,
        permission_id=bypass_permission.id,
        granted_by=test_user.id,
    )
    async_session.add(role_permission)
    await async_session.commit()

    # Assign test_role to test_user
    user_role = UserRole(
        user_id=test_user.id,
        role_id=test_role.id,
        organization_id=test_organization.id,
    )
    async_session.add(user_role)
    await async_session.commit()

    # Create CurrentUser object for test_user (non-admin but with bypass permission)
    regular_user = CurrentUser(
        id=str(test_user.id),
        email=test_user.email,
        organization_id=str(test_organization.id),
        is_admin=False,
        email_verified=True,
        roles=[test_role.name],
        org_is_active=True,
        org_name="Test Org",
    )

    # Test: User with bypass permission can access disabled flag
    dependency = require_feature_flag("bypass_test_flag")
    result = await dependency(regular_user, async_session)
    assert result == regular_user


@pytest.mark.asyncio
async def test_require_feature_flag_without_bypass_permission(
    async_session, test_organization, test_user
):
    """Test that users without bypass permission cannot access disabled flags."""
    from src.api.deps import CurrentUser, require_feature_flag

    # Create a feature flag that is disabled by default
    await create_feature_flag(
        async_session,
        {"key": "no_bypass_flag", "name": "No Bypass", "default_enabled": False},
    )

    # Create CurrentUser object for test_user (no bypass permission, non-admin)
    regular_user = CurrentUser(
        id=str(test_user.id),
        email=test_user.email,
        organization_id=str(test_organization.id),
        is_admin=False,
        email_verified=True,
        roles=[],
        org_is_active=True,
        org_name="Test Org",
    )

    # Test: User without bypass permission gets 403 for disabled flag
    dependency = require_feature_flag("no_bypass_flag")

    try:
        await dependency(regular_user, async_session)
        assert False, "Should have raised HTTPException"
    except Exception as e:
        assert e.status_code == 403
        assert "not enabled" in str(e.detail)
