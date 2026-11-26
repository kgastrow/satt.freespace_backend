"""
Query Parameter DSL for standardized filtering, sorting, and pagination.

This module provides utilities for parsing filter parameters in the format:
- filter[field]=value (implicit eq operator)
- filter[field][operator]=value (explicit operator)

Supported operators:
- eq: equals (default)
- ne: not equals
- gt, gte, lt, lte: comparisons
- in: value in list (comma-separated)
- contains: partial string match (case-insensitive)
- is_null: null check (value should be 'true' or 'false')

Usage in endpoints:
    from src.core.query_params import parse_filters, FilterSpec

    @router.get("/items")
    async def list_items(request: Request):
        filters = parse_filters(request, allowed_fields={"status", "user_id", "created_at"})
        # filters is List[FilterSpec]
"""

from dataclasses import dataclass
from enum import Enum
import re
from typing import Any, Optional

from fastapi import HTTPException, Request, status


class FilterOperator(str, Enum):
    """Supported filter operators."""

    EQ = "eq"
    NE = "ne"
    GT = "gt"
    GTE = "gte"
    LT = "lt"
    LTE = "lte"
    IN = "in"
    CONTAINS = "contains"
    IS_NULL = "is_null"


@dataclass
class FilterSpec:
    """Represents a single filter specification."""

    field: str
    operator: FilterOperator
    value: Any

    def __post_init__(self) -> None:
        """Convert value based on operator."""
        if self.operator == FilterOperator.IN:
            # Split comma-separated values
            if isinstance(self.value, str):
                self.value = [v.strip() for v in self.value.split(",") if v.strip()]
        elif self.operator == FilterOperator.IS_NULL:
            # Convert to boolean
            self.value = str(self.value).lower() in ("true", "1", "yes")


@dataclass
class SortSpec:
    """Represents a single sort specification."""

    field: str
    direction: str  # 'asc' or 'desc'


# Regex patterns for parsing filter parameters
# Matches: filter[field] or filter[field][operator]
FILTER_PATTERN = re.compile(r"^filter\[(\w+)\](?:\[(\w+)\])?$")

# Regex pattern for parsing sort parameters
# Matches: field:direction (e.g., created_at:desc)
SORT_PATTERN = re.compile(r"^(\w+):(asc|desc)$", re.IGNORECASE)


def parse_filters(
    request: Request,
    allowed_fields: Optional[set[str]] = None,
) -> list[FilterSpec]:
    """
    Parse filter parameters from request query string.

    Args:
        request: FastAPI Request object
        allowed_fields: Set of allowed field names. If None, all fields are allowed.

    Returns:
        List of FilterSpec objects

    Raises:
        HTTPException: If an invalid field or operator is provided

    Example:
        # URL: /items?filter[status]=active&filter[created_at][gte]=2024-01-01
        filters = parse_filters(request, allowed_fields={"status", "created_at"})
        # Returns: [
        #     FilterSpec(field="status", operator=EQ, value="active"),
        #     FilterSpec(field="created_at", operator=GTE, value="2024-01-01")
        # ]
    """
    filters: list[FilterSpec] = []

    for key, value in request.query_params.items():
        match = FILTER_PATTERN.match(key)
        if not match:
            continue

        field = match.group(1)
        operator_str = match.group(2) or "eq"

        # Validate field if allowed_fields is specified
        if allowed_fields is not None and field not in allowed_fields:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid filter field: {field}. Allowed fields: {', '.join(sorted(allowed_fields))}",
            )

        # Validate operator
        try:
            operator = FilterOperator(operator_str.lower())
        except ValueError:
            valid_operators = ", ".join(op.value for op in FilterOperator)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid filter operator: {operator_str}. Valid operators: {valid_operators}",
            )

        filters.append(FilterSpec(field=field, operator=operator, value=value))

    return filters


def parse_sort(
    sort_param: Optional[str],
    allowed_fields: Optional[set[str]] = None,
    default_sort: Optional[str] = None,
) -> list[SortSpec]:
    """
    Parse sort parameter.

    Args:
        sort_param: Sort string in format "field:direction" or "field1:dir1,field2:dir2"
        allowed_fields: Set of allowed field names for sorting
        default_sort: Default sort if none provided (e.g., "created_at:desc")

    Returns:
        List of SortSpec objects

    Raises:
        HTTPException: If invalid sort field or direction

    Example:
        # sort=created_at:desc,name:asc
        sorts = parse_sort("created_at:desc,name:asc", allowed_fields={"created_at", "name"})
        # Returns: [SortSpec("created_at", "desc"), SortSpec("name", "asc")]
    """
    if not sort_param:
        if default_sort:
            sort_param = default_sort
        else:
            return []

    sorts: list[SortSpec] = []

    for part in sort_param.split(","):
        part = part.strip()
        if not part:
            continue

        match = SORT_PATTERN.match(part)
        if not match:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid sort format: {part}. Expected format: field:asc or field:desc",
            )

        field = match.group(1)
        direction = match.group(2).lower()

        # Validate field if allowed_fields is specified
        if allowed_fields is not None and field not in allowed_fields:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid sort field: {field}. Allowed fields: {', '.join(sorted(allowed_fields))}",
            )

        sorts.append(SortSpec(field=field, direction=direction))

    return sorts


def get_search_param(request: Request) -> Optional[str]:
    """
    Extract the search parameter (q) from request.

    Args:
        request: FastAPI Request object

    Returns:
        Search string or None
    """
    return request.query_params.get("q")


def get_pagination_params(
    request: Request,
    default_limit: int = 50,
    max_limit: int = 100,
) -> tuple[int, int]:
    """
    Extract pagination parameters from request.

    Args:
        request: FastAPI Request object
        default_limit: Default limit if not specified
        max_limit: Maximum allowed limit

    Returns:
        Tuple of (limit, offset)

    Raises:
        HTTPException: If invalid pagination values
    """
    try:
        limit = int(request.query_params.get("limit", default_limit))
        offset = int(request.query_params.get("offset", 0))
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid pagination parameters. limit and offset must be integers.",
        )

    if limit < 1:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="limit must be at least 1",
        )

    if limit > max_limit:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"limit cannot exceed {max_limit}",
        )

    if offset < 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="offset must be non-negative",
        )

    return limit, offset
