"""Worktree and port management operations for isolated ADW workflows.

Provides utilities for creating and managing git worktrees under trees/<adw_id>/
and allocating unique ports for each isolated instance.

ADW IDs use format: YYYYMMDDHHMMSS-<12-char-uuid> (e.g., 20260107143052-a1b2c3d4e5f6)

Cross-codebase isolation:
    Ports come from the machine-wide resource registry (adw_modules/resources.py,
    ~/.adw/resources.json), shared by every codebase on the machine: each ADW leases a
    backend/frontend pair from 9100-9199 / 9200-9299. With ADW_RESOURCES=static, the old
    scheme applies instead: ADW_CODEBASE_INDEX and ADW_MAX_CODEBASES partition 9100-9114 /
    9200-9214 so each codebase gets its own non-overlapping slice.
"""

import fcntl
import os
import signal
import subprocess
import logging
import socket
import shutil
import time
from typing import Tuple, Optional, List
from adw_modules.state import ADWState
from adw_modules import resources
from adw_modules.database_ops import (
    create_isolated_database,
    drop_isolated_database,
    flush_redis_db_for_adw,
)


# Static scheme (ADW_RESOURCES=static only; the default is the machine-wide registry, adw_modules/resources.py):
# partition port ranges across codebases.
# ADW_CODEBASE_INDEX selects which slice this codebase uses (0-based).
# ADW_MAX_CODEBASES sets how many slices to divide the range into.
# Defaults preserve backward compatibility (single codebase gets full range).
ADW_CODEBASE_INDEX = int(os.environ.get("ADW_CODEBASE_INDEX", "0"))
ADW_MAX_CODEBASES = int(os.environ.get("ADW_MAX_CODEBASES", "1"))

# BUG-044 fix: Define port range constants instead of magic numbers
_TOTAL_PORT_RANGE = 15  # Total ports available: 9100-9114 / 9200-9214
_SLOTS_PER_CODEBASE = _TOTAL_PORT_RANGE // ADW_MAX_CODEBASES

BACKEND_PORT_BASE = 9100 + (ADW_CODEBASE_INDEX * _SLOTS_PER_CODEBASE)
FRONTEND_PORT_BASE = 9200 + (ADW_CODEBASE_INDEX * _SLOTS_PER_CODEBASE)
PORT_RANGE_SIZE = _SLOTS_PER_CODEBASE

# Lock acquisition timeout in seconds
LOCK_TIMEOUT_SECONDS = 30
# Git's own locks (.git/config, the index, a ref): another git command in this repository holds one. Several
# workflows of an Ore batch start together, and `git worktree add -b` failed with "could not lock config file
# .git/config: File exists". Worth another try after a moment.
GIT_LOCK_ERRORS = ("could not lock config file", ".lock': file exists", "cannot lock ref")
GIT_LOCK_RETRIES = 5


def is_git_lock_error(stderr: str) -> bool:
    low = (stderr or "").lower()
    return any(e in low for e in GIT_LOCK_ERRORS)


def _run_git_retrying(cmd: List[str], cwd: str, logger: logging.Logger, timeout: int = 60,
                      retries: int = GIT_LOCK_RETRIES, delay: float = 1.0) -> subprocess.CompletedProcess:
    """cmd, again (after 1, 2, 3... seconds) while it fails because git's lock on a file is held. Raises
    subprocess.TimeoutExpired like subprocess.run."""
    for attempt in range(retries):
        result = subprocess.run(cmd, capture_output=True, text=True, cwd=cwd, timeout=timeout)
        if result.returncode == 0 or not is_git_lock_error(result.stderr) or attempt == retries - 1:
            return result
        logger.warning(f"{' '.join(cmd[:3])}: a git lock is held, trying again: {result.stderr.strip()[:200]}")
        time.sleep(delay * (attempt + 1))
    return result

# Stale lock file age in hours
STALE_LOCK_AGE_HOURS = 24

# Validate configuration at module load
assert 0 <= ADW_CODEBASE_INDEX < ADW_MAX_CODEBASES, (
    f"ADW_CODEBASE_INDEX ({ADW_CODEBASE_INDEX}) must be >= 0 and < ADW_MAX_CODEBASES ({ADW_MAX_CODEBASES})"
)
assert _SLOTS_PER_CODEBASE >= 1, (
    f"ADW_MAX_CODEBASES ({ADW_MAX_CODEBASES}) is too large for {_TOTAL_PORT_RANGE} total port slots"
)
assert BACKEND_PORT_BASE >= 1024, "BACKEND_PORT_BASE should be >= 1024 to avoid privileged ports"
assert BACKEND_PORT_BASE + PORT_RANGE_SIZE <= 65535, "Backend port range exceeds maximum"
assert FRONTEND_PORT_BASE + PORT_RANGE_SIZE <= 65535, "Frontend port range exceeds maximum"


def _get_project_root() -> str:
    """Get the project root directory."""
    return os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    )


def _get_lock_file_path(lock_name: str) -> str:
    """Get path to a lock file in the trees directory.

    Handles race conditions in directory creation.
    """
    project_root = _get_project_root()
    locks_dir = os.path.join(project_root, "trees", ".locks")
    try:
        os.makedirs(locks_dir, exist_ok=True)
    except OSError as e:
        # In case of permission or race condition errors
        if not os.path.exists(locks_dir):
            raise RuntimeError(f"Failed to create locks directory: {e}")
    return os.path.join(locks_dir, f"{lock_name}.lock")


def _acquire_lock_with_timeout(
    lock_file,
    timeout_seconds: int = LOCK_TIMEOUT_SECONDS,
    exclusive: bool = True
) -> bool:
    """Acquire file lock with timeout.

    Args:
        lock_file: Open file object to lock
        timeout_seconds: Timeout in seconds
        exclusive: If True, acquire exclusive lock; otherwise shared lock

    Returns:
        True if lock acquired, False if timed out
    """
    lock_type = fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH

    # Try non-blocking first
    try:
        fcntl.flock(lock_file.fileno(), lock_type | fcntl.LOCK_NB)
        return True
    except BlockingIOError:
        pass

    # Set up timeout handler
    def timeout_handler(signum, frame):
        raise TimeoutError("Lock acquisition timed out")

    old_handler = signal.signal(signal.SIGALRM, timeout_handler)
    signal.alarm(timeout_seconds)

    try:
        fcntl.flock(lock_file.fileno(), lock_type)
        return True
    except TimeoutError:
        return False
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, old_handler)


def cleanup_stale_lock_files(max_age_hours: int = STALE_LOCK_AGE_HOURS) -> List[str]:
    """Remove lock files older than max_age_hours.

    Args:
        max_age_hours: Maximum age of lock files in hours

    Returns:
        List of removed lock file paths
    """
    removed = []
    project_root = _get_project_root()
    locks_dir = os.path.join(project_root, "trees", ".locks")

    if not os.path.exists(locks_dir):
        return removed

    current_time = time.time()
    max_age_seconds = max_age_hours * 3600

    for lock_file in os.listdir(locks_dir):
        lock_path = os.path.join(locks_dir, lock_file)
        try:
            file_age = current_time - os.path.getmtime(lock_path)
            if file_age > max_age_seconds:
                os.remove(lock_path)
                removed.append(lock_path)
        except (OSError, IOError):
            pass

    return removed


def _cleanup_partial_worktree(
    worktree_path: str, project_root: str, logger: logging.Logger
) -> None:
    """Clean up a partially created worktree after a failure.

    This handles both the directory cleanup and git worktree prune.

    Args:
        worktree_path: Path to the worktree directory
        project_root: Project root directory for git commands
        logger: Logger instance
    """
    # Remove directory if it exists
    if os.path.exists(worktree_path):
        try:
            shutil.rmtree(worktree_path)
            logger.info(f"Cleaned up partial worktree directory: {worktree_path}")
        except Exception as e:
            logger.warning(f"Failed to clean up worktree directory {worktree_path}: {e}")

    # Run git worktree prune to clean up any orphaned references
    try:
        subprocess.run(
            ["git", "worktree", "prune"],
            capture_output=True,
            text=True,
            cwd=project_root,
            timeout=30,
        )
    except Exception as e:
        logger.debug(f"git worktree prune failed (non-fatal): {e}")


def _get_worktree_branch(worktree_path: str, project_root: str) -> Optional[str]:
    """Detect the current branch of an existing worktree.

    Args:
        worktree_path: Path to the worktree directory
        project_root: Project root directory (unused, kept for consistency)

    Returns:
        Branch name if detected, None otherwise
    """
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True,
            text=True,
            cwd=worktree_path,
            timeout=30,
        )
        if result.returncode == 0:
            branch = result.stdout.strip()
            if branch and branch != "HEAD":  # detached HEAD
                return branch
    except (subprocess.TimeoutExpired, Exception):
        pass
    return None


def create_worktree(
    adw_id: str, branch_name: str, logger: logging.Logger
) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """Create a git worktree for isolated ADW execution.

    Uses file-based locking with proper handle management to prevent race
    conditions during concurrent worktree creation.

    Args:
        adw_id: The ADW ID for this worktree
        branch_name: The branch name to create the worktree from
        logger: Logger instance

    Returns:
        Tuple of (worktree_path, actual_branch_name, error_message)
        worktree_path is the absolute path if successful, None if error
        actual_branch_name is the branch the worktree is on (may differ from
        branch_name if worktree already existed with a different branch)
    """
    project_root = _get_project_root()

    # Create trees directory if it doesn't exist
    trees_dir = os.path.join(project_root, "trees")
    os.makedirs(trees_dir, exist_ok=True)

    # Cleanup stale lock files periodically (non-blocking, best-effort)
    try:
        removed = cleanup_stale_lock_files()
        if removed:
            logger.debug(f"Cleaned up {len(removed)} stale lock files")
    except Exception as e:
        logger.debug(f"Failed to cleanup stale locks (non-fatal): {e}")

    # Construct worktree path
    worktree_path = os.path.join(trees_dir, adw_id)

    # Use file-based locking to prevent race conditions
    # Keep file handle open for entire duration to maintain lock. One lock for the repository, not one per ADW:
    # concurrent `git worktree add`s in one repository fight over .git/config.
    lock_file_path = _get_lock_file_path("worktree_create")
    lock_file = None

    try:
        lock_file = open(lock_file_path, "w")

        # Acquire lock with timeout
        if not _acquire_lock_with_timeout(lock_file, LOCK_TIMEOUT_SECONDS * 4):   # behind the others' fetches
            return None, None, f"Timeout waiting for worktree creation lock for {adw_id}"

        # BUG-076 fix: Check if worktree already exists (after acquiring lock)
        # Lock will be released in finally block, not here
        if os.path.exists(worktree_path):
            logger.warning(f"Worktree already exists at {worktree_path}")
            actual_branch = _get_worktree_branch(worktree_path, project_root)
            if actual_branch:
                logger.info(f"Existing worktree is on branch: {actual_branch}")
            else:
                logger.warning("Could not detect branch of existing worktree")
            # Note: Lock is released properly in the finally block below
            return worktree_path, actual_branch, None

        # First, fetch latest changes from origin
        logger.info("Fetching latest changes from origin")
        try:
            fetch_result = subprocess.run(
                ["git", "fetch", "origin"],
                capture_output=True,
                text=True,
                cwd=project_root,
                timeout=120,
            )
            if fetch_result.returncode != 0:
                logger.warning(f"Failed to fetch from origin: {fetch_result.stderr}")
        except subprocess.TimeoutExpired:
            logger.warning("Git fetch timed out, continuing with local state")

        # Create the worktree using git, branching from origin/main. --no-track: the branch's upstream is set when
        # it is first pushed (git push -u), not to origin/main here, which also writes .git/config.
        cmd = ["git", "worktree", "add", "--no-track", "-b", branch_name, worktree_path, "origin/main"]
        try:
            result = _run_git_retrying(cmd, project_root, logger)
        except subprocess.TimeoutExpired:
            # Clean up partial worktree on timeout
            _cleanup_partial_worktree(worktree_path, project_root, logger)
            return None, None, "Git worktree creation timed out"

        if result.returncode != 0:
            # If branch already exists, try without -b
            if "already exists" in result.stderr:
                _cleanup_partial_worktree(worktree_path, project_root, logger)
                cmd = ["git", "worktree", "add", worktree_path, branch_name]
                try:
                    result = _run_git_retrying(cmd, project_root, logger)
                except subprocess.TimeoutExpired:
                    _cleanup_partial_worktree(worktree_path, project_root, logger)
                    return None, None, "Git worktree creation timed out (retry)"

            if result.returncode != 0:
                error_msg = f"Failed to create worktree: {result.stderr}"
                logger.error(error_msg)
                # Clean up partial worktree on failure
                _cleanup_partial_worktree(worktree_path, project_root, logger)
                return None, None, error_msg

        logger.info(f"Created worktree at {worktree_path} for branch {branch_name}")
        return worktree_path, branch_name, None

    except Exception as e:
        logger.error(f"Error creating worktree: {e}")
        # Clean up partial worktree on exception
        _cleanup_partial_worktree(worktree_path, project_root, logger)
        return None, None, str(e)

    finally:
        if lock_file:
            try:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
                lock_file.close()
            except Exception:
                pass


def validate_worktree(adw_id: str, state: ADWState) -> Tuple[bool, Optional[str]]:
    """Validate worktree exists in state, filesystem, and git.

    Performs three-way validation to ensure consistency:
    1. State has worktree_path
    2. Directory exists on filesystem
    3. Git knows about the worktree

    Args:
        adw_id: The ADW ID to validate
        state: The ADW state object

    Returns:
        Tuple of (is_valid, error_message)
    """
    # Check state has worktree_path
    worktree_path = state.get("worktree_path")
    if not worktree_path:
        return False, "No worktree_path in state"

    # Normalize path for comparison
    worktree_path = os.path.abspath(worktree_path)

    # Check directory exists
    if not os.path.exists(worktree_path):
        return False, f"Worktree directory not found: {worktree_path}"

    # Check git knows about it
    project_root = _get_project_root()
    try:
        result = subprocess.run(
            ["git", "worktree", "list"],
            capture_output=True,
            text=True,
            cwd=project_root,
            timeout=30,
        )
    except subprocess.TimeoutExpired:
        return False, "Git worktree list command timed out"

    if result.returncode != 0:
        return False, f"Git worktree list failed: {result.stderr}"

    # Parse git worktree list output properly
    # Each line starts with the worktree path followed by commit info
    # Example: "/path/to/worktree  abc1234 [branch-name]"
    # Note: Paths can contain spaces, so we need to be careful with parsing
    # The format is: <path> <commit> [<branch>] where path ends at the commit hash
    import re
    for line in result.stdout.strip().split('\n'):
        if not line.strip():
            continue
        # Use regex to match: path (any chars) followed by space and 7-40 char hex commit
        # This handles paths with spaces correctly
        match = re.match(r'^(.+?)\s+([0-9a-f]{7,40})\s', line)
        if match:
            listed_path = match.group(1).strip()
        else:
            # Fallback: first space-separated token
            listed_path = line.split()[0] if line.split() else ""

        if os.path.abspath(listed_path) == worktree_path:
            return True, None

    return False, "Worktree not registered with git"


def get_worktree_path(adw_id: str) -> str:
    """Get absolute path to worktree.

    Args:
        adw_id: The ADW ID

    Returns:
        Absolute path to worktree directory
    """
    return os.path.join(_get_project_root(), "trees", adw_id)


def _pids_with_cwd_in(folder: str, logger: logging.Logger) -> set:
    """Processes of this user whose working directory is folder or inside it (/proc on Linux, lsof elsewhere)."""
    folder = os.path.realpath(folder)
    inside = lambda path: path == folder or path.startswith(folder + os.sep)  # noqa: E731
    pids: set = set()
    if os.path.isdir("/proc/self"):
        for entry in os.listdir("/proc"):
            if entry.isdigit():
                try:
                    if inside(os.readlink(f"/proc/{entry}/cwd")):
                        pids.add(int(entry))
                except OSError:
                    pass
        return pids
    try:
        out = subprocess.run(["lsof", "-a", "-d", "cwd", "-u", str(os.getuid()), "-Fn"], capture_output=True,
                             text=True, timeout=20).stdout
    except (subprocess.TimeoutExpired, OSError) as e:
        logger.debug(f"lsof for working directories failed: {e}")
        return pids
    pid = None
    for line in out.splitlines():
        if line.startswith("p") and line[1:].isdigit():
            pid = int(line[1:])
        elif line.startswith("n") and pid is not None and inside(os.path.realpath(line[1:])):
            pids.add(pid)
    return pids


def _kill_worktree_processes(adw_id: str, logger: logging.Logger) -> None:
    """Kill all processes scoped to a specific worktree.

    Uses pgrep -f to match processes whose command line contains the worktree
    path (trees/{adw_id}/...), and processes whose working directory is in the
    worktree (e.g. a `python main.py` server, whose command line doesn't name
    it). This is safe for parallel worktrees because the ADW ID in the path is
    unique per module.

    Sends SIGTERM first for graceful shutdown, then SIGKILL after a timeout.
    """
    patterns = [
        f"trees/{adw_id}/app/backend/.venv",   # uvicorn, ARQ workers
        f"trees/{adw_id}/app/frontend",         # vite/node
        f"trees/{adw_id}/scripts/start.sh",     # the start.sh wrapper itself
    ]

    all_pids: set = set()
    for pattern in patterns:
        try:
            result = subprocess.run(
                ["pgrep", "-f", pattern],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0 and result.stdout.strip():
                for pid_str in result.stdout.strip().split("\n"):
                    pid_str = pid_str.strip()
                    if pid_str.isdigit():
                        all_pids.add(int(pid_str))
        except (subprocess.TimeoutExpired, Exception) as e:
            logger.debug(f"pgrep for pattern '{pattern}' failed: {e}")
    all_pids |= _pids_with_cwd_in(get_worktree_path(adw_id), logger)
    all_pids.discard(os.getpid())

    if not all_pids:
        logger.debug(f"No running processes found for worktree {adw_id}")
        return

    logger.info(f"Sending SIGTERM to {len(all_pids)} worktree processes: {all_pids}")
    for pid in all_pids:
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        except OSError as e:
            logger.debug(f"Failed to SIGTERM pid {pid}: {e}")

    # Wait up to 5 seconds for graceful shutdown
    deadline = time.time() + 5
    remaining = set(all_pids)
    while remaining and time.time() < deadline:
        time.sleep(0.5)
        still_alive = set()
        for pid in remaining:
            try:
                os.kill(pid, 0)  # Check if process is still alive
                still_alive.add(pid)
            except ProcessLookupError:
                pass
            except OSError:
                still_alive.add(pid)
        remaining = still_alive

    if remaining:
        logger.info(f"Sending SIGKILL to {len(remaining)} remaining processes: {remaining}")
        for pid in remaining:
            try:
                os.kill(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            except OSError as e:
                logger.debug(f"Failed to SIGKILL pid {pid}: {e}")
        time.sleep(0.5)

    logger.info(f"Worktree process cleanup complete for {adw_id}")


def remove_worktree(
    adw_id: str,
    logger: logging.Logger,
    backend_port: Optional[int] = None,
    frontend_port: Optional[int] = None,
) -> Tuple[bool, Optional[str]]:
    """Remove a worktree and clean up, including isolated database, Redis, and port reservations.

    Also cleans up associated lock files to prevent accumulation.

    Review fix #9: Accepts optional port parameters so callers can pass the
    actual assigned ports (which may differ from get_ports_for_adw() if
    alternatives were assigned during setup).

    Args:
        adw_id: The ADW ID for the worktree to remove
        logger: Logger instance
        backend_port: Actual backend port (if known). Falls back to deterministic assignment.
        frontend_port: Actual frontend port (if known). Falls back to deterministic assignment.

    Returns:
        Tuple of (success, error_message)
    """
    project_root = _get_project_root()
    worktree_path = get_worktree_path(adw_id)

    # Kill processes scoped to this worktree before any other cleanup.
    # Dev servers (uvicorn, vite, ARQ) started by /prepare_app via start.sh
    # survive after the Claude Code subprocess exits because they're nohup'd.
    # We must terminate them first so ports are freed before reservation release.
    _kill_worktree_processes(adw_id, logger)

    # Drop the isolated database
    db_success, db_error = drop_isolated_database(adw_id, logger)
    if not db_success:
        logger.warning(f"Failed to drop isolated database: {db_error}")
        # Continue with worktree removal even if database drop fails

    # Flush the isolated Redis database
    redis_success, redis_error = flush_redis_db_for_adw(adw_id, logger)
    if not redis_success:
        logger.warning(f"Failed to flush Redis database: {redis_error}")
        # Continue with worktree removal even if Redis flush fails

    # Release port reservations
    # Review fix #9: Use actual ports if provided, fall back to deterministic
    try:
        if resources.enabled():
            resources.release_lease(adw_id)
        if backend_port is None or frontend_port is None:
            backend_port, frontend_port = (0, 0) if resources.enabled() else get_ports_for_adw(adw_id)
        release_ports(adw_id, backend_port, frontend_port)
        logger.debug(f"Released port reservations: {backend_port}, {frontend_port}")
    except Exception as e:
        logger.warning(f"Failed to release port reservations: {e}")
        # Continue with worktree removal even if port release fails

    # Remove via git
    # BUG-048 fix: Add cwd and timeout to prevent hanging and ensure correct execution
    cmd = ["git", "worktree", "remove", worktree_path, "--force"]
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=project_root,
            timeout=60,
        )
    except subprocess.TimeoutExpired:
        logger.warning("Git worktree remove command timed out, attempting manual cleanup")
        result = type('obj', (object,), {'returncode': 1, 'stderr': 'timeout'})()

    if result.returncode != 0:
        # Try to clean up manually if git command failed
        if os.path.exists(worktree_path):
            try:
                shutil.rmtree(worktree_path)
                logger.warning(f"Manually removed worktree directory: {worktree_path}")
            except Exception as e:
                return (
                    False,
                    f"Failed to remove worktree: {result.stderr}, manual cleanup failed: {e}",
                )

        # Review fix #7: Run git worktree prune after manual cleanup to remove
        # stale git metadata that would otherwise cause false positives in
        # validate_worktree() and prevent future worktree creation at same path
        try:
            subprocess.run(
                ["git", "worktree", "prune"],
                capture_output=True,
                text=True,
                cwd=project_root,
                timeout=30,
            )
            logger.debug("Ran git worktree prune after manual cleanup")
        except Exception as e:
            logger.debug(f"git worktree prune failed (non-fatal): {e}")

    # BUG-049 fix: Clean up lock files to prevent accumulation
    lock_file_path = _get_lock_file_path(f"worktree_{adw_id}")
    try:
        if os.path.exists(lock_file_path):
            os.remove(lock_file_path)
            logger.debug(f"Cleaned up lock file: {lock_file_path}")
    except Exception as e:
        logger.warning(f"Failed to remove lock file {lock_file_path}: {e}")
        # Non-fatal, continue

    logger.info(f"Removed worktree at {worktree_path}")
    return True, None


def setup_worktree_environment(
    worktree_path: str,
    backend_port: int,
    frontend_port: int,
    adw_id: str,
    logger: logging.Logger,
) -> Tuple[Optional[str], int, int, Optional[str]]:
    """Set up worktree environment with ports, database, and Playwright directories.

    Creates .ports.env, isolated database, and directories for Playwright output.
    Includes cleanup on failure to prevent orphaned resources (BUG-003 fix).

    Args:
        worktree_path: Path to the worktree
        backend_port: Backend port number
        frontend_port: Frontend port number
        adw_id: The ADW ID for this workflow
        logger: Logger instance

    Returns:
        Tuple of (database_name, actual_backend_port, actual_frontend_port, error_message)
        Ports may differ from input if originals were unavailable.
        database_name is the isolated database name if successful, None if error.
    """
    db_name = None
    ports_reserved = False  # BUG-077 fix: Track if ports were reserved for cleanup

    try:
        # Verify ports are available before proceeding
        if not is_port_available(backend_port):
            # Try to find alternative ports
            logger.warning(f"Backend port {backend_port} is not available, searching for alternatives")
            try:
                backend_port, frontend_port = find_next_available_ports(adw_id)
                ports_reserved = True  # find_next_available_ports reserves internally
                logger.info(f"Found alternative ports: backend={backend_port}, frontend={frontend_port}")
            except RuntimeError as e:
                return None, backend_port, frontend_port, f"No available ports found: {e}"
        elif not is_port_available(frontend_port):
            logger.warning(f"Frontend port {frontend_port} is not available, searching for alternatives")
            try:
                backend_port, frontend_port = find_next_available_ports(adw_id)
                ports_reserved = True  # find_next_available_ports reserves internally
                logger.info(f"Found alternative ports: backend={backend_port}, frontend={frontend_port}")
            except RuntimeError as e:
                return None, backend_port, frontend_port, f"No available ports found: {e}"
        else:
            # BUG-4 fix: Port reservation failure should be an error, not just a warning
            # Without reservation, another concurrent ADW could claim the same ports
            if _reserve_ports(adw_id, backend_port, frontend_port):
                ports_reserved = True
            else:
                # Try to find alternative ports instead of continuing with unreserved ports
                logger.warning(f"Could not reserve ports {backend_port}/{frontend_port}, searching for alternatives")
                try:
                    backend_port, frontend_port = find_next_available_ports(adw_id)
                    ports_reserved = True
                    logger.info(f"Found alternative ports: backend={backend_port}, frontend={frontend_port}")
                except RuntimeError as e:
                    return None, backend_port, frontend_port, f"Failed to reserve ports: {e}"

        # BUG-3 fix: Wrap .ports.env file write in try-except with cleanup
        # Create .ports.env file with port configuration
        ports_env_path = os.path.join(worktree_path, ".ports.env")

        try:
            with open(ports_env_path, "w") as f:
                f.write(f"BACKEND_PORT={backend_port}\n")
                f.write(f"FRONTEND_PORT={frontend_port}\n")
                f.write(f"VITE_API_URL=http://localhost:{backend_port}/api/v1\n")
        except (IOError, OSError) as e:
            # Clean up reserved ports on write failure
            if ports_reserved:
                release_ports(adw_id, backend_port, frontend_port)
            return None, backend_port, frontend_port, f"Failed to write .ports.env: {e}"

        logger.info(
            f"Created .ports.env with Backend: {backend_port}, Frontend: {frontend_port}"
        )

        # Create directories for Playwright output (screenshots, videos)
        playwright_output_dir = os.path.join(worktree_path, "playwright-output")
        os.makedirs(playwright_output_dir, exist_ok=True)
        logger.info("Created Playwright output directory")

        # A leased Redis database may hold the keys of the workflow that had it before: start clean
        if resources.enabled():
            flush_redis_db_for_adw(adw_id, logger)

        # Create isolated database for this workflow
        db_name, db_error = create_isolated_database(adw_id, logger)
        if db_error:
            # BUG-077 fix: Release ports on database creation failure
            if ports_reserved:
                release_ports(adw_id, backend_port, frontend_port)
                logger.debug(f"Released ports {backend_port}/{frontend_port} due to database error")
            return None, backend_port, frontend_port, db_error

        if resources.enabled():
            resources.update(adw_id, db_name=db_name, worktree=worktree_path)

        # BUG-046 fix: Updated comment to accurately reflect behavior
        # The database name is returned and stored in ADWState by the caller.
        # The /install_worktree command uses this to update config.json.

        return db_name, backend_port, frontend_port, None

    except Exception as e:
        # BUG-003 fix: Clean up database on failure to prevent orphaned resources
        # BUG-051 fix: Return error tuple instead of raising for consistency
        # BUG-077 fix: Also clean up port reservations on failure
        logger.error(f"Setup failed, cleaning up: {e}")
        if db_name:
            logger.info(f"Dropping orphaned database: {db_name}")
            drop_isolated_database(adw_id, logger)
        if ports_reserved:
            logger.info(f"Releasing ports {backend_port}/{frontend_port}")
            release_ports(adw_id, backend_port, frontend_port)
        return None, backend_port, frontend_port, f"Setup failed: {e}"


# Port management functions


def get_ports_for_adw(adw_id: str) -> Tuple[int, int]:
    """The ADW's ports.

    Registry (default): the ports of the ADW's machine-wide lease, which is taken here when it has none
    (raises resources.ResourcesExhausted, a RuntimeError, when no pair is free).
    ADW_RESOURCES=static: deterministically assigned from the ADW ID, as below.

    Uses the unique hash portion of the ADW ID to avoid collisions between
    ADWs created on the same day. ADW IDs have format:
    YYYYMMDDHHMMSS-XXXXXXXXXXXX where XXXXXXXXXXXX is a 12-char hex hash.

    Note: With PORT_RANGE_SIZE=15, a maximum of 15 concurrent ADWs can run
    without port conflicts. If more concurrent ADWs are needed, increase
    PORT_RANGE_SIZE (max 65535 - BACKEND_PORT_BASE for backend ports).

    Args:
        adw_id: The ADW ID

    Returns:
        Tuple of (backend_port, frontend_port)

    Raises:
        ValueError: If calculated ports are outside valid range (1-65535)
    """
    if resources.enabled():
        # Registry: the ADW's lease (taken now if it has none). Held while its worktree exists.
        lease = resources.acquire(adw_id, hold="worktree", worktree=get_worktree_path(adw_id))
        return lease["backend_port"], lease["frontend_port"]

    # ADW ID format: YYYYMMDDHHMMSS-XXXXXXXXXXXX
    # Extract the hash portion after the hyphen for better distribution
    try:
        if '-' in adw_id:
            # Extract hash portion directly (more reliable than last N chars)
            hash_portion = adw_id.split('-')[-1]
        else:
            # Fallback for malformed IDs
            hash_portion = adw_id[-12:]

        # Filter to alphanumeric and convert from hex
        id_chars = "".join(c for c in hash_portion if c.isalnum())
        if not id_chars:
            raise ValueError("No alphanumeric characters in ID hash portion")

        index = int(id_chars, 16) % PORT_RANGE_SIZE
    except ValueError:
        # Fallback to simple hash if hex conversion fails
        index = abs(hash(adw_id)) % PORT_RANGE_SIZE

    backend_port = BACKEND_PORT_BASE + index
    frontend_port = FRONTEND_PORT_BASE + index

    # Validate port numbers are in valid range
    if not (1 <= backend_port <= 65535):
        raise ValueError(f"Backend port {backend_port} is outside valid range (1-65535)")
    if not (1 <= frontend_port <= 65535):
        raise ValueError(f"Frontend port {frontend_port} is outside valid range (1-65535)")

    return backend_port, frontend_port


def is_port_available(port: int) -> bool:
    """Check if a port is available for binding.

    Checks both localhost and all interfaces to be thorough.

    Args:
        port: Port number to check

    Returns:
        True if port is available, False otherwise
    """
    # Check localhost first (most common case)
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.settimeout(1)
            s.bind(("localhost", port))
    except (socket.error, OSError):
        return False

    # Also check all interfaces to be safe
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.settimeout(1)
            s.bind(("0.0.0.0", port))
            return True
    except (socket.error, OSError):
        return False


def _get_port_reservation_file(backend_port: int, frontend_port: int) -> str:
    """Get path to port reservation file."""
    project_root = _get_project_root()
    reservations_dir = os.path.join(project_root, "trees", ".port_reservations")
    os.makedirs(reservations_dir, exist_ok=True)
    return os.path.join(reservations_dir, f"ports_{backend_port}_{frontend_port}.reserved")


def _is_port_reserved(backend_port: int, frontend_port: int) -> bool:
    """Check if ports are already reserved by another ADW.

    BUG-9 fix: Uses file locking for atomic check-and-remove of stale reservations
    to prevent race conditions where two processes both see a stale file.
    """
    if resources.enabled():
        leased = {(lease.get("backend_port"), lease.get("frontend_port"))
                  for lease in resources.snapshot()["leases"].values()}
        return (backend_port, frontend_port) in leased
    reservation_file = _get_port_reservation_file(backend_port, frontend_port)
    if not os.path.exists(reservation_file):
        return False

    # BUG-9 fix: Use file locking for atomic stale check and removal
    lock_file_path = reservation_file + ".lock"
    lock_file = None

    try:
        lock_file = open(lock_file_path, "w")
        # Non-blocking try first, then short timeout if needed
        try:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            # Another process has the lock, assume reserved
            return True

        # Double-check file still exists after acquiring lock
        if not os.path.exists(reservation_file):
            return False

        # Check if reservation is stale (older than 24 hours)
        file_age = time.time() - os.path.getmtime(reservation_file)
        if file_age > STALE_LOCK_AGE_HOURS * 3600:
            # Stale reservation, remove it atomically while holding lock
            os.remove(reservation_file)
            return False

        return True

    except (OSError, IOError):
        # If we can't check properly, assume reserved to be safe
        return True

    finally:
        if lock_file:
            try:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
                lock_file.close()
            except Exception:
                pass


def _reserve_ports(adw_id: str, backend_port: int, frontend_port: int) -> bool:
    """Reserve ports for an ADW.

    Args:
        adw_id: The ADW ID
        backend_port: Backend port to reserve
        frontend_port: Frontend port to reserve

    Returns:
        True if reservation succeeded, False otherwise
    """
    if resources.enabled():
        try:
            lease = resources.acquire(adw_id, hold="worktree", worktree=get_worktree_path(adw_id),
                                      prefer_ports=(backend_port, frontend_port))
        except resources.ResourcesExhausted:
            return False
        return (lease["backend_port"], lease["frontend_port"]) == (backend_port, frontend_port)
    reservation_file = _get_port_reservation_file(backend_port, frontend_port)
    try:
        with open(reservation_file, "w") as f:
            f.write(f"{adw_id}\n{time.time()}\n")
        return True
    except (OSError, IOError):
        return False


def release_ports(adw_id: str, backend_port: int, frontend_port: int) -> None:
    """Release port reservation for an ADW.

    Args:
        adw_id: The ADW ID
        backend_port: Backend port to release
        frontend_port: Frontend port to release
    """
    if resources.enabled():
        resources.release_lease(adw_id)           # ports and Redis database together
    reservation_file = _get_port_reservation_file(backend_port, frontend_port)
    try:
        if os.path.exists(reservation_file):
            # Verify this ADW owns the reservation
            with open(reservation_file, "r") as f:
                reserved_adw = f.readline().strip()
            if reserved_adw == adw_id:
                os.remove(reservation_file)
    except (OSError, IOError):
        pass


def find_next_available_ports(adw_id: str, max_attempts: int = PORT_RANGE_SIZE) -> Tuple[int, int]:
    """Find available ports starting from deterministic assignment.

    Uses file-based locking AND port reservation files to prevent race
    conditions where two processes both check and try to use the same port.

    Args:
        adw_id: The ADW ID
        max_attempts: Maximum number of attempts (default PORT_RANGE_SIZE)

    Returns:
        Tuple of (backend_port, frontend_port)

    Raises:
        RuntimeError: If no available ports found
    """
    if resources.enabled():
        # The registry only leases pairs nobody listens on; the ADW keeps its lease if it has one.
        return get_ports_for_adw(adw_id)

    base_backend, base_frontend = get_ports_for_adw(adw_id)
    base_index = base_backend - BACKEND_PORT_BASE

    # Use file-based locking for port allocation
    lock_file_path = _get_lock_file_path("port_allocation")
    lock_file = None

    try:
        lock_file = open(lock_file_path, "w")

        # Acquire lock with timeout
        if not _acquire_lock_with_timeout(lock_file, LOCK_TIMEOUT_SECONDS):
            raise RuntimeError("Timeout waiting for port allocation lock")

        for offset in range(max_attempts):
            index = (base_index + offset) % PORT_RANGE_SIZE
            backend_port = BACKEND_PORT_BASE + index
            frontend_port = FRONTEND_PORT_BASE + index

            # Check if ports are reserved by another ADW
            if _is_port_reserved(backend_port, frontend_port):
                continue

            # Check if ports are actually available
            if is_port_available(backend_port) and is_port_available(frontend_port):
                # Reserve the ports
                if _reserve_ports(adw_id, backend_port, frontend_port):
                    return backend_port, frontend_port

        raise RuntimeError("No available ports in the allocated range")

    finally:
        if lock_file:
            try:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
                lock_file.close()
            except Exception:
                pass
