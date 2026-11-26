"""
SQLAlchemy Query Builder for applying DSL filters, sorting, and pagination.

This module provides utilities for applying parsed filter specifications
to SQLAlchemy queries in a type-safe manner.

Usage:
    from src.core.query_params import parse_filters, parse_sort
    from src.core.query_builder import apply_filters, apply_sort, apply_pagination

    @router.get("/items")
    async def list_items(request: Request, session: AsyncSession):
        filters = parse_filters(request, allowed_fields=ALLOWED_FILTERS)
        sorts = parse_sort(request.query_params.get("sort"), allowed_fields=ALLOWED_SORTS)
        limit, offset = get_pagination_params(request)

        query = select(Item).where(Item.organization_id == org_id)
        query = apply_filters(query, Item, filters, FIELD_MAPPING)
        query = apply_sort(query, Item, sorts, FIELD_MAPPING)
        query = apply_pagination(query, limit, offset)

        result = await session.execute(query)
        items = result.scalars().all()
"""

from typing import Any, Optional, TypeVar
from uuid import UUID

from sqlalchemy import Select, func, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import DeclarativeBase

from src.core.query_params import FilterOperator, FilterSpec, SortSpec


T = TypeVar("T", bound=DeclarativeBase)


def apply_filters(
    query: Select[tuple[T]],
    model: type[T],
    filters: list[FilterSpec],
    field_mapping: Optional[dict[str, str]] = None,
) -> Select[tuple[T]]:
    """
    Apply filter specifications to a SQLAlchemy query.

    Args:
        query: Base SQLAlchemy Select query
        model: SQLAlchemy model class
        filters: List of FilterSpec objects from parse_filters()
        field_mapping: Optional mapping from API field names to model attribute names
                      e.g., {"user_type": "user_type_id"} maps filter[user_type] to model.user_type_id

    Returns:
        Modified query with filters applied

    Example:
        query = select(User).where(User.organization_id == org_id)
        query = apply_filters(query, User, filters, {"type": "user_type_id"})
    """
    for filter_spec in filters:
        # Map API field name to model attribute name if mapping exists
        model_field = filter_spec.field
        if field_mapping and filter_spec.field in field_mapping:
            model_field = field_mapping[filter_spec.field]

        # Get the model attribute
        if not hasattr(model, model_field):
            # Skip unknown fields (should be caught by parse_filters validation)
            continue

        column = getattr(model, model_field)
        value = filter_spec.value

        # Apply the filter based on operator
        query = _apply_filter_operator(query, column, filter_spec.operator, value)

    return query


def _apply_filter_operator(
    query: Select[Any],
    column: Any,
    operator: FilterOperator,
    value: Any,
) -> Select[Any]:
    """Apply a single filter operator to the query."""
    # Convert UUID strings if the column type is UUID
    value = _convert_value_for_column(column, value, operator)

    match operator:
        case FilterOperator.EQ:
            return query.where(column == value)
        case FilterOperator.NE:
            return query.where(column != value)
        case FilterOperator.GT:
            return query.where(column > value)
        case FilterOperator.GTE:
            return query.where(column >= value)
        case FilterOperator.LT:
            return query.where(column < value)
        case FilterOperator.LTE:
            return query.where(column <= value)
        case FilterOperator.IN:
            if isinstance(value, list):
                return query.where(column.in_(value))
            return query.where(column == value)
        case FilterOperator.CONTAINS:
            # Case-insensitive partial match
            return query.where(func.lower(column).like(func.lower(f"%{value}%")))
        case FilterOperator.IS_NULL:
            if value:  # is_null=true
                return query.where(column.is_(None))
            else:  # is_null=false
                return query.where(column.isnot(None))
        case _:
            return query


def _convert_value_for_column(column: Any, value: Any, operator: FilterOperator) -> Any:
    """Convert value to appropriate type based on column type."""
    # Handle UUID columns
    try:
        column_type = str(column.type)
        if "UUID" in column_type:
            if operator == FilterOperator.IN and isinstance(value, list):
                return [UUID(v) if isinstance(v, str) else v for v in value]
            elif isinstance(value, str) and operator != FilterOperator.CONTAINS:
                try:
                    return UUID(value)
                except ValueError:
                    return value
    except Exception:
        pass

    return value


def apply_sort(
    query: Select[tuple[T]],
    model: type[T],
    sorts: list[SortSpec],
    field_mapping: Optional[dict[str, str]] = None,
    default_sort_field: Optional[str] = None,
    default_sort_direction: str = "desc",
) -> Select[tuple[T]]:
    """
    Apply sort specifications to a SQLAlchemy query.

    Args:
        query: Base SQLAlchemy Select query
        model: SQLAlchemy model class
        sorts: List of SortSpec objects from parse_sort()
        field_mapping: Optional mapping from API field names to model attribute names
        default_sort_field: Default field to sort by if no sorts specified
        default_sort_direction: Default direction for default sort ("asc" or "desc")

    Returns:
        Modified query with sorting applied
    """
    if not sorts and default_sort_field:
        sorts = [SortSpec(field=default_sort_field, direction=default_sort_direction)]

    for sort_spec in sorts:
        # Map API field name to model attribute name if mapping exists
        model_field = sort_spec.field
        if field_mapping and sort_spec.field in field_mapping:
            model_field = field_mapping[sort_spec.field]

        # Get the model attribute
        if not hasattr(model, model_field):
            continue

        column = getattr(model, model_field)

        if sort_spec.direction == "asc":
            query = query.order_by(column.asc())
        else:
            query = query.order_by(column.desc())

    return query


def apply_pagination(
    query: Select[tuple[T]],
    limit: int,
    offset: int,
) -> Select[tuple[T]]:
    """
    Apply pagination to a SQLAlchemy query.

    Args:
        query: Base SQLAlchemy Select query
        limit: Maximum number of results
        offset: Number of results to skip

    Returns:
        Modified query with pagination applied
    """
    return query.limit(limit).offset(offset)


async def get_total_count(
    session: AsyncSession,
    base_query: Select[Any],
) -> int:
    """
    Get total count for a query (before pagination).

    Args:
        session: SQLAlchemy async session
        base_query: Query to count (without limit/offset)

    Returns:
        Total count of matching records
    """
    count_query = base_query.with_only_columns(func.count()).order_by(None)
    result = await session.execute(count_query)
    return result.scalar() or 0


def apply_search(
    query: Select[tuple[T]],
    model: type[T],
    search_term: Optional[str],
    search_fields: list[str],
) -> Select[tuple[T]]:
    """
    Apply full-text search across multiple fields.

    Args:
        query: Base SQLAlchemy Select query
        model: SQLAlchemy model class
        search_term: Search string
        search_fields: List of model field names to search in

    Returns:
        Modified query with search filter applied

    Example:
        query = apply_search(query, User, "john", ["first_name", "last_name", "email"])
    """
    if not search_term or not search_fields:
        return query

    search_pattern = f"%{search_term}%"
    conditions = []

    for field_name in search_fields:
        if hasattr(model, field_name):
            column = getattr(model, field_name)
            conditions.append(func.lower(column).like(func.lower(search_pattern)))

    if conditions:
        query = query.where(or_(*conditions))

    return query
