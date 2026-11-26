"""
Report generation service.

This module provides a registry pattern for report generators,
allowing extensible report types to be added.
"""

from collections.abc import Awaitable
from dataclasses import dataclass
from typing import Any, Callable, Optional

from sqlalchemy.ext.asyncio import AsyncSession


@dataclass
class ReportTypeInfo:
    """Information about a registered report type."""

    code: str
    name: str
    description: str


# Type alias for report generator functions
# Generator receives: (session, organization_id, parameters) -> (file_bytes, content_type, row_count)
ReportGenerator = Callable[
    [AsyncSession, str, Optional[dict[str, Any]]],
    Awaitable[tuple[bytes, str, int]],
]


# Registry of report generators
_REPORT_GENERATORS: dict[str, tuple[ReportGenerator, ReportTypeInfo]] = {}


def register_generator(
    report_type: str,
    generator: ReportGenerator,
    name: str,
    description: str,
) -> None:
    """
    Register a report generator.

    Args:
        report_type: Unique code for this report type (e.g., "users_report")
        generator: Async function that generates the report
        name: Human-readable name
        description: Description of what the report contains
    """
    info = ReportTypeInfo(code=report_type, name=name, description=description)
    _REPORT_GENERATORS[report_type] = (generator, info)


def get_generator(report_type: str) -> Optional[ReportGenerator]:
    """
    Get a report generator by type.

    Args:
        report_type: The report type code

    Returns:
        The generator function or None if not found
    """
    entry = _REPORT_GENERATORS.get(report_type)
    return entry[0] if entry else None


def get_available_report_types() -> list[ReportTypeInfo]:
    """
    Get list of available report types.

    Returns:
        List of ReportTypeInfo for all registered generators
    """
    return [info for _, info in _REPORT_GENERATORS.values()]


def is_valid_report_type(report_type: str) -> bool:
    """
    Check if a report type is registered.

    Args:
        report_type: The report type code

    Returns:
        True if the report type is registered
    """
    return report_type in _REPORT_GENERATORS


# Import and register all generators when this module is loaded
# This ensures all generators are registered when the service is first used
def _register_all_generators() -> None:
    """Register all built-in report generators."""
    # Import here to avoid circular imports
    from src.services.reports.users_report import generate_users_report

    register_generator(
        report_type="users_report",
        generator=generate_users_report,
        name="Users Report",
        description="Export all users in the organization with their details and roles",
    )


# Auto-register generators on module import
_register_all_generators()


__all__ = [
    "ReportGenerator",
    "ReportTypeInfo",
    "register_generator",
    "get_generator",
    "get_available_report_types",
    "is_valid_report_type",
]
