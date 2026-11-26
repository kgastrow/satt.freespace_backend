"""
OAuth access tokens for FCM HTTP v1 (BF-68, D10). OWNER: M7.

The Google service-account JSON lives on the VPS OUTSIDE the repository and
outside any web-served path; its path is configuration
(``freespace.fcm_credentials_path`` -> ``settings.FREESPACE_FCM_CREDENTIALS_PATH``).
Nothing in source control contains key material
(``tests/freespace/test_m7_secrets.py`` greps the repository for it).

The token is cached in-process and refreshed before it expires. Expiry is
judged by google-auth against REAL time (``Credentials.valid`` includes a
refresh skew of a few minutes), never against the Freespace clock: a mock-mode
clock offset must not make a valid OAuth token look expired or vice versa.
"""

from __future__ import annotations

import asyncio
from typing import Any, Protocol


FCM_OAUTH_SCOPE = "https://www.googleapis.com/auth/firebase.messaging"


class FcmCredentialsError(RuntimeError):
    """The service-account file is missing, unreadable, malformed, or Google
    refused to mint a token for it. Treated like an FCM 401/403 (BF-66)."""


class FcmTokenUnavailableError(RuntimeError):
    """A token refresh failed for a TRANSIENT reason (network / DNS / timeout
    talking to Google's OAuth endpoint). Nothing was sent to FCM, so the send
    is RETRYABLE; this is NOT a credential failure."""


class AccessTokenProvider(Protocol):
    """Anything that yields a bearer token for FCM. ``invalidate`` forces a
    refresh on the next call (used after a 401 from FCM)."""

    async def get_token(self) -> str: ...

    def invalidate(self) -> None: ...


class ServiceAccountTokenProvider:
    """google-auth service-account credentials with an async-safe cache.

    ``Credentials.refresh`` is synchronous (it uses ``requests``), so it runs
    in a worker thread; one ``asyncio.Lock`` makes 20 concurrent senders wait
    for a single refresh instead of starting 20.
    """

    def __init__(self, credentials_path: str) -> None:
        self.credentials_path = credentials_path
        self._credentials: Any = None
        self._lock = asyncio.Lock()

    def _load(self) -> Any:
        if not self.credentials_path:
            raise FcmCredentialsError("FCM credentials path is not configured")
        try:
            from google.oauth2 import service_account

            return service_account.Credentials.from_service_account_file(
                self.credentials_path, scopes=[FCM_OAUTH_SCOPE]
            )
        except FileNotFoundError as exc:
            raise FcmCredentialsError("FCM service-account file not found") from exc
        except (ValueError, KeyError, OSError) as exc:
            # Never include the file content in the message.
            raise FcmCredentialsError(
                f"FCM service-account file unreadable ({type(exc).__name__})"
            ) from exc

    @staticmethod
    def _refresh(credentials: Any) -> None:
        import google.auth.exceptions
        from google.auth.transport.requests import Request

        try:
            credentials.refresh(Request())
        except (
            google.auth.exceptions.TransportError,
            google.auth.exceptions.TimeoutError,
            TimeoutError,
            ConnectionError,
        ) as exc:
            # Google's token endpoint was not reached / did not answer (DNS,
            # connect, timeout): the credential itself is fine, try again later.
            raise FcmTokenUnavailableError(
                f"FCM OAuth token endpoint unreachable ({type(exc).__name__})"
            ) from exc
        except google.auth.exceptions.GoogleAuthError as exc:
            # RefreshError & co: Google refused the credential.
            raise FcmCredentialsError(
                f"FCM OAuth token refresh failed ({type(exc).__name__})"
            ) from exc

    async def get_token(self) -> str:
        credentials = self._credentials
        if credentials is not None and credentials.valid and credentials.token:
            return str(credentials.token)
        async with self._lock:
            if self._credentials is None:
                self._credentials = await asyncio.to_thread(self._load)
            credentials = self._credentials
            if not (credentials.valid and credentials.token):
                await asyncio.to_thread(self._refresh, credentials)
            return str(credentials.token)

    def invalidate(self) -> None:
        """Drop the cached credentials; the file is re-read on the next call
        (so a rotated service-account file is picked up without a restart)."""
        self._credentials = None


class StaticTokenProvider:
    """Fixed token, for tests of ``HttpFcmClient`` against a mock transport."""

    def __init__(self, token: str) -> None:
        self.token = token
        self.invalidated = 0

    async def get_token(self) -> str:
        return self.token

    def invalidate(self) -> None:
        self.invalidated += 1
