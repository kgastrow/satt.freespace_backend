"""
FastAPI application configuration.
Configuration is loaded from config.json in the project root.
"""

from functools import lru_cache
import json
import logging
import os
import sys
from typing import Optional

from pydantic import BaseModel, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


# ─────────────────────────────────────────────────────────────
# Payment Provider Configuration Models
# ─────────────────────────────────────────────────────────────


class StripeConfig(BaseModel):
    """Stripe-specific system configuration."""

    enabled: bool = False
    secret_key: str = ""
    publishable_key: str = ""
    webhook_secret: str = ""
    api_version: str = "2024-06-20"
    platform_account_id: str = ""  # For Stripe Connect marketplace scenarios


class PayfastConfig(BaseModel):
    """PayFast-specific system configuration (South Africa)."""

    enabled: bool = False
    merchant_id: str = ""
    merchant_key: str = ""
    passphrase: str = ""
    sandbox: bool = True


class PaypalConfig(BaseModel):
    """PayPal-specific system configuration."""

    enabled: bool = False
    client_id: str = ""
    client_secret: str = ""
    sandbox: bool = True


class PaymentsConfig(BaseModel):
    """
    Payment system configuration.

    Provides nested access to payment provider settings:
        settings.payments.default_provider
        settings.payments.stripe.secret_key
        settings.payments.payfast.merchant_id
    """

    default_provider: str = "stripe"
    webhook_tolerance_seconds: int = 300

    # Provider configurations
    stripe: StripeConfig = StripeConfig()
    payfast: PayfastConfig = PayfastConfig()
    paypal: PaypalConfig = PaypalConfig()


class Settings(BaseSettings):
    """Application settings loaded from config.json."""

    model_config = SettingsConfigDict(
        case_sensitive=False,
        extra="ignore",
    )

    # Application
    APP_NAME: str = "Freespace Webapp"
    TEAM_NAME: str = "Your Team"

    # Server
    SERVER_HOST: str = "0.0.0.0"
    SERVER_PORT: int = 8000
    DEBUG: bool = False
    ENABLE_DOCS: bool = True  # Enable OpenAPI docs (/docs, /redoc)
    # ── Public origins ────────────────────────────────────────────────────
    # Two distinct origins, because a link a HUMAN clicks and a URL a MACHINE
    # signs are not the same host once the SPA and the API are served
    # separately. Behind a single origin, set both to the same value.
    #
    # PUBLIC_URL_FRONTEND is the origin that serves the SPA bundle. EVERY URL
    # MAILED TO A USER is built from it, because every one of them is a
    # client-side route in app/frontend/src/router.tsx, not an API route:
    #   - password reset   {FRONTEND}/reset-password  (api/users.py, api/auth.py)
    #   - invitations      {FRONTEND}/register        (api/invitation.py)
    #   - unsubscribe page {FRONTEND}/unsubscribe     (notifications/unsubscribe.py)
    #   - SSO redirect_uri {FRONTEND}/oauth/callback  (api/sso.py fallback)
    # Default is the Vite dev server (app/frontend/vite.config.ts falls back to
    # 5173; .ports.env FRONTEND_PORT overrides it there).
    PUBLIC_URL_FRONTEND: str = "http://localhost:5173"

    # PUBLIC_URL_BACKEND is the origin that serves this FastAPI app under
    # /api/v1. Anything a THIRD-PARTY SYSTEM calls or SIGNS is built from it:
    #   - Twilio webhook signature reconstruction (api/webhooks_notifications.py)
    #     and the status_callback handed to Twilio (notifications/dispatcher.py).
    #     A signature is computed over the exact URL string, so a frontend
    #     origin here fails verification on every callback.
    #   - RFC 8058 one-click unsubscribe POST target
    #     {BACKEND}/api/v1/notifications/unsubscribe/one-click
    #   - local-file download/upload URLs (services/files/local_storage.py,
    #     which appends /api/v1/files/...)
    # Default matches SERVER_PORT; the .ports.env BACKEND_PORT fixup below
    # rewrites the port in this value only.
    PUBLIC_URL_BACKEND: str = "http://localhost:8000"

    # DEPRECATED alias for the two settings above. It meant the frontend origin
    # in some call sites and the backend origin in others, which is why it was
    # split. Setting it (config.json "public_url", or a PUBLIC_URL env var) with
    # neither new key set back-fills BOTH and logs a deprecation warning, so an
    # existing single-origin deployment keeps working unchanged. Its resolved
    # value always mirrors PUBLIC_URL_BACKEND; read the explicit settings
    # instead. New code must not read this field.
    PUBLIC_URL: str = "http://localhost:8000"

    # Trusted client-IP header.
    #
    # Name the request header your CDN/edge OVERWRITES on every request
    # (Cloudflare: "CF-Connecting-IP"; Akamai / CF Enterprise:
    # "True-Client-IP"). That value keys audit records AND the login/2FA
    # brute-force lockout, so getting it wrong is a security bug, not a
    # cosmetic one.
    #
    # Empty by default: the client IP then falls back to the connection peer
    # address, which is correct for local development and for a plain reverse
    # proxy (provided uvicorn's --forwarded-allow-ips names the proxy and not
    # '*'), and merely imprecise behind a CDN.
    #
    # Append-only headers (X-Forwarded-For, Forwarded, X-Forwarded) are
    # REFUSED: a proxy appends to them, so their leftmost value is whatever the
    # client sent and is forgeable. Configuring one aborts startup.
    # See src/core/client_ip.py.
    TRUSTED_CLIENT_IP_HEADER: str = ""

    # Database - PgBouncer (application connections)
    DATABASE_HOST: str = "localhost"
    DATABASE_PORT: int = 6432  # PgBouncer port
    DATABASE_USER: str = "appuser"
    DATABASE_PASSWORD: str = "password"
    DATABASE_NAME: str = "appdb"
    DATABASE_ECHO: bool = False

    # Database - Direct (migrations, admin)
    DATABASE_DIRECT_HOST: str = "localhost"
    DATABASE_DIRECT_PORT: int = 5432  # PostgreSQL port

    # =======================================================================
    # Database Pool Settings (SQLAlchemy-side pooling in front of PgBouncer)
    # =======================================================================
    #
    # These are OPT-IN. With DATABASE_POOL_ENABLED false (the default) the
    # application engine uses NullPool and every setting below except
    # DATABASE_POOL_RECYCLE is inert - NullPool holds no connections, so there
    # is nothing to size, overflow, time out or pre-ping. Set
    # DATABASE_POOL_ENABLED true to switch the application engine to
    # AsyncAdaptedQueuePool, at which point every value below is read.
    # DATABASE_POOL_RECYCLE is always read, by the direct engine.
    #
    # See src/database.py for why the switch is opt-in rather than the default
    # (it requires specific PgBouncer server_reset_query settings) and for the
    # sizing arithmetic you must redo for your own deployment.
    #
    # WARNING - the pool_recycle trap: SQLAlchemy treats ANY pool_recycle value
    # greater than -1 as a live recycle age, so DATABASE_POOL_RECYCLE = 0 means
    # "recycle on every checkout". That silently turns a QueuePool back into a
    # NullPool with extra bookkeeping, with no error and no log line anywhere.
    # Use -1 to disable recycling; never 0.
    DATABASE_POOL_ENABLED: bool = False
    DATABASE_POOL_SIZE: int = 2
    DATABASE_MAX_OVERFLOW: int = 1
    DATABASE_POOL_TIMEOUT: int = 30
    DATABASE_POOL_RECYCLE: int = 1800
    DATABASE_POOL_PRE_PING: bool = True

    # Database Statement Timeout (prevents runaway queries from holding locks)
    DB_STATEMENT_TIMEOUT_MS: int = 30000  # 30 seconds

    # JWT Authentication
    JWT_SECRET: str = "your-secret-key-change-in-production"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_SECONDS: int = 900  # 15 minutes
    REFRESH_TOKEN_EXPIRE_SECONDS: int = 2592000  # 30 days
    IMPERSONATION_TOKEN_EXPIRE_SECONDS: int = 900  # 15 minutes - shorter for security

    # Cookie Configuration (for httpOnly refresh token delivery)
    COOKIE_DOMAIN: str = ""  # Empty = use request domain
    COOKIE_SECURE: bool = True  # False for local dev without HTTPS
    COOKIE_SAMESITE: str = "lax"
    COOKIE_PATH: str = "/api/v1"

    # Encryption (for sensitive data like API keys, credentials)
    # Generate with: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    ENCRYPTION_KEY: str = ""  # Primary encryption key (required in production)
    ENCRYPTION_KEY_PREVIOUS: str = ""  # Previous key for rotation (decrypt only)

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # Cache TTLs
    CACHE_ENABLED: bool = True
    CACHE_JWT_TTL: int = 3600  # 1 hour max
    CACHE_USER_TTL: int = 300  # 5 minutes
    CACHE_ORG_TTL: int = 300  # 5 minutes
    CACHE_ROLES_TTL: int = 60  # 1 minute
    # How long the cache backend stays marked unavailable after a Redis error
    # before the next call re-probes it. The cache never latches off
    # permanently: one blip must not disable caching for the life of the
    # process. See AsyncCacheService._mark_unavailable.
    CACHE_UNAVAILABLE_COOLDOWN: int = 10  # seconds

    # Redis Connection Pool
    REDIS_POOL_SIZE: int = 20  # Max connections in Redis pool

    # Email
    EMAIL_SERVER: str = "smtp.example.com"
    EMAIL_PORT: int = 587
    EMAIL_USERNAME: str = ""
    EMAIL_PASSWORD: str = ""
    EMAIL_USE_TLS: bool = True
    EMAIL_USE_SSL: bool = False
    EMAIL_SENDER: str = "noreply@example.com"

    # ARQ Background Jobs
    ARQ_REDIS_URL: str = "redis://localhost:6379/1"

    # Rate Limiting
    RATE_LIMIT_ENABLED: bool = True
    RATE_LIMIT_DEFAULT: str = "100/minute"
    RATE_LIMIT_LOGIN: str = "5/minute"
    RATE_LIMIT_OTP_VERIFY: str = "5/minute"  # Strict limit for OTP verification
    RATE_LIMIT_OTP_SEND: str = "1/minute"  # Limit OTP send requests
    RATE_LIMIT_METRICS: str = (
        "60/minute"  # Limit metrics endpoint to prevent reconnaissance
    )
    RATE_LIMIT_EMAIL_TEST: str = "5/5minute"  # 5 per 5 minutes to prevent abuse

    # Logging
    LOG_LEVEL: str = "INFO"
    LOG_FILE: str = "app.log"

    # Request/Response Logging
    REQUEST_LOGGING_ENABLED: bool = False
    REQUEST_LOGGING_FILE: str = "request_response.log"
    REQUEST_LOGGING_EXCLUDED_PATHS: str = "/health,/metrics,/docs,/redoc,/openapi.json"
    REQUEST_LOGGING_MAX_BODY_SIZE: int = 10240  # 10KB
    REQUEST_LOGGING_DB_ENABLED: bool = (
        False  # Store logs in database (in addition to file)
    )

    # Request size limit (default 100MB - matches default max file size)
    MAX_REQUEST_BODY_BYTES: int = 104857600  # 100MB

    # Metrics
    METRICS_ENABLED: bool = True
    METRICS_ENDPOINT: str = "/metrics"
    METRICS_EXCLUDED_PATHS: str = "/metrics,/health,/docs,/redoc,/openapi.json"
    METRICS_SLOW_REQUEST_THRESHOLD: float = 1.0  # seconds
    METRICS_SLOW_QUERY_THRESHOLD: float = 0.1  # seconds (100ms)
    METRICS_USER_ACTIVITY_WINDOW: int = 300  # 5 minutes
    METRICS_INSTANCE_ID: str = ""  # Auto-generated if empty

    # Testing
    TESTING: bool = False

    # CORS Configuration
    # Comma-separated list of allowed origins (e.g., "https://app.example.com,https://admin.example.com")
    # Use "*" only for development - in production, specify exact origins
    CORS_ALLOWED_ORIGINS: str = "*"
    CORS_ALLOWED_METHODS: str = "GET,POST,PUT,PATCH,DELETE,OPTIONS"
    CORS_ALLOWED_HEADERS: str = "Authorization,Content-Type,X-API-Key,X-Request-ID,X-App-Commit"

    # API Documentation Authentication
    API_DOCS_USERNAME: str = "freespace"
    API_DOCS_PASSWORD: str = "freespace"

    # AWS
    AWS_REGION: str = "us-east-1"
    AWS_ACCESS_KEY_ID: str = ""
    AWS_SECRET_ACCESS_KEY: str = ""

    # S3
    S3_BUCKET: str = "freespace-files"
    S3_REGION: str = "us-east-1"
    S3_ENDPOINT_URL: str = ""

    # Local Storage (fallback when S3 not configured)
    LOCAL_STORAGE_PATH: str = "./uploads"
    LOCAL_STORAGE_ENABLED: bool = False  # Auto-enabled when S3 not configured

    # GeoIP Database (MaxMind GeoLite2-City)
    GEOIP_DATABASE_PATH: str = "./data/GeoLite2-City.mmdb"
    GEOIP_ENABLED: bool = True

    # Twilio
    TWILIO_ACCOUNT_SID: str = ""
    TWILIO_AUTH_TOKEN: str = ""
    TWILIO_SMS_FROM: str = ""
    TWILIO_WHATSAPP_FROM: str = "whatsapp:+14155238886"

    # Web Push (VAPID)
    #
    # Startup defaults only. The effective keypair is resolved per request from
    # the SystemConfig store first, falling back to these - see
    # services/notifications/web_push_config.py. Leaving them blank leaves Web
    # Push dormant: /notifications/push/vapid-key answers 503 and no client ever
    # prompts. Generate a pair with POST /notifications/push/providers/web-push/generate
    # or see docs/deploy-web-push.md.
    VAPID_PUBLIC_KEY: str = ""
    VAPID_PRIVATE_KEY: str = ""
    VAPID_SUBJECT: str = ""

    # Notifications
    DEFAULT_SMS_PROVIDER: str = "aws_sns"
    DEFAULT_WHATSAPP_PROVIDER: str = "twilio"
    BULK_BATCH_SIZE: int = 100
    BULK_RATE_LIMIT_PER_SECOND: int = 50
    UNSUBSCRIBE_TOKEN_EXPIRY_DAYS: int = 30

    # Template Drift Detection
    TEMPLATE_REPO_URL: str = ""
    TEMPLATE_REPO_LOCAL_PATH: str = "./data/template-repo"

    # SSO Configuration
    GOOGLE_CLIENT_ID: str = ""
    GOOGLE_CLIENT_SECRET: str = ""
    GOOGLE_REDIRECT_URI: str = ""

    # Payment Configuration (nested model)
    payments: PaymentsConfig = PaymentsConfig()

    @model_validator(mode="after")
    def _resolve_public_url_aliases(self) -> "Settings":
        """Back-fill the split public origins from the deprecated PUBLIC_URL.

        PUBLIC_URL used to mean the frontend origin for emailed links AND the
        backend origin for webhook signatures. Splitting it must not silently
        re-point an existing deployment's password-reset emails, so a config
        that still sets only the old key keeps its exact previous behaviour
        (both origins equal to it) and is told, loudly, what to set instead.
        """
        provided = self.model_fields_set
        legacy_set = "PUBLIC_URL" in provided
        frontend_set = "PUBLIC_URL_FRONTEND" in provided
        backend_set = "PUBLIC_URL_BACKEND" in provided

        if legacy_set and not (frontend_set and backend_set):
            if not frontend_set:
                self.PUBLIC_URL_FRONTEND = self.PUBLIC_URL
            if not backend_set:
                self.PUBLIC_URL_BACKEND = self.PUBLIC_URL
            logging.getLogger(__name__).warning(
                "DEPRECATED: 'public_url' (PUBLIC_URL) is deprecated and will "
                "be removed. It has been applied to both PUBLIC_URL_FRONTEND "
                "and PUBLIC_URL_BACKEND (%s). Set 'public_url_frontend' (the "
                "origin serving the SPA, used for password-reset, invitation, "
                "unsubscribe and SSO redirect links) and 'public_url_backend' "
                "(the origin serving /api/v1, used for webhook signature "
                "verification and one-click unsubscribe) explicitly. Behind a "
                "single origin, set both to the same value.",
                self.PUBLIC_URL,
            )

        # Any straggler still reading the deprecated field gets the BACKEND
        # origin: every remaining in-tree reader of it (local file storage URLs)
        # builds an /api/v1 path. The assignment would otherwise mark the field
        # as explicitly set, so model_fields_set is restored - callers use it to
        # tell a configured value from a default.
        self.PUBLIC_URL = self.PUBLIC_URL_BACKEND
        if not legacy_set:
            self.__pydantic_fields_set__.discard("PUBLIC_URL")
        return self

    # Convenience properties for backward compatibility
    @property
    def PAYMENTS_DEFAULT_PROVIDER(self) -> str:
        return self.payments.default_provider

    @property
    def PAYMENTS_WEBHOOK_TOLERANCE_SECONDS(self) -> int:
        return self.payments.webhook_tolerance_seconds

    @property
    def STRIPE_ENABLED(self) -> bool:
        return self.payments.stripe.enabled

    @property
    def STRIPE_SECRET_KEY(self) -> str:
        return self.payments.stripe.secret_key

    @property
    def STRIPE_PUBLISHABLE_KEY(self) -> str:
        return self.payments.stripe.publishable_key

    @property
    def STRIPE_WEBHOOK_SECRET(self) -> str:
        return self.payments.stripe.webhook_secret

    @property
    def STRIPE_API_VERSION(self) -> str:
        return self.payments.stripe.api_version

    @property
    def STRIPE_PLATFORM_ACCOUNT_ID(self) -> str:
        return self.payments.stripe.platform_account_id

    @property
    def PAYFAST_ENABLED(self) -> bool:
        return self.payments.payfast.enabled

    @property
    def PAYFAST_MERCHANT_ID(self) -> str:
        return self.payments.payfast.merchant_id

    @property
    def PAYFAST_MERCHANT_KEY(self) -> str:
        return self.payments.payfast.merchant_key

    @property
    def PAYFAST_PASSPHRASE(self) -> str:
        return self.payments.payfast.passphrase

    @property
    def PAYFAST_SANDBOX(self) -> bool:
        return self.payments.payfast.sandbox

    @property
    def PAYPAL_ENABLED(self) -> bool:
        return self.payments.paypal.enabled

    @property
    def PAYPAL_CLIENT_ID(self) -> str:
        return self.payments.paypal.client_id

    @property
    def PAYPAL_CLIENT_SECRET(self) -> str:
        return self.payments.paypal.client_secret

    @property
    def PAYPAL_SANDBOX(self) -> bool:
        return self.payments.paypal.sandbox

    @property
    def DATABASE_URL(self) -> str:
        """Async database URL via PgBouncer."""
        return (
            f"postgresql+asyncpg://{self.DATABASE_USER}:{self.DATABASE_PASSWORD}"
            f"@{self.DATABASE_HOST}:{self.DATABASE_PORT}/{self.DATABASE_NAME}"
        )

    @property
    def DATABASE_URL_SYNC(self) -> str:
        """Sync database URL for Alembic (direct to PostgreSQL)."""
        return (
            f"postgresql+psycopg2://{self.DATABASE_USER}:{self.DATABASE_PASSWORD}"
            f"@{self.DATABASE_DIRECT_HOST}:{self.DATABASE_DIRECT_PORT}/{self.DATABASE_NAME}"
        )

    @property
    def DATABASE_URL_DIRECT(self) -> str:
        """Direct async database URL (bypassing PgBouncer)."""
        return (
            f"postgresql+asyncpg://{self.DATABASE_USER}:{self.DATABASE_PASSWORD}"
            f"@{self.DATABASE_DIRECT_HOST}:{self.DATABASE_DIRECT_PORT}/{self.DATABASE_NAME}"
        )

    @classmethod
    def from_json_file(cls, config_path: Optional[str] = None) -> "Settings":
        """
        Load settings from config.json file.
        This is the primary configuration source for the application.
        """
        if config_path is None:
            base_dir = os.path.dirname(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            )
            config_path = os.path.join(base_dir, "config.json")

        config_values = {}

        if os.path.exists(config_path):
            try:
                with open(config_path) as f:
                    config_data = json.load(f)

                # Map JSON config structure to Settings fields
                if "app" in config_data:
                    app = config_data["app"]
                    config_values["APP_NAME"] = app.get("name", "Freespace Webapp")
                    config_values["TEAM_NAME"] = app.get("team_name", "Your Team")

                if "server" in config_data:
                    server = config_data["server"]
                    config_values["SERVER_HOST"] = server.get("host", "0.0.0.0")
                    config_values["SERVER_PORT"] = server.get("port", 8000)
                    if "debug" in server:
                        config_values["DEBUG"] = server.get("debug", False)
                    if "enable_docs" in server:
                        config_values["ENABLE_DOCS"] = server.get("enable_docs", True)
                    if "trusted_client_ip_header" in server:
                        config_values["TRUSTED_CLIENT_IP_HEADER"] = server.get(
                            "trusted_client_ip_header", ""
                        )
                    if "max_request_body_bytes" in server:
                        config_values["MAX_REQUEST_BODY_BYTES"] = server.get(
                            "max_request_body_bytes", 104857600
                        )

                if "database" in config_data:
                    db = config_data["database"]
                    # For PgBouncer setup, use pgbouncer_port for app, port for direct
                    config_values["DATABASE_HOST"] = db.get("host", "localhost")
                    config_values["DATABASE_PORT"] = db.get(
                        "pgbouncer_port", db.get("port", 6432)
                    )
                    config_values["DATABASE_USER"] = db.get("user", "appuser")
                    config_values["DATABASE_PASSWORD"] = db.get("password", "password")
                    config_values["DATABASE_NAME"] = db.get("db", "appdb")
                    config_values["DATABASE_DIRECT_HOST"] = db.get("host", "localhost")
                    config_values["DATABASE_DIRECT_PORT"] = db.get("port", 5432)
                    if "echo" in db:
                        config_values["DATABASE_ECHO"] = db.get("echo", False)

                    if "pooling" in db:
                        pool = db["pooling"]
                        config_values["DATABASE_POOL_ENABLED"] = pool.get(
                            "enabled", False
                        )
                        config_values["DATABASE_POOL_SIZE"] = pool.get("pool_size", 2)
                        config_values["DATABASE_MAX_OVERFLOW"] = pool.get(
                            "max_overflow", 1
                        )
                        config_values["DATABASE_POOL_TIMEOUT"] = pool.get(
                            "pool_timeout", 30
                        )
                        config_values["DATABASE_POOL_RECYCLE"] = pool.get(
                            "pool_recycle", 1800
                        )
                        config_values["DATABASE_POOL_PRE_PING"] = pool.get(
                            "pool_pre_ping", True
                        )

                    if "statement_timeout_ms" in db:
                        config_values["DB_STATEMENT_TIMEOUT_MS"] = db.get(
                            "statement_timeout_ms", 30000
                        )

                # Split public origins. "public_url" is the deprecated
                # single-origin key; the model validator back-fills whichever
                # of the two it was not given and warns. Only keys actually
                # present are forwarded, so model_fields_set can tell an
                # explicit setting apart from a default.
                if "public_url_frontend" in config_data:
                    config_values["PUBLIC_URL_FRONTEND"] = config_data[
                        "public_url_frontend"
                    ]
                if "public_url_backend" in config_data:
                    config_values["PUBLIC_URL_BACKEND"] = config_data[
                        "public_url_backend"
                    ]
                if "public_url" in config_data:
                    config_values["PUBLIC_URL"] = config_data["public_url"]

                if "jwt" in config_data:
                    jwt_config = config_data["jwt"]
                    config_values["JWT_SECRET"] = jwt_config.get("secret", "")
                    if "algorithm" in jwt_config:
                        config_values["JWT_ALGORITHM"] = jwt_config.get(
                            "algorithm", "HS256"
                        )
                    config_values["ACCESS_TOKEN_EXPIRE_SECONDS"] = jwt_config.get(
                        "access_token_expiry", 86400
                    )
                    config_values["REFRESH_TOKEN_EXPIRE_SECONDS"] = jwt_config.get(
                        "refresh_token_expiry", 2592000
                    )

                if "encryption" in config_data:
                    encryption_config = config_data["encryption"]
                    config_values["ENCRYPTION_KEY"] = encryption_config.get("key", "")
                    config_values["ENCRYPTION_KEY_PREVIOUS"] = encryption_config.get(
                        "key_previous", ""
                    )

                if "email" in config_data:
                    email = config_data["email"]
                    config_values["EMAIL_SERVER"] = email.get("server", "")
                    config_values["EMAIL_PORT"] = email.get("port", 587)
                    config_values["EMAIL_USERNAME"] = email.get("username", "")
                    config_values["EMAIL_PASSWORD"] = email.get("password", "")
                    config_values["EMAIL_USE_TLS"] = email.get("use_tls", True)
                    config_values["EMAIL_USE_SSL"] = email.get("use_ssl", False)
                    config_values["EMAIL_SENDER"] = email.get("sender", "")

                if "redis" in config_data:
                    redis_config = config_data["redis"]
                    # Env vars take precedence over config.json for Redis URLs,
                    # allowing Playwright e2e tests and ADW worktrees to override
                    # the database for isolation.
                    if not os.environ.get("REDIS_URL"):
                        config_values["REDIS_URL"] = redis_config.get(
                            "url", "redis://localhost:6379/0"
                        )
                    if "arq_url" in redis_config and not os.environ.get("ARQ_REDIS_URL"):
                        config_values["ARQ_REDIS_URL"] = redis_config.get(
                            "arq_url", "redis://localhost:6379/1"
                        )
                    if "pool_size" in redis_config:
                        config_values["REDIS_POOL_SIZE"] = redis_config.get(
                            "pool_size", 20
                        )

                if "cache" in config_data:
                    cache = config_data["cache"]
                    if "enabled" in cache:
                        config_values["CACHE_ENABLED"] = cache.get("enabled", True)
                    if "jwt_ttl" in cache:
                        config_values["CACHE_JWT_TTL"] = cache.get("jwt_ttl", 3600)
                    if "user_ttl" in cache:
                        config_values["CACHE_USER_TTL"] = cache.get("user_ttl", 300)
                    if "org_ttl" in cache:
                        config_values["CACHE_ORG_TTL"] = cache.get("org_ttl", 300)
                    if "roles_ttl" in cache:
                        config_values["CACHE_ROLES_TTL"] = cache.get("roles_ttl", 60)
                    if "unavailable_cooldown" in cache:
                        config_values["CACHE_UNAVAILABLE_COOLDOWN"] = cache.get(
                            "unavailable_cooldown", 10
                        )

                if "rate_limit" in config_data:
                    rate_limit = config_data["rate_limit"]
                    if "enabled" in rate_limit and not os.environ.get("RATE_LIMIT_ENABLED"):
                        config_values["RATE_LIMIT_ENABLED"] = rate_limit.get(
                            "enabled", True
                        )
                    if "default" in rate_limit:
                        config_values["RATE_LIMIT_DEFAULT"] = rate_limit.get(
                            "default", "100/minute"
                        )
                    if "login" in rate_limit:
                        config_values["RATE_LIMIT_LOGIN"] = rate_limit.get(
                            "login", "5/minute"
                        )
                    if "otp_verify" in rate_limit:
                        config_values["RATE_LIMIT_OTP_VERIFY"] = rate_limit.get(
                            "otp_verify", "5/minute"
                        )
                    if "otp_send" in rate_limit:
                        config_values["RATE_LIMIT_OTP_SEND"] = rate_limit.get(
                            "otp_send", "3/minute"
                        )

                if "logging" in config_data:
                    logging_config = config_data["logging"]
                    config_values["LOG_LEVEL"] = logging_config.get("level", "INFO")
                    config_values["LOG_FILE"] = logging_config.get(
                        "filename", "app.log"
                    )

                if "request_logging" in config_data:
                    request_logging = config_data["request_logging"]
                    if "enabled" in request_logging:
                        config_values["REQUEST_LOGGING_ENABLED"] = request_logging.get(
                            "enabled", False
                        )
                    if "filename" in request_logging:
                        config_values["REQUEST_LOGGING_FILE"] = request_logging.get(
                            "filename", "request_response.log"
                        )
                    if "excluded_paths" in request_logging:
                        config_values["REQUEST_LOGGING_EXCLUDED_PATHS"] = (
                            request_logging.get(
                                "excluded_paths",
                                "/health,/metrics,/docs,/redoc,/openapi.json",
                            )
                        )
                    if "max_body_size" in request_logging:
                        config_values["REQUEST_LOGGING_MAX_BODY_SIZE"] = (
                            request_logging.get("max_body_size", 10240)
                        )
                    if "db_enabled" in request_logging:
                        config_values["REQUEST_LOGGING_DB_ENABLED"] = (
                            request_logging.get("db_enabled", False)
                        )

                if "metrics" in config_data:
                    metrics = config_data["metrics"]
                    if "enabled" in metrics:
                        config_values["METRICS_ENABLED"] = metrics.get("enabled", True)
                    if "endpoint" in metrics:
                        config_values["METRICS_ENDPOINT"] = metrics.get(
                            "endpoint", "/metrics"
                        )
                    if "excluded_paths" in metrics:
                        config_values["METRICS_EXCLUDED_PATHS"] = metrics.get(
                            "excluded_paths", ""
                        )
                    if "slow_request_threshold" in metrics:
                        config_values["METRICS_SLOW_REQUEST_THRESHOLD"] = metrics.get(
                            "slow_request_threshold", 1.0
                        )
                    if "slow_query_threshold" in metrics:
                        config_values["METRICS_SLOW_QUERY_THRESHOLD"] = metrics.get(
                            "slow_query_threshold", 0.1
                        )
                    if "user_activity_window" in metrics:
                        config_values["METRICS_USER_ACTIVITY_WINDOW"] = metrics.get(
                            "user_activity_window", 300
                        )
                    if "instance_id" in metrics:
                        config_values["METRICS_INSTANCE_ID"] = metrics.get(
                            "instance_id", ""
                        )

                if "aws" in config_data:
                    aws = config_data["aws"]
                    config_values["AWS_REGION"] = aws.get("region", "us-east-1")
                    config_values["AWS_ACCESS_KEY_ID"] = aws.get("access_key_id", "")
                    config_values["AWS_SECRET_ACCESS_KEY"] = aws.get(
                        "secret_access_key", ""
                    )

                if "s3" in config_data:
                    s3 = config_data["s3"]
                    config_values["S3_BUCKET"] = s3.get("bucket", "freespace-files")
                    config_values["S3_REGION"] = s3.get("region", "us-east-1")
                    config_values["S3_ENDPOINT_URL"] = s3.get("endpoint_url", "")

                if "local_storage" in config_data:
                    local = config_data["local_storage"]
                    config_values["LOCAL_STORAGE_PATH"] = local.get("path", "./uploads")
                    config_values["LOCAL_STORAGE_ENABLED"] = local.get("enabled", False)

                if "twilio" in config_data:
                    twilio = config_data["twilio"]
                    config_values["TWILIO_ACCOUNT_SID"] = twilio.get("account_sid", "")
                    config_values["TWILIO_AUTH_TOKEN"] = twilio.get("auth_token", "")
                    config_values["TWILIO_SMS_FROM"] = twilio.get("sms_from", "")
                    config_values["TWILIO_WHATSAPP_FROM"] = twilio.get(
                        "whatsapp_from", "whatsapp:+14155238886"
                    )

                if "web_push" in config_data:
                    web_push = config_data["web_push"]
                    config_values["VAPID_PUBLIC_KEY"] = web_push.get("public_key", "")
                    config_values["VAPID_PRIVATE_KEY"] = web_push.get("private_key", "")
                    config_values["VAPID_SUBJECT"] = web_push.get("subject", "")

                if "notifications" in config_data:
                    notif = config_data["notifications"]
                    config_values["DEFAULT_SMS_PROVIDER"] = notif.get(
                        "default_sms_provider", "aws_sns"
                    )
                    config_values["DEFAULT_WHATSAPP_PROVIDER"] = notif.get(
                        "default_whatsapp_provider", "twilio"
                    )
                    config_values["BULK_BATCH_SIZE"] = notif.get("bulk_batch_size", 100)
                    config_values["BULK_RATE_LIMIT_PER_SECOND"] = notif.get(
                        "bulk_rate_limit_per_second", 50
                    )
                    config_values["UNSUBSCRIBE_TOKEN_EXPIRY_DAYS"] = notif.get(
                        "unsubscribe_token_expiry_days", 30
                    )

                if "api_docs" in config_data:
                    api_docs = config_data["api_docs"]
                    config_values["API_DOCS_USERNAME"] = api_docs.get(
                        "username", "freespace"
                    )
                    config_values["API_DOCS_PASSWORD"] = api_docs.get(
                        "password", "freespace"
                    )

                if "cors" in config_data:
                    cors = config_data["cors"]
                    if "allowed_origins" in cors and not os.environ.get("CORS_ALLOWED_ORIGINS"):
                        config_values["CORS_ALLOWED_ORIGINS"] = cors.get(
                            "allowed_origins", "*"
                        )
                    if "allowed_methods" in cors:
                        config_values["CORS_ALLOWED_METHODS"] = cors.get(
                            "allowed_methods", "GET,POST,PUT,PATCH,DELETE,OPTIONS"
                        )
                    if "allowed_headers" in cors:
                        config_values["CORS_ALLOWED_HEADERS"] = cors.get(
                            "allowed_headers",
                            "Authorization,Content-Type,X-API-Key,X-Request-ID,X-App-Commit",
                        )

                if "template_repo" in config_data:
                    template_repo = config_data["template_repo"]
                    if "url" in template_repo:
                        config_values["TEMPLATE_REPO_URL"] = template_repo.get(
                            "url", ""
                        )
                    if "local_path" in template_repo:
                        config_values["TEMPLATE_REPO_LOCAL_PATH"] = template_repo.get(
                            "local_path", "./data/template-repo"
                        )

                if "sso" in config_data:
                    sso = config_data["sso"]
                    if "google" in sso:
                        google = sso["google"]
                        config_values["GOOGLE_CLIENT_ID"] = google.get("client_id", "")
                        config_values["GOOGLE_CLIENT_SECRET"] = google.get(
                            "client_secret", ""
                        )
                        config_values["GOOGLE_REDIRECT_URI"] = google.get(
                            "redirect_uri", ""
                        )

                if "cookies" in config_data:
                    cookies = config_data["cookies"]
                    if "domain" in cookies:
                        config_values["COOKIE_DOMAIN"] = cookies.get("domain", "")
                    if "secure" in cookies and not os.environ.get("COOKIE_SECURE"):
                        config_values["COOKIE_SECURE"] = cookies.get("secure", True)
                    if "samesite" in cookies:
                        config_values["COOKIE_SAMESITE"] = cookies.get(
                            "samesite", "lax"
                        )
                    if "path" in cookies:
                        config_values["COOKIE_PATH"] = cookies.get(
                            "path", "/api/v1/auth"
                        )

                if "testing" in config_data:
                    config_values["TESTING"] = config_data.get("testing", False)

                if "payments" in config_data:
                    payments_data = config_data["payments"]

                    # Build nested PaymentsConfig from config.json
                    stripe_config = StripeConfig()
                    if "stripe" in payments_data:
                        stripe_data = payments_data["stripe"]
                        stripe_config = StripeConfig(
                            enabled=stripe_data.get("enabled", False),
                            secret_key=stripe_data.get("secret_key", ""),
                            publishable_key=stripe_data.get("publishable_key", ""),
                            webhook_secret=stripe_data.get("webhook_secret", ""),
                            api_version=stripe_data.get("api_version", "2024-06-20"),
                            platform_account_id=stripe_data.get(
                                "platform_account_id", ""
                            ),
                        )

                    payfast_config = PayfastConfig()
                    if "payfast" in payments_data:
                        payfast_data = payments_data["payfast"]
                        payfast_config = PayfastConfig(
                            enabled=payfast_data.get("enabled", False),
                            merchant_id=payfast_data.get("merchant_id", ""),
                            merchant_key=payfast_data.get("merchant_key", ""),
                            passphrase=payfast_data.get("passphrase", ""),
                            sandbox=payfast_data.get("sandbox", True),
                        )

                    paypal_config = PaypalConfig()
                    if "paypal" in payments_data:
                        paypal_data = payments_data["paypal"]
                        paypal_config = PaypalConfig(
                            enabled=paypal_data.get("enabled", False),
                            client_id=paypal_data.get("client_id", ""),
                            client_secret=paypal_data.get("client_secret", ""),
                            sandbox=paypal_data.get("sandbox", True),
                        )

                    config_values["payments"] = PaymentsConfig(
                        default_provider=payments_data.get(
                            "default_provider", "stripe"
                        ),
                        webhook_tolerance_seconds=payments_data.get(
                            "webhook_tolerance_seconds", 300
                        ),
                        stripe=stripe_config,
                        payfast=payfast_config,
                        paypal=paypal_config,
                    )

            except (OSError, json.JSONDecodeError) as e:
                print(f"Warning: Could not load config.json: {e}")

        # Check for .ports.env override (in project root, two levels up from config.json)
        base_dir = os.path.dirname(config_path)
        ports_env_path = os.path.join(base_dir, "..", "..", ".ports.env")
        if os.path.exists(ports_env_path):
            try:
                with open(ports_env_path) as f:
                    for line in f:
                        line = line.strip()
                        if line.startswith("BACKEND_PORT="):
                            port_str = line.split("=", 1)[1].strip()
                            if port_str.isdigit():
                                config_values["SERVER_PORT"] = int(port_str)
                                # BACKEND_PORT moves the backend origin only.
                                # PUBLIC_URL_FRONTEND is deliberately excluded:
                                # rewriting :8000 there would corrupt a frontend
                                # origin that legitimately runs on 8000, and the
                                # frontend port is FRONTEND_PORT, not this one.
                                # PUBLIC_URL is still rewritten because it is the
                                # deprecated alias a pre-split config.json sets,
                                # and it back-fills the backend origin.
                                for key in ("PUBLIC_URL_BACKEND", "PUBLIC_URL"):
                                    if key in config_values:
                                        origin = config_values[key]
                                        if ":8000" in origin:
                                            config_values[key] = origin.replace(
                                                ":8000", f":{port_str}"
                                            )
            except OSError:
                pass  # Ignore errors reading .ports.env

        # Create settings with values from config.json
        return cls(**{k: v for k, v in config_values.items() if v is not None})


@lru_cache
def get_settings() -> Settings:
    """
    Get cached settings instance.
    Loads configuration from config.json in the project root.
    """
    # Check if we're in test mode
    if "pytest" in sys.modules:
        return Settings(
            TESTING=True,
            DATABASE_HOST="localhost",
            DATABASE_PORT=5432,  # Direct connection for tests
            DATABASE_DIRECT_PORT=5432,
            JWT_SECRET="test_secret_key_for_testing",
            REDIS_URL="redis://localhost:6379/14",  # Use DB 14 for unit tests (DB 15+ reserved for e2e)
            CACHE_ENABLED=False,  # Disable caching in tests by default
            COOKIE_SECURE=False,  # No HTTPS in tests
        )

    # Try to load from config.json with env var overrides
    return Settings.from_json_file()


# Global settings instance
settings = get_settings()
