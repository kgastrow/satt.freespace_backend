"""Tests for SSO service providers."""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from src.services.sso import BaseSSOProvider, GoogleSSOProvider, SSOProviderFactory


class TestBaseSSOProvider:
    """Tests for abstract BaseSSOProvider interface."""

    def test_base_provider_is_abstract(self):
        """Test that BaseSSOProvider cannot be instantiated directly."""
        with pytest.raises(TypeError):
            BaseSSOProvider()


class TestGoogleSSOProvider:
    """Tests for GoogleSSOProvider implementation."""

    @pytest.fixture
    def google_provider(self):
        """Create a GoogleSSOProvider instance for testing."""
        return GoogleSSOProvider(
            client_id="test_client_id", client_secret="test_client_secret"
        )

    async def test_get_authorization_url(self, google_provider):
        """Test Google authorization URL generation."""
        state = "test_state_parameter"
        redirect_uri = "http://localhost:8000/sso/google/callback"

        url = await google_provider.get_authorization_url(state, redirect_uri)

        # Verify URL structure
        assert url.startswith(GoogleSSOProvider.AUTHORIZATION_ENDPOINT)
        assert "client_id=test_client_id" in url
        assert f"state={state}" in url
        assert "redirect_uri=http" in url
        assert "response_type=code" in url
        assert (
            "scope=openid+email+profile" in url
            or "scope=openid%20email%20profile" in url
        )

    async def test_exchange_code_for_tokens_success(self, google_provider):
        """Test successful token exchange with Google."""
        mock_response_data = {
            "access_token": "test_access_token",
            "id_token": "test_id_token",
            "expires_in": 3600,
            "token_type": "Bearer",
        }

        # Mock httpx.AsyncClient
        with patch("src.services.sso.google.httpx.AsyncClient") as mock_client:
            mock_instance = MagicMock()
            mock_client.return_value.__aenter__.return_value = mock_instance

            mock_response = MagicMock()
            mock_response.json.return_value = mock_response_data
            mock_response.raise_for_status = MagicMock()

            mock_instance.post = AsyncMock(return_value=mock_response)

            result = await google_provider.exchange_code_for_tokens(
                code="test_auth_code",
                redirect_uri="http://localhost:8000/sso/google/callback",
            )

            assert result == mock_response_data
            assert result["access_token"] == "test_access_token"
            assert result["id_token"] == "test_id_token"

            # Verify the POST request was made correctly
            mock_instance.post.assert_called_once()
            call_args = mock_instance.post.call_args
            assert call_args[0][0] == GoogleSSOProvider.TOKEN_ENDPOINT
            assert call_args[1]["data"]["code"] == "test_auth_code"
            assert call_args[1]["data"]["client_id"] == "test_client_id"
            assert call_args[1]["data"]["client_secret"] == "test_client_secret"

    async def test_exchange_code_for_tokens_failure(self, google_provider):
        """Test token exchange failure handling."""
        with patch("src.services.sso.google.httpx.AsyncClient") as mock_client:
            mock_instance = MagicMock()
            mock_client.return_value.__aenter__.return_value = mock_instance

            # Simulate HTTP error
            mock_response = MagicMock()
            mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
                "Token exchange failed",
                request=MagicMock(),
                response=MagicMock(status_code=400),
            )

            mock_instance.post = AsyncMock(return_value=mock_response)

            with pytest.raises(httpx.HTTPStatusError):
                await google_provider.exchange_code_for_tokens(
                    code="invalid_code",
                    redirect_uri="http://localhost:8000/sso/google/callback",
                )

    async def test_get_user_info_success(self, google_provider):
        """Test successful user info retrieval from Google."""
        mock_user_data = {
            "id": "123456789",
            "email": "test@example.com",
            "verified_email": True,
            "name": "Test User",
            "given_name": "Test",
            "family_name": "User",
            "picture": "https://example.com/photo.jpg",
        }

        with patch("src.services.sso.google.httpx.AsyncClient") as mock_client:
            mock_instance = MagicMock()
            mock_client.return_value.__aenter__.return_value = mock_instance

            mock_response = MagicMock()
            mock_response.json.return_value = mock_user_data
            mock_response.raise_for_status = MagicMock()

            mock_instance.get = AsyncMock(return_value=mock_response)

            result = await google_provider.get_user_info(
                access_token="test_access_token"
            )

            assert result == mock_user_data
            assert result["email"] == "test@example.com"
            assert result["name"] == "Test User"

            # Verify the GET request was made correctly
            mock_instance.get.assert_called_once()
            call_args = mock_instance.get.call_args
            assert call_args[0][0] == GoogleSSOProvider.USERINFO_ENDPOINT
            assert (
                call_args[1]["headers"]["Authorization"] == "Bearer test_access_token"
            )

    async def test_get_user_info_failure(self, google_provider):
        """Test user info retrieval failure handling."""
        with patch("src.services.sso.google.httpx.AsyncClient") as mock_client:
            mock_instance = MagicMock()
            mock_client.return_value.__aenter__.return_value = mock_instance

            # Simulate HTTP error
            mock_response = MagicMock()
            mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
                "Userinfo request failed",
                request=MagicMock(),
                response=MagicMock(status_code=401),
            )

            mock_instance.get = AsyncMock(return_value=mock_response)

            with pytest.raises(httpx.HTTPStatusError):
                await google_provider.get_user_info(access_token="invalid_token")


class TestSSOProviderFactory:
    """Tests for SSOProviderFactory."""

    def test_get_google_provider(self):
        """Test getting Google provider instance from factory."""
        with patch("src.services.sso.factory.settings") as mock_settings:
            mock_settings.GOOGLE_CLIENT_ID = "test_client_id"
            mock_settings.GOOGLE_CLIENT_SECRET = "test_client_secret"

            provider = SSOProviderFactory.get_provider("google")

            assert provider is not None
            assert isinstance(provider, GoogleSSOProvider)
            assert provider.client_id == "test_client_id"
            assert provider.client_secret == "test_client_secret"

    def test_get_google_provider_not_configured(self):
        """Test getting Google provider when not configured returns None."""
        with patch("src.services.sso.factory.settings") as mock_settings:
            mock_settings.GOOGLE_CLIENT_ID = ""
            mock_settings.GOOGLE_CLIENT_SECRET = ""

            provider = SSOProviderFactory.get_provider("google")

            assert provider is None

    def test_get_google_provider_case_insensitive(self):
        """Test provider name lookup is case-insensitive."""
        with patch("src.services.sso.factory.settings") as mock_settings:
            mock_settings.GOOGLE_CLIENT_ID = "test_client_id"
            mock_settings.GOOGLE_CLIENT_SECRET = "test_client_secret"

            provider = SSOProviderFactory.get_provider("GOOGLE")

            assert provider is not None
            assert isinstance(provider, GoogleSSOProvider)

    def test_get_unknown_provider(self):
        """Test getting unknown provider raises ValueError."""
        with pytest.raises(ValueError, match="Unknown SSO provider: unknown"):
            SSOProviderFactory.get_provider("unknown")

    def test_get_supported_providers(self):
        """Test getting list of supported providers."""
        providers = SSOProviderFactory.get_supported_providers()

        assert isinstance(providers, list)
        assert "google" in providers
        assert len(providers) >= 1


class TestSSOStateParameter:
    """Tests for OAuth state parameter handling."""

    async def test_state_parameter_in_authorization_url(self):
        """Test that state parameter is properly included for CSRF protection."""
        provider = GoogleSSOProvider(
            client_id="test_client_id", client_secret="test_client_secret"
        )

        # State should encode organization context
        state = "org_12345_user_67890_nonce_abc123"
        redirect_uri = "http://localhost:8000/sso/google/callback"

        url = await provider.get_authorization_url(state, redirect_uri)

        # Verify state is in URL
        assert f"state={state}" in url
