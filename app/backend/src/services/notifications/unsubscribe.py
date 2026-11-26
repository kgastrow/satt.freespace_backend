"""
Unsubscribe token service for notifications.

Generates and validates JWT-based tokens for unsubscribe links in emails.
Tokens encode the user, organization, category, and channel information
needed to process an unsubscribe request.
"""

from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import jwt
from jwt.exceptions import ExpiredSignatureError, InvalidTokenError

from src.core.config import settings
from src.core.security import jwt_decode_options
from src.logger.logger import Logger as logger


class UnsubscribeService:
    """
    Generate and validate unsubscribe tokens for email links.

    Tokens are JWT-based and contain:
    - user_id: The user to unsubscribe
    - organization_id: The organization context
    - category_code: The notification category (optional, for category-specific unsubscribe)
    - channel: The notification channel
    - exp: Expiration time

    Tokens have a long expiration (default 30 days) since users may click
    unsubscribe links from old emails.
    """

    # Default token expiration: 30 days
    DEFAULT_TOKEN_EXPIRY_SECONDS = 30 * 24 * 60 * 60

    def __init__(
        self,
        secret_key: Optional[str] = None,
        algorithm: str = "HS256",
        token_expiry_seconds: Optional[int] = None,
        base_url: Optional[str] = None,
        frontend_base_url: Optional[str] = None,
        backend_base_url: Optional[str] = None,
    ):
        """
        Initialize the unsubscribe service.

        Args:
            secret_key: JWT secret key. Defaults to settings.JWT_SECRET.
            algorithm: JWT algorithm. Defaults to HS256.
            token_expiry_seconds: Token expiration in seconds. Defaults to 30 days.
            base_url: Single origin used for BOTH links. Convenience for a
                deployment (or test) that serves the SPA and the API from one
                host. Overridden per-link by the two arguments below.
            frontend_base_url: Origin serving the SPA, used for the human
                unsubscribe page. Defaults to settings.PUBLIC_URL_FRONTEND.
            backend_base_url: Origin serving /api/v1, used for the RFC 8058
                one-click POST endpoint. Defaults to settings.PUBLIC_URL_BACKEND.
        """
        self._secret_key = secret_key or settings.JWT_SECRET
        self._algorithm = algorithm
        self._token_expiry = token_expiry_seconds or self.DEFAULT_TOKEN_EXPIRY_SECONDS
        self._base_url = base_url
        self._frontend_base_url = frontend_base_url
        self._backend_base_url = backend_base_url

    @property
    def base_url(self) -> str:
        """Deprecated alias for :attr:`frontend_base_url`.

        Kept because the footer link - the origin this used to mean in practice
        - is the frontend one. New code should name the origin it wants.
        """
        return self.frontend_base_url

    @property
    def frontend_base_url(self) -> str:
        """Origin of the human-facing unsubscribe PAGE.

        The page is an SPA route (``path: 'unsubscribe'`` in
        app/frontend/src/router.tsx) that reads ``?token`` and calls the API
        itself, so it is served by the frontend origin - the same one that
        serves ``/reset-password`` and ``/register``.
        """
        if self._frontend_base_url:
            return self._frontend_base_url.rstrip("/")
        if self._base_url:
            return self._base_url.rstrip("/")
        return getattr(settings, "PUBLIC_URL_FRONTEND", "http://localhost:5173").rstrip(
            "/"
        )

    @property
    def backend_base_url(self) -> str:
        """Origin of the machine-facing one-click unsubscribe ENDPOINT.

        That is a real API route (``/api/v1/notifications/unsubscribe/one-click``)
        which a mailbox provider POSTs to directly, without a browser and
        without the SPA, so it must name the backend origin. Where the SPA and
        the API share a host the two properties simply agree.
        """
        if self._backend_base_url:
            return self._backend_base_url.rstrip("/")
        if self._base_url:
            return self._base_url.rstrip("/")
        return getattr(settings, "PUBLIC_URL_BACKEND", "http://localhost:8000").rstrip(
            "/"
        )

    def generate_token(
        self,
        user_id: str,
        organization_id: str,
        category_code: Optional[str] = None,
        channel: str = "email",
        expiry_seconds: Optional[int] = None,
    ) -> str:
        """
        Generate a signed token for an unsubscribe link.

        Args:
            user_id: User's unique identifier
            organization_id: Organization's unique identifier
            category_code: Optional notification category code.
                          If None, unsubscribe applies to all categories.
            channel: Notification channel. Defaults to 'email'.
            expiry_seconds: Custom token expiration. Defaults to 30 days.

        Returns:
            Encoded JWT token string.

        Example:
            >>> token = unsubscribe_service.generate_token(
            ...     user_id="user-uuid",
            ...     organization_id="org-uuid",
            ...     category_code="marketing"
            ... )
        """
        expiry = expiry_seconds or self._token_expiry
        exp_time = datetime.now(timezone.utc) + timedelta(seconds=expiry)

        payload = {
            "user_id": str(user_id),
            "organization_id": str(organization_id),
            "channel": channel,
            "exp": exp_time,
            "iat": datetime.now(timezone.utc),
            "type": "unsubscribe",
        }

        if category_code:
            payload["category_code"] = category_code

        token = jwt.encode(payload, self._secret_key, algorithm=self._algorithm)

        return token

    def validate_token(self, token: str) -> Optional[dict[str, Any]]:
        """
        Validate an unsubscribe token and return its payload.

        Args:
            token: JWT token string to validate

        Returns:
            Dictionary containing token payload if valid:
                - user_id: str
                - organization_id: str
                - category_code: Optional[str]
                - channel: str
            Returns None if token is invalid or expired.

        Example:
            >>> payload = unsubscribe_service.validate_token(token)
            >>> if payload:
            ...     user_id = payload["user_id"]
        """
        try:
            payload = jwt.decode(
                token,
                self._secret_key,
                algorithms=[self._algorithm],
                options=jwt_decode_options(),
            )

            # Verify this is an unsubscribe token
            if payload.get("type") != "unsubscribe":
                logger.warning("Token is not an unsubscribe token")
                return None

            # Return relevant fields
            return {
                "user_id": payload["user_id"],
                "organization_id": payload["organization_id"],
                "category_code": payload.get("category_code"),
                "channel": payload.get("channel", "email"),
            }

        except ExpiredSignatureError:
            logger.info("Unsubscribe token has expired")
            return None
        except InvalidTokenError as e:
            logger.warning(f"Invalid unsubscribe token: {e}")
            return None
        except Exception as e:
            logger.error(f"Error validating unsubscribe token: {e}")
            return None

    def get_unsubscribe_url(
        self,
        user_id: str,
        organization_id: str,
        category_code: Optional[str] = None,
        channel: str = "email",
    ) -> str:
        """
        Generate a full unsubscribe URL for email footers.

        Args:
            user_id: User's unique identifier
            organization_id: Organization's unique identifier
            category_code: Optional notification category code.
                          If None, unsubscribe applies to all categories.
            channel: Notification channel. Defaults to 'email'.

        Returns:
            Full URL string for the unsubscribe endpoint.

        Example:
            >>> url = unsubscribe_service.get_unsubscribe_url(
            ...     user_id="user-uuid",
            ...     organization_id="org-uuid",
            ...     category_code="marketing"
            ... )
            "https://example.com/unsubscribe?token=..."
        """
        token = self.generate_token(
            user_id=user_id,
            organization_id=organization_id,
            category_code=category_code,
            channel=channel,
        )

        # Points at the FRONTEND page (app/frontend/src/router.tsx registers
        # `path: "unsubscribe"`), which reads ?token and calls the API itself.
        # This used to point at "/api/notifications/unsubscribe": a path that
        # does not exist (the API is mounted under /api/v1) and that, even with
        # the prefix corrected, answers with raw JSON instead of a page. Every
        # unsubscribe link in every email was therefore dead.
        return f"{self.frontend_base_url}/unsubscribe?token={token}"

    def get_one_click_unsubscribe_url(
        self,
        user_id: str,
        organization_id: str,
        category_code: Optional[str] = None,
        channel: str = "email",
    ) -> str:
        """
        Generate a one-click unsubscribe URL for List-Unsubscribe headers.

        This URL can be used in the List-Unsubscribe-Post email header
        for RFC 8058 compliant one-click unsubscribe.

        Args:
            user_id: User's unique identifier
            organization_id: Organization's unique identifier
            category_code: Optional notification category code
            channel: Notification channel. Defaults to 'email'.

        Returns:
            Full URL string for the one-click unsubscribe POST endpoint.
        """
        token = self.generate_token(
            user_id=user_id,
            organization_id=organization_id,
            category_code=category_code,
            channel=channel,
        )

        # The API is mounted under /api/v1 (main.py includes v1_router with
        # that prefix), so this is built from the BACKEND origin - the mailbox
        # provider POSTs here machine-to-machine and never loads the SPA. The
        # token travels in the QUERY STRING because the provider owns the
        # request body (RFC 8058 posts "List-Unsubscribe=One-Click" as form
        # data).
        return (
            f"{self.backend_base_url}"
            f"/api/v1/notifications/unsubscribe/one-click?token={token}"
        )

    def get_list_unsubscribe_headers(
        self,
        user_id: str,
        organization_id: str,
        category_code: Optional[str] = None,
        channel: str = "email",
    ) -> dict[str, str]:
        """
        Generate email headers for RFC 8058 List-Unsubscribe support.

        Returns headers that can be added to outgoing emails to enable
        one-click unsubscribe in email clients that support it.

        Args:
            user_id: User's unique identifier
            organization_id: Organization's unique identifier
            category_code: Optional notification category code
            channel: Notification channel. Defaults to 'email'.

        Returns:
            Dictionary with List-Unsubscribe and List-Unsubscribe-Post headers.
            The URI advertised in List-Unsubscribe is the ONE-CLICK POST
            endpoint, not the human page, because a provider POSTing to the
            page URL would not complete an opt-out.

        Example:
            >>> headers = unsubscribe_service.get_list_unsubscribe_headers(
            ...     user_id="user-uuid",
            ...     organization_id="org-uuid"
            ... )
            >>> # Add to email:
            >>> # List-Unsubscribe: <https://...>, <mailto:...>
            >>> # List-Unsubscribe-Post: List-Unsubscribe=One-Click
        """
        # RFC 8058: when List-Unsubscribe-Post is present the HTTPS URI in
        # List-Unsubscribe MUST accept the provider's POST. This previously
        # advertised the human page URL alongside the -Post header (and threw
        # the one-click URL away without using it), so every provider POST
        # landed on a route that could not opt anyone out. Gmail and Yahoo
        # grade those failures against sending-domain reputation.
        url = self.get_one_click_unsubscribe_url(
            user_id=user_id,
            organization_id=organization_id,
            category_code=category_code,
            channel=channel,
        )

        return {
            "List-Unsubscribe": f"<{url}>",
            "List-Unsubscribe-Post": "List-Unsubscribe=One-Click",
        }


# Singleton instance
unsubscribe_service = UnsubscribeService()
