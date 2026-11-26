"""
Serializers for Query DSL responses.

Provides generic, reusable response models for list endpoints with standardized
structure for pagination, sorting, and filtering metadata.

The SDL supports two pagination strategies:

1. **Offset-based pagination** (default): Traditional pagination using total/limit/offset.
   Best for: UI pagination controls, random access to pages, small-to-medium datasets.

2. **Cursor-based pagination**: Uses opaque cursors for consistent performance.
   Best for: Large datasets, real-time data, infinite scroll, append-only logs.

Usage (offset-based):
    from src.serialisers.query import create_list_response_model

    UserListResponse = create_list_response_model(UserResponse, "User")

    @router.get("/users", response_model=UserListResponse)
    async def list_users(...):
        return {"items": users, "total": total, "limit": limit, "offset": offset}

Usage (cursor-based):
    from src.serialisers.query import create_cursor_list_response_model

    RequestLogListResponse = create_cursor_list_response_model(RequestLogResponse, "RequestLog")

    @router.get("/request-logs", response_model=RequestLogListResponse)
    async def list_request_logs(...):
        return {"items": logs, "next_cursor": cursor, "has_more": has_more, "limit": limit}
"""

from typing import Generic, Optional, TypeVar

from pydantic import BaseModel, ConfigDict, Field

from src.serialisers.common import PaginatedResponse


T = TypeVar("T", bound=BaseModel)


class ListResponseBase(PaginatedResponse):
    """
    Base class for offset-based list responses with standard pagination.

    All list endpoints using offset pagination should return responses
    inheriting from this class with an 'items' field containing the list of resources.

    Fields:
        - items: List of resource items
        - total: Total number of items matching the query
        - limit: Maximum items per page (1-100)
        - offset: Number of items skipped
    """

    model_config = ConfigDict(extra="forbid")


class CursorListResponseBase(BaseModel):
    """
    Base class for cursor-based list responses.

    Use cursor-based pagination when:
    - Dataset is very large (>100k rows)
    - Data changes frequently (offset can skip/duplicate items)
    - Implementing infinite scroll
    - Querying append-only data (logs, events, audit trails)

    Fields:
        - items: List of resource items
        - next_cursor: Opaque cursor for next page (null if no more results)
        - has_more: Whether there are more results to fetch
        - limit: Number of items per page
    """

    next_cursor: Optional[str] = Field(
        None, description="Cursor for next page (null if no more results)"
    )
    has_more: bool = Field(..., description="Whether there are more results")
    limit: int = Field(..., description="Number of items per page")

    model_config = ConfigDict(extra="forbid")


def create_list_response_model(
    item_model: type[T],
    resource_name: str,
) -> type[BaseModel]:
    """
    Factory function to create a typed offset-paginated list response model.

    Args:
        item_model: The Pydantic model for individual items
        resource_name: Name of the resource (for documentation)

    Returns:
        A new Pydantic model class for the list response

    Example:
        UserListResponse = create_list_response_model(UserResponse, "User")
        # Creates a model with: items: List[UserResponse], total, limit, offset
    """

    class ListResponse(ListResponseBase):
        items: list[item_model] = Field(  # type: ignore
            ..., description=f"List of {resource_name} items"
        )

        model_config = ConfigDict(extra="forbid")

    # Set a descriptive name for the model
    ListResponse.__name__ = f"{resource_name}ListResponse"
    ListResponse.__qualname__ = f"{resource_name}ListResponse"

    return ListResponse


def create_cursor_list_response_model(
    item_model: type[T],
    resource_name: str,
) -> type[BaseModel]:
    """
    Factory function to create a typed cursor-paginated list response model.

    Use cursor-based pagination for:
    - Large datasets (>100k rows) where offset performance degrades
    - Real-time/streaming data where offset can miss or duplicate items
    - Infinite scroll UIs
    - Append-only data like logs, events, audit trails

    Args:
        item_model: The Pydantic model for individual items
        resource_name: Name of the resource (for documentation)

    Returns:
        A new Pydantic model class for the cursor-based list response

    Example:
        RequestLogListResponse = create_cursor_list_response_model(RequestLogResponse, "RequestLog")
        # Creates a model with: items: List[RequestLogResponse], next_cursor, has_more, limit
    """

    class CursorListResponse(CursorListResponseBase):
        items: list[item_model] = Field(  # type: ignore
            ..., description=f"List of {resource_name} items"
        )

        model_config = ConfigDict(extra="forbid")

    # Set a descriptive name for the model
    CursorListResponse.__name__ = f"{resource_name}CursorListResponse"
    CursorListResponse.__qualname__ = f"{resource_name}CursorListResponse"

    return CursorListResponse


# Pre-defined generic list response for dynamic typing scenarios
class GenericListResponse(ListResponseBase, Generic[T]):
    """
    Generic offset-paginated list response for use with type hints.

    Note: For actual endpoint response_model, use create_list_response_model()
    as FastAPI needs concrete types for OpenAPI schema generation.
    """

    items: list[T] = Field(..., description="List of items")


class GenericCursorListResponse(CursorListResponseBase, Generic[T]):
    """
    Generic cursor-paginated list response for use with type hints.

    Note: For actual endpoint response_model, use create_cursor_list_response_model()
    as FastAPI needs concrete types for OpenAPI schema generation.
    """

    items: list[T] = Field(..., description="List of items")


# Common pagination parameters as a dependency-injectable model
class PaginationParams(BaseModel):
    """
    Standard offset-based pagination parameters.

    Can be used as a Pydantic model for query parameter validation.
    """

    limit: int = Field(default=50, ge=1, le=100, description="Maximum items to return")
    offset: int = Field(default=0, ge=0, description="Number of items to skip")

    model_config = ConfigDict(extra="forbid")


class CursorPaginationParams(BaseModel):
    """
    Standard cursor-based pagination parameters.

    Can be used as a Pydantic model for query parameter validation.
    The cursor is an opaque string returned from the previous response's next_cursor.
    """

    limit: int = Field(default=50, ge=1, le=100, description="Maximum items to return")
    cursor: Optional[str] = Field(
        default=None,
        description="Opaque cursor from previous response (omit for first page)",
    )

    model_config = ConfigDict(extra="forbid")


class SortParams(BaseModel):
    """
    Standard sort parameters.

    Sort format: field:direction (e.g., "created_at:desc")
    Multiple sorts: field1:dir1,field2:dir2
    """

    sort: Optional[str] = Field(
        default=None,
        description="Sort field and direction (e.g., 'created_at:desc')",
        pattern=r"^[\w]+:(asc|desc)(,[\w]+:(asc|desc))*$",
    )

    model_config = ConfigDict(extra="forbid")


class QueryMetadata(BaseModel):
    """
    Metadata about the query that produced the results.

    Can be included in responses for debugging/introspection.
    """

    filters_applied: int = Field(
        default=0, description="Number of filters applied to the query"
    )
    sort_applied: Optional[str] = Field(
        default=None, description="Sort specification applied"
    )
    search_term: Optional[str] = Field(
        default=None, description="Search term if full-text search was used"
    )

    model_config = ConfigDict(extra="forbid")
