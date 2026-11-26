"""Canonical client IP resolution.

There is exactly one correct way to answer "who sent this request" in this
codebase, and it lives here. Everything that records or keys on a client
address must call :func:`get_client_ip` (re-exported from
``src.services.audit`` for the ~30 existing call sites).

WHY THIS MODULE EXISTS
----------------------
The previous implementation lived in ``services.audit`` and took
``X-Forwarded-For[0]`` -- the LEFTMOST entry -- with no trusted-proxy check at
all. That value is not merely audit metadata in this application:

* ``src/api/auth.py`` keys the login and 2FA brute-force lockout on it. A
  client that rotates the header gets UNLIMITED password and OTP attempts
  because the failure counter never accumulates against one key, and a client
  that sends a victim's address gets THAT address locked out -- a targeted
  denial of service against a named user.
* It is written into ``refresh_tokens.ip_address`` and into audit rows, both of
  which are shown back to users as fact.

A proxy or CDN APPENDS to ``X-Forwarded-For``; it does not overwrite it. So the
leftmost entry is whatever the client put there first, and it is forgeable by
anyone, always.

THE RULE
--------
Only trust a header the edge OVERWRITES on every request. ``CF-Connecting-IP``
(Cloudflare) and ``True-Client-IP`` (Akamai, Cloudflare Enterprise) are of that
kind. ``X-Forwarded-For``, ``Forwarded`` and ``X-Forwarded`` are append-only and
can never be trusted -- naming one in ``TRUSTED_CLIENT_IP_HEADER`` is refused
below, and refused again at startup in ``main.py``.

Trusting any header at all is only sound while the edge is genuinely the only
route in. Whatever CDN or proxy a fork deploys behind, the origin must reject
connections that did not come through it (an IP allow-list, mTLS, a tunnel, or
a private network); otherwise anyone who learns the origin address can connect
directly and set the trusted header to anything they like.

WHEN NOT CONFIGURED
-------------------
``TRUSTED_CLIENT_IP_HEADER`` is empty by default and the fallback is
``request.client.host``. That is correct for local development (the peer is the
client) and for a plain reverse proxy with no CDN -- provided uvicorn's
``--forwarded-allow-ips`` names the proxy's address and NOT ``'*'``, so uvicorn
resolves ``request.client.host`` to the rightmost untrusted forwarded entry,
which the proxy appended and a client cannot forge. With ``'*'`` uvicorn's
``_TrustedHosts.always_trust`` short-circuits to the LEFTMOST forwarded entry
and the peer address becomes forgeable too -- see
``deploy/ayzer-webapp-api.service``. Behind a CDN the fallback yields the edge
address, which is wrong but not forgeable, so production behind a CDN should
set the header explicitly.
"""

from typing import Optional

from src.core.config import settings
from src.logger.logger import Logger


# Headers that a CDN or proxy APPENDS to rather than overwrites. Their leftmost
# value is whatever the client sent, so naming one as the trusted source hands
# every client the ability to forge its own address.
#
# Public because the startup guard in ``main.py`` refuses to boot a production
# box configured with one of these: this module only ignores such a header and
# falls back to the peer address, which is silent, so the two must agree on the
# list.
APPEND_ONLY_HEADERS = frozenset({"x-forwarded-for", "forwarded", "x-forwarded"})

_warned_about_header = False
_warned_about_unset = False


def _trusted_header() -> Optional[str]:
    """Return the configured trusted header, or None if unset or unusable."""
    global _warned_about_header, _warned_about_unset

    header = (getattr(settings, "TRUSTED_CLIENT_IP_HEADER", "") or "").strip()
    if not header:
        if not _warned_about_unset and not (settings.TESTING or settings.DEBUG):
            _warned_about_unset = True
            Logger.warning(
                "TRUSTED_CLIENT_IP_HEADER is not configured. Client IPs used for "
                "audit records and for the login/2FA lockout fall back to the "
                "connection peer address. Behind a CDN that resolves to the edge "
                "node, so every visitor through one PoP shares a lockout and a "
                "rate-limit bucket. Set it to the header your edge OVERWRITES "
                "(e.g. CF-Connecting-IP) and make sure the origin only accepts "
                "connections from that edge."
            )
        return None

    if header.lower() in APPEND_ONLY_HEADERS:
        if not _warned_about_header:
            _warned_about_header = True
            Logger.error(
                "TRUSTED_CLIENT_IP_HEADER is set to %r, which proxies APPEND to "
                "rather than overwrite. Its leftmost value is client-supplied and "
                "forgeable. Ignoring it and falling back to the peer address. Use "
                "the header your edge overwrites instead (e.g. CF-Connecting-IP).",
                header,
            )
        return None

    return header


def get_client_ip(request) -> Optional[str]:
    """Resolve the client IP for audit, logging, lockout and rate-limit keying.

    Reads ``TRUSTED_CLIENT_IP_HEADER`` when configured and usable, otherwise
    falls back to the connection peer as uvicorn resolved it. Returns None only
    when there is no peer at all (which happens in some test transports).
    """
    header = _trusted_header()
    if header:
        value = request.headers.get(header)
        if value:
            # Single-valued in practice; split defensively so a comma-joined
            # duplicate header cannot smuggle a second address through.
            candidate = value.split(",")[0].strip()
            if candidate:
                return candidate

    client = getattr(request, "client", None)
    if client:
        return client.host

    return None


def client_ip_key(request) -> str:
    """slowapi ``key_func``. Same resolution, but must return a str.

    Unresolvable clients share the ``"unknown"`` bucket. That is deliberate: an
    unkeyable request should be rate limited alongside its peers rather than
    escape the limiter entirely.
    """
    return get_client_ip(request) or "unknown"
