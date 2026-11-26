"""SSO provider factory for creating provider instances."""

from typing import Optional

from src.core.config import settings
from src.services.sso.base import BaseSSOProvider
from src.services.sso.google import GoogleSSOProvider


class SSOProviderFactory:
    """Factory for creating SSO provider instances."""

    @staticmethod
    def get_provider(provider_name: str) -> Optional[BaseSSOProvider]:
        """
        Get SSO provider instance by name.

        Args:
            provider_name: Name of the provider (e.g., 'google')

        Returns:
            SSO provider instance or None if provider not supported/configured

        Raises:
            ValueError: If provider name is not recognized
        """
        provider_name = provider_name.lower()

        if provider_name == "google":
            # Check if Google SSO is configured
            if not settings.GOOGLE_CLIENT_ID or not settings.GOOGLE_CLIENT_SECRET:
                return None

            return GoogleSSOProvider(
                client_id=settings.GOOGLE_CLIENT_ID,
                client_secret=settings.GOOGLE_CLIENT_SECRET,
            )

        # Future providers can be added here:
        # elif provider_name == "microsoft":
        #     return MicrosoftSSOProvider(...)
        # elif provider_name == "github":
        #     return GitHubSSOProvider(...)

        raise ValueError(f"Unknown SSO provider: {provider_name}")

    @staticmethod
    def get_supported_providers() -> list[str]:
        """
        Get list of supported provider names.

        Returns:
            List of provider names that can be used with get_provider()
        """
        return ["google"]
