"""Validation for browser Web Push endpoint URLs.

A push endpoint is a URL the SERVER will POST to, supplied by an authenticated
client. Unvalidated, that is a server-side request forgery primitive: any user
could register ``http://127.0.0.1:6379/`` or a cloud metadata address and have
the worker make the request for them, from inside the network, repeatedly and
on a schedule they control (every notification they qualify for).

Web Push endpoints are not arbitrary URLs. They are issued by a handful of
browser push services, over HTTPS, at well-known hosts. So this is an allowlist,
not a denylist: anything that is not recognisably one of those services is
refused, which fails closed for the SSRF case and for typos alike.

Deliberately a leaf module — stdlib only — so both the request serialiser and
the dispatch path can validate with the same rule without an import cycle.
"""

from __future__ import annotations

from urllib.parse import urlsplit


#: Hosts (exact) or parent domains (leading dot = any subdomain) operated by the
#: browser push services. Endpoints are only ever issued by these.
ALLOWED_PUSH_HOSTS: tuple[str, ...] = (
    # Chrome / Chromium / Edge-on-Chromium (FCM)
    "fcm.googleapis.com",
    "android.googleapis.com",
    # Firefox
    ".push.services.mozilla.com",
    # Safari / iOS + macOS WebKit
    "web.push.apple.com",
    ".push.apple.com",
    # Legacy Edge / Windows (WNS)
    ".notify.windows.com",
    ".notify.live.net",
    ".wns.windows.com",
)

#: A real endpoint is a couple of hundred characters. The cap exists so an
#: oversized value is refused at the edge rather than stored and re-POSTed.
MAX_ENDPOINT_LENGTH = 1000

#: Per-user ceiling on live subscriptions. A person has a handful of devices; a
#: number far above that is either a bug re-registering in a loop or an attempt
#: to fan a single notification into an unbounded number of outbound requests.
MAX_ACTIVE_SUBSCRIPTIONS_PER_USER = 20


class InvalidPushEndpoint(ValueError):
    """Raised when an endpoint URL is not a usable browser push endpoint."""


def is_allowed_push_host(host: str) -> bool:
    """True when ``host`` belongs to a known browser push service."""
    host = (host or "").lower().rstrip(".")
    if not host:
        return False
    for allowed in ALLOWED_PUSH_HOSTS:
        if allowed.startswith("."):
            if host.endswith(allowed) or host == allowed[1:]:
                return True
        elif host == allowed:
            return True
    return False


def validate_push_endpoint(endpoint: str) -> str:
    """Return ``endpoint`` unchanged, or raise :class:`InvalidPushEndpoint`.

    Enforces: a length cap, an ``https`` scheme (the push protocol has no
    plaintext mode, and http would also admit every internal address), no
    embedded credentials, no explicit port (an allowlisted host on a surprising
    port is not something a browser ever issues), and an allowlisted host.
    """
    value = (endpoint or "").strip()
    if not value:
        raise InvalidPushEndpoint("Push endpoint is required")
    if len(value) > MAX_ENDPOINT_LENGTH:
        raise InvalidPushEndpoint(
            f"Push endpoint exceeds {MAX_ENDPOINT_LENGTH} characters"
        )

    try:
        parts = urlsplit(value)
    except ValueError as e:
        raise InvalidPushEndpoint("Push endpoint is not a valid URL") from e

    if parts.scheme.lower() != "https":
        raise InvalidPushEndpoint("Push endpoint must use https")
    if parts.username or parts.password:
        raise InvalidPushEndpoint("Push endpoint must not carry credentials")

    try:
        port = parts.port
    except ValueError as e:
        raise InvalidPushEndpoint("Push endpoint has an invalid port") from e
    if port is not None and port != 443:
        raise InvalidPushEndpoint("Push endpoint must use the default https port")

    if not is_allowed_push_host(parts.hostname or ""):
        raise InvalidPushEndpoint(
            "Push endpoint host is not a recognised browser push service"
        )

    return value
