"""
Freespace public wire API, mounted at ``/v1`` (D1) - NOT under ``/api/v1``.

``public_router`` aggregates the ParkIT intake and the app endpoints exactly
as the functional description writes them (``/v1/ingest/...``,
``/v1/sites...``, ``/v1/devices/...``). ``main.py`` includes it with
``prefix="/v1"``; this is the stated exception to CLAUDE.md rule 9.

``mock_router`` (``/mock/...``) is separate and is included at the root by
``main.py`` only when ``settings.FREESPACE_MOCK_MODE`` is on (BF-84).

Feature modules add routes to their own files; nobody edits this file.
"""

from typing import Any

from fastapi import APIRouter, FastAPI

from src.api.freespace_public import app_sites, devices, ingest, mock
from src.logger.logger import Logger as logger
from src.services.freespace.mock_mode import mock_routes_enabled


public_router = APIRouter()
public_router.include_router(ingest.router)
public_router.include_router(app_sites.router)
public_router.include_router(devices.router)

mock_router = mock.router


def include_freespace_public_routers(app: FastAPI, settings: Any) -> None:
    """Mount ``public_router`` at ``/v1`` and, only in mock mode, ``mock_router``
    at the root. Called by ``main.create_application`` (after
    ``validate_mock_mode``)."""
    app.include_router(public_router, prefix="/v1")
    if mock_routes_enabled(settings):
        app.include_router(mock_router)
        logger.warning("Freespace MOCK MODE is ON: /mock/* routes are registered")


__all__ = ["public_router", "mock_router", "include_freespace_public_routers"]
