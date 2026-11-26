"""
Rows that must exist for every site, and the fresh-cycle reset (D6, D13, BF-72).

* ``create_site_dependents`` - call right after inserting a ``Site`` (M1's
  create endpoint, the test fixtures, seed scripts). It creates the
  ``site_engine_state`` row (the D6 lock target must always exist) and one
  ``site_message_template`` row per ``TEMPLATED_ADVISORY_TYPES`` from
  ``templates.DEFAULT_TEMPLATES``.
* ``reset_engine_cycle`` - BF-72: switching ``managed`` off and back on starts
  a fresh cycle. M1 calls it (under the same transaction as the settings
  change) when ``managed`` goes false -> true.

Both only flush; the caller commits.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from src.constants.freespace import (
    DEFAULT_LOCALE,
    TEMPLATED_ADVISORY_TYPES,
    EngineState,
)
from src.models.site import Site
from src.models.site_engine_state import SiteEngineState
from src.models.site_message_template import SiteMessageTemplate
from src.services.freespace.loaders import (
    apply_engine_state,
    engine_state_from_row,
    load_engine_state_row,
)
from src.services.freespace.templates import DEFAULT_TEMPLATES
from src.services.freespace.types import EngineStateData, initial_engine_state


async def create_site_dependents(
    session: AsyncSession, site: Site, now: datetime
) -> tuple[SiteEngineState, list[SiteMessageTemplate]]:
    """Create the engine-state row and default templates of a new ``site``.

    ``site`` must already be added to the session (its ``id`` set). Idempotent
    for the engine-state row: an existing row is returned unchanged. Template
    rows are always created, so call this once per site.
    """
    if site.id is None:
        site.id = uuid.uuid4()
    await session.flush()

    state_row = await load_engine_state_row(session, site.id)
    if state_row is None:
        state_row = SiteEngineState(
            organization_id=site.organization_id,
            site_id=site.id,
            state=EngineState.IDLE.value,
            state_entered_at=now,
            zone_advisory_state={},
            ops_alert_state={},
        )
        apply_engine_state(state_row, initial_engine_state(now))
        session.add(state_row)

    templates: list[SiteMessageTemplate] = []
    for advisory_type in TEMPLATED_ADVISORY_TYPES:
        title, body = DEFAULT_TEMPLATES[advisory_type]
        row = SiteMessageTemplate(
            organization_id=site.organization_id,
            site_id=site.id,
            advisory_type=advisory_type.value,
            locale=DEFAULT_LOCALE,
            title=title,
            body=body,
        )
        session.add(row)
        templates.append(row)

    await session.flush()
    return state_row, templates


async def reset_engine_cycle(
    session: AsyncSession, site_id: uuid.UUID, now: datetime
) -> EngineStateData:
    """Start a fresh cycle (BF-72) under the D6 row lock.

    State -> IDLE entered at ``now``; timers, cycle id, last-notified values,
    last-sent fingerprint, in-flight guard and zone-advisory state cleared.
    The current recommendation and staleness flags are kept (they describe
    the data, not the cycle). Returns the new state. Raises ``LookupError``
    when the site has no engine-state row.
    """
    row = await load_engine_state_row(session, site_id, for_update=True)
    if row is None:
        raise LookupError(f"site {site_id} has no engine state row")
    current = engine_state_from_row(row)
    fresh = replace(
        initial_engine_state(now),
        current_zone_slug=current.current_zone_slug,
        current_zone_since=current.current_zone_since,
        stale=current.stale,
        stale_since=current.stale_since,
        last_evaluated_at=current.last_evaluated_at,
    )
    apply_engine_state(row, fresh)
    await session.flush()
    return fresh
