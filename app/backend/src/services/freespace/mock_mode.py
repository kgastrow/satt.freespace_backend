"""
Mock-mode startup guard (BF-84, D13). Fully implemented.

The template has no environment name, only DEBUG and TESTING, so the
production check is: mock mode on, DEBUG off and no acknowledgement flag ->
refuse to start. ``main.create_application`` calls ``validate_mock_mode``
before registering any route, and registers the ``/mock`` router only when
mock mode is on (off -> 404, not 403).
"""

from __future__ import annotations

from typing import Any


class MockModeConfigurationError(RuntimeError):
    """Raised when mock mode is enabled in a non-debug deployment without the
    explicit acknowledgement flag."""


def validate_mock_mode(settings: Any) -> None:
    """Raise ``MockModeConfigurationError`` for an unsafe mock-mode config.

    ``settings`` is the application ``Settings`` (or any object with
    ``FREESPACE_MOCK_MODE``, ``FREESPACE_MOCK_MODE_ACKNOWLEDGED`` and
    ``DEBUG``).
    """
    if not getattr(settings, "FREESPACE_MOCK_MODE", False):
        return
    if getattr(settings, "DEBUG", False):
        return
    if getattr(settings, "FREESPACE_MOCK_MODE_ACKNOWLEDGED", False):
        return
    raise MockModeConfigurationError(
        "CRITICAL: freespace.mock_mode is on in a non-debug deployment. Mock "
        "mode exposes /mock/* endpoints that fabricate occupancy and move the "
        "engine clock. Turn it off, or set freespace.mock_mode_acknowledged "
        "to true if this really is a demonstration deployment."
    )


def mock_routes_enabled(settings: Any) -> bool:
    """Whether the /mock router must be registered (after validation)."""
    return bool(getattr(settings, "FREESPACE_MOCK_MODE", False))
