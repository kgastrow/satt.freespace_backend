"""
Middleware package for FastAPI application.
"""

from src.middleware.cache_metrics import (
    record_cache_delete,
    record_cache_error,
    record_cache_hit,
    record_cache_miss,
    record_cache_set,
    update_cache_connection_status,
)
from src.middleware.db_metrics import (
    get_pool_stats,
    setup_db_metrics,
)
from src.middleware.metrics import (
    INSTANCE_ID,
    record_auth_failure,
    record_exception,
    setup_metrics,
    update_active_users,
)
from src.middleware.request_response_logging import (
    setup_request_response_logging,
)


__all__ = [
    "setup_metrics",
    "record_auth_failure",
    "record_exception",
    "update_active_users",
    "INSTANCE_ID",
    "setup_db_metrics",
    "get_pool_stats",
    "record_cache_hit",
    "record_cache_miss",
    "record_cache_error",
    "record_cache_set",
    "record_cache_delete",
    "update_cache_connection_status",
    "setup_request_response_logging",
]
