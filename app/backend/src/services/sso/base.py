"""Base SSO provider abstract class."""

from abc import ABC, abstractmethod
from typing import Any


class BaseSSOProvider(ABC):
    """Abstract base class for SSO providers."""

    @abstractmethod
    async def get_authorization_url(self, state: str, redirect_uri: str) -> str:
        """
        Generate OAuth authorization URL for the provider.

        Args:
            state: CSRF protection state parameter (should encode organization context)
            redirect_uri: OAuth callback URL

        Returns:
            Authorization URL to redirect user to
        """
        pass

    @abstractmethod
    async def exchange_code_for_tokens(
        self, code: str, redirect_uri: str
    ) -> dict[str, Any]:
        """
        Exchange authorization code for access tokens.

        Args:
            code: Authorization code from OAuth callback
            redirect_uri: OAuth callback URL (must match authorization request)

        Returns:
            Dictionary containing access_token and optionally refresh_token, id_token
        """
        pass

    @abstractmethod
    async def get_user_info(self, access_token: str) -> dict[str, Any]:
        """
        Retrieve user profile information using access token.

        Args:
            access_token: OAuth access token

        Returns:
            Dictionary containing user profile data (email, name, etc.)
        """
        pass
