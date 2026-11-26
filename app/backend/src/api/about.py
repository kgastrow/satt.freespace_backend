"""
About page API endpoints.

Provides public endpoint for viewing about page content and admin endpoint for managing it.
The about content is stored in system_config with keys 'about.content' and 'about.content_type'.
"""

from typing import Annotated, Literal

from fastapi import APIRouter, Depends
from fastapi.requests import Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import (
    CurrentUser,
    get_current_super_admin,
    get_current_user,
    get_session,
)
from src.core.response_codes import get_response_code
from src.crud.system_config import get_system_config_by_key, update_system_config
from src.services.audit import audit_service, get_client_ip, get_user_agent


router = APIRouter(prefix="/about", tags=["About"])


# =============================================================================
# Request/Response Models
# =============================================================================


class AboutContentResponse(BaseModel):
    """Response model for about page content."""

    content: str = Field(description="The about page content (plain text or HTML)")
    content_type: Literal["plain", "html"] = Field(
        default="html",
        description="Content type: 'plain' for plain text, 'html' for HTML",
    )


class UpdateAboutContentRequest(BaseModel):
    """Request model for updating about page content."""

    content: str = Field(description="The about page content (plain text or HTML)")
    content_type: Literal["plain", "html"] = Field(
        default="html",
        description="Content type: 'plain' for plain text, 'html' for HTML",
    )


class UpdateAboutContentResponse(BaseModel):
    """Response model for about page content update."""

    message: str
    message_code: str
    about: AboutContentResponse


# =============================================================================
# Public Endpoint
# =============================================================================


@router.get("", response_model=AboutContentResponse)
async def get_about_content(
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """
    Get the about page content.

    Requires authentication. Returns the content configured by administrators.
    """
    # Get about content from system config
    content_config = await get_system_config_by_key(session, "about.content")
    content_type_config = await get_system_config_by_key(session, "about.content_type")

    content = content_config.value if content_config else ""
    content_type = content_type_config.value if content_type_config else "html"

    # Validate content_type
    if content_type not in ("plain", "html"):
        content_type = "html"

    return AboutContentResponse(
        content=content,
        content_type=content_type,
    )


# =============================================================================
# Admin Endpoint
# =============================================================================


@router.put("", response_model=UpdateAboutContentResponse)
async def update_about_content(
    request_body: UpdateAboutContentRequest,
    http_request: Request,
    current_user: Annotated[CurrentUser, Depends(get_current_super_admin)],
    session: Annotated[AsyncSession, Depends(get_session)],
):
    """
    Update the about page content.

    Requires super admin access (is_admin=True).
    Allows setting plain text or HTML content for the about page.
    """
    # Get old values for audit
    old_content_config = await get_system_config_by_key(session, "about.content")
    old_content_type_config = await get_system_config_by_key(
        session, "about.content_type"
    )

    old_content = old_content_config.value if old_content_config else ""
    old_content_type = (
        old_content_type_config.value if old_content_type_config else "html"
    )

    # Update both config values
    await update_system_config(
        session=session,
        key="about.content",
        value=request_body.content,
        description="HTML content displayed on the About page in user settings",
        updated_by_user_id=str(current_user.id),
    )

    await update_system_config(
        session=session,
        key="about.content_type",
        value=request_body.content_type,
        description="Content type for the about page (plain or html)",
        updated_by_user_id=str(current_user.id),
    )

    # Audit log the changes
    await audit_service.log_update(
        session=session,
        organization_id=current_user.organization_id,
        resource_type="AboutContent",
        resource_id="about",
        old_values={
            "content": (
                old_content[:100] + "..." if len(old_content) > 100 else old_content
            ),
            "content_type": old_content_type,
        },
        new_values={
            "content": (
                request_body.content[:100] + "..."
                if len(request_body.content) > 100
                else request_body.content
            ),
            "content_type": request_body.content_type,
        },
        actor_id=current_user.id,
        ip_address=get_client_ip(http_request),
        user_agent=get_user_agent(http_request),
    )

    return UpdateAboutContentResponse(
        message="About page content updated successfully",
        message_code=get_response_code("common.success"),
        about=AboutContentResponse(
            content=request_body.content,
            content_type=request_body.content_type,
        ),
    )
