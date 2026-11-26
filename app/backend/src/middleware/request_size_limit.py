"""
Request body size limit middleware.

Rejects requests with Content-Length exceeding the configured maximum
before the body is buffered into memory, preventing memory exhaustion
from oversized uploads.
"""

from typing import Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from src.core.config import settings


class RequestSizeLimitMiddleware(BaseHTTPMiddleware):
    """
    Middleware that enforces a maximum request body size.

    Checks the Content-Length header and rejects requests that exceed
    the configured limit with a 413 Payload Too Large response.
    """

    async def dispatch(self, request: Request, call_next: Callable):
        content_length = request.headers.get("content-length")
        if content_length:
            try:
                if int(content_length) > settings.MAX_REQUEST_BODY_BYTES:
                    return JSONResponse(
                        status_code=413,
                        content={
                            "detail": f"Request body too large. Maximum size is {settings.MAX_REQUEST_BODY_BYTES} bytes.",
                            "detail_code": "common.payload_too_large",
                        },
                    )
            except ValueError:
                pass

        return await call_next(request)
