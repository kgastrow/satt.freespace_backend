"""
Session Metadata Service.
Handles user-agent parsing and IP geolocation for session tracking.
"""

from __future__ import annotations

import os
from typing import Any

from user_agents import parse as parse_user_agent

from src.core.config import settings
from src.logger.logger import Logger


# Lazy-loaded GeoIP reader
_geoip_reader: Any | None = None


def _get_geoip_reader() -> Any | None:
    """
    Get or initialize the GeoIP database reader.
    Returns None if GeoIP is disabled or database not available.
    """
    global _geoip_reader

    if not settings.GEOIP_ENABLED:
        return None

    if _geoip_reader is not None:
        return _geoip_reader

    try:
        import geoip2.database

        db_path = settings.GEOIP_DATABASE_PATH
        if not os.path.exists(db_path):
            Logger.warning(
                f"GeoIP database not found at {db_path}. Geolocation disabled."
            )
            return None

        _geoip_reader = geoip2.database.Reader(db_path)
        Logger.info(f"GeoIP database loaded from {db_path}")
        return _geoip_reader
    except ImportError:
        Logger.warning("geoip2 library not installed. Geolocation disabled.")
        return None
    except Exception as e:
        Logger.error(f"Failed to load GeoIP database: {e}")
        return None


def reload_geoip_reader() -> bool:
    """
    Reload the GeoIP database reader after database file update.

    Closes the existing reader (if any) and forces re-initialization
    on the next lookup request.

    Returns:
        True if the reader was successfully reloaded, False otherwise.
    """
    global _geoip_reader
    if _geoip_reader is not None:
        try:
            _geoip_reader.close()
        except Exception:
            pass
        _geoip_reader = None
    return _get_geoip_reader() is not None


class SessionMetadataService:
    """Service for parsing session metadata from user-agent and IP address."""

    @staticmethod
    def parse_device_info(user_agent: str | None) -> dict:
        """
        Parse user-agent string into device type, browser, and OS information.

        Args:
            user_agent: The user-agent string from the HTTP request

        Returns:
            Dictionary with device_type, browser, os, and is_bot fields
        """
        if not user_agent:
            return {
                "device_type": "unknown",
                "browser": "Unknown",
                "os": "Unknown",
                "is_bot": False,
            }

        try:
            ua = parse_user_agent(user_agent)

            # Determine device type
            if ua.is_mobile:
                device_type = "mobile"
            elif ua.is_tablet:
                device_type = "tablet"
            elif ua.is_pc:
                device_type = "desktop"
            else:
                device_type = "unknown"

            # Format browser info
            browser_version = ua.browser.version_string
            browser = f"{ua.browser.family}"
            if browser_version and browser_version != "Other":
                browser = f"{browser} {browser_version}"

            # Format OS info
            os_version = ua.os.version_string
            os_name = f"{ua.os.family}"
            if os_version and os_version != "Other":
                os_name = f"{os_name} {os_version}"

            return {
                "device_type": device_type,
                "browser": browser if browser != "Other" else "Unknown",
                "os": os_name if os_name != "Other" else "Unknown",
                "is_bot": ua.is_bot,
            }
        except Exception as e:
            Logger.warning(f"Failed to parse user-agent '{user_agent[:100]}...': {e}")
            return {
                "device_type": "unknown",
                "browser": "Unknown",
                "os": "Unknown",
                "is_bot": False,
            }

    @staticmethod
    def get_location_from_ip(
        ip_address: str | None,
    ) -> tuple[str | None, str | None, str | None]:
        """
        Look up geographic location from IP address using MaxMind GeoLite2.

        Args:
            ip_address: The IP address to look up

        Returns:
            Tuple of (city, country, country_code)
            Returns (None, None, None) if lookup fails or GeoIP is unavailable
        """
        if not ip_address:
            return None, None, None

        # Skip private/local IP addresses
        if ip_address.startswith(
            (
                "127.",
                "10.",
                "192.168.",
                "172.16.",
                "172.17.",
                "172.18.",
                "172.19.",
                "172.20.",
                "172.21.",
                "172.22.",
                "172.23.",
                "172.24.",
                "172.25.",
                "172.26.",
                "172.27.",
                "172.28.",
                "172.29.",
                "172.30.",
                "172.31.",
                "::1",
                "fe80:",
            )
        ):
            return None, None, None

        reader = _get_geoip_reader()
        if reader is None:
            return None, None, None

        try:
            import geoip2.errors

            response = reader.city(ip_address)

            city = response.city.name if response.city else None
            country = response.country.name if response.country else None
            country_code = response.country.iso_code if response.country else None

            return city, country, country_code
        except geoip2.errors.AddressNotFoundError:
            Logger.debug(f"IP address not found in GeoIP database: {ip_address}")
            return None, None, None
        except Exception as e:
            Logger.warning(f"GeoIP lookup failed for {ip_address}: {e}")
            return None, None, None

    @staticmethod
    def mask_ip_address(ip_address: str | None) -> str | None:
        """
        Partially mask an IP address for privacy.

        IPv4: 192.168.1.100 -> 192.168.x.x
        IPv6: 2001:db8::1 -> 2001:db8:x:x:x:x:x:x

        Args:
            ip_address: The IP address to mask

        Returns:
            Masked IP address or None if input is None
        """
        if not ip_address:
            return None

        if ":" in ip_address:
            # IPv6
            parts = ip_address.split(":")
            if len(parts) >= 2:
                return f"{parts[0]}:{parts[1]}:x:x:x:x:x:x"
            return ip_address
        else:
            # IPv4
            parts = ip_address.split(".")
            if len(parts) == 4:
                return f"{parts[0]}.{parts[1]}.x.x"
            return ip_address


# Module-level convenience functions
def parse_device_info(user_agent: str | None) -> dict:
    """Parse user-agent string into device info."""
    return SessionMetadataService.parse_device_info(user_agent)


def get_location_from_ip(
    ip_address: str | None,
) -> tuple[str | None, str | None, str | None]:
    """Look up location from IP address."""
    return SessionMetadataService.get_location_from_ip(ip_address)


def mask_ip_address(ip_address: str | None) -> str | None:
    """Partially mask an IP address for privacy."""
    return SessionMetadataService.mask_ip_address(ip_address)
