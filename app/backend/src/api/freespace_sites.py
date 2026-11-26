"""
Admin: sites CRUD, site settings (config) and message templates
(BF-1, BF-70 - BF-72, BF-77, BF-78). OWNER: M1.

Mounted under ``/api/v1`` via ``v1_router``; prefix ``/admin/sites``.
Sites are addressed by row UUID (``/{site_id}``). This router has the
generic ``/{site_id}`` routes, so it is included LAST among the Freespace
admin routers (CLAUDE.md rule 13).
Permissions: ``sites:read`` / ``sites:write``.

Tenant rule (D2, Q2): super admins see every organization; everyone else only
their own. A site of another organization answers 404 ``site.not_found``.

Every config change writes an ``audit_service`` before/after entry (BF-77)
and a ``CONFIG_CHANGED`` event. The audit write commits, so it is always done
last, after the data and event writes of the same request.
"""

from __future__ import annotations

from collections.abc import Mapping
import traceback
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import CurrentUser, get_session, require_permission
from src.constants.freespace import (
    DEFAULT_LOCALE,
    DEFAULT_TIME_ZONE,
    PERM_SITES_READ,
    PERM_SITES_WRITE,
    SLUG_RE,
    TEMPLATED_ADVISORY_TYPES,
    AdvisoryType,
    ConfigChangeReason,
    EventType,
    StateChangeReason,
)
from src.core.exceptions import create_http_exception
from src.core.response_codes import get_response_code
from src.crud.freespace_sites import (
    get_scoped_site,
    list_sites,
    organization_exists,
    organization_names,
    site_slug_exists,
    soft_delete_site,
)
from src.crud.freespace_templates import list_template_rows, upsert_template
from src.logger.logger import Logger
from src.models.site import Site
from src.models.site_message_template import SiteMessageTemplate
from src.serialisers.freespace_sites import (
    CreateSiteRequest,
    CreateSiteResponse,
    DeleteSiteResponse,
    SiteConfigResponse,
    SiteListResponse,
    SiteResponse,
    UpdateSiteConfigRequest,
    UpdateSiteConfigResponse,
    UpdateSiteRequest,
    UpdateSiteResponse,
)
from src.serialisers.freespace_templates import (
    TemplateInput,
    TemplateListResponse,
    TemplateResponse,
    UpdateTemplateResponse,
    UpdateTemplatesRequest,
    UpdateTemplatesResponse,
)
from src.services.audit import audit_service, get_client_ip, get_user_agent
from src.services.freespace.clock import Clock, get_clock
from src.services.freespace.events import write_event
from src.services.freespace.loaders import load_engine_state_row
from src.services.freespace.site_bootstrap import (
    create_site_dependents,
    reset_engine_cycle,
)
from src.services.freespace.site_config import (
    SITE_CONFIG_FIELDS,
    SiteConfigError,
    validate_fcm_topic,
    validate_site_config,
    validate_time_zone,
)
from src.services.freespace.templates import (
    DEFAULT_TEMPLATES,
    TemplateValidationError,
    validate_template,
)
from src.services.freespace.types import EventDraft


router = APIRouter(prefix="/admin/sites", tags=["freespace-admin-sites"])

ReadUser = Annotated[CurrentUser, Depends(require_permission(PERM_SITES_READ))]
WriteUser = Annotated[CurrentUser, Depends(require_permission(PERM_SITES_WRITE))]
Session = Annotated[AsyncSession, Depends(get_session)]
ClockDep = Annotated[Clock, Depends(get_clock)]

SITE_DETAIL_FIELDS = ("name", "fcm_topic")


# ─────────────────────────────────────────────────────────────
# Shared helpers (also used by freespace_zones)
# ─────────────────────────────────────────────────────────────


def tenant_scope(current_user: CurrentUser) -> UUID | None:
    """None = no tenant filter (super admin)."""
    return None if current_user.is_admin else UUID(current_user.organization_id)


def site_not_found() -> HTTPException:
    return create_http_exception(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Site not found",
        detail_code="site.not_found",
    )


async def require_site(
    session: AsyncSession, site_id: UUID, current_user: CurrentUser
) -> Site:
    """Resolve a live site in the caller's tenant scope, else 404."""
    site = await get_scoped_site(session, site_id, tenant_scope(current_user))
    if site is None:
        raise site_not_found()
    return site


def internal_error(http_request: Request, name: str, exc: Exception) -> HTTPException:
    error_tb = traceback.format_exc()
    Logger.error(f"Unexpected error in {name}: {exc}\n{error_tb}")
    http_request.state.error_traceback = error_tb
    return create_http_exception(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="Internal server error",
        detail_code="common.internal_error",
    )


def unprocessable(detail: str, detail_code: str) -> HTTPException:
    return create_http_exception(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail=detail,
        detail_code=detail_code,
    )


def changed_values(
    before: Mapping[str, Any], after: Mapping[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Only the keys whose value differs, as (old, new)."""
    keys = [key for key in after if before.get(key) != after.get(key)]
    return {k: before.get(k) for k in keys}, {k: after.get(k) for k in keys}


async def record_config_change(
    session: AsyncSession,
    clock: Clock,
    http_request: Request,
    current_user: CurrentUser,
    site: Site,
    *,
    reason: ConfigChangeReason,
    resource_type: str,
    resource_id: UUID,
    before: Mapping[str, Any],
    after: Mapping[str, Any],
    zone_slug: str | None = None,
    details: Mapping[str, Any] | None = None,
    create: bool = False,
    delete: bool = False,
) -> None:
    """BF-77: a ``CONFIG_CHANGED`` event in the site timeline, then the audit
    entry (who / when / before / after). The audit write commits the session,
    so call this after every other write of the request."""
    if create or delete:
        old, new = dict(before), dict(after)
    else:
        old, new = changed_values(before, after)
    event_details: dict[str, Any] = {
        "actor_id": current_user.id,
        "before": old,
        "after": new,
    }
    if create:
        event_details["created"] = True
    if delete:
        event_details["deleted"] = True
    if details:
        event_details.update(details)
    await write_event(
        session,
        site_id=site.id,
        organization_id=site.organization_id,
        draft=EventDraft(
            type=EventType.CONFIG_CHANGED,
            occurred_at=clock.now(),
            reason=reason.value,
            zone_slug=zone_slug,
            details=event_details,
        ),
        collapse=False,
    )
    org_id = str(site.organization_id)
    ip = get_client_ip(http_request)
    agent = get_user_agent(http_request)
    if create:
        await audit_service.log_create(
            session=session,
            organization_id=org_id,
            resource_type=resource_type,
            resource_id=str(resource_id),
            actor_id=current_user.id,
            ip_address=ip,
            user_agent=agent,
            resource_data=dict(after),
        )
    elif delete:
        await audit_service.log_delete(
            session=session,
            organization_id=org_id,
            resource_type=resource_type,
            resource_id=str(resource_id),
            actor_id=current_user.id,
            ip_address=ip,
            user_agent=agent,
            resource_data=dict(before),
        )
    else:
        await audit_service.log_update(
            session=session,
            organization_id=org_id,
            resource_type=resource_type,
            resource_id=str(resource_id),
            old_values=dict(old),
            new_values=dict(new),
            actor_id=current_user.id,
            ip_address=ip,
            user_agent=agent,
        )
    await session.commit()


def _config_values(site: Site) -> dict[str, Any]:
    return {name: getattr(site, name) for name in SITE_CONFIG_FIELDS}


# ─────────────────────────────────────────────────────────────
# Sites
# ─────────────────────────────────────────────────────────────


@router.get("", response_model=SiteListResponse)
async def list_sites_endpoint(
    http_request: Request,
    current_user: ReadUser,
    session: Session,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    organization_id: UUID | None = Query(None),
):
    """List sites. Super admins see every organization (optionally filtered by
    ``organization_id``); everyone else only their own."""
    try:
        scope = tenant_scope(current_user)
        if scope is None:
            scope = organization_id
        rows, total = await list_sites(session, scope, limit=limit, offset=offset)
        names = await organization_names(session, [row.organization_id for row in rows])
        return SiteListResponse(
            items=[
                SiteResponse.from_row(row, names.get(row.organization_id))
                for row in rows
            ],
            total=total,
            limit=limit,
            offset=offset,
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise internal_error(http_request, "list_sites_endpoint", exc)


@router.post("", response_model=CreateSiteResponse, status_code=status.HTTP_201_CREATED)
async def create_site_endpoint(
    request: CreateSiteRequest,
    http_request: Request,
    current_user: WriteUser,
    session: Session,
    clock: ClockDep,
):
    """Create a site (unmanaged, unlisted, default settings, engine-state row
    and default templates). Non-super-admins create in their own organization."""
    try:
        if not SLUG_RE.match(request.slug):
            raise unprocessable(
                "slug must match [a-z0-9][a-z0-9_-]{0,63}", "site.invalid_slug"
            )
        org_id = UUID(current_user.organization_id)
        if request.organization_id is not None:
            if not current_user.is_admin and request.organization_id != org_id:
                raise create_http_exception(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Organization not found",
                    detail_code="site.organization_not_found",
                )
            if not await organization_exists(session, request.organization_id):
                raise create_http_exception(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Organization not found",
                    detail_code="site.organization_not_found",
                )
            org_id = request.organization_id
        try:
            time_zone = validate_time_zone(request.time_zone or DEFAULT_TIME_ZONE)
            topic = validate_fcm_topic(request.fcm_topic or f"freespace-{request.slug}")
        except SiteConfigError as exc:
            raise unprocessable(str(exc), exc.detail_code)
        if await site_slug_exists(session, request.slug):
            raise create_http_exception(
                status_code=status.HTTP_409_CONFLICT,
                detail="A site with this slug already exists",
                detail_code="site.slug_conflict",
            )

        now = clock.now()
        site = Site(
            organization_id=org_id,
            slug=request.slug,
            name=request.name.strip(),
            time_zone=time_zone,
            fcm_topic=topic,
            managed=False,
            listed=False,
        )
        session.add(site)
        try:
            await session.flush()
        except IntegrityError:
            await session.rollback()
            raise create_http_exception(
                status_code=status.HTTP_409_CONFLICT,
                detail="A site with this slug already exists",
                detail_code="site.slug_conflict",
            )
        await create_site_dependents(session, site, now)
        await record_config_change(
            session,
            clock,
            http_request,
            current_user,
            site,
            reason=ConfigChangeReason.SITE_SETTINGS,
            resource_type="Site",
            resource_id=site.id,
            before={},
            after={
                "slug": site.slug,
                "name": site.name,
                "time_zone": site.time_zone,
                "fcm_topic": site.fcm_topic,
            },
            create=True,
        )
        await session.refresh(site)
        return CreateSiteResponse(
            message="Site created successfully",
            message_code=get_response_code("site.created"),
            site=SiteResponse.from_row(site),
        )
    except HTTPException:
        raise
    except ValueError as exc:
        raise create_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
            detail_code="common.validation_error",
        )
    except Exception as exc:
        raise internal_error(http_request, "create_site_endpoint", exc)


@router.get("/{site_id}", response_model=SiteResponse)
async def get_site_endpoint(
    site_id: UUID, http_request: Request, current_user: ReadUser, session: Session
):
    try:
        site = await require_site(session, site_id, current_user)
        return SiteResponse.from_row(site)
    except HTTPException:
        raise
    except Exception as exc:
        raise internal_error(http_request, "get_site_endpoint", exc)


@router.put("/{site_id}", response_model=UpdateSiteResponse)
async def update_site_endpoint(
    site_id: UUID,
    request: UpdateSiteRequest,
    http_request: Request,
    current_user: WriteUser,
    session: Session,
    clock: ClockDep,
):
    """Update the site name / FCM topic. The slug (wire siteId) is immutable."""
    try:
        site = await require_site(session, site_id, current_user)
        before = {name: getattr(site, name) for name in SITE_DETAIL_FIELDS}
        after = dict(before)
        if request.name is not None:
            if not request.name.strip():
                raise unprocessable("name must not be empty", "site.invalid_settings")
            after["name"] = request.name.strip()
        if request.fcm_topic is not None:
            try:
                after["fcm_topic"] = validate_fcm_topic(request.fcm_topic)
            except SiteConfigError as exc:
                raise unprocessable(str(exc), exc.detail_code)
        if after != before:
            for name, value in after.items():
                setattr(site, name, value)
            site.updated_time = clock.now()
            await session.flush()
            await record_config_change(
                session,
                clock,
                http_request,
                current_user,
                site,
                reason=ConfigChangeReason.SITE_SETTINGS,
                resource_type="Site",
                resource_id=site.id,
                before=before,
                after=after,
            )
            await session.refresh(site)
        return UpdateSiteResponse(
            message="Site updated successfully",
            message_code=get_response_code("site.updated"),
            site=SiteResponse.from_row(site),
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise internal_error(http_request, "update_site_endpoint", exc)


@router.delete("/{site_id}", response_model=DeleteSiteResponse)
async def delete_site_endpoint(
    site_id: UUID,
    http_request: Request,
    current_user: WriteUser,
    session: Session,
    clock: ClockDep,
):
    """Soft delete the site with its zones and templates (D12). Its ingest
    keys stop working because the site is no longer live."""
    try:
        site = await require_site(session, site_id, current_user)
        before = {"slug": site.slug, "name": site.name, "managed": site.managed}
        await soft_delete_site(session, site, clock.now())
        await record_config_change(
            session,
            clock,
            http_request,
            current_user,
            site,
            reason=ConfigChangeReason.SITE_SETTINGS,
            resource_type="Site",
            resource_id=site.id,
            before=before,
            after={},
            delete=True,
        )
        return DeleteSiteResponse(
            message="Site deleted successfully",
            message_code=get_response_code("site.deleted"),
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise internal_error(http_request, "delete_site_endpoint", exc)


# ─────────────────────────────────────────────────────────────
# Config (BF-71, BF-72)
# ─────────────────────────────────────────────────────────────


@router.get("/{site_id}/config", response_model=SiteConfigResponse)
async def get_site_config_endpoint(
    site_id: UUID, http_request: Request, current_user: ReadUser, session: Session
):
    try:
        site = await require_site(session, site_id, current_user)
        return SiteConfigResponse.from_row(site)
    except HTTPException:
        raise
    except Exception as exc:
        raise internal_error(http_request, "get_site_config_endpoint", exc)


@router.put("/{site_id}/config", response_model=UpdateSiteConfigResponse)
async def update_site_config_endpoint(
    site_id: UUID,
    request: UpdateSiteConfigRequest,
    http_request: Request,
    current_user: WriteUser,
    session: Session,
    clock: ClockDep,
):
    """Change the site settings. Omitted fields keep their value; the merged
    result is validated as a whole and refused (422, never clamped) when
    invalid. Turning ``managed`` on starts a fresh engine cycle (BF-72)."""
    try:
        site = await require_site(session, site_id, current_user)
        before = _config_values(site)
        merged = dict(before)
        merged.update(request.model_dump(exclude_none=True))
        try:
            after = validate_site_config(merged)
        except SiteConfigError as exc:
            raise unprocessable(str(exc), exc.detail_code)

        if after != before:
            now = clock.now()
            for name, value in after.items():
                setattr(site, name, value)
            site.updated_time = now
            await session.flush()

            managed_changed = before["managed"] != after["managed"]
            reason = ConfigChangeReason.SITE_SETTINGS
            if managed_changed:
                reason = (
                    ConfigChangeReason.MANAGED_ON
                    if after["managed"]
                    else ConfigChangeReason.MANAGED_OFF
                )
            if managed_changed and after["managed"]:
                # BF-72: off -> on starts a fresh cycle.
                if await load_engine_state_row(session, site.id) is not None:
                    fresh = await reset_engine_cycle(session, site.id, now)
                    await write_event(
                        session,
                        site_id=site.id,
                        organization_id=site.organization_id,
                        draft=EventDraft(
                            type=EventType.STATE_CHANGE,
                            occurred_at=now,
                            reason=StateChangeReason.CYCLE_RESTARTED.value,
                            cycle_id=fresh.cycle_id,
                            details={"state": str(fresh.state)},
                        ),
                        collapse=False,
                    )
            await record_config_change(
                session,
                clock,
                http_request,
                current_user,
                site,
                reason=reason,
                resource_type="SiteConfig",
                resource_id=site.id,
                before=before,
                after=after,
            )
            await session.refresh(site)
        return UpdateSiteConfigResponse(
            message="Site settings updated successfully",
            message_code=get_response_code("site.config_updated"),
            config=SiteConfigResponse.from_row(site),
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise internal_error(http_request, "update_site_config_endpoint", exc)


# ─────────────────────────────────────────────────────────────
# Message templates (BF-70)
# ─────────────────────────────────────────────────────────────


def _parse_advisory_type(value: str, *, status_code: int) -> AdvisoryType:
    try:
        advisory_type = AdvisoryType(value)
    except ValueError:
        advisory_type = None  # type: ignore[assignment]
    if advisory_type is None or advisory_type not in TEMPLATED_ADVISORY_TYPES:
        raise create_http_exception(
            status_code=status_code,
            detail=f"Unknown advisory type: {value}",
            detail_code="site_template.unknown_type",
        )
    return advisory_type


def _check_template(advisory_type: AdvisoryType, title: str, body: str) -> None:
    try:
        validate_template(advisory_type, title, body)
    except TemplateValidationError as exc:
        raise unprocessable(
            str(exc),
            (
                "site_template.invalid_placeholder"
                if exc.unknown
                else "site_template.invalid"
            ),
        )


def _template_response(
    advisory_type: AdvisoryType, rows: Mapping[str, SiteMessageTemplate]
) -> TemplateResponse:
    row = rows.get(advisory_type.value)
    if row is None:  # a site created without dependents: show the default
        title, body = DEFAULT_TEMPLATES[advisory_type]
        row = SiteMessageTemplate(
            advisory_type=advisory_type.value,
            locale=DEFAULT_LOCALE,
            title=title,
            body=body,
        )
    return TemplateResponse.from_row(row)


async def _all_templates(session: AsyncSession, site: Site) -> list[TemplateResponse]:
    rows = await list_template_rows(session, site.id)
    return [_template_response(t, rows) for t in TEMPLATED_ADVISORY_TYPES]


async def _save_templates(
    session: AsyncSession,
    clock: Clock,
    http_request: Request,
    current_user: CurrentUser,
    site: Site,
    updates: list[tuple[AdvisoryType, str, str]],
) -> None:
    rows = await list_template_rows(session, site.id)
    before: dict[str, Any] = {}
    after: dict[str, Any] = {}
    for advisory_type, title, body in updates:
        current = _template_response(advisory_type, rows)
        before[advisory_type.value] = {"title": current.title, "body": current.body}
        after[advisory_type.value] = {"title": title, "body": body}
    changed = {key for key in after if after[key] != before[key]}
    if not changed:
        return
    for advisory_type, title, body in updates:
        if advisory_type.value in changed:
            await upsert_template(session, site, advisory_type, title, body)
    await record_config_change(
        session,
        clock,
        http_request,
        current_user,
        site,
        reason=ConfigChangeReason.TEMPLATES,
        resource_type="SiteMessageTemplate",
        resource_id=site.id,
        before=before,
        after=after,
    )


@router.get("/{site_id}/templates", response_model=TemplateListResponse)
async def list_templates_endpoint(
    site_id: UUID, http_request: Request, current_user: ReadUser, session: Session
):
    """One template per advisory type (English only in this revision)."""
    try:
        site = await require_site(session, site_id, current_user)
        return TemplateListResponse(items=await _all_templates(session, site))
    except HTTPException:
        raise
    except Exception as exc:
        raise internal_error(http_request, "list_templates_endpoint", exc)


@router.put("/{site_id}/templates", response_model=UpdateTemplatesResponse)
async def update_templates_endpoint(
    site_id: UUID,
    request: UpdateTemplatesRequest,
    http_request: Request,
    current_user: WriteUser,
    session: Session,
    clock: ClockDep,
):
    """Save templates for several advisory types, all or nothing. A template
    using a placeholder its type does not provide is refused (422)."""
    try:
        site = await require_site(session, site_id, current_user)
        updates: list[tuple[AdvisoryType, str, str]] = []
        seen: set[AdvisoryType] = set()
        for item in request.templates:
            advisory_type = _parse_advisory_type(
                item.advisory_type, status_code=status.HTTP_422_UNPROCESSABLE_ENTITY
            )
            if advisory_type in seen:
                raise unprocessable(
                    f"Duplicate advisory type: {advisory_type.value}",
                    "site_template.invalid",
                )
            seen.add(advisory_type)
            _check_template(advisory_type, item.title, item.body)
            updates.append((advisory_type, item.title, item.body))
        await _save_templates(session, clock, http_request, current_user, site, updates)
        return UpdateTemplatesResponse(
            message="Templates updated successfully",
            message_code=get_response_code("site_template.updated"),
            items=await _all_templates(session, site),
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise internal_error(http_request, "update_templates_endpoint", exc)


@router.get("/{site_id}/templates/{advisory_type}", response_model=TemplateResponse)
async def get_template_endpoint(
    site_id: UUID,
    advisory_type: str,
    http_request: Request,
    current_user: ReadUser,
    session: Session,
):
    try:
        site = await require_site(session, site_id, current_user)
        parsed = _parse_advisory_type(
            advisory_type, status_code=status.HTTP_404_NOT_FOUND
        )
        rows = await list_template_rows(session, site.id)
        return _template_response(parsed, rows)
    except HTTPException:
        raise
    except Exception as exc:
        raise internal_error(http_request, "get_template_endpoint", exc)


@router.put(
    "/{site_id}/templates/{advisory_type}", response_model=UpdateTemplateResponse
)
async def update_template_endpoint(
    site_id: UUID,
    advisory_type: str,
    request: TemplateInput,
    http_request: Request,
    current_user: WriteUser,
    session: Session,
    clock: ClockDep,
):
    """Save the template of one advisory type."""
    try:
        site = await require_site(session, site_id, current_user)
        parsed = _parse_advisory_type(
            advisory_type, status_code=status.HTTP_404_NOT_FOUND
        )
        _check_template(parsed, request.title, request.body)
        await _save_templates(
            session,
            clock,
            http_request,
            current_user,
            site,
            [(parsed, request.title, request.body)],
        )
        rows = await list_template_rows(session, site.id)
        return UpdateTemplateResponse(
            message="Template updated successfully",
            message_code=get_response_code("site_template.updated"),
            template=_template_response(parsed, rows),
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise internal_error(http_request, "update_template_endpoint", exc)


@router.post(
    "/{site_id}/templates/{advisory_type}/reset", response_model=UpdateTemplateResponse
)
async def reset_template_endpoint(
    site_id: UUID,
    advisory_type: str,
    http_request: Request,
    current_user: WriteUser,
    session: Session,
    clock: ClockDep,
):
    """Restore the default wording of one advisory type."""
    try:
        site = await require_site(session, site_id, current_user)
        parsed = _parse_advisory_type(
            advisory_type, status_code=status.HTTP_404_NOT_FOUND
        )
        title, body = DEFAULT_TEMPLATES[parsed]
        await _save_templates(
            session, clock, http_request, current_user, site, [(parsed, title, body)]
        )
        rows = await list_template_rows(session, site.id)
        return UpdateTemplateResponse(
            message="Template reset to default",
            message_code=get_response_code("site_template.reset"),
            template=_template_response(parsed, rows),
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise internal_error(http_request, "reset_template_endpoint", exc)
