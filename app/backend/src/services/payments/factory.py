"""
Payment provider factory for creating provider instances.

Supports:
- System-wide provider instances (shared credentials)
- Organization-specific instances (org credentials or Connect accounts)

Provider classes register at module load time.
"""

from typing import TYPE_CHECKING, Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.services.payments.base import PaymentProvider, ProviderCapabilities


if TYPE_CHECKING:
    from src.models.organization_payment_settings import OrganizationPaymentSettings


class PaymentProviderFactory:
    """
    Factory for instantiating payment providers.

    Supports:
    - System-wide provider instances (shared credentials)
    - Organization-specific instances (org credentials or Connect accounts)

    Provider classes register at module load time.
    """

    _providers: dict[str, type[PaymentProvider]] = {}
    _system_instances: dict[str, PaymentProvider] = {}
    _org_instances: dict[str, dict[str, PaymentProvider]] = (
        {}
    )  # {org_id: {provider: instance}}

    @classmethod
    def register(cls, name: str, provider_class: type[PaymentProvider]) -> None:
        """Register a provider class."""
        cls._providers[name] = provider_class

    @classmethod
    def get_provider(
        cls,
        name: Optional[str] = None,
        organization_settings: Optional["OrganizationPaymentSettings"] = None,
    ) -> PaymentProvider:
        """
        Get a provider instance.

        Args:
            name: Provider name (uses system default if None)
            organization_settings: Org settings for credential resolution

        Returns:
            Configured PaymentProvider instance

        Raises:
            ValueError: If provider not registered
        """
        if name is None:
            if organization_settings and organization_settings.default_provider:
                name = organization_settings.default_provider
            else:
                name = settings.payments.default_provider

        if name not in cls._providers:
            available = ", ".join(cls._providers.keys()) or "none"
            raise ValueError(
                f"Unknown payment provider: {name}. "
                f"Available providers: {available}"
            )

        # If org settings provided, check for org-specific credentials
        if organization_settings:
            return cls._get_org_provider(name, organization_settings)

        # Fall back to system instance
        return cls._get_system_provider(name)

    @classmethod
    def _get_system_provider(cls, name: str) -> PaymentProvider:
        """Get system-wide provider instance with global credentials."""
        if name not in cls._system_instances:
            cls._system_instances[name] = cls._providers[name]()
        return cls._system_instances[name]

    @classmethod
    def _get_org_provider(
        cls,
        name: str,
        org_settings: "OrganizationPaymentSettings",
    ) -> PaymentProvider:
        """
        Get org-specific provider instance.

        Uses org credentials if available, otherwise falls back to system.
        """
        org_id = str(org_settings.organization_id)

        # Check if org has custom credentials for this provider
        has_custom_credentials = cls._has_org_credentials(name, org_settings)

        if not has_custom_credentials:
            # Use system instance
            return cls._get_system_provider(name)

        # Create/cache org-specific instance
        if org_id not in cls._org_instances:
            cls._org_instances[org_id] = {}

        if name not in cls._org_instances[org_id]:
            credentials = cls._extract_org_credentials(name, org_settings)
            cls._org_instances[org_id][name] = cls._providers[name](**credentials)

        return cls._org_instances[org_id][name]

    @classmethod
    def _has_org_credentials(
        cls,
        provider: str,
        org_settings: "OrganizationPaymentSettings",
    ) -> bool:
        """Check if org has custom credentials for a provider."""
        if provider == "stripe":
            return bool(
                org_settings.stripe_secret_key or org_settings.stripe_connect_account_id
            )
        elif provider == "payfast":
            return bool(org_settings.payfast_merchant_id)
        elif provider == "paypal":
            return bool(org_settings.paypal_client_id)
        return False

    @classmethod
    def _extract_org_credentials(
        cls,
        provider: str,
        org_settings: "OrganizationPaymentSettings",
    ) -> dict:
        """Extract credentials from org settings, falling back to system config."""
        if provider == "stripe":
            return {
                "secret_key": org_settings.stripe_secret_key
                or settings.payments.stripe.secret_key,
                "publishable_key": org_settings.stripe_publishable_key
                or settings.payments.stripe.publishable_key,
                "webhook_secret": org_settings.stripe_webhook_secret
                or settings.payments.stripe.webhook_secret,
                "connect_account_id": org_settings.stripe_connect_account_id,
            }
        elif provider == "payfast":
            return {
                "merchant_id": org_settings.payfast_merchant_id
                or settings.payments.payfast.merchant_id,
                "merchant_key": org_settings.payfast_merchant_key
                or settings.payments.payfast.merchant_key,
                "passphrase": org_settings.payfast_passphrase
                or settings.payments.payfast.passphrase,
                "sandbox": org_settings.payfast_sandbox,
            }
        elif provider == "paypal":
            return {
                "client_id": org_settings.paypal_client_id
                or settings.payments.paypal.client_id,
                "client_secret": org_settings.paypal_client_secret
                or settings.payments.paypal.client_secret,
                "sandbox": org_settings.paypal_sandbox,
            }
        return {}

    @classmethod
    async def get_provider_for_org(
        cls,
        session: AsyncSession,
        organization_id: UUID,
        provider_name: Optional[str] = None,
    ) -> PaymentProvider:
        """
        Get provider instance for an organization (async helper).

        Validates provider is enabled before returning.

        Args:
            session: Database session
            organization_id: Organization UUID
            provider_name: Specific provider (uses org default if None)

        Returns:
            Configured PaymentProvider instance

        Raises:
            ValueError: If provider not enabled for org
        """
        from src.crud.organization_payment_settings import (
            get_payment_settings,
            is_provider_enabled,
        )

        org_settings = await get_payment_settings(session, str(organization_id))

        if not org_settings or not org_settings.payments_allowed:
            raise ValueError("Payments not enabled for this organization")

        # Determine provider name
        _name = (
            provider_name
            or org_settings.default_provider
            or settings.payments.default_provider
        )
        name: str = str(_name) if _name else "stripe"

        # Verify provider is enabled
        if not await is_provider_enabled(session, str(organization_id), name):
            raise ValueError(f"Provider '{name}' not enabled for this organization")

        return cls.get_provider(name, org_settings)

    @classmethod
    def list_providers(cls) -> list[str]:
        """List all registered provider names."""
        return list(cls._providers.keys())

    @classmethod
    def get_provider_capabilities(cls, name: str) -> ProviderCapabilities:
        """Get capabilities for a provider without instantiating."""
        if name not in cls._providers:
            raise ValueError(f"Unknown provider: {name}")
        # Create temporary instance to get capabilities
        # In practice, capabilities are static and could be class attributes
        instance = cls._providers[name]()
        return instance.capabilities

    @classmethod
    def clear_cache(cls) -> None:
        """Clear cached instances (for testing)."""
        cls._system_instances.clear()
        cls._org_instances.clear()

    @classmethod
    def invalidate_org_cache(cls, organization_id: str) -> None:
        """Invalidate cached provider instances for an organization."""
        org_id = str(organization_id)
        if org_id in cls._org_instances:
            del cls._org_instances[org_id]
