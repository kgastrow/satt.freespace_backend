import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.crud.organization import (
    get_organization_details,
    update_organization_details,
)
from src.models.file import File
from src.models.organization import Organization


@pytest.mark.asyncio
async def test_get_organization_details(
    async_session: AsyncSession, test_organization: Organization
):
    """Test retrieving organization details"""
    org = await get_organization_details(
        session=async_session, org_id=str(test_organization.id)
    )

    assert org.id == test_organization.id
    assert org.name == test_organization.name
    assert org.slug == test_organization.slug


@pytest.mark.asyncio
async def test_get_organization_details_not_found(async_session: AsyncSession):
    """Test retrieving non-existent organization raises ValueError"""
    from uuid import uuid4

    with pytest.raises(ValueError, match="not found"):
        await get_organization_details(session=async_session, org_id=str(uuid4()))


@pytest.mark.asyncio
async def test_update_organization_details_all_fields(
    async_session: AsyncSession, test_organization: Organization
):
    """Test updating all organization detail fields"""
    update_data = {
        "display_name": "Test Display Name",
        "physical_address_line1": "123 Main St",
        "physical_address_line2": "Suite 100",
        "city": "Test City",
        "state_province": "Test State",
        "postal_code": "12345",
        "country": "Test Country",
        "contact_email": "contact@test.com",
        "contact_phone": "+12025551234",
    }

    org = await update_organization_details(
        session=async_session,
        org_id=str(test_organization.id),
        request=update_data,
    )

    assert org.display_name == "Test Display Name"
    assert org.physical_address_line1 == "123 Main St"
    assert org.physical_address_line2 == "Suite 100"
    assert org.city == "Test City"
    assert org.state_province == "Test State"
    assert org.postal_code == "12345"
    assert org.country == "Test Country"
    assert org.contact_email == "contact@test.com"
    assert org.contact_phone == "+12025551234"


@pytest.mark.asyncio
async def test_update_organization_details_partial(
    async_session: AsyncSession, test_organization: Organization
):
    """Test updating only some fields leaves others unchanged"""
    update_data = {
        "display_name": "Updated Display Name",
        "city": "Updated City",
    }

    org = await update_organization_details(
        session=async_session,
        org_id=str(test_organization.id),
        request=update_data,
    )

    assert org.display_name == "Updated Display Name"
    assert org.city == "Updated City"
    assert org.physical_address_line1 is None
    assert org.contact_email is None


@pytest.mark.asyncio
async def test_update_organization_details_invalid_email(
    async_session: AsyncSession, test_organization: Organization
):
    """Test that invalid email format is rejected"""
    from pydantic import ValidationError

    update_data = {
        "contact_email": "not-an-email",
    }

    with pytest.raises(ValidationError):
        await update_organization_details(
            session=async_session,
            org_id=str(test_organization.id),
            request=update_data,
        )


@pytest.mark.asyncio
async def test_update_organization_details_with_logo(
    async_session: AsyncSession, test_organization: Organization, test_user
):
    """Test updating organization with logo_file_id"""
    # Create a file in the organization
    test_file = File(
        organization_id=test_organization.id,
        uploaded_by_user_id=test_user.id,
        original_filename="logo.png",
        storage_key="test/logo.png",
        content_type="image/png",
        size_bytes=1024,
    )
    async_session.add(test_file)
    await async_session.commit()
    await async_session.refresh(test_file)

    update_data = {
        "logo_file_id": test_file.id,
    }

    org = await update_organization_details(
        session=async_session,
        org_id=str(test_organization.id),
        request=update_data,
    )

    assert org.logo_file_id == test_file.id


@pytest.mark.asyncio
async def test_update_organization_details_invalid_logo_file(
    async_session: AsyncSession, test_organization: Organization
):
    """Test that invalid logo_file_id is rejected"""
    from uuid import uuid4

    update_data = {
        "logo_file_id": uuid4(),
    }

    with pytest.raises(ValueError, match="not found or does not belong"):
        await update_organization_details(
            session=async_session,
            org_id=str(test_organization.id),
            request=update_data,
        )


@pytest.mark.asyncio
async def test_update_organization_details_logo_from_other_org(
    async_session: AsyncSession,
    test_organization: Organization,
    second_organization: Organization,
    test_user,
    second_org_user,
):
    """Test that logo_file_id from another organization is rejected"""
    # Create a file in the second organization
    other_file = File(
        organization_id=second_organization.id,
        uploaded_by_user_id=second_org_user.id,
        original_filename="other_logo.png",
        storage_key="test/other_logo.png",
        content_type="image/png",
        size_bytes=1024,
    )
    async_session.add(other_file)
    await async_session.commit()
    await async_session.refresh(other_file)

    update_data = {
        "logo_file_id": other_file.id,
    }

    with pytest.raises(ValueError, match="not found or does not belong"):
        await update_organization_details(
            session=async_session,
            org_id=str(test_organization.id),
            request=update_data,
        )


@pytest.mark.asyncio
async def test_update_organization_details_not_found(async_session: AsyncSession):
    """Test updating non-existent organization raises ValueError"""
    from uuid import uuid4

    update_data = {
        "display_name": "Test",
    }

    with pytest.raises(ValueError, match="not found"):
        await update_organization_details(
            session=async_session, org_id=str(uuid4()), request=update_data
        )


# API Endpoint Tests


@pytest.mark.asyncio
async def test_api_get_organization_details_as_owner(
    client, async_session, test_organization, owner_role, test_user, test_jwt_token
):
    """Test GET /organizations/{org_id}/details as organization owner"""
    from src.crud.user_role import assign_role

    # Assign owner role to test user
    await assign_role(
        session=async_session,
        request={
            "user_id": test_user.id,
            "role_id": owner_role.id,
        },
        assigned_by_user_id=str(test_user.id),
        organization_id=str(test_organization.id),
    )

    response = await client.get(
        f"/api/v1/organizations/{test_organization.id}/details",
        headers={"Authorization": test_jwt_token},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == str(test_organization.id)
    assert data["name"] == test_organization.name
    assert data["slug"] == test_organization.slug


@pytest.mark.asyncio
async def test_api_get_organization_details_as_admin(
    client, async_session, test_organization, admin_role, test_user, test_jwt_token
):
    """Test GET /organizations/{org_id}/details as organization admin"""
    from src.crud.user_role import assign_role

    # Assign admin role to test user
    await assign_role(
        session=async_session,
        request={
            "user_id": test_user.id,
            "role_id": admin_role.id,
        },
        assigned_by_user_id=str(test_user.id),
        organization_id=str(test_organization.id),
    )

    response = await client.get(
        f"/api/v1/organizations/{test_organization.id}/details",
        headers={"Authorization": test_jwt_token},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == str(test_organization.id)


@pytest.mark.asyncio
async def test_api_get_organization_details_as_super_admin(
    admin_client, test_organization, test_admin_token
):
    """Test GET /organizations/{org_id}/details as super admin"""
    response = await admin_client.get(
        f"/api/v1/organizations/{test_organization.id}/details",
        headers={"Authorization": test_admin_token},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == str(test_organization.id)


@pytest.mark.asyncio
async def test_api_get_organization_details_forbidden_regular_user(
    client, test_organization, test_jwt_token
):
    """Test GET /organizations/{org_id}/details forbidden for regular users without admin/owner role"""
    response = await client.get(
        f"/api/v1/organizations/{test_organization.id}/details",
        headers={"Authorization": test_jwt_token},
    )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_api_get_organization_details_forbidden_other_org(
    client, second_organization, test_jwt_token
):
    """Test GET /organizations/{org_id}/details forbidden for other organization"""
    response = await client.get(
        f"/api/v1/organizations/{second_organization.id}/details",
        headers={"Authorization": test_jwt_token},
    )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_api_patch_organization_details_as_owner(
    client, async_session, test_organization, owner_role, test_user, test_jwt_token
):
    """Test PATCH /organizations/{org_id}/details as organization owner"""
    from src.crud.user_role import assign_role

    # Assign owner role to test user
    await assign_role(
        session=async_session,
        request={
            "user_id": test_user.id,
            "role_id": owner_role.id,
        },
        assigned_by_user_id=str(test_user.id),
        organization_id=str(test_organization.id),
    )

    update_data = {
        "display_name": "API Test Org",
        "city": "API Test City",
        "contact_email": "api@test.com",
    }

    response = await client.patch(
        f"/api/v1/organizations/{test_organization.id}/details",
        headers={"Authorization": test_jwt_token},
        json=update_data,
    )

    assert response.status_code == 200
    data = response.json()
    assert data["display_name"] == "API Test Org"
    assert data["city"] == "API Test City"
    assert data["contact_email"] == "api@test.com"


@pytest.mark.asyncio
async def test_api_patch_organization_details_as_admin(
    client, async_session, test_organization, admin_role, test_user, test_jwt_token
):
    """Test PATCH /organizations/{org_id}/details as organization admin"""
    from src.crud.user_role import assign_role

    # Assign admin role to test user
    await assign_role(
        session=async_session,
        request={
            "user_id": test_user.id,
            "role_id": admin_role.id,
        },
        assigned_by_user_id=str(test_user.id),
        organization_id=str(test_organization.id),
    )

    update_data = {
        "physical_address_line1": "456 Admin St",
    }

    response = await client.patch(
        f"/api/v1/organizations/{test_organization.id}/details",
        headers={"Authorization": test_jwt_token},
        json=update_data,
    )

    assert response.status_code == 200
    data = response.json()
    assert data["physical_address_line1"] == "456 Admin St"


@pytest.mark.asyncio
async def test_api_patch_organization_details_as_super_admin(
    admin_client, test_organization, test_admin_token
):
    """Test PATCH /organizations/{org_id}/details as super admin"""
    update_data = {
        "display_name": "Super Admin Updated",
        "country": "USA",
    }

    response = await admin_client.patch(
        f"/api/v1/organizations/{test_organization.id}/details",
        headers={"Authorization": test_admin_token},
        json=update_data,
    )

    assert response.status_code == 200
    data = response.json()
    assert data["display_name"] == "Super Admin Updated"
    assert data["country"] == "USA"


@pytest.mark.asyncio
async def test_api_patch_organization_details_forbidden_regular_user(
    client, test_organization, test_jwt_token
):
    """Test PATCH /organizations/{org_id}/details forbidden for regular users"""
    update_data = {
        "display_name": "Should Fail",
    }

    response = await client.patch(
        f"/api/v1/organizations/{test_organization.id}/details",
        headers={"Authorization": test_jwt_token},
        json=update_data,
    )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_api_patch_organization_details_forbidden_other_org(
    client, second_organization, test_jwt_token
):
    """Test PATCH /organizations/{org_id}/details forbidden for other organization"""
    update_data = {
        "display_name": "Should Fail",
    }

    response = await client.patch(
        f"/api/v1/organizations/{second_organization.id}/details",
        headers={"Authorization": test_jwt_token},
        json=update_data,
    )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_api_patch_organization_details_invalid_email(
    client, async_session, test_organization, owner_role, test_user, test_jwt_token
):
    """Test PATCH /organizations/{org_id}/details rejects invalid email"""
    from src.crud.user_role import assign_role

    # Assign owner role to test user
    await assign_role(
        session=async_session,
        request={
            "user_id": test_user.id,
            "role_id": owner_role.id,
        },
        assigned_by_user_id=str(test_user.id),
        organization_id=str(test_organization.id),
    )

    update_data = {
        "contact_email": "not-an-email",
    }

    response = await client.patch(
        f"/api/v1/organizations/{test_organization.id}/details",
        headers={"Authorization": test_jwt_token},
        json=update_data,
    )

    assert response.status_code == 422  # Validation error


# Template Helper Tests


@pytest.mark.asyncio
async def test_get_organization_template_variables_all_fields(
    async_session: AsyncSession, test_organization: Organization
):
    """Test template variables generation with all fields populated"""
    from src.crud.organization import update_organization_details
    from src.services.notifications.template_renderer import (
        get_organization_template_variables,
    )

    # Populate all organization details
    await update_organization_details(
        session=async_session,
        org_id=str(test_organization.id),
        request={
            "display_name": "Acme Corporation",
            "physical_address_line1": "123 Main Street",
            "physical_address_line2": "Suite 400",
            "city": "New York",
            "state_province": "NY",
            "postal_code": "10001",
            "country": "USA",
            "contact_email": "info@acme.com",
            "contact_phone": "+1-212-555-0100",
        },
    )
    await async_session.refresh(test_organization)

    variables = get_organization_template_variables(test_organization)

    assert variables["org_name"] == test_organization.name
    assert variables["org_display_name"] == "Acme Corporation"
    assert variables["org_address_line1"] == "123 Main Street"
    assert variables["org_address_line2"] == "Suite 400"
    assert variables["org_city"] == "New York"
    assert variables["org_state_province"] == "NY"
    assert variables["org_postal_code"] == "10001"
    assert variables["org_country"] == "USA"
    assert variables["org_contact_email"] == "info@acme.com"
    assert variables["org_contact_phone"] == "+1-212-555-0100"
    assert (
        variables["org_address"]
        == "123 Main Street, Suite 400, New York, NY, 10001, USA"
    )


@pytest.mark.asyncio
async def test_get_organization_template_variables_display_name_fallback(
    test_organization: Organization,
):
    """Test that org_display_name falls back to org_name when display_name is None"""
    from src.services.notifications.template_renderer import (
        get_organization_template_variables,
    )

    variables = get_organization_template_variables(test_organization)

    assert variables["org_display_name"] == test_organization.name


@pytest.mark.asyncio
async def test_get_organization_template_variables_minimal_fields(
    test_organization: Organization,
):
    """Test template variables generation with minimal fields (only name)"""
    from src.services.notifications.template_renderer import (
        get_organization_template_variables,
    )

    variables = get_organization_template_variables(test_organization)

    assert variables["org_name"] == test_organization.name
    assert variables["org_display_name"] == test_organization.name
    assert variables["org_address"] == ""
    assert variables["org_address_line1"] == ""
    assert variables["org_address_line2"] == ""
    assert variables["org_city"] == ""
    assert variables["org_state_province"] == ""
    assert variables["org_postal_code"] == ""
    assert variables["org_country"] == ""
    assert variables["org_contact_email"] == ""
    assert variables["org_contact_phone"] == ""


@pytest.mark.asyncio
async def test_get_organization_template_variables_partial_address(
    async_session: AsyncSession, test_organization: Organization
):
    """Test formatted address with partial address fields"""
    from src.crud.organization import update_organization_details
    from src.services.notifications.template_renderer import (
        get_organization_template_variables,
    )

    # Populate partial address
    await update_organization_details(
        session=async_session,
        org_id=str(test_organization.id),
        request={
            "physical_address_line1": "456 Oak Avenue",
            "city": "San Francisco",
            "country": "USA",
        },
    )
    await async_session.refresh(test_organization)

    variables = get_organization_template_variables(test_organization)

    assert variables["org_address"] == "456 Oak Avenue, San Francisco, USA"
    assert variables["org_address_line2"] == ""
    assert variables["org_state_province"] == ""


@pytest.mark.asyncio
async def test_get_organization_template_variables_in_template_rendering(
    async_session: AsyncSession, test_organization: Organization
):
    """Test using organization template variables in actual template rendering"""
    from src.crud.organization import update_organization_details
    from src.services.notifications.template_renderer import (
        get_organization_template_variables,
        template_renderer,
    )

    # Set up organization details
    await update_organization_details(
        session=async_session,
        org_id=str(test_organization.id),
        request={
            "display_name": "Acme Corp",
            "city": "Chicago",
            "contact_email": "support@acme.com",
        },
    )
    await async_session.refresh(test_organization)

    variables = get_organization_template_variables(test_organization)

    # Test plain text template
    template = "Welcome to {org_display_name}! We're located in {org_city}. Contact us at {org_contact_email}."
    rendered = template_renderer.render(template, variables)

    assert (
        rendered
        == "Welcome to Acme Corp! We're located in Chicago. Contact us at support@acme.com."
    )

    # Test HTML template
    html_template = "<p>From {org_display_name} in {org_city}</p>"
    rendered_html = template_renderer.render_html(html_template, variables)

    assert rendered_html == "<p>From Acme Corp in Chicago</p>"


@pytest.mark.asyncio
async def test_get_organization_template_variables_city_state_formatting(
    async_session: AsyncSession, test_organization: Organization
):
    """Test city and state are joined with comma in formatted address"""
    from src.crud.organization import update_organization_details
    from src.services.notifications.template_renderer import (
        get_organization_template_variables,
    )

    # Set up city and state
    await update_organization_details(
        session=async_session,
        org_id=str(test_organization.id),
        request={
            "city": "Austin",
            "state_province": "Texas",
        },
    )
    await async_session.refresh(test_organization)

    variables = get_organization_template_variables(test_organization)

    assert variables["org_address"] == "Austin, Texas"
