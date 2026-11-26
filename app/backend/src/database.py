"""
Async SQLAlchemy database configuration for FastAPI.
Supports PgBouncer connection pooling with prepared statement disabled.

Note: Tests use their own in-memory SQLite database configured in tests/conftest.py
for proper isolation and performance.
"""

from collections.abc import AsyncGenerator
from typing import Any
from uuid import uuid4

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import AsyncAdaptedQueuePool, NullPool

from src.core.config import settings


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy models."""

    pass


def _unique_prepared_statement_name() -> str:
    """Name every server-side prepared statement uniquely.

    SQLAlchemy's asyncpg dialect prepares by name on every execute, even with
    its own cache disabled. Its default name function is a PER-CONNECTION
    counter (``__asyncpg_stmt_1__``, ``__asyncpg_stmt_2__``, ...), so the same
    names repeat across every pooled connection. Under PgBouncer transaction
    pooling the next transaction can land on a different backend, where that
    name was never prepared -> intermittent
    ``prepared statement "__asyncpg_stmt_N__" does not exist``, under
    concurrency only.

    NullPool hides this completely: every request gets a virgin connection
    whose counter restarts at 1, so the bug only appears the moment you turn
    a real pool on. That is why this function exists alongside
    DATABASE_POOL_ENABLED and not before it.
    """
    return f"__app_{uuid4().hex}__"


def create_async_engine_from_config(use_direct: bool = False) -> AsyncEngine:
    """
    Create async SQLAlchemy engine.

    Args:
        use_direct: If True, connect directly to PostgreSQL (for migrations).
                   If False, connect via PgBouncer (for application).
    """
    # Convert statement timeout from milliseconds to string for PostgreSQL
    statement_timeout_str = str(settings.DB_STATEMENT_TIMEOUT_MS)

    if use_direct:
        database_url = settings.DATABASE_URL_DIRECT
        # Direct connection can use larger pool and prepared statements
        engine_kwargs = {
            "echo": settings.DATABASE_ECHO,
            "pool_pre_ping": True,
            "pool_recycle": settings.DATABASE_POOL_RECYCLE,
            "poolclass": AsyncAdaptedQueuePool,
            "pool_size": 5,
            "max_overflow": 10,
            "connect_args": {
                "statement_cache_size": 100,
                "command_timeout": 30,
                # Set PostgreSQL statement_timeout to prevent runaway queries
                "server_settings": {
                    "statement_timeout": statement_timeout_str,
                },
            },
        }
    else:
        database_url = settings.DATABASE_URL
        # =======================================================================
        # PgBouncer Connection Configuration
        # =======================================================================
        #
        # ASSUMPTION: PgBouncer is configured in TRANSACTION POOLING MODE.
        #
        # This is the recommended mode for web applications because:
        # - Connections are returned to the pool after each transaction completes
        # - Allows many application connections to share fewer PostgreSQL connections
        # - Best balance of connection efficiency and feature compatibility
        #
        # Pooling: NullPool by default, QueuePool opt-in
        # ----------------------------------------------
        # DATABASE_POOL_ENABLED (default false) selects between the two.
        #
        # NullPool opens a fresh connection per request and closes it after,
        # deferring all pooling to PgBouncer. That is the conservative default
        # and it is what this template has always shipped, but be clear about
        # what it costs:
        # - Every single request pays a TCP handshake plus a full SCRAM-SHA-256
        #   authentication against a SINGLE-THREADED PgBouncer. At high request
        #   rates PgBouncer saturates on authentication CPU long before
        #   max_client_conn is reached.
        # - There is NO backpressure. With no pool there is no queue, so a
        #   latency spike grows the number of in-flight connections without
        #   bound until PgBouncer stops accepting them.
        #
        # THE PGBOUNCER FAILURE MODE YOU MUST KNOW (universal, and the reason
        # this is worth reading): at max_client_conn PgBouncer does not refuse
        # connections - it HANGS them. It simply stops calling accept(), and the
        # kernel's listen backlog holds the socket open. The client sees a
        # completed TCP handshake and then silence. So a starting worker blocks
        # forever with no error, no log line, and no failed health check; it
        # just never becomes ready. Do not go looking for a connection-refused
        # error, it will not be there. Check PgBouncer's `SHOW POOLS` / `SHOW
        # CLIENTS` and the accept queue instead.
        #
        # A bounded QueuePool fixes both: connections stay warm (no per-request
        # auth) and overload queues on pool_timeout instead of expanding without
        # limit. It is OPT-IN rather than the default because it has a hard
        # dependency on how PgBouncer is configured - see the prepared-statement
        # section below - and a template cannot verify your PgBouncer for you.
        # Turning it on with the wrong PgBouncer settings trades a known,
        # survivable cost for intermittent query failures under concurrency.
        #
        # SIZING - re-derive this for YOUR deployment; the numbers below are a
        # worked example using this file's own defaults, not a capacity plan:
        #
        #   total connections = (workers x (pool_size + max_overflow))
        #                       summed over every process that connects
        #
        #   With the template defaults (pool_size=2, max_overflow=1) and, say,
        #   4 API workers plus 1 ARQ worker:
        #       4 x (2 + 1) = 12   (API)
        #     + 1 x (2 + 1) =  3   (ARQ; cron runs inside the ARQ worker and is
        #                           not a separate consumer)
        #     ------------------
        #                     15   against PgBouncer's max_client_conn
        #
        #   Then sanity-check the OTHER ceiling: PgBouncer's default_pool_size
        #   (default 20-25) bounds the PgBouncer -> PostgreSQL leg. If your
        #   client-side total greatly exceeds it, requests queue inside
        #   PgBouncer on query_wait_timeout and your pool_timeout never fires -
        #   the binding constraint moved and your timeout tuning is aimed at the
        #   wrong queue.
        #
        #   Read max_client_conn from your own pgbouncer.ini. If the file is not
        #   readable, do not guess: probe it, and remember the ceiling presents
        #   as a hang (above), not an error.
        #
        # POOL_RECYCLE TRAP: SQLAlchemy treats ANY pool_recycle > -1 as a live
        # recycle age. A deployed DATABASE_POOL_RECYCLE of 0 therefore recycles
        # the connection on EVERY checkout, silently degrading this QueuePool
        # back to a NullPool with extra bookkeeping - no error, no warning, just
        # the performance you were trying to fix. Use -1 to disable recycling;
        # never 0. Keep the value comfortably below any idle timeout on the
        # server side.
        #
        # Why statement_cache_size=0 - and why that alone is NOT enough once
        # you enable pooling:
        # ------------------------------------------------------------------
        # asyncpg uses prepared statements by default. In transaction pooling
        # mode PgBouncer may route subsequent queries to different backend
        # connections, causing "prepared statement does not exist" errors.
        #
        # There are TWO caches, and disabling only one is the trap:
        #   - asyncpg's own cache            -> statement_cache_size
        #   - SQLAlchemy's asyncpg dialect   -> prepared_statement_cache_size
        # and even with BOTH at 0 the dialect still issues a server-side NAMED
        # prepare on every execute, using a per-connection counter for the name.
        # Across a pool those names repeat, so a name prepared on one backend is
        # referenced on another -> intermittent InvalidSQLStatementNameError,
        # only under concurrency, only with a real pool.
        # prepared_statement_name_func closes that last hole.
        #
        # DEPENDENCY THIS CODE CANNOT ENFORCE: unique names only stay bounded if
        # PgBouncer actually deallocates them. asyncpg issues its Close at the
        # start of the NEXT execute, which under transaction pooling can land on
        # a different backend where PostgreSQL treats it as a silent no-op.
        # Configure PgBouncer with:
        #     server_reset_query = DEALLOCATE ALL
        #     server_reset_query_always = 1
        # (transaction mode SKIPS the reset query without that second flag).
        # Without it, server-side prepared statements accumulate per backend.
        # This is the reason DATABASE_POOL_ENABLED defaults to false.
        #
        # CAVEATS - Session-level features that DO NOT work with transaction pooling:
        # ---------------------------------------------------------------------------
        # - SET commands (session variables reset between transactions)
        # - LISTEN/NOTIFY (notifications lost when connection returns to pool)
        # - Advisory locks (released when connection returns to pool)
        # - Temporary tables (dropped when connection returns to pool)
        # - Cursors held across transactions (WITH HOLD cursors)
        # - Session-level prepared statements
        #
        # If you need any of these features, use the direct_engine instead, or
        # configure a separate PgBouncer pool in SESSION pooling mode.
        #
        # =======================================================================
        connect_args: dict[str, Any] = {
            # Disable prepared statement cache for PgBouncer transaction pooling
            "statement_cache_size": 0,
            "command_timeout": 30,
            # Note: statement_timeout cannot be set via server_settings with PgBouncer
            # transaction pooling. Configure it in postgresql.conf instead, or use
            # direct_engine for tasks that need it.
        }

        if settings.DATABASE_POOL_ENABLED:
            # Opt-in bounded pool. Every DATABASE_POOL_* setting is read here;
            # this is the only place they are not dead config.
            connect_args["prepared_statement_cache_size"] = 0
            connect_args["prepared_statement_name_func"] = (
                _unique_prepared_statement_name
            )
            engine_kwargs = {
                "echo": settings.DATABASE_ECHO,
                "poolclass": AsyncAdaptedQueuePool,
                "pool_size": settings.DATABASE_POOL_SIZE,
                "max_overflow": settings.DATABASE_MAX_OVERFLOW,
                # The backpressure NullPool does not have: under overload a
                # request waits here and then fails, instead of opening
                # connections without bound.
                "pool_timeout": settings.DATABASE_POOL_TIMEOUT,
                # pool_pre_ping costs a probe round trip on every checkout,
                # against the single-threaded component this pool exists to
                # unload. PgBouncer already absorbs server-side connection death
                # transparently, so the residual risk is a PgBouncer restart -
                # bounded and one-time. Left configurable, defaulted on to match
                # the previous direct-engine behaviour.
                "pool_pre_ping": settings.DATABASE_POOL_PRE_PING,
                # See the POOL_RECYCLE TRAP note above: 0 here silently
                # degrades this pool back to NullPool behaviour.
                "pool_recycle": settings.DATABASE_POOL_RECYCLE,
                "connect_args": connect_args,
            }
        else:
            engine_kwargs = {
                "echo": settings.DATABASE_ECHO,
                # NullPool: don't maintain SQLAlchemy pool, let PgBouncer handle it
                "poolclass": NullPool,
                "connect_args": connect_args,
            }

    return create_async_engine(database_url, **engine_kwargs)


# Application engine (via PgBouncer)
async_engine = create_async_engine_from_config(use_direct=False)

# Direct engine for migrations and admin tasks
direct_engine = create_async_engine_from_config(use_direct=True)

# Async session factory
AsyncSessionLocal = async_sessionmaker(
    bind=async_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


async def get_async_session() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency for database sessions.
    Provides transaction management with automatic commit/rollback.
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_db() -> None:
    """Initialize database tables (for development/testing)."""
    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def close_db() -> None:
    """Close database connections."""
    await async_engine.dispose()
    await direct_engine.dispose()
