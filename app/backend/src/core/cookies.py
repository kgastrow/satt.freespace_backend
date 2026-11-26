"""
Cookie utility functions for httpOnly refresh token management.

Refresh tokens are delivered via httpOnly cookies (invisible to JavaScript)
instead of JSON response bodies. This prevents XSS attacks from stealing
refresh tokens. Access tokens remain in JSON bodies, stored in Redux only.
"""

from fastapi import Request, Response

from src.core.config import settings


REFRESH_COOKIE_NAME = "refresh_token"


def set_refresh_cookie(response: Response, refresh_token: str) -> None:
    """
    Set the refresh token as an httpOnly cookie on the response.

    The cookie is configured with:
    - HttpOnly: JavaScript cannot read it
    - Secure: HTTPS only (configurable for local dev)
    - SameSite=Lax: Blocks cross-origin POST (CSRF protection)
    - Path=/api/v1: Sent to all API endpoints (needed by /sessions for current-session detection)
    - Max-Age: Matches refresh token TTL (30 days)
    """
    response.set_cookie(
        key=REFRESH_COOKIE_NAME,
        value=refresh_token,
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite=settings.COOKIE_SAMESITE,
        path=settings.COOKIE_PATH,
        max_age=settings.REFRESH_TOKEN_EXPIRE_SECONDS,
        domain=settings.COOKIE_DOMAIN or None,
    )


def clear_refresh_cookie(response: Response) -> None:
    """
    Delete the refresh token cookie by setting Max-Age=0.

    Must use the same path and domain attributes as set_refresh_cookie
    for the browser to correctly match and delete the cookie.
    """
    response.delete_cookie(
        key=REFRESH_COOKIE_NAME,
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite=settings.COOKIE_SAMESITE,
        path=settings.COOKIE_PATH,
        domain=settings.COOKIE_DOMAIN or None,
    )


def get_refresh_token_from_cookie(request: Request) -> str | None:
    """Read the refresh token value from the request cookie."""
    return request.cookies.get(REFRESH_COOKIE_NAME)
