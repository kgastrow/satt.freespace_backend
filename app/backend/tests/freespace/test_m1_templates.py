"""M1: pure message templates (BF-70, BF-57 fingerprint)."""

from __future__ import annotations

import pytest

from src.constants.freespace import TEMPLATED_ADVISORY_TYPES, AdvisoryType
from src.services.freespace import templates as t
from src.services.freespace.types import MessageTemplate


def _tpl(advisory_type, title, body):
    return MessageTemplate(
        advisory_type=advisory_type, title=title, body=body, locale="en"
    )


class TestDefaults:
    def test_every_type_has_a_default(self):
        assert set(t.DEFAULT_TEMPLATES) == set(TEMPLATED_ADVISORY_TYPES)

    @pytest.mark.parametrize("advisory_type", list(TEMPLATED_ADVISORY_TYPES))
    def test_defaults_are_valid_and_site_titled(self, advisory_type):
        title, body = t.DEFAULT_TEMPLATES[advisory_type]
        assert title == "{site} parking"
        t.validate_template(advisory_type, title, body)

    @pytest.mark.parametrize("advisory_type", list(TEMPLATED_ADVISORY_TYPES))
    def test_no_hard_coded_venue(self, advisory_type):
        title, body = t.DEFAULT_TEMPLATES[advisory_type]
        assert "ABSA" not in title + body
        assert "Alice Lane" not in title + body
        assert "TODO" not in title + body

    def test_reference_wording(self):
        _, initial = t.DEFAULT_TEMPLATES[AdvisoryType.SITE_INITIAL]
        assert "filling up" in initial and "{topZones}" in initial
        _, change = t.DEFAULT_TEMPLATES[AdvisoryType.SITE_CHANGE]
        assert change.startswith("Parking availability has changed. {zone}")
        _, zone = t.DEFAULT_TEMPLATES[AdvisoryType.ZONE_ADVISORY]
        assert zone == "{fullZone} is full. {zone} has available bays."
        _, recovery = t.DEFAULT_TEMPLATES[AdvisoryType.RECOVERY]
        assert "improved at {site}" in recovery


class TestValidation:
    def test_extract(self):
        assert t.extract_placeholders("{site} and {zone}, {site} {x y}") == {
            "site",
            "zone",
        }

    @pytest.mark.parametrize(
        "advisory_type,placeholder",
        [
            (AdvisoryType.SITE_INITIAL, "fullZone"),
            (AdvisoryType.SITE_CHANGE, "fullZone"),
            (AdvisoryType.RECOVERY, "fullZone"),
            (AdvisoryType.TEST, "zone"),
            (AdvisoryType.TEST, "topZones"),
            (AdvisoryType.TEST, "occupancyPct"),
            (AdvisoryType.ZONE_ADVISORY, "bogus"),
        ],
    )
    def test_unknown_placeholder_rejected_in_title_and_body(
        self, advisory_type, placeholder
    ):
        for title, body in (
            ("{" + placeholder + "}", "ok"),
            ("ok", "x {" + placeholder + "} y"),
        ):
            with pytest.raises(t.TemplateValidationError) as exc:
                t.validate_template(advisory_type, title, body)
            assert exc.value.unknown == (placeholder,)

    def test_zone_advisory_allows_full_zone(self):
        t.validate_template(
            AdvisoryType.ZONE_ADVISORY,
            "{fullZone}",
            "{site} {zone} {topZones} {occupancyPct}",
        )

    @pytest.mark.parametrize(
        "title,body",
        [("", "b"), ("  ", "b"), ("t", ""), ("t" * 256, "b"), ("t", "b" * 2001)],
    )
    def test_empty_or_too_long(self, title, body):
        with pytest.raises(t.TemplateValidationError) as exc:
            t.validate_template(AdvisoryType.SITE_CHANGE, title, body)
        assert exc.value.unknown == ()


class TestRender:
    def test_format_top_zones(self):
        assert t.format_top_zones([]) == ""
        assert t.format_top_zones(["Basement 3"]) == "Basement 3"
        assert (
            t.format_top_zones(["Basement 3", "Basement 4"])
            == "Basement 3 and Basement 4"
        )

    def test_build_context_and_render(self):
        ctx = t.build_context(
            site_name="Alice Lane",
            zone_name="Basement 4",
            top_zone_names=["Basement 3", "Basement 4"],
            occupancy_pct=91,
            full_zone_name="Basement 1",
        )
        assert ctx == {
            "site": "Alice Lane",
            "zone": "Basement 4",
            "topZones": "Basement 3 and Basement 4",
            "occupancyPct": "91",
            "fullZone": "Basement 1",
        }
        title, body = t.DEFAULT_TEMPLATES[AdvisoryType.SITE_INITIAL]
        out = t.render(_tpl(AdvisoryType.SITE_INITIAL, title, body), ctx)
        assert out.title == "Alice Lane parking"
        assert out.body.startswith(
            "Alice Lane parking is filling up. Basement 3 and Basement 4 currently"
        )

    def test_missing_values_render_empty(self):
        ctx = t.build_context(
            site_name="S", zone_name=None, top_zone_names=[], occupancy_pct=None
        )
        out = t.render(
            _tpl(
                AdvisoryType.SITE_CHANGE,
                "{site}{zone}",
                "[{occupancyPct}] {fullZone}{nope}",
            ),
            ctx,
        )
        assert out.title == "S"
        assert out.body == "[] "

    def test_values_are_not_re_expanded_or_formatted(self):
        ctx = t.build_context(
            site_name="{zone}", zone_name="Z", top_zone_names=[], occupancy_pct=1
        )
        out = t.render(
            _tpl(AdvisoryType.SITE_CHANGE, "{site}", "{site.__class__} {0}"), ctx
        )
        assert out.title == "{zone}"
        assert out.body == "{site.__class__} {0}"


class TestFingerprint:
    def test_hex_and_deterministic(self):
        a = t.fingerprint(AdvisoryType.SITE_INITIAL, "b3", ["b3", "b4"], "body")
        assert len(a) == 64 and int(a, 16) >= 0
        assert a == t.fingerprint(AdvisoryType.SITE_INITIAL, "b3", ["b3", "b4"], "body")

    def test_top_zone_set_is_order_insensitive_for_initial(self):
        assert t.fingerprint(
            AdvisoryType.SITE_INITIAL, "b3", ["b3", "b4"], "x"
        ) == t.fingerprint(AdvisoryType.SITE_INITIAL, "b3", ["b4", "b3"], "x")

    def test_top_zones_ignored_for_other_types(self):
        assert t.fingerprint(
            AdvisoryType.SITE_CHANGE, "b3", ["b3", "b4"], "x"
        ) == t.fingerprint(AdvisoryType.SITE_CHANGE, "b3", [], "x")

    @pytest.mark.parametrize(
        "args",
        [
            (AdvisoryType.SITE_INITIAL, "b3", ["b3", "b5"], "x"),
            (AdvisoryType.SITE_INITIAL, "b4", ["b3", "b4"], "x"),
            (AdvisoryType.SITE_INITIAL, "b3", ["b3", "b4"], "y"),
            (AdvisoryType.SITE_CHANGE, "b3", ["b3", "b4"], "x"),
        ],
    )
    def test_differs(self, args):
        base = t.fingerprint(AdvisoryType.SITE_INITIAL, "b3", ["b3", "b4"], "x")
        assert t.fingerprint(*args) != base
