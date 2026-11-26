"""
Request/Response logging middleware for FastAPI.
Captures API requests with timing, status codes, and sanitized payloads.
"""

import asyncio
import json
import logging
from logging.handlers import RotatingFileHandler
import time
import traceback
from typing import Any, Callable, Optional

from fastapi import Request, Response
from starlette.background import BackgroundTask
from starlette.middleware.base import BaseHTTPMiddleware

from src.core.config import settings


# Strong references for fire-and-forget Tasks. asyncio's event loop only holds
# weak references to Tasks, so without this set the GC can reclaim the Task
# mid-await — cancelling the AsyncSessionLocal __aexit__ and leaking the
# underlying connection in `idle in transaction` state.
_background_tasks: set[asyncio.Task[Any]] = set()


def setup_request_logger(log_file: str) -> logging.Logger:
    """Setup a dedicated logger for request/response logging."""
    logger = logging.getLogger("request_response_logger")
    logger.setLevel(logging.INFO)

    # Avoid duplicate handlers
    if logger.handlers:
        return logger

    # File handler with rotation
    file_handler = RotatingFileHandler(
        log_file, maxBytes=1024 * 1024 * 100, backupCount=10
    )
    file_formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
    file_handler.setFormatter(file_formatter)
    logger.addHandler(file_handler)

    return logger


def sanitize_data(data: dict) -> dict:
    """
    Sanitize sensitive fields in data before logging.
    Masks passwords, tokens, API keys, and other sensitive information.
    """
    if not data:
        return {}

    sensitive_keys = [
        # Authentication tokens and secrets
        "password",
        "token",
        "access_token",
        "refresh_token",
        "api_key",
        "secret",
        "private_key",
        "authorization",
        "secret_access_key",
        "auth_token",
        # Session and CSRF tokens
        "session_id",
        "csrf_token",
        "csrf",
        # Authentication codes
        "pin",
        "otp",
        "verification_code",
        "mfa_code",
        "totp",
        "recovery_code",
        # Personal identification numbers
        "ssn",
        "social_security",
        "tax_id",
        "national_id",
        # Payment data (PCI DSS compliance)
        "credit_card",
        "card_number",
        "cvv",
        "cvc",
        "expiry",
        "card_exp",
        # Banking information
        "bank_account",
        "account_number",
        "routing_number",
        "iban",
        "swift",
        "bic",
        # Government IDs
        "license",
        "passport",
        "drivers_license",
        # Personal information
        "dob",
        "date_of_birth",
        "birth_date",
    ]

    sanitized: dict[str, Any] = {}
    for key, value in data.items():
        if any(sensitive in key.lower() for sensitive in sensitive_keys):
            if isinstance(value, str) and len(value) > 4:
                sanitized[key] = value[:4] + "****"
            else:
                sanitized[key] = "********"
        elif isinstance(value, dict):
            sanitized[key] = sanitize_data(value)
        elif isinstance(value, list):
            sanitized[key] = [
                sanitize_data(item) if isinstance(item, dict) else item
                for item in value
            ]
        else:
            sanitized[key] = value

    return sanitized


class RequestResponseLoggingMiddleware(BaseHTTPMiddleware):
    """
    Middleware to log all API requests with timing, status, and sanitized payloads.
    Logs are written to a separate file for debugging purposes.
    """

    def __init__(
        self,
        app,
        excluded_paths: Optional[set[str]] = None,
        max_body_size: int = 10240,  # 10KB default
    ):
        super().__init__(app)
        self.excluded_paths = excluded_paths or set()
        self.max_body_size = max_body_size
        self.logger = setup_request_logger(settings.REQUEST_LOGGING_FILE)

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Skip logging for excluded paths
        if request.url.path in self.excluded_paths:
            return await call_next(request)

        # Get dynamic config (cached in Redis)
        from src.services.config_cache import get_request_logging_config

        config = await get_request_logging_config()

        # Skip logging if disabled via dynamic config
        if not config.enabled:
            return await call_next(request)

        # Use dynamic max body size
        max_body_size = config.max_body_size

        # Capture request details
        method = request.method
        path = request.url.path
        start_time = time.perf_counter()

        # Capture request body
        request_body = None
        if method in ["POST", "PUT", "PATCH"]:
            try:
                # Read the request body
                body_bytes = await request.body()

                # Store it back for downstream handlers
                async def receive():
                    return {"type": "http.request", "body": body_bytes}

                request._receive = receive

                # Parse and sanitize
                if len(body_bytes) > max_body_size:
                    request_body = {
                        "truncated": f"Body too large ({len(body_bytes)} bytes)"
                    }
                elif body_bytes:
                    try:
                        body_data = json.loads(body_bytes)
                        request_body = sanitize_data(body_data)
                    except (json.JSONDecodeError, UnicodeDecodeError):
                        request_body = {
                            "raw": f"<non-json data, {len(body_bytes)} bytes>"
                        }
            except Exception as e:
                request_body = {"error": f"Failed to read request body: {str(e)}"}

        # Process the request
        status_code = 500
        response_body = None
        response = None
        error_traceback = None

        try:
            response = await call_next(request)
            status_code = response.status_code

            # Check if the exception handler stored a traceback in request.state
            # This happens when an exception was caught by FastAPI's exception handlers
            if status_code >= 500 and hasattr(request.state, "error_traceback"):
                error_traceback = request.state.error_traceback

            # Note: Response body capturing is complex with streaming responses
            # For now, we skip response body logging to avoid breaking the response

        except Exception as exc:
            # Capture full stack trace for debugging
            error_traceback = traceback.format_exc()
            response_body = {"exception": str(exc), "type": type(exc).__name__}
            status_code = 500
            raise

        finally:
            # Calculate duration
            duration_ms = (time.perf_counter() - start_time) * 1000

            # Prepare log entry
            log_entry = {
                "method": method,
                "path": path,
                "status_code": status_code,
                "duration_ms": round(duration_ms, 2),
                "ip_address": request.client.host if request.client else None,
                "user_agent": request.headers.get("user-agent"),
            }

            if request_body is not None:
                log_entry["request_body"] = request_body

            if response_body is not None:
                log_entry["response_body"] = response_body

            if error_traceback is not None:
                log_entry["error_traceback"] = error_traceback

            # Log to file
            self.logger.info(json.dumps(log_entry))

            # Write to database if enabled
            if config.db_enabled:
                from src.database import AsyncSessionLocal
                from src.services.request_log_writer import write_request_log_to_db

                async def write_to_db():
                    """Background task to write request log to database."""
                    async with AsyncSessionLocal() as session:
                        try:
                            await write_request_log_to_db(
                                session=session,
                                method=method,
                                path=path,
                                status_code=status_code,
                                duration_ms=round(duration_ms),
                                request_body=request_body,
                                response_body=response_body,
                                ip_address=(
                                    request.client.host if request.client else None
                                ),
                                user_agent=request.headers.get("user-agent"),
                                authorization_header=request.headers.get(
                                    "authorization"
                                ),
                                error_traceback=error_traceback,
                            )
                            await session.commit()
                        except Exception:
                            await session.rollback()

                if response is not None:
                    # Attach background task to response for successful requests
                    response.background = BackgroundTask(write_to_db)
                else:
                    # For exceptions, we need to write synchronously since there's no response
                    # to attach a background task to. Use asyncio to run it.
                    try:
                        task = asyncio.create_task(write_to_db())
                        _background_tasks.add(task)
                        task.add_done_callback(_background_tasks.discard)
                    except RuntimeError:
                        # If no event loop is running, skip DB logging for this error
                        pass

        return response


def setup_request_response_logging(
    app, excluded_paths: Optional[set[str]] = None
) -> None:
    """
    Configure and attach request/response logging middleware to the FastAPI application.
    The middleware checks dynamic configuration per-request, so it's always attached.
    """
    max_body_size = getattr(settings, "REQUEST_LOGGING_MAX_BODY_SIZE", 10240)

    app.add_middleware(
        RequestResponseLoggingMiddleware,
        excluded_paths=excluded_paths,
        max_body_size=max_body_size,
    )
