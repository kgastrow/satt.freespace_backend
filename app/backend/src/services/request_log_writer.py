"""
Request log writer service for asynchronously writing request logs to the database.
"""

from typing import Any, Optional

import jwt
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.security import jwt_decode_options
from src.crud.request_log import create_request_log
from src.logger.logger import Logger as logger


async def write_request_log_to_db(
    session: AsyncSession,
    method: str,
    path: str,
    status_code: int,
    duration_ms: int,
    request_body: Optional[dict[str, Any]] = None,
    response_body: Optional[dict[str, Any]] = None,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
    authorization_header: Optional[str] = None,
    error_traceback: Optional[str] = None,
) -> None:
    """
    Write a request log entry to the database.

    Extracts organization_id and user_id from JWT token if present.
    Handles database errors gracefully to avoid failing the request.

    Args:
        session: Database session
        method: HTTP method
        path: Request path
        status_code: HTTP status code
        duration_ms: Request duration in milliseconds
        request_body: Sanitized request body (optional)
        response_body: Sanitized response body (optional)
        ip_address: Client IP address
        user_agent: User agent string
        authorization_header: Authorization header value (for extracting JWT)
        error_traceback: Full stack trace for 500 errors (optional)
    """
    organization_id: Optional[str] = None
    user_id: Optional[str] = None

    # Extract organization_id and user_id from JWT token if present
    if authorization_header:
        try:
            # Parse Bearer token
            parts = authorization_header.split(" ")
            if len(parts) == 2 and parts[0].lower() == "bearer":
                token = parts[1]
                # Decode without verification to extract claims
                # We don't need to verify here because the request has already been authenticated
                data = jwt.decode(
                    token,
                    settings.JWT_SECRET,
                    algorithms=["HS256"],
                    # verify_exp stays False: a request that was authenticated
                    # while valid must still be attributable after the token
                    # expires. Merged with the shared iat policy.
                    options=jwt_decode_options(verify_signature=True, verify_exp=False),
                )
                organization_id = data.get("organization_id")
                user_id = data.get("user_id")
        except (jwt.InvalidTokenError, ValueError, KeyError):
            # If token parsing fails, just log without user context
            pass

    try:
        await create_request_log(
            session=session,
            method=method,
            path=path,
            status_code=status_code,
            duration_ms=duration_ms,
            request_body=request_body,
            response_body=response_body,
            ip_address=ip_address,
            user_agent=user_agent,
            organization_id=organization_id,
            user_id=user_id,
            error_traceback=error_traceback,
        )
    except Exception as exc:
        # Log the error but don't fail the request
        logger.error(f"Failed to write request log to database: {exc}")
