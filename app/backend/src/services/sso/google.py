"""Google OAuth 2.0 SSO provider implementation."""

from typing import Any
import urllib.parse

import httpx

from src.services.sso.base import BaseSSOProvider


class GoogleSSOProvider(BaseSSOProvider):
    """Google OAuth 2.0 SSO provider."""

    AUTHORIZATION_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
    TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"
    USERINFO_ENDPOINT = "https://www.googleapis.com/oauth2/v2/userinfo"

    def __init__(self, client_id: str, client_secret: str):
        """
        Initialize Google SSO provider.

        Args:
            client_id: Google OAuth client ID
            client_secret: Google OAuth client secret
        """
        self.client_id = client_id
        self.client_secret = client_secret

    async def get_authorization_url(self, state: str, redirect_uri: str) -> str:
        """
        Generate Google OAuth authorization URL.

        Args:
            state: CSRF protection state parameter
            redirect_uri: OAuth callback URL

        Returns:
            Authorization URL to redirect user to
        """
        params = {
            "client_id": self.client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": "openid email profile",
            "state": state,
            "access_type": "online",
            "prompt": "select_account",
        }

        query_string = urllib.parse.urlencode(params)
        return f"{self.AUTHORIZATION_ENDPOINT}?{query_string}"

    async def exchange_code_for_tokens(
        self, code: str, redirect_uri: str
    ) -> dict[str, Any]:
        """
        Exchange authorization code for Google OAuth tokens.

        Args:
            code: Authorization code from OAuth callback
            redirect_uri: OAuth callback URL

        Returns:
            Dictionary containing access_token, id_token, and other OAuth data

        Raises:
            httpx.HTTPStatusError: If token exchange fails
        """
        data = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "code": code,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
        }

        async with httpx.AsyncClient() as client:
            response = await client.post(self.TOKEN_ENDPOINT, data=data)
            response.raise_for_status()
            return response.json()

    async def get_user_info(self, access_token: str) -> dict[str, Any]:
        """
        Retrieve Google user profile information.

        Args:
            access_token: OAuth access token

        Returns:
            Dictionary containing user profile (email, name, picture, etc.)

        Raises:
            httpx.HTTPStatusError: If userinfo request fails
        """
        headers = {"Authorization": f"Bearer {access_token}"}

        async with httpx.AsyncClient() as client:
            response = await client.get(self.USERINFO_ENDPOINT, headers=headers)
            response.raise_for_status()
            return response.json()
