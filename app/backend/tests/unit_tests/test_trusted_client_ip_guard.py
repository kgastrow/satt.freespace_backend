"""
Tests for the startup guard on TRUSTED_CLIENT_IP_HEADER (main.py).

The guard is deliberately asymmetric: unset is a warning, an append-only header
is fatal. See _validate_trusted_client_ip_header for why.
"""

import pytest

import main
from src.core.client_ip import APPEND_ONLY_HEADERS


@pytest.fixture
def prod_settings(monkeypatch):
    """Pretend this is a production boot: guards are skipped in TESTING/DEBUG."""
    monkeypatch.setattr(main.settings, "TESTING", False, raising=False)
    monkeypatch.setattr(main.settings, "DEBUG", False, raising=False)

    def _set(header: str):
        monkeypatch.setattr(
            main.settings, "TRUSTED_CLIENT_IP_HEADER", header, raising=False
        )

    return _set


@pytest.mark.parametrize("header", sorted(APPEND_ONLY_HEADERS))
def test_append_only_header_aborts_startup(prod_settings, header):
    """Wrong on every topology: the header is ignored at runtime, so the
    operator believes they configured trust and got a silent fallback."""
    prod_settings(header)

    with pytest.raises(RuntimeError, match="APPEND"):
        main._validate_trusted_client_ip_header()


def test_append_only_check_is_case_insensitive(prod_settings):
    prod_settings("X-Forwarded-For")

    with pytest.raises(RuntimeError):
        main._validate_trusted_client_ip_header()


def test_unset_header_warns_but_boots(prod_settings, monkeypatch):
    """A template that refused to boot until a fork named a CDN header would
    just get the guard deleted."""
    prod_settings("")
    warnings = []
    monkeypatch.setattr(
        main.logger, "warning", lambda msg, *a, **k: warnings.append(msg)
    )

    main._validate_trusted_client_ip_header()

    assert len(warnings) == 1
    assert "TRUSTED_CLIENT_IP_HEADER" in warnings[0]


def test_overwrite_style_header_is_accepted_silently(prod_settings, monkeypatch):
    prod_settings("CF-Connecting-IP")
    warnings = []
    monkeypatch.setattr(
        main.logger, "warning", lambda msg, *a, **k: warnings.append(msg)
    )

    main._validate_trusted_client_ip_header()

    assert warnings == []


def test_guard_is_skipped_in_testing(monkeypatch):
    monkeypatch.setattr(main.settings, "TESTING", True, raising=False)
    monkeypatch.setattr(main.settings, "DEBUG", False, raising=False)
    monkeypatch.setattr(
        main.settings, "TRUSTED_CLIENT_IP_HEADER", "X-Forwarded-For", raising=False
    )

    main._validate_trusted_client_ip_header()


def test_guard_is_skipped_in_debug(monkeypatch):
    """On a laptop the peer really is the client."""
    monkeypatch.setattr(main.settings, "TESTING", False, raising=False)
    monkeypatch.setattr(main.settings, "DEBUG", True, raising=False)
    monkeypatch.setattr(
        main.settings, "TRUSTED_CLIENT_IP_HEADER", "X-Forwarded-For", raising=False
    )

    main._validate_trusted_client_ip_header()
