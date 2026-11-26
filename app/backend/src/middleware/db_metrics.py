"""
Database query instrumentation for Prometheus metrics.
Uses SQLAlchemy event hooks to track query performance.
"""

import time

from prometheus_client import Counter, Gauge, Histogram
from sqlalchemy import event
from sqlalchemy.engine import Engine
from sqlalchemy.pool import Pool

from src.core.config import settings
from src.logger.logger import Logger as logger


# ==================== Database Metrics ====================

DB_QUERIES_TOTAL = Counter(
    "db_queries_total",
    "Total database queries executed",
    ["operation"],
)

DB_QUERY_DURATION_SECONDS = Histogram(
    "db_query_duration_seconds",
    "Database query duration in seconds",
    ["operation"],
    buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5],
)

DB_SLOW_QUERIES_TOTAL = Counter(
    "db_slow_queries_total",
    "Database queries exceeding slow threshold",
    ["operation"],
)

DB_QUERY_ERRORS_TOTAL = Counter(
    "db_query_errors_total",
    "Database query errors",
    ["operation", "error_type"],
)

DB_CONNECTION_POOL_SIZE = Gauge(
    "db_connection_pool_size",
    "Database connection pool size",
    ["pool_name"],
)

DB_CONNECTIONS_CHECKED_OUT = Gauge(
    "db_connections_checked_out",
    "Database connections currently in use",
    ["pool_name"],
)

DB_CONNECTIONS_OVERFLOW = Gauge(
    "db_connections_overflow",
    "Database connections in overflow",
    ["pool_name"],
)

DB_CONNECTION_CHECKOUT_TIME_SECONDS = Histogram(
    "db_connection_checkout_time_seconds",
    "Time to acquire a database connection",
    ["pool_name"],
    buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0],
)

DB_TRANSACTIONS_TOTAL = Counter(
    "db_transactions_total",
    "Total database transactions",
    ["status"],  # committed, rolled_back
)


# ==================== Query Timing Storage ====================

# Store query start times in connection info (thread-local via connection)
QUERY_START_KEY = "_metrics_query_start"
CHECKOUT_START_KEY = "_metrics_checkout_start"


# ==================== Event Handlers ====================


def _extract_operation(statement: str) -> str:
    """Extract the operation type from a SQL statement."""
    if not statement:
        return "UNKNOWN"

    # Get first word and uppercase
    first_word = (
        statement.strip().split()[0].upper() if statement.strip() else "UNKNOWN"
    )

    # Normalize to common operations
    if first_word in ("SELECT", "INSERT", "UPDATE", "DELETE", "WITH"):
        return first_word
    elif first_word in ("BEGIN", "START"):
        return "BEGIN"
    elif first_word in ("COMMIT",):
        return "COMMIT"
    elif first_word in ("ROLLBACK",):
        return "ROLLBACK"
    elif first_word in ("CREATE", "ALTER", "DROP", "TRUNCATE"):
        return "DDL"
    else:
        return "OTHER"


def before_cursor_execute(conn, cursor, statement, parameters, context, executemany):
    """Record query start time before execution."""
    conn.info[QUERY_START_KEY] = time.perf_counter()


def after_cursor_execute(conn, cursor, statement, parameters, context, executemany):
    """Record query metrics after execution."""
    start_time = conn.info.pop(QUERY_START_KEY, None)
    if start_time is None:
        return

    duration = time.perf_counter() - start_time
    operation = _extract_operation(statement)

    # Record metrics
    DB_QUERIES_TOTAL.labels(operation=operation).inc()
    DB_QUERY_DURATION_SECONDS.labels(operation=operation).observe(duration)

    # Track slow queries
    if duration > settings.METRICS_SLOW_QUERY_THRESHOLD:
        DB_SLOW_QUERIES_TOTAL.labels(operation=operation).inc()
        logger.warning(
            f"Slow query detected: {operation} took {duration:.3f}s "
            f"(threshold: {settings.METRICS_SLOW_QUERY_THRESHOLD}s)"
        )


def handle_error(exception_context):
    """Record query errors."""
    statement = exception_context.statement
    operation = _extract_operation(statement) if statement else "UNKNOWN"
    error_type = type(exception_context.original_exception).__name__

    DB_QUERY_ERRORS_TOTAL.labels(
        operation=operation,
        error_type=error_type,
    ).inc()


def on_checkout(dbapi_connection, connection_record, connection_proxy):
    """Record connection checkout time."""
    connection_record.info[CHECKOUT_START_KEY] = time.perf_counter()


def on_checkin(dbapi_connection, connection_record):
    """Record connection pool metrics on checkin."""
    start_time = connection_record.info.pop(CHECKOUT_START_KEY, None)
    if start_time:
        duration = time.perf_counter() - start_time
        DB_CONNECTION_CHECKOUT_TIME_SECONDS.labels(pool_name="default").observe(
            duration
        )


def update_pool_metrics(pool: Pool, pool_name: str = "default"):
    """Update connection pool gauge metrics."""
    # NullPool doesn't have these methods (PgBouncer handles pooling)
    # Use getattr for pool methods that aren't in the base Pool type stubs
    # but exist on concrete pool implementations like QueuePool
    size_fn = getattr(pool, "size", None)
    if size_fn is None:
        return
    checkedout_fn = getattr(pool, "checkedout", lambda: 0)
    overflow_fn = getattr(pool, "overflow", lambda: 0)
    DB_CONNECTION_POOL_SIZE.labels(pool_name=pool_name).set(size_fn())
    DB_CONNECTIONS_CHECKED_OUT.labels(pool_name=pool_name).set(checkedout_fn())
    DB_CONNECTIONS_OVERFLOW.labels(pool_name=pool_name).set(overflow_fn())


def on_connect(dbapi_connection, connection_record):
    """Called when a new connection is created."""
    pass  # Could add connection creation metrics here


def on_commit(conn):
    """Track successful commits."""
    DB_TRANSACTIONS_TOTAL.labels(status="committed").inc()


def on_rollback(conn):
    """Track rollbacks."""
    DB_TRANSACTIONS_TOTAL.labels(status="rolled_back").inc()


# ==================== Setup Function ====================


def setup_db_metrics(engine: Engine) -> None:
    """
    Attach event listeners to SQLAlchemy engine for metrics collection.

    Args:
        engine: SQLAlchemy Engine (sync or async) to instrument
    """
    if not settings.METRICS_ENABLED:
        return

    # Query execution timing
    event.listen(engine, "before_cursor_execute", before_cursor_execute)
    event.listen(engine, "after_cursor_execute", after_cursor_execute)

    # Error handling
    event.listen(engine, "handle_error", handle_error)

    # Connection pool events (only for engines with pools)
    if hasattr(engine, "pool"):
        pool = engine.pool
        event.listen(pool, "checkout", on_checkout)
        event.listen(pool, "checkin", on_checkin)
        event.listen(pool, "connect", on_connect)

    # Transaction events
    event.listen(engine, "commit", on_commit)
    event.listen(engine, "rollback", on_rollback)

    logger.info("Database metrics instrumentation enabled")


def get_pool_stats(engine: Engine) -> dict:
    """
    Get current connection pool statistics.

    Returns:
        Dict with pool size, checked out, and overflow counts.
        Returns zeros for pools that don't track these stats (e.g., NullPool).
    """
    if not hasattr(engine, "pool"):
        return {"error": "Engine has no pool"}

    pool = engine.pool

    # NullPool and some other pool types don't have size/checkedout/overflow methods
    # since they don't maintain a pool of connections (PgBouncer handles pooling)
    # Use getattr for pool methods that aren't in the base Pool type stubs
    # but exist on concrete pool implementations like QueuePool
    size_fn = getattr(pool, "size", None)
    if size_fn is None:
        return {
            "pool_size": 0,
            "checked_out": 0,
            "overflow": 0,
            "checked_in": 0,
        }

    checkedout_fn = getattr(pool, "checkedout", lambda: 0)
    overflow_fn = getattr(pool, "overflow", lambda: 0)
    checkedin_fn = getattr(pool, "checkedin", lambda: 0)

    return {
        "pool_size": size_fn(),
        "checked_out": checkedout_fn(),
        "overflow": overflow_fn(),
        "checked_in": checkedin_fn(),
    }
