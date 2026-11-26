"""
Pure message templates: placeholders, validation, rendering, fingerprint
(BF-57, BF-70). OWNER: M1 (M6 and M8 consume it).

Placeholders use single braces: ``{site}``, ``{zone}``, ``{topZones}``,
``{occupancyPct}``, ``{fullZone}``. A template that references a placeholder
its advisory type does not provide is rejected on save (BF-70).

Implemented here: ``ALLOWED_PLACEHOLDERS``, ``PLACEHOLDER_RE``,
``TemplateValidationError``. Everything else is an M1 stub.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import hashlib
import re
from typing import Final

from src.constants.freespace import AdvisoryType
from src.services.freespace.types import MessageTemplate, RenderedMessage


PLACEHOLDER_SITE: Final = "site"  # site display name
PLACEHOLDER_ZONE: Final = "zone"  # recommended zone's name
PLACEHOLDER_TOP_ZONES: Final = "topZones"  # "Basement 3 and Basement 4"
PLACEHOLDER_OCCUPANCY_PCT: Final = "occupancyPct"  # site floor(pct), digits only
PLACEHOLDER_FULL_ZONE: Final = "fullZone"  # ZONE_ADVISORY: the full zone's name

# Matches "{name}"; "{{" / "}}" are NOT escapes in this revision.
PLACEHOLDER_RE: Final = re.compile(r"\{([A-Za-z][A-Za-z0-9_]*)\}")

ALLOWED_PLACEHOLDERS: Final[Mapping[AdvisoryType, frozenset[str]]] = {
    AdvisoryType.SITE_INITIAL: frozenset(
        {
            PLACEHOLDER_SITE,
            PLACEHOLDER_ZONE,
            PLACEHOLDER_TOP_ZONES,
            PLACEHOLDER_OCCUPANCY_PCT,
        }
    ),
    AdvisoryType.SITE_CHANGE: frozenset(
        {
            PLACEHOLDER_SITE,
            PLACEHOLDER_ZONE,
            PLACEHOLDER_TOP_ZONES,
            PLACEHOLDER_OCCUPANCY_PCT,
        }
    ),
    AdvisoryType.ZONE_ADVISORY: frozenset(
        {
            PLACEHOLDER_SITE,
            PLACEHOLDER_ZONE,
            PLACEHOLDER_TOP_ZONES,
            PLACEHOLDER_OCCUPANCY_PCT,
            PLACEHOLDER_FULL_ZONE,
        }
    ),
    AdvisoryType.RECOVERY: frozenset(
        {
            PLACEHOLDER_SITE,
            PLACEHOLDER_ZONE,
            PLACEHOLDER_TOP_ZONES,
            PLACEHOLDER_OCCUPANCY_PCT,
        }
    ),
    AdvisoryType.TEST: frozenset({PLACEHOLDER_SITE}),
}

# Default (title, body) per templated advisory type, English (BF-70; wording
# from spec §9 / proposal §6, see specs/freespace_reference_extracts.md).
# Placeholder names follow the functional description; "ABSA" / "Alice Lane"
# are never hard-coded (``{site}`` instead). The reference documents define no
# title, so every type defaults to "{site} parking". ``ZONE_ADVISORY``: the
# proposal's "{zone}" (the full zone) is ``{fullZone}`` here and its
# "{recommended zone}" is ``{zone}``. Used by
# site_bootstrap.create_site_dependents when a site is created.
DEFAULT_TITLE: Final = "{site} parking"

DEFAULT_TEMPLATES: Final[Mapping[AdvisoryType, tuple[str, str]]] = {
    AdvisoryType.SITE_INITIAL: (
        DEFAULT_TITLE,
        "{site} parking is filling up. {topZones} currently have the most "
        "available bays. Open Freespace for current availability.",
    ),
    AdvisoryType.SITE_CHANGE: (
        DEFAULT_TITLE,
        "Parking availability has changed. {zone} is now the recommended "
        "parking area. Open Freespace for the latest information.",
    ),
    AdvisoryType.ZONE_ADVISORY: (
        DEFAULT_TITLE,
        "{fullZone} is full. {zone} has available bays.",
    ),
    AdvisoryType.RECOVERY: (
        DEFAULT_TITLE,
        "Parking availability has improved at {site}. Open Freespace to "
        "check available areas.",
    ),
    AdvisoryType.TEST: (
        DEFAULT_TITLE,
        "This is a test notification from Freespace for {site}.",
    ),
}

MAX_TITLE_LENGTH: Final = 255
MAX_BODY_LENGTH: Final = 2000


class TemplateValidationError(ValueError):
    """A template uses placeholders its advisory type does not provide, or is
    otherwise invalid. ``unknown`` lists the offending placeholder names."""

    def __init__(self, message: str, unknown: Sequence[str] = ()) -> None:
        super().__init__(message)
        self.unknown = tuple(unknown)


def extract_placeholders(text: str) -> frozenset[str]:
    """Placeholder names used in ``text``."""
    return frozenset(PLACEHOLDER_RE.findall(text))


def validate_template(advisory_type: AdvisoryType, title: str, body: str) -> None:
    """BF-70. Raise ``TemplateValidationError`` when title or body uses a
    placeholder outside ``ALLOWED_PLACEHOLDERS[advisory_type]``, or when the
    title/body is empty or too long (title <= 255 chars). Returns None when
    valid."""
    if not title.strip():
        raise TemplateValidationError("Title must not be empty")
    if not body.strip():
        raise TemplateValidationError("Body must not be empty")
    if len(title) > MAX_TITLE_LENGTH:
        raise TemplateValidationError(
            f"Title must be at most {MAX_TITLE_LENGTH} characters"
        )
    if len(body) > MAX_BODY_LENGTH:
        raise TemplateValidationError(
            f"Body must be at most {MAX_BODY_LENGTH} characters"
        )
    allowed = ALLOWED_PLACEHOLDERS.get(advisory_type, frozenset())
    used = extract_placeholders(title) | extract_placeholders(body)
    unknown = sorted(used - allowed)
    if unknown:
        names = ", ".join("{" + name + "}" for name in unknown)
        raise TemplateValidationError(
            f"Placeholder(s) {names} not available for {advisory_type.value}",
            unknown,
        )


def format_top_zones(zone_names: Sequence[str]) -> str:
    """BF-70 ``{topZones}``: "" / "A" / "A and B"."""
    names = [name for name in zone_names if name]
    if not names:
        return ""
    if len(names) == 1:
        return names[0]
    return ", ".join(names[:-1]) + " and " + names[-1]


def build_context(
    *,
    site_name: str,
    zone_name: str | None,
    top_zone_names: Sequence[str],
    occupancy_pct: int | None,
    full_zone_name: str | None = None,
) -> dict[str, str]:
    """Placeholder values for ``render``. Missing values render as ""
    (occupancy None -> ""). Keys are the PLACEHOLDER_* names."""
    return {
        PLACEHOLDER_SITE: site_name,
        PLACEHOLDER_ZONE: zone_name or "",
        PLACEHOLDER_TOP_ZONES: format_top_zones(top_zone_names),
        PLACEHOLDER_OCCUPANCY_PCT: (
            "" if occupancy_pct is None else str(int(occupancy_pct))
        ),
        PLACEHOLDER_FULL_ZONE: full_zone_name or "",
    }


def _substitute(text: str, context: Mapping[str, str]) -> str:
    return PLACEHOLDER_RE.sub(lambda m: str(context.get(m.group(1), "")), text)


def render(template: MessageTemplate, context: Mapping[str, str]) -> RenderedMessage:
    """Substitute placeholders in title and body. Placeholders absent from
    ``context`` render as "" (validation already guarantees they are
    allowed). Pure string work; no format-spec / attribute access."""
    return RenderedMessage(
        title=_substitute(template.title, context),
        body=_substitute(template.body, context),
    )


def fingerprint(
    advisory_type: AdvisoryType,
    recommended_zone_slug: str | None,
    top_zones: Sequence[str],
    body: str,
) -> str:
    """BF-57 fingerprint: SHA-256 hex (64 chars) over the advisory type, the
    recommended zone slug, the top-two zone SET (order-insensitive; included
    for SITE_INITIAL only, ignored for other types) and the full rendered
    body. Deterministic across processes."""
    top = sorted(set(top_zones)) if advisory_type == AdvisoryType.SITE_INITIAL else []
    parts = [
        AdvisoryType(advisory_type).value,
        recommended_zone_slug or "",
        "\x1f".join(top),
        body,
    ]
    return hashlib.sha256("\x1e".join(parts).encode("utf-8")).hexdigest()
