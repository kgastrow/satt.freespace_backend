"""
FastAPI application entry point.
Configures middleware, routers, and lifecycle events.
"""
import base64
from contextlib import asynccontextmanager
import secrets
import traceback

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from sqlalchemy import text
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.gzip import GZipMiddleware

from src.core.client_ip import APPEND_ONLY_HEADERS
from src.core.config import settings
from src.core.rate_limit import limiter
from src.database import async_engine, close_db
from src.logger.logger import Logger as logger
from src.logger.logger import print_exception_with_trace
from src.middleware import (
    get_pool_stats,
    setup_db_metrics,
    setup_metrics,
    setup_request_response_logging,
)
from src.middleware.rate_limit_metrics import (
    record_rate_limit_check,
    record_rate_limit_violation,
)
from src.services.cache import cache_service


def _validate_trusted_client_ip_header() -> None:
    """Fail fast on a client-IP configuration that is wrong on every topology.

    The client IP is not just audit metadata here: ``src/api/auth.py`` keys the
    login and 2FA brute-force lockout on it, and it is stored on refresh tokens
    and shown to users in their session list. See ``src/core/client_ip.py``.

    Two outcomes, deliberately different:

    * UNSET -> a loud WARNING, not a refusal. The fallback (the connection peer
      address) is safe wherever uvicorn's ``--forwarded-allow-ips`` names the
      real proxy, which covers local development and a plain reverse proxy; it
      is merely imprecise behind a CDN. A template that refused to boot until a
      fork named a CDN header would just get the guard deleted.
    * An APPEND-ONLY header (X-Forwarded-For, Forwarded, X-Forwarded) -> refuse
      to boot. Proxies append to those, so the leftmost value is client-supplied
      and forgeable; ``client_ip.py`` therefore ignores such a header and
      silently falls back. Silently trusting nothing when the operator believes
      they configured trust is worse than not starting, and this case is wrong
      on every deployment topology, not just some.

    Skipped under TESTING and DEBUG, like the other startup guards: on a laptop
    the peer really is the client.
    """
    if settings.TESTING or settings.DEBUG:
        return

    header = (settings.TRUSTED_CLIENT_IP_HEADER or "").strip()

    if not header:
        logger.warning(
            "TRUSTED_CLIENT_IP_HEADER is not configured. Client IPs (audit "
            "records, session lists, per-IP rate limits and the login/2FA "
            "lockout) fall back to the connection peer address. That is correct "
            "behind a reverse proxy whose address is named in uvicorn's "
            "--forwarded-allow-ips, but behind a CDN it resolves to the edge "
            "node, so every visitor through one PoP shares a lockout and a rate "
            'limit bucket. Set "server": {"trusted_client_ip_header": '
            '"CF-Connecting-IP"} (or your edge equivalent) in config.json, and '
            "make sure the origin only accepts connections from that edge. "
            "Never set --forwarded-allow-ips='*': it makes every client-supplied "
            "X-Forwarded-For trusted. See src/core/client_ip.py."
        )
        return

    if header.lower() in APPEND_ONLY_HEADERS:
        raise RuntimeError(
            f"CRITICAL: TRUSTED_CLIENT_IP_HEADER is set to {header!r}, which "
            "proxies APPEND to rather than overwrite. Its leftmost value is "
            "client-supplied and forgeable, so it is ignored at runtime and the "
            "client IP silently falls back to the peer address. Use the header "
            "your edge OVERWRITES instead (Cloudflare: CF-Connecting-IP; "
            "Akamai: True-Client-IP), or leave it empty to use the peer address "
            "deliberately."
        )


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup and shutdown events."""
    # Startup
    logger.info("Starting application...")

    # Security validation - ensure production-safe secrets are configured
    # Skip validation in testing mode
    if not settings.TESTING:
        # Validate JWT_SECRET is not using the default placeholder
        if settings.JWT_SECRET == "your-secret-key-change-in-production":
            raise RuntimeError(
                "CRITICAL: Default JWT_SECRET detected. "
                "Configure a secure secret before deploying to production. "
                "Generate with: python -c \"import secrets; print(secrets.token_urlsafe(64))\""
            )

        # Validate CORS is not using wildcard in production
        if settings.CORS_ALLOWED_ORIGINS.strip() == "*":
            raise RuntimeError(
                "CRITICAL: CORS_ALLOWED_ORIGINS is set to '*'. "
                "Configure specific origins in config.json before deploying to production. "
                'Example: "cors_allowed_origins": "https://app.example.com,https://admin.example.com"'
            )

        # Validate client IP trust configuration (audit + brute force lockout)
        _validate_trusted_client_ip_header()

        # Validate ENCRYPTION_KEY is configured for production
        if not settings.ENCRYPTION_KEY:
            raise RuntimeError(
                "CRITICAL: No ENCRYPTION_KEY configured. "
                "A separate encryption key is required (do not reuse JWT_SECRET). "
                "Generate with: python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
            )

    # Initialize shared Redis pool manager (single pool for all services)
    from src.core.redis_pool import redis_pool_manager
    await redis_pool_manager.connect()

    # Wire shared Redis clients into all services
    if redis_pool_manager.client_db0:
        cache_service.set_redis(redis_pool_manager.client_db0)

        try:
            from src.services.job_stats import job_stats_service
            job_stats_service.set_redis(redis_pool_manager.client_db0)
        except Exception as e:
            logger.warning(f"Failed to initialize job stats service: {e}")

        try:
            from src.core.api_key_rate_limit import api_key_rate_limiter
            api_key_rate_limiter.set_redis(redis_pool_manager.client_db0)
        except Exception as e:
            logger.warning(f"Failed to initialize API key rate limiter: {e}")

        try:
            from src.services.brute_force_detector import brute_force_detector
            brute_force_detector.set_redis(redis_pool_manager.client_db0)
        except Exception as e:
            logger.warning(f"Failed to initialize brute force detector: {e}")

        try:
            from src.services.user_activity import user_activity_service
            user_activity_service.set_redis(redis_pool_manager.client_db0)
            logger.info("User activity tracking enabled")
        except ImportError:
            logger.info("User activity service not configured")
    else:
        # Fallback: let cache_service create its own pool
        await cache_service.connect()

    # Wire shared DB 1 client into queue health service
    if redis_pool_manager.client_db1:
        try:
            from src.services.queue_health import queue_health_service
            queue_health_service.set_redis(redis_pool_manager.client_db1)
        except Exception as e:
            logger.warning(f"Failed to initialize queue health service: {e}")

    # Wire dedicated pub/sub connection
    if redis_pool_manager.pubsub_client:
        try:
            from src.services.websocket.redis_pubsub import redis_pubsub
            redis_pubsub.set_redis(redis_pool_manager.pubsub_client)
        except Exception as e:
            logger.warning(f"Failed to initialize pub/sub service: {e}")

    # Initialize task queue (if using ARQ)
    try:
        from src.services.tasks import task_queue
        await task_queue.connect()
        logger.info("Task queue connected")
    except ImportError:
        logger.info("Task queue not configured")

    # Verify database connection and setup metrics
    try:
        async with async_engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        logger.info("Database connection verified")

        # Setup database metrics instrumentation
        setup_db_metrics(async_engine.sync_engine)
        logger.info("Database metrics instrumentation enabled")
    except Exception as e:
        logger.error(f"Database connection failed: {e}")
        raise

    # Initialize file storage (S3 or local fallback)
    try:
        from src.services.files.file_manager import init_file_manager

        # Check if S3 is properly configured
        s3_configured = bool(settings.S3_BUCKET and settings.AWS_ACCESS_KEY_ID)

        if s3_configured:
            # Use S3 storage
            from src.services.files.s3_storage import init_s3_storage

            storage = init_s3_storage(
                bucket=settings.S3_BUCKET,
                region=settings.S3_REGION,
                access_key_id=settings.AWS_ACCESS_KEY_ID or None,
                secret_access_key=settings.AWS_SECRET_ACCESS_KEY or None,
                endpoint_url=settings.S3_ENDPOINT_URL or None,
                enabled=True,
            )
            init_file_manager(storage)
            if storage.is_available():
                logger.info("File manager initialized with S3 storage")
            else:
                logger.warning("File manager initialized but S3 storage is not available")
        else:
            # Fall back to local storage
            from src.services.files.local_storage import init_local_storage

            # Use local storage if explicitly enabled or if S3 is not configured
            local_enabled = settings.LOCAL_STORAGE_ENABLED or not s3_configured

            storage = init_local_storage(
                storage_path=settings.LOCAL_STORAGE_PATH,
                base_url=settings.PUBLIC_URL,
                enabled=local_enabled,
            )
            init_file_manager(storage)
            if storage.is_available():
                logger.info(f"File manager initialized with local storage at {settings.LOCAL_STORAGE_PATH}")
            else:
                logger.warning("File manager initialized but local storage is not available")
    except Exception as e:
        logger.warning(f"Failed to initialize file manager: {e}")

    # Register cron job handlers with the scheduler service
    from src.services.cron_scheduler import cron_scheduler_service
    cron_scheduler_service.register_all_handlers()

    logger.info("Application started successfully")

    yield

    # Shutdown
    logger.info("Shutting down application...")

    # Close task queue (ARQ has its own connection)
    try:
        from src.services.tasks import task_queue
        await task_queue.disconnect()
    except ImportError:
        pass

    # Stop pub/sub listener before tearing down the Redis pool so the
    # listener task is cancelled cleanly rather than orphaned.
    try:
        from src.services.websocket.redis_pubsub import redis_pubsub
        await redis_pubsub.stop()
    except Exception as e:
        logger.warning(f"Failed to stop pub/sub service cleanly: {e}")

    # Close shared Redis pool manager (closes all pools at once)
    from src.core.redis_pool import redis_pool_manager
    await redis_pool_manager.disconnect()

    # Close database connections
    await close_db()

    logger.info("Application shutdown complete")


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """
    Middleware to add security headers to all responses.

    These headers provide defense-in-depth protection even if reverse proxy
    headers are misconfigured or bypassed.
    """

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        # Prevent clickjacking attacks
        response.headers["X-Frame-Options"] = "DENY"
        # Prevent MIME type sniffing
        response.headers["X-Content-Type-Options"] = "nosniff"
        # Enable XSS filter in older browsers
        response.headers["X-XSS-Protection"] = "1; mode=block"
        # Enforce HTTPS for 1 year (only effective over HTTPS)
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        # Control referrer information sent with requests
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        # Restrict browser features
        response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
        # Content Security Policy
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self'; "
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
            "img-src 'self' data: blob: https:; "
            "font-src 'self' data: https://fonts.gstatic.com; "
            "connect-src 'self' wss: ws: https:"
        )
        return response


async def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded):
    """Custom rate limit exceeded handler that records metrics."""
    # Extract client IP
    ip = request.client.host if request.client else "unknown"

    # Extract endpoint
    endpoint = request.url.path

    # Extract organization_id from request state if available (set by auth middleware)
    org_id = getattr(request.state, "organization_id", None) or "unknown"

    # Record metrics
    record_rate_limit_violation(org_id, ip, endpoint)
    record_rate_limit_check(endpoint, allowed=False)

    # Delegate to standard slowapi handler for 429 response
    return _rate_limit_exceeded_handler(request, exc)


def create_application() -> FastAPI:
    """Create and configure FastAPI application."""
    # Determine if docs should be enabled (default: True, configurable via ENABLE_DOCS)
    enable_docs = getattr(settings, 'ENABLE_DOCS', True)

    app = FastAPI(
        title=f"{settings.APP_NAME} Backend API",
        description="""
## Multi-tenant Backend API

A production-ready FastAPI backend with:
- **JWT Authentication** with organization context
- **Row-level Multi-tenancy** with strict data isolation
- **Role-Based Access Control** (RBAC)
- **Redis Caching** for performance
- **Background Jobs** with ARQ
- **Prometheus Metrics** for observability

### API Versioning
This API uses URL-based versioning. All endpoints are prefixed with `/api/v1/`.

- **Current Version**: v1 (`/api/v1/`)
- **Versioning Strategy**: New major versions (v2, v3, etc.) will be added as separate prefixes when breaking changes are introduced
- **Backward Compatibility**: Multiple API versions can coexist to allow gradual client migration
- **Stability**: v1 is the current stable version and will be maintained for the foreseeable future

Example endpoint: `POST /api/v1/auth/login`

### Authentication
All protected endpoints require a Bearer token in the Authorization header:
```
Authorization: Bearer <your-jwt-token>
```

### Rate Limiting
- Default: 100 requests/minute
- Login: 5 requests/minute
- OTP/Password Reset: 3 requests/minute
        """,
        version="2.0.0",
        lifespan=lifespan,
        docs_url="/docs" if enable_docs else None,
        redoc_url="/redoc" if enable_docs else None,
        openapi_tags=[
            {"name": "auth", "description": "Authentication operations"},
            {"name": "users", "description": "User management (admin)"},
            {"name": "roles", "description": "Role management"},
            {"name": "organizations", "description": "Organization management"},
            {"name": "audit-logs", "description": "Audit log viewing (admin)"},
            {"name": "health", "description": "Health check endpoints"},
        ],
    )

    # Setup Prometheus metrics (must be before other middleware)
    setup_metrics(app)

    # Setup request/response logging (after metrics middleware)
    excluded_paths = set(
        path.strip()
        for path in settings.REQUEST_LOGGING_EXCLUDED_PATHS.split(",")
        if path.strip()
    )
    setup_request_response_logging(app, excluded_paths=excluded_paths)

    # Add rate limiter
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)
    app.add_middleware(SlowAPIMiddleware)

    # Request body size limit (reject oversized uploads before buffering)
    from src.middleware.request_size_limit import RequestSizeLimitMiddleware
    app.add_middleware(RequestSizeLimitMiddleware)

    # Security headers middleware (should be early in the chain)
    app.add_middleware(SecurityHeadersMiddleware)

    # CORS middleware - parse allowed origins from settings
    # Note: Refresh tokens are delivered via httpOnly cookies scoped to
    # Path=/api/v1/auth. CSRF is mitigated by SameSite=Lax (blocks cross-origin
    # POST) and because the refresh endpoint only returns a short-lived access
    # token, not a state-changing action. The Authorization: Bearer header
    # is still required for all API calls.
    # In production, configure CORS_ALLOWED_ORIGINS to specific domains
    cors_origins = [
        origin.strip()
        for origin in settings.CORS_ALLOWED_ORIGINS.split(",")
        if origin.strip()
    ]
    cors_methods = [
        method.strip()
        for method in settings.CORS_ALLOWED_METHODS.split(",")
        if method.strip()
    ]
    cors_headers = [
        header.strip()
        for header in settings.CORS_ALLOWED_HEADERS.split(",")
        if header.strip()
    ]

    # Security warning: allow_credentials=True with allow_origins=["*"] is insecure
    # If using wildcard origins, credentials should be disabled
    allow_credentials = "*" not in cors_origins

    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=allow_credentials,
        allow_methods=cors_methods,
        allow_headers=cors_headers,
    )

    # GZIP compression for responses (only compress responses >= 1000 bytes)
    app.add_middleware(GZipMiddleware, minimum_size=1000)

    # Add middleware to protect API documentation endpoints
    if enable_docs:
        @app.middleware("http")
        async def docs_auth_middleware(request: Request, call_next):
            """Middleware to protect /docs and /redoc endpoints with HTTP basic auth."""
            if request.url.path in ["/docs", "/redoc", "/openapi.json"]:
                # Check for Authorization header
                auth_header = request.headers.get("Authorization")
                if not auth_header or not auth_header.startswith("Basic "):
                    return JSONResponse(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        content={"detail": "Not authenticated"},
                        headers={"WWW-Authenticate": "Basic"},
                    )

                # Decode and verify credentials
                try:
                    auth_decoded = base64.b64decode(auth_header[6:]).decode("utf-8")
                    username, password = auth_decoded.split(":", 1)

                    correct_username = secrets.compare_digest(
                        username, settings.API_DOCS_USERNAME
                    )
                    correct_password = secrets.compare_digest(
                        password, settings.API_DOCS_PASSWORD
                    )

                    if not (correct_username and correct_password):
                        return JSONResponse(
                            status_code=status.HTTP_401_UNAUTHORIZED,
                            content={"detail": "Incorrect username or password"},
                            headers={"WWW-Authenticate": "Basic"},
                        )
                except (ValueError, UnicodeDecodeError):
                    return JSONResponse(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        content={"detail": "Invalid authorization header"},
                        headers={"WWW-Authenticate": "Basic"},
                    )

            response = await call_next(request)
            return response

    # HTTPException handler for localized responses
    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException):
        """Handle HTTPException to properly flatten detail_code structure."""
        # If detail is a dict with detail and detail_code, flatten it
        if isinstance(exc.detail, dict) and "detail" in exc.detail and "detail_code" in exc.detail:
            return JSONResponse(
                status_code=exc.status_code,
                content={
                    "detail": exc.detail["detail"],
                    "detail_code": exc.detail["detail_code"]
                },
                headers=exc.headers
            )
        # Otherwise, return as-is
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail},
            headers=exc.headers
        )

    # Global exception handler
    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        # Capture and store traceback for request logging middleware
        error_traceback = traceback.format_exc()
        request.state.error_traceback = error_traceback

        # Print exception with stack trace to stdout
        print_exception_with_trace(exc, f"Unhandled exception in request: {request.method} {request.url.path}")
        # Log to file as well
        logger.error(f"Unhandled exception: {exc}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={
                "detail": "Internal server error",
                "detail_code": "common.internal_error"
            },
        )

    # Health check endpoints
    @app.get("/health", tags=["health"])
    async def health_check():
        """LIVENESS probe: can this process serve at all?

        Deliberately checks NOTHING, and must stay that way. A liveness probe
        that tests dependencies restarts the app when the database goes down -
        which does not fix the database, and kills a process that could still
        serve cached reads and every route that never touches Postgres.
        Dependency state belongs in /health/detailed, which is the readiness
        signal. Do not "fix" this endpoint by making it probe anything.

        Never anything but 200 while the process is up: that is the whole point.
        `no-store` so a cached verdict can never stand in for a live one.
        """
        return JSONResponse(
            content={"status": "healthy"},
            headers={"Cache-Control": "no-store"},
        )

    @app.get("/health/detailed", tags=["health"])
    async def detailed_health_check():
        """READINESS check: per-component status, with a truthful status code.

        This endpoint used to answer HTTP 200 with "healthy" straight through a
        total Redis failure, and 200 with "unhealthy" through a database
        failure - so a monitor watching the status code saw green during an
        outage. Both are fixed here, and the split is hard vs soft dependency,
        not up vs down:

        * Postgres down  -> nothing works. "unhealthy", HTTP 503.
        * Redis down     -> cache misses and a slower site. "degraded", HTTP 200.
        * Task queue down-> jobs backlog, requests are fine. "degraded", HTTP 200.

        Reachable unauthenticated in most deployments, so component failures are
        published as a coarse "error" and the exception text is only LOGGED.
        SQLAlchemy and asyncpg errors routinely carry the database host, port,
        user and name; serving those publicly hands out the shape of the
        internal network the moment anything breaks. The detail is not lost,
        only unpublished.

        NOTE FOR WHOEVER WIRES THIS UP: if your deployment is a SINGLE origin
        with no failover pool, the 503 exists to make monitoring truthful, not
        to shed traffic. Nothing in a deploy script, load balancer or health
        gate may treat it as "pull the box out of service" - with one box that
        turns a degraded site into a dark one. Probe /health for liveness; this
        endpoint is not that.
        """
        health: dict = {"status": "healthy", "components": {}}
        hard_failures: list[str] = []
        soft_failures: list[str] = []

        def record(component: str, detail: str, *, hard: bool) -> None:
            """Log the real error; publish only a redacted verdict.

            Severity tracks the verdict, not the fact of a failure: a soft
            dependency logs WARNING because a monitor polling every minute
            through a Redis outage would otherwise fill the log with ERROR for
            a site that is still serving.
            """
            message = f"Health check: {component} failed: {detail}"
            if hard:
                logger.error(message)
                hard_failures.append(component)
            else:
                logger.warning(message)
                soft_failures.append(component)
            # Redacted on purpose - see the docstring.
            health["components"][component] = "error"

        # Check database - the one hard dependency. Without it no request that
        # reads or writes anything can be served, so this is what decides 503.
        try:
            async with async_engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
            health["components"]["database"] = "ok"

            # Include pool stats (counters only - no connection details)
            health["components"]["database_pool"] = get_pool_stats(
                async_engine.sync_engine
            )
        except Exception as e:
            record("database", str(e), hard=True)

        # Check Redis. "disabled" is a deliberate configuration, not a fault,
        # so it does not degrade anything - only a live Redis that fails does.
        try:
            if cache_service._redis:
                await cache_service._redis.ping()
                health["components"]["redis"] = "ok"
            else:
                health["components"]["redis"] = "disabled"
        except Exception as e:
            record("redis", str(e), hard=False)

        # Check task queue. Same distinction: "not configured" is a choice, a
        # configured pool that is not connected is a fault.
        try:
            from src.services.tasks import task_queue
            if task_queue._pool:
                health["components"]["task_queue"] = "ok"
            else:
                logger.warning("Health check: task_queue failed: pool not connected")
                soft_failures.append("task_queue")
                # Published verbatim to everyone: "disconnected" is a state, not
                # an exception string, so it discloses nothing.
                health["components"]["task_queue"] = "disconnected"
        except ImportError:
            health["components"]["task_queue"] = "not configured"

        if hard_failures:
            health["status"] = "unhealthy"
            status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        elif soft_failures:
            health["status"] = "degraded"
            status_code = status.HTTP_200_OK
        else:
            status_code = status.HTTP_200_OK

        return JSONResponse(
            status_code=status_code,
            content=health,
            headers={"Cache-Control": "no-store"},
        )

    # Include API routers.
    #
    # A failure here is swallowed on purpose: this is a template, and a fork may
    # legitimately strip optional modules, so a missing import must not convert a
    # degraded deploy into a hard outage. But it is logged at ERROR with the full
    # traceback rather than WARNING with one line - an ImportError here silently
    # removes the ENTIRE API surface, which must be loud in monitoring and must
    # name the actual missing module, not just the top-level package.
    try:
        # Include v1 API router with /api/v1 prefix
        from src.api.v1 import v1_router
        app.include_router(v1_router, prefix="/api/v1")
        logger.info("API v1 routers included")
    except ImportError as e:
        logger.error(
            f"Could not import API routers - the ENTIRE /api/v1 surface is "
            f"missing from this process: {e}",
            exc_info=True,
        )

    # Include WebSocket router at root level (outside /api/v1 for cleaner URL)
    try:
        from src.api.websocket import router as websocket_router
        app.include_router(websocket_router)
        logger.info("WebSocket router included")
    except ImportError as e:
        logger.error(
            f"Could not import WebSocket router - realtime endpoints are "
            f"missing from this process: {e}",
            exc_info=True,
        )

    return app


# Create application instance
app = create_application()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host=settings.SERVER_HOST,
        port=settings.SERVER_PORT,
        reload=settings.DEBUG,
        workers=1 if settings.DEBUG else 4,
    )
