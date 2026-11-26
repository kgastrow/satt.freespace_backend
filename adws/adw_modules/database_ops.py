"""Database operations for isolated ADW workflows.

Provides utilities for creating and dropping isolated databases for each ADW workflow.
Each workflow gets its own database to prevent migration conflicts between
parallel agents.

ADW IDs use format: YYYYMMDDHHMMSS-<8-char-uuid> (e.g., 20260110234549-ccfd0008)
Database names: appdb_ccfd0008 (single codebase) or appdb_0_ccfd0008 (multi-codebase)

Cross-codebase isolation:
    Redis databases are leased from the machine-wide resource registry (adw_modules/resources.py,
    ~/.adw/resources.json), shared by every codebase on the machine. PostgreSQL database names are
    unique per ADW id; with ADW_MAX_CODEBASES > 1 the codebase index is part of the name too.
    ADW_RESOURCES=static brings back the static Redis slices (2-14 split by ADW_CODEBASE_INDEX /
    ADW_MAX_CODEBASES).

    Why database indexes and not key prefixes: the app has no Redis key prefix setting (cache, rate
    limiter, ARQ queue and pub/sub use fixed key names; see app/backend/src/core/redis_pool.py), so a
    database per worktree is the only isolation it supports. Pub/sub channels are server-wide in Redis
    whatever the database, so worktrees could still hear each other's pub/sub messages.
"""

import json
import logging
import os
import shutil
import subprocess
from typing import Optional, Tuple

from adw_modules import resources

# Cross-codebase isolation: partition Redis DB range and PG names across codebases.
ADW_CODEBASE_INDEX = int(os.environ.get("ADW_CODEBASE_INDEX", "0"))
ADW_MAX_CODEBASES = int(os.environ.get("ADW_MAX_CODEBASES", "1"))

# Cache for psql path
_psql_path: Optional[str] = None


def find_psql() -> str:
    """Find the psql executable in common installation paths.

    Searches in order:
    1. System PATH (via shutil.which)
    2. Homebrew PostgreSQL installations (various versions)
    3. Common macOS/Linux paths

    Returns:
        Path to psql executable, or 'psql' if not found (will fail at runtime)
    """
    global _psql_path
    if _psql_path is not None:
        return _psql_path

    # First, check if psql is in PATH
    psql_in_path = shutil.which("psql")
    if psql_in_path:
        _psql_path = psql_in_path
        return _psql_path

    # Common Homebrew PostgreSQL paths (check multiple versions)
    homebrew_paths = [
        "/opt/homebrew/opt/postgresql@16/bin/psql",
        "/opt/homebrew/opt/postgresql@15/bin/psql",
        "/opt/homebrew/opt/postgresql@14/bin/psql",
        "/opt/homebrew/opt/postgresql/bin/psql",
        "/usr/local/opt/postgresql@16/bin/psql",
        "/usr/local/opt/postgresql@15/bin/psql",
        "/usr/local/opt/postgresql@14/bin/psql",
        "/usr/local/opt/postgresql/bin/psql",
    ]

    # Common system paths
    system_paths = [
        "/usr/bin/psql",
        "/usr/local/bin/psql",
        "/usr/pgsql-16/bin/psql",
        "/usr/pgsql-15/bin/psql",
        "/usr/pgsql-14/bin/psql",
    ]

    for path in homebrew_paths + system_paths:
        if os.path.isfile(path) and os.access(path, os.X_OK):
            _psql_path = path
            return _psql_path

    # Fallback to 'psql' - will fail at runtime with clear error
    _psql_path = "psql"
    return _psql_path


def get_database_config() -> dict:
    """Load database configuration from parent repo's config.json.

    Returns:
        Dictionary with database configuration (host, port, user, password, db)
    """
    # Get project root (parent of adws directory)
    project_root = os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    )
    config_path = os.path.join(project_root, "app", "backend", "config.json")

    default_config = {
        "host": "localhost",
        "port": 5432,
        "user": "freespace-user",
        "password": "freespace-pass",
        "db": "freespace",
    }

    if not os.path.exists(config_path):
        return default_config

    try:
        with open(config_path, "r") as f:
            config = json.load(f)
            db_config = config.get("database", {})
            return {
                "host": db_config.get("host", default_config["host"]),
                "port": db_config.get("port", default_config["port"]),
                "user": db_config.get("user", default_config["user"]),
                "password": db_config.get("password", default_config["password"]),
                "db": db_config.get("db", default_config["db"]),
            }
    except (json.JSONDecodeError, IOError):
        return default_config


def get_database_name_for_adw(adw_id: str) -> str:
    """Generate isolated database name for ADW workflow.

    Uses the codebase index and last 8 characters of the ADW ID.
    When running multiple codebases, the index is included in the name
    to prevent collisions. Single-codebase mode preserves the original
    format for backward compatibility.

    Args:
        adw_id: The ADW ID (format: YYYYMMDDHHMMSS-XXXXXXXX)

    Returns:
        Database name (format: appdb_{hash} or appdb_{codebase_index}_{hash})
    """
    # Extract last 8 alphanumeric characters
    id_suffix = "".join(c for c in adw_id[-8:] if c.isalnum())
    if ADW_MAX_CODEBASES > 1:
        return f"appdb_{ADW_CODEBASE_INDEX}_{id_suffix}"
    return f"appdb_{id_suffix}"


def get_redis_db_for_adw(adw_id: str) -> int:
    """Deterministically assign Redis database based on ADW ID.

    Uses databases 2-14 (13 total) for ADW worktrees to avoid conflicts with:
    - Databases 0-1:   Main app (cache + ARQ)
    - Databases 15+:   E2E test isolation (15 DBs per codebase index,
                        configured in playwright.config.ts)

    When running multiple codebases (ADW_MAX_CODEBASES > 1), the 2-14 range
    is partitioned so each codebase gets its own non-overlapping slice.

    Each worktree uses a single Redis database for both cache and ARQ,
    since their key patterns don't overlap (arq:* vs jwt:*, user:*, etc.).

    Args:
        adw_id: The ADW ID (format: YYYYMMDDHHMMSS-XXXXXXXX)

    Returns:
        Redis database number (2-14)

    Registry (default): the Redis database of the ADW's machine-wide lease, taken here when it has none
    (adw_modules/resources.py; pool ADW_REDIS_DBS, default 2-14 and 30-164, clamped to the server's
    `databases`). The rest of this docstring describes ADW_RESOURCES=static.
    """
    if resources.enabled():
        lease = resources.get(adw_id)
        if lease and lease.get("redis_db") is not None:
            return int(lease["redis_db"])
        lease = resources.acquire(adw_id, hold="worktree",
                                  worktree=os.path.join(resources.codebase_root(), "trees", adw_id))
        return int(lease["redis_db"])
    total_redis_dbs = 13  # databases 2-14
    redis_slots_per_codebase = total_redis_dbs // ADW_MAX_CODEBASES
    base_db = 2 + (ADW_CODEBASE_INDEX * redis_slots_per_codebase)

    try:
        # Use last 8 chars of ADW ID (the unique hash) for distribution
        id_chars = "".join(c for c in adw_id[-8:] if c.isalnum())
        index = int(id_chars, 16) % redis_slots_per_codebase
    except ValueError:
        # Fallback to simple hash if hex conversion fails
        index = hash(adw_id) % redis_slots_per_codebase

    return base_db + index


def flush_redis_db_for_adw(
    adw_id: str, logger: logging.Logger
) -> Tuple[bool, Optional[str]]:
    """Flush the Redis database allocated to an ADW workflow.

    Called during worktree cleanup to remove all cached data for the workflow.

    Args:
        adw_id: The ADW ID for this workflow
        logger: Logger instance

    Returns:
        Tuple of (success, error_message)
    """
    if resources.enabled():
        lease = resources.get(adw_id)
        if not lease or lease.get("redis_db") is None:
            logger.info(f"No Redis database leased for ADW {adw_id}; nothing to flush")
            return True, None
        redis_db = int(lease["redis_db"])
        allowed = redis_db in resources.redis_pool() and redis_db > 1
    else:
        redis_db = get_redis_db_for_adw(adw_id)
        allowed = 2 <= redis_db <= 14

    # Safety check: only flush databases in the ADW worktree range (static: 2-14; registry: ADW_REDIS_DBS).
    # DBs 0-1 are the main app, DBs 15+ are e2e tests.
    if not allowed:
        error_msg = f"Refusing to flush Redis database {redis_db} (outside the worktree range)"
        logger.error(error_msg)
        return False, error_msg

    logger.info(f"Flushing Redis database {redis_db} for ADW {adw_id}")

    try:
        import redis

        r = redis.Redis(host="localhost", port=6379, db=redis_db)
        r.flushdb()
        logger.info(f"Flushed Redis database {redis_db}")
        return True, None
    except ImportError:
        # redis package not installed, skip cleanup
        logger.warning("Redis package not installed, skipping Redis cleanup")
        return True, None
    except Exception as e:
        error_msg = f"Failed to flush Redis database {redis_db}: {e}"
        logger.warning(error_msg)
        # Non-fatal - continue with cleanup even if Redis flush fails
        return False, error_msg


def create_isolated_database(
    adw_id: str, logger: logging.Logger
) -> Tuple[str, Optional[str]]:
    """Create isolated database for ADW workflow.

    Creates database: appdb_{adw_id_short}
    Grants all privileges to the app user.

    Args:
        adw_id: The ADW ID for this workflow
        logger: Logger instance

    Returns:
        Tuple of (database_name, error_message)
        database_name is the name if successful, empty string if error
    """
    db_name = get_database_name_for_adw(adw_id)
    config = get_database_config()

    logger.info(f"Creating isolated database: {db_name}")

    # Build psql command to create database
    # We need to connect to postgres database to create a new database
    psql_env = os.environ.copy()
    psql_env["PGPASSWORD"] = config["password"]

    # Check if database already exists
    psql = find_psql()
    logger.debug(f"Using psql at: {psql}")

    check_cmd = [
        psql,
        "-h",
        config["host"],
        "-p",
        str(config["port"]),
        "-U",
        config["user"],
        "-d",
        "postgres",
        "-tAc",
        f"SELECT 1 FROM pg_database WHERE datname = '{db_name}'",
    ]

    try:
        result = subprocess.run(
            check_cmd, capture_output=True, text=True, env=psql_env, timeout=30
        )

        if result.stdout.strip() == "1":
            logger.info(f"Database {db_name} already exists, reusing")
            return db_name, None

    except subprocess.TimeoutExpired:
        error_msg = "Timeout checking database existence"
        logger.error(error_msg)
        return "", error_msg
    except Exception as e:
        error_msg = f"Error checking database existence: {e}"
        logger.error(error_msg)
        return "", error_msg

    # Create the database
    create_cmd = [
        psql,
        "-h",
        config["host"],
        "-p",
        str(config["port"]),
        "-U",
        config["user"],
        "-d",
        "postgres",
        "-c",
        f'CREATE DATABASE "{db_name}"',
    ]

    try:
        result = subprocess.run(
            create_cmd, capture_output=True, text=True, env=psql_env, timeout=30
        )

        if result.returncode != 0:
            error_msg = f"Failed to create database: {result.stderr}"

            # BUG-009 fix: Check for permission error and provide actionable command
            if (
                "permission denied" in result.stderr.lower()
                or "CREATEDB" in result.stderr
            ):
                error_msg = (
                    f"Database creation failed due to missing CREATEDB privilege.\n"
                    f"Please run the following command to grant the privilege:\n\n"
                    f"  psql -h {config['host']} -p {config['port']} -U postgres -c "
                    f"\"ALTER USER \\\"{config['user']}\\\" CREATEDB;\"\n\n"
                    f"Original error: {result.stderr}"
                )

            logger.error(error_msg)
            return "", error_msg

        logger.info(f"Created database: {db_name}")
        return db_name, None

    except subprocess.TimeoutExpired:
        error_msg = "Timeout creating database"
        logger.error(error_msg)
        return "", error_msg
    except Exception as e:
        error_msg = f"Error creating database: {e}"
        logger.error(error_msg)
        return "", error_msg


def drop_isolated_database(
    adw_id: str, logger: logging.Logger
) -> Tuple[bool, Optional[str]]:
    """Drop the isolated database for ADW workflow.

    Args:
        adw_id: The ADW ID for this workflow
        logger: Logger instance

    Returns:
        Tuple of (success, error_message)
    """
    db_name = get_database_name_for_adw(adw_id)
    config = get_database_config()

    logger.info(f"Dropping isolated database: {db_name}")

    psql_env = os.environ.copy()
    psql_env["PGPASSWORD"] = config["password"]

    psql = find_psql()
    logger.debug(f"Using psql at: {psql}")

    # First, terminate any active connections to the database
    terminate_cmd = [
        psql,
        "-h",
        config["host"],
        "-p",
        str(config["port"]),
        "-U",
        config["user"],
        "-d",
        "postgres",
        "-c",
        f"""
        SELECT pg_terminate_backend(pid)
        FROM pg_stat_activity
        WHERE datname = '{db_name}' AND pid <> pg_backend_pid()
        """,
    ]

    try:
        subprocess.run(
            terminate_cmd, capture_output=True, text=True, env=psql_env, timeout=30
        )
    except Exception as e:
        logger.warning(f"Failed to terminate connections: {e}")

    # Drop the database
    drop_cmd = [
        psql,
        "-h",
        config["host"],
        "-p",
        str(config["port"]),
        "-U",
        config["user"],
        "-d",
        "postgres",
        "-c",
        f'DROP DATABASE IF EXISTS "{db_name}"',
    ]

    try:
        result = subprocess.run(
            drop_cmd, capture_output=True, text=True, env=psql_env, timeout=30
        )

        if result.returncode != 0:
            error_msg = f"Failed to drop database: {result.stderr}"
            logger.error(error_msg)
            return False, error_msg

        logger.info(f"Dropped database: {db_name}")
        return True, None

    except subprocess.TimeoutExpired:
        error_msg = "Timeout dropping database"
        logger.error(error_msg)
        return False, error_msg
    except Exception as e:
        error_msg = f"Error dropping database: {e}"
        logger.error(error_msg)
        return False, error_msg


def update_worktree_database_config(
    worktree_path: str,
    database_name: str,
    logger: logging.Logger,
    adw_id: Optional[str] = None,
    frontend_port: Optional[int] = None,
) -> bool:
    """Update config.json in worktree to use isolated database, Redis, and security settings.

    Updates:
    - Database name to use isolated database
    - Removes pgbouncer_port to bypass PgBouncer (direct PostgreSQL connection)
    - Redis URLs to use isolated Redis database (if adw_id provided)
    - JWT secret to a random value (prevents startup failure from security check)
    - CORS allowed origins (prevents startup failure from wildcard '*' check)
    - Encryption key (prevents startup failure from missing key check)

    Args:
        worktree_path: Path to the worktree
        database_name: Name of the isolated database
        logger: Logger instance
        adw_id: The ADW ID for Redis database allocation (optional for backwards compat)
        frontend_port: Frontend port for CORS configuration (optional, defaults to 5173)

    Returns:
        True if successful, False otherwise
    """
    import base64
    import secrets

    config_path = os.path.join(worktree_path, "app", "backend", "config.json")

    if not os.path.exists(config_path):
        logger.warning(f"Config file not found at {config_path}")
        return False

    try:
        with open(config_path, "r") as f:
            config = json.load(f)

        # Update database name
        if "database" not in config:
            config["database"] = {}

        old_db = config["database"].get("db", "unknown")
        config["database"]["db"] = database_name

        # Remove pgbouncer_port to bypass PgBouncer and connect directly to PostgreSQL.
        # The app's config.py uses pgbouncer_port if present, falling back to port.
        # By removing pgbouncer_port, the app will use port (5432) for direct connection.
        # This avoids needing to configure PgBouncer for each isolated ADW database.
        had_pgbouncer = "pgbouncer_port" in config["database"]
        if had_pgbouncer:
            del config["database"]["pgbouncer_port"]
            logger.info("Removed pgbouncer_port to bypass PgBouncer")

        # Update Redis URLs to use isolated database if adw_id provided
        if adw_id:
            redis_db = get_redis_db_for_adw(adw_id)
            if "redis" not in config:
                config["redis"] = {}

            # Use same database for both cache and ARQ (keys don't conflict)
            redis_url = f"redis://localhost:6379/{redis_db}"
            config["redis"]["url"] = redis_url
            config["redis"]["arq_url"] = redis_url
            logger.info(f"Updated Redis URLs to use database {redis_db}")

        # Generate random JWT secret to prevent startup failure from security check.
        # The backend rejects the default placeholder "your-secret-key-change-in-production".
        if "jwt" not in config:
            config["jwt"] = {}

        default_jwt_secret = "your-secret-key-change-in-production"
        if config["jwt"].get("secret") == default_jwt_secret or not config["jwt"].get("secret"):
            new_secret = secrets.token_urlsafe(64)
            config["jwt"]["secret"] = new_secret
            logger.info("Generated random JWT secret for worktree")

        # Set CORS allowed origins to prevent startup failure from wildcard '*' check.
        # The backend rejects '*' as CORS origin in non-testing mode.
        if "cors" not in config:
            config["cors"] = {}

        current_cors = config["cors"].get("allowed_origins", "")
        if current_cors == "*" or not current_cors:
            # Use assigned frontend port if provided, otherwise default to 5173
            fe_port = frontend_port or 5173
            cors_origins = (
                f"http://localhost:{fe_port},"
                f"http://127.0.0.1:{fe_port},"
                "http://localhost:5173,"
                "http://127.0.0.1:5173"
            )
            config["cors"]["allowed_origins"] = cors_origins
            logger.info(f"Set CORS allowed origins for frontend port {fe_port}")

        # Generate encryption key to prevent startup failure from missing key check.
        # The backend requires a valid Fernet-compatible key.
        if "encryption" not in config:
            config["encryption"] = {}

        if not config["encryption"].get("key"):
            # Generate a Fernet-compatible key (32 bytes, URL-safe base64 encoded)
            encryption_key = base64.urlsafe_b64encode(os.urandom(32)).decode()
            config["encryption"]["key"] = encryption_key
            logger.info("Generated encryption key for worktree")

        with open(config_path, "w") as f:
            json.dump(config, f, indent=4)

        logger.info(f"Updated config.json database: {old_db} -> {database_name}")
        return True

    except (json.JSONDecodeError, IOError) as e:
        logger.error(f"Failed to update config.json: {e}")
        return False
