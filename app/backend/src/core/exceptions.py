"""
Exception utilities for consistent error responses with translation codes.
"""

from typing import Any, Optional

from fastapi import HTTPException

from src.core.response_codes import get_response_code


def create_http_exception(
    status_code: int,
    detail: str,
    detail_code: str,
    headers: Optional[dict[str, str]] = None,
) -> HTTPException:
    """
    Create HTTPException with both detail message and detail_code.

    Args:
        status_code: HTTP status code
        detail: Human-readable error message (English)
        detail_code: Translation code key (e.g., "user.not_found")
        headers: Optional HTTP headers

    Returns:
        HTTPException with detail_code in the detail dict

    Example:
        raise create_http_exception(
            status_code=404,
            detail="User not found",
            detail_code="user.not_found"
        )
    """
    # Get the actual translation code from the mapping
    code = get_response_code(detail_code)

    # Create detail dict with both message and code
    error_detail: dict[str, Any] = {"detail": detail, "detail_code": code}

    # FastAPI will serialize this dict in the response
    return HTTPException(status_code=status_code, detail=error_detail, headers=headers)


def create_success_response(
    message: str, message_code: str, **kwargs: Any
) -> dict[str, Any]:
    """
    Create success response dict with message and message_code.

    Args:
        message: Human-readable success message (English)
        message_code: Translation code key (e.g., "user.created")
        **kwargs: Additional fields to include in response

    Returns:
        Dict with message, message_code, and any additional fields

    Example:
        return create_success_response(
            message="User created successfully",
            message_code="user.created",
            user=user_data
        )
    """
    # Get the actual translation code from the mapping
    code = get_response_code(message_code)

    # Build response with message, code, and any additional fields
    response: dict[str, Any] = {
        "message": message,
        "message_code": code,
        **kwargs,
    }

    return response
