"""
Tests for canonical client IP resolution (src/core/client_ip.py).

The client IP is not decoration: src/api/auth.py keys the login and 2FA
brute-force lockout on it, so a forgeable value means unlimited credential
attempts and a targeted lockout of any named user. These tests pin the two
properties that prevent that:

1. X-Forwarded-For is NEVER read unless explicitly configured, and configuring
   it is refused because proxies append to it.
2. A configured overwrite-style header is read, and only that one.
"""

import pytest

from src.core import client_ip as client_ip_module
from src.core.client_ip import APPEND_ONLY_HEADERS, client_ip_key, get_client_ip


class _FakeClient:
    def __init__(self, host: str):
        self.host = host


class _FakeRequest:
    def __init__(self, headers: dict | None = None, peer: str | None = "10.0.0.1"):
        # Header lookup is case-insensitive in Starlette; mimic that.
        self.headers = {k.lower(): v for k, v in (headers or {}).items()}
        self.client = _FakeClient(peer) if peer else None

    def __getattr__(self, name):  # pragma: no cover - defensive
        raise AttributeError(name)


class _CaseInsensitiveRequest(_FakeRequest):
    """Request whose .headers.get() lowercases the key, as Starlette does."""

    class _Headers(dict):
        def get(self, key, default=None):
            return dict.get(self, key.lower(), default)

    def __init__(self, headers: dict | None = None, peer: str | None = "10.0.0.1"):
        super().__init__(headers, peer)
        self.headers = self._Headers({k.lower(): v for k, v in (headers or {}).items()})


@pytest.fixture(autouse=True)
def _reset_warning_flags():
    """The warn-once globals must not leak between tests."""
    client_ip_module._warned_about_header = False
    client_ip_module._warned_about_unset = False
    yield
    client_ip_module._warned_about_header = False
    client_ip_module._warned_about_unset = False


@pytest.fixture
def trusted_header(monkeypatch):
    def _set(value: str):
        monkeypatch.setattr(
            client_ip_module.settings, "TRUSTED_CLIENT_IP_HEADER", value, raising=False
        )

    return _set


# ==================== The core regression ====================


def test_x_forwarded_for_is_ignored_when_unconfigured(trusted_header):
    """The whole point: a client-supplied XFF must not become the client IP."""
    trusted_header("")
    request = _CaseInsensitiveRequest(
        headers={"X-Forwarded-For": "1.2.3.4, 5.6.7.8"}, peer="10.0.0.1"
    )
    assert get_client_ip(request) == "10.0.0.1"


def test_x_real_ip_is_ignored_when_unconfigured(trusted_header):
    """X-Real-IP was also trusted blindly by the old implementation."""
    trusted_header("")
    request = _CaseInsensitiveRequest(headers={"X-Real-IP": "1.2.3.4"}, peer="10.0.0.1")
    assert get_client_ip(request) == "10.0.0.1"


@pytest.mark.parametrize("header", sorted(APPEND_ONLY_HEADERS))
def test_append_only_headers_are_refused(trusted_header, header):
    """Configuring an append-only header must not enable trusting it."""
    trusted_header(header)
    request = _CaseInsensitiveRequest(headers={header: "1.2.3.4"}, peer="10.0.0.1")
    assert get_client_ip(request) == "10.0.0.1"


def test_append_only_check_is_case_insensitive(trusted_header):
    trusted_header("X-Forwarded-For")
    request = _CaseInsensitiveRequest(
        headers={"X-Forwarded-For": "1.2.3.4"}, peer="10.0.0.1"
    )
    assert get_client_ip(request) == "10.0.0.1"


# ==================== Configured trusted header ====================


def test_configured_header_is_used(trusted_header):
    trusted_header("CF-Connecting-IP")
    request = _CaseInsensitiveRequest(
        headers={"CF-Connecting-IP": "203.0.113.7"}, peer="10.0.0.1"
    )
    assert get_client_ip(request) == "203.0.113.7"


def test_configured_header_does_not_enable_other_headers(trusted_header):
    """Only the configured header is trusted, never XFF as a bonus."""
    trusted_header("CF-Connecting-IP")
    request = _CaseInsensitiveRequest(
        headers={"X-Forwarded-For": "1.2.3.4"}, peer="10.0.0.1"
    )
    assert get_client_ip(request) == "10.0.0.1"


def test_configured_header_missing_falls_back_to_peer(trusted_header):
    trusted_header("CF-Connecting-IP")
    request = _CaseInsensitiveRequest(headers={}, peer="10.0.0.1")
    assert get_client_ip(request) == "10.0.0.1"


def test_configured_header_empty_value_falls_back_to_peer(trusted_header):
    trusted_header("CF-Connecting-IP")
    request = _CaseInsensitiveRequest(
        headers={"CF-Connecting-IP": "   "}, peer="10.0.0.1"
    )
    assert get_client_ip(request) == "10.0.0.1"


def test_duplicate_trusted_header_takes_first_value_only(trusted_header):
    """A comma-joined duplicate header must not smuggle a second address."""
    trusted_header("CF-Connecting-IP")
    request = _CaseInsensitiveRequest(
        headers={"CF-Connecting-IP": "203.0.113.7, 1.2.3.4"}, peer="10.0.0.1"
    )
    assert get_client_ip(request) == "203.0.113.7"


def test_whitespace_only_setting_is_treated_as_unset(trusted_header):
    trusted_header("   ")
    request = _CaseInsensitiveRequest(
        headers={"X-Forwarded-For": "1.2.3.4"}, peer="10.0.0.1"
    )
    assert get_client_ip(request) == "10.0.0.1"


# ==================== No peer ====================


def test_no_client_returns_none(trusted_header):
    trusted_header("")
    request = _CaseInsensitiveRequest(headers={}, peer=None)
    assert get_client_ip(request) is None


def test_client_ip_key_never_returns_none(trusted_header):
    """slowapi needs a str; an unkeyable request shares the 'unknown' bucket
    rather than escaping the limiter entirely."""
    trusted_header("")
    request = _CaseInsensitiveRequest(headers={}, peer=None)
    assert client_ip_key(request) == "unknown"


def test_client_ip_key_matches_get_client_ip(trusted_header):
    trusted_header("CF-Connecting-IP")
    request = _CaseInsensitiveRequest(
        headers={"CF-Connecting-IP": "203.0.113.7"}, peer="10.0.0.1"
    )
    assert client_ip_key(request) == get_client_ip(request) == "203.0.113.7"


# ==================== Re-export contract ====================


def test_audit_reexports_the_canonical_implementation():
    """~30 modules import get_client_ip from services.audit; they must get the
    hardened implementation, not a second copy."""
    from src.services.audit import get_client_ip as audit_get_client_ip

    assert audit_get_client_ip is get_client_ip


def test_services_package_reexport_is_canonical():
    from src.services import get_client_ip as services_get_client_ip

    assert services_get_client_ip is get_client_ip


def test_rate_limiter_keys_on_canonical_client_ip():
    """A5 is only meaningful if the limiter buckets on the S2 value."""
    from src.core.rate_limit import limiter

    assert limiter._key_func is client_ip_key
