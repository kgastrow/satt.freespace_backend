"""Git operations for ADW composable architecture.

Provides centralized git operations that build on top of github.py module.
"""

import re
import subprocess
import json
import logging
import time
from typing import Optional, Tuple, TYPE_CHECKING

# Import GitHub functions from existing module
from adw_modules.github import get_repo_url, extract_repo_path, make_issue_comment, fetch_issue

# Import workflow_ops at module level to avoid circular imports
if TYPE_CHECKING:
    from adw_modules.state import ADWState

# BUG-093 fix: Thread-safe lazy import using threading.Lock
import threading

_create_pull_request = None
_create_pull_request_lock = threading.Lock()

def _get_create_pull_request():
    """Lazy import of create_pull_request to avoid circular imports.

    BUG-093 fix: Uses threading.Lock to ensure thread-safe initialization.
    """
    global _create_pull_request
    if _create_pull_request is None:
        with _create_pull_request_lock:
            # Double-check locking pattern
            if _create_pull_request is None:
                from adw_modules.workflow_ops import create_pull_request
                _create_pull_request = create_pull_request
    return _create_pull_request

# BUG-036 fix: Retry settings for git operations
GIT_MAX_RETRIES = 3
GIT_RETRY_DELAY = 5  # seconds

# Logger for this module
logger = logging.getLogger(__name__)


def get_current_branch(cwd: Optional[str] = None) -> str:
    """Get current git branch name.

    Returns:
        Branch name if successful, empty string on error.
    """
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True,
            text=True,
            cwd=cwd,
            timeout=30,
        )
        # BUG-083 fix: Check returncode before using stdout
        if result.returncode != 0:
            logging.getLogger(__name__).warning(
                f"Get current branch failed: {result.stderr.strip()}"
            )
            return ""
        return result.stdout.strip()
    except subprocess.TimeoutExpired:
        logging.getLogger(__name__).warning("Get current branch timed out")
        return ""


def push_branch(
    branch_name: str, cwd: Optional[str] = None, max_retries: int = GIT_MAX_RETRIES
) -> Tuple[bool, Optional[str]]:
    """Push current branch to remote with retry on network errors.

    Handles both network errors and timeouts with proper retry logic.

    Returns (success, error_message).
    """
    last_error = None
    result = None  # BUG-087 fix: Initialize result to None

    for attempt in range(max_retries):
        try:
            result = subprocess.run(
                ["git", "push", "-u", "origin", branch_name],
                capture_output=True,
                text=True,
                cwd=cwd,
                timeout=120,  # 2 minute timeout
            )
        except subprocess.TimeoutExpired:
            last_error = "Git push timed out"
            result = None  # BUG-087 fix: Reset result on timeout
            if attempt < max_retries - 1:
                wait_time = GIT_RETRY_DELAY * (attempt + 1)
                logger.warning(f"Git push timed out, retrying in {wait_time}s...")
                time.sleep(wait_time)
                continue
            break

        # BUG-087 fix: Only check result if not None
        if result is None:
            continue

        if result.returncode == 0:
            return True, None

        last_error = result.stderr

        # Retry on network-related errors
        error_lower = result.stderr.lower()
        is_transient = any(msg in error_lower for msg in [
            "unable to access",
            "could not resolve",
            "connection refused",
            "connection reset",
            "network unreachable",
            "timed out",
            "ssl",
            "temporarily unavailable",
            "could not lock config file",   # another workflow's git command holds .git/config (push -u writes it)
            ".lock': file exists",
        ])

        if is_transient and attempt < max_retries - 1:
            wait_time = GIT_RETRY_DELAY * (attempt + 1)
            logger.warning(f"Git push failed with transient error, retrying in {wait_time}s...")
            time.sleep(wait_time)
            continue

        # Non-transient error or last attempt
        break

    return False, last_error


def check_pr_exists(branch_name: str) -> Optional[str]:
    """Check if PR exists for branch. Returns PR URL if exists.

    Note: For detailed error information, use check_pr_exists_with_error().
    """
    pr_url, _ = check_pr_exists_with_error(branch_name)
    return pr_url


def check_pr_exists_with_error(
    branch_name: str, max_retries: int = GIT_MAX_RETRIES
) -> Tuple[Optional[str], Optional[str]]:
    """Check if PR exists for branch with error reporting and retry logic.

    Retries on transient network errors with exponential backoff.

    Returns:
        Tuple of (pr_url, error_message)
        - (url, None) if PR found
        - (None, None) if no PR exists (not an error)
        - (None, error_message) if check failed
    """
    # Use github.py functions to get repo info
    try:
        repo_url = get_repo_url()
        repo_path = extract_repo_path(repo_url)
    except Exception as e:
        error_msg = f"Failed to get repo info: {e}"
        logger.warning(error_msg)
        return None, error_msg

    last_error = None
    for attempt in range(max_retries):
        try:
            result = subprocess.run(
                [
                    "gh",
                    "pr",
                    "list",
                    "--repo",
                    repo_path,
                    "--head",
                    branch_name,
                    "--json",
                    "url",
                ],
                capture_output=True,
                text=True,
                timeout=60,
            )
        except subprocess.TimeoutExpired:
            last_error = "PR check timed out"
            if attempt < max_retries - 1:
                wait_time = GIT_RETRY_DELAY * (attempt + 1)
                logger.warning(f"PR check timed out, retrying in {wait_time}s...")
                time.sleep(wait_time)
                continue
            logger.warning(last_error)
            return None, last_error

        if result.returncode != 0:
            error_lower = result.stderr.lower()
            # Check for transient errors
            is_transient = any(msg in error_lower for msg in [
                "rate limit", "429", "502", "503", "504",
                "temporarily unavailable", "service unavailable",
                "connection", "timeout"
            ])

            if is_transient and attempt < max_retries - 1:
                wait_time = GIT_RETRY_DELAY * (attempt + 1)
                logger.warning(f"PR check failed with transient error, retrying in {wait_time}s...")
                time.sleep(wait_time)
                last_error = f"gh pr list failed: {result.stderr}"
                continue

            error_msg = f"gh pr list failed: {result.stderr}"
            logger.warning(error_msg)
            return None, error_msg

        try:
            prs = json.loads(result.stdout)
            if prs:
                return prs[0]["url"], None
            # No PR found - not an error
            return None, None
        except (json.JSONDecodeError, KeyError, IndexError) as e:
            error_msg = f"Failed to parse PR response: {e}"
            logger.warning(error_msg)
            return None, error_msg

    # Should not reach here, but return last error if we do
    return None, last_error


def validate_branch_name(branch_name: str) -> Tuple[bool, Optional[str]]:
    """Validate branch name follows expected conventions.

    ADW branches should follow pattern: {type}-issue-{number}-adw-{id}-{suffix}

    Returns:
        Tuple of (is_valid, error_message)
    """
    if not branch_name:
        return False, "Branch name is empty"

    if branch_name in ("main", "master", "develop"):
        return False, f"Cannot use protected branch: {branch_name}"

    # Check for valid git branch name characters
    if not re.match(r'^[\w./-]+$', branch_name):
        return False, f"Branch name contains invalid characters: {branch_name}"

    # Check for proper ADW format (optional but recommended)
    adw_pattern = r'^(chore|bug|feature)-issue-\d+-adw-\d{14}-[a-f0-9]+-'
    if not re.match(adw_pattern, branch_name):
        logger.debug(f"Branch name doesn't match ADW pattern (may be fine): {branch_name}")

    return True, None


def create_branch(
    branch_name: str, cwd: Optional[str] = None
) -> Tuple[bool, Optional[str]]:
    """Create and checkout a new branch. Returns (success, error_message)."""
    # Validate branch name first
    is_valid, error = validate_branch_name(branch_name)
    if not is_valid:
        return False, error

    # Create branch
    try:
        result = subprocess.run(
            ["git", "checkout", "-b", branch_name],
            capture_output=True,
            text=True,
            cwd=cwd,
            timeout=30,
        )
    except subprocess.TimeoutExpired:
        return False, "Git checkout -b timed out"

    if result.returncode != 0:
        # Check if error is because branch already exists
        if "already exists" in result.stderr:
            # Try to checkout existing branch
            try:
                result = subprocess.run(
                    ["git", "checkout", branch_name],
                    capture_output=True,
                    text=True,
                    cwd=cwd,
                    timeout=30,
                )
            except subprocess.TimeoutExpired:
                return False, "Git checkout timed out"

            if result.returncode != 0:
                return False, result.stderr
            return True, None
        return False, result.stderr
    return True, None


def commit_changes(
    message: str, cwd: Optional[str] = None
) -> Tuple[bool, Optional[str]]:
    """Stage all changes and commit. Returns (success, error_message)."""
    # Check if there are changes to commit
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            capture_output=True,
            text=True,
            cwd=cwd,
            timeout=30,
        )
    except subprocess.TimeoutExpired:
        return False, "Git status timed out"

    if not result.stdout.strip():
        return True, None  # No changes to commit

    # Stage all changes
    try:
        result = subprocess.run(
            ["git", "add", "-A"],
            capture_output=True,
            text=True,
            cwd=cwd,
            timeout=60,
        )
    except subprocess.TimeoutExpired:
        return False, "Git add timed out"

    if result.returncode != 0:
        return False, result.stderr

    # Commit
    try:
        result = subprocess.run(
            ["git", "commit", "-m", message],
            capture_output=True,
            text=True,
            cwd=cwd,
            timeout=60,
        )
    except subprocess.TimeoutExpired:
        return False, "Git commit timed out"

    if result.returncode != 0:
        return False, result.stderr
    return True, None


def get_pr_number(branch_name: str) -> Optional[str]:
    """Get PR number for a branch. Returns PR number if exists."""
    # Use github.py functions to get repo info
    try:
        repo_url = get_repo_url()
        repo_path = extract_repo_path(repo_url)
    except Exception as e:
        logger.warning(f"Failed to get repo info: {e}")
        return None

    try:
        result = subprocess.run(
            [
                "gh",
                "pr",
                "list",
                "--repo",
                repo_path,
                "--head",
                branch_name,
                "--json",
                "number",
                "--limit",
                "1",
            ],
            capture_output=True,
            text=True,
            timeout=60,
        )
    except subprocess.TimeoutExpired:
        logger.warning("PR number check timed out")
        return None

    if result.returncode == 0:
        try:
            prs = json.loads(result.stdout)
            if prs:
                return str(prs[0]["number"])
        except (json.JSONDecodeError, KeyError, IndexError) as e:
            logger.warning(f"Failed to parse PR number response: {e}")
    return None


def approve_pr(pr_number: str, logger: logging.Logger) -> Tuple[bool, Optional[str]]:
    """Approve a PR. Returns (success, error_message)."""
    try:
        repo_url = get_repo_url()
        repo_path = extract_repo_path(repo_url)
    except Exception as e:
        return False, f"Failed to get repo info: {e}"

    # BUG-053 fix: Add timeout to prevent hanging
    try:
        result = subprocess.run(
            [
                "gh",
                "pr",
                "review",
                pr_number,
                "--repo",
                repo_path,
                "--approve",
                "--body",
                "ADW Ship workflow approved this PR after validating all state fields.",
            ],
            capture_output=True,
            text=True,
            timeout=60,
        )
    except subprocess.TimeoutExpired:
        return False, "PR approval timed out"

    if result.returncode != 0:
        return False, result.stderr

    logger.info(f"Approved PR #{pr_number}")
    return True, None


def merge_pr(
    pr_number: str, logger: logging.Logger, merge_method: str = "squash"
) -> Tuple[bool, Optional[str]]:
    """Merge a PR. Returns (success, error_message).

    Args:
        pr_number: The PR number to merge
        logger: Logger instance
        merge_method: One of 'merge', 'squash', 'rebase' (default: 'squash')
    """
    try:
        repo_url = get_repo_url()
        repo_path = extract_repo_path(repo_url)
    except Exception as e:
        return False, f"Failed to get repo info: {e}"

    # First check if PR is mergeable
    # BUG-053 fix: Add timeout to prevent hanging
    try:
        result = subprocess.run(
            [
                "gh",
                "pr",
                "view",
                pr_number,
                "--repo",
                repo_path,
                "--json",
                "mergeable,mergeStateStatus",
            ],
            capture_output=True,
            text=True,
            timeout=60,
        )
    except subprocess.TimeoutExpired:
        return False, "PR status check timed out"

    if result.returncode != 0:
        return False, f"Failed to check PR status: {result.stderr}"

    # BUG-054 fix: Handle JSON parsing errors
    try:
        pr_status = json.loads(result.stdout)
    except json.JSONDecodeError as e:
        return False, f"Failed to parse PR status: {e}"

    if pr_status.get("mergeable") != "MERGEABLE":
        return (
            False,
            f"PR is not mergeable. Status: {pr_status.get('mergeStateStatus', 'unknown')}",
        )

    # Merge the PR
    merge_cmd = [
        "gh",
        "pr",
        "merge",
        pr_number,
        "--repo",
        repo_path,
        f"--{merge_method}",
    ]

    # Add auto-merge body
    merge_cmd.extend(
        ["--body", "Merged by ADW Ship workflow after successful validation."]
    )

    # BUG-053 fix: Add timeout to prevent hanging
    try:
        result = subprocess.run(merge_cmd, capture_output=True, text=True, timeout=120)
    except subprocess.TimeoutExpired:
        return False, "PR merge timed out"

    if result.returncode != 0:
        return False, result.stderr

    logger.info(f"Merged PR #{pr_number} using {merge_method} method")
    return True, None


def finalize_git_operations(
    state, logger: logging.Logger, cwd: Optional[str] = None
) -> Tuple[bool, Optional[str]]:
    """Standard git finalization: push branch and create/update PR.

    Returns (success, error_message) instead of silently failing.
    IMPORTANT: Callers MUST check the return value!

    Returns:
        Tuple of (success, error_message) - error_message is None on success
    """
    branch_name = state.get("branch_name")
    if not branch_name:
        # Fallback: use current git branch if not main
        current_branch = get_current_branch(cwd=cwd)
        if current_branch and current_branch != "main":
            logger.warning(
                f"No branch name in state, using current branch: {current_branch}"
            )
            branch_name = current_branch
        else:
            error_msg = "No branch name in state and current branch is main, skipping git operations"
            logger.error(error_msg)
            return False, error_msg

    # Validate branch name
    is_valid, validation_error = validate_branch_name(branch_name)
    if not is_valid:
        logger.error(f"Invalid branch name: {validation_error}")
        return False, validation_error

    # Always push
    success, error = push_branch(branch_name, cwd=cwd)
    if not success:
        logger.error(f"Failed to push branch: {error}")
        return False, f"Failed to push branch: {error}"

    logger.info(f"Pushed branch: {branch_name}")

    # Handle PR - use new function with error reporting
    pr_url, pr_check_error = check_pr_exists_with_error(branch_name)
    issue_number = state.get("issue_number")
    adw_id = state.get("adw_id")

    if pr_check_error:
        # Review fix #8: Distinguish "check failed" from "no PR exists".
        # If the check itself failed (transient network error), do NOT fall through
        # to PR creation - that could create duplicates or produce misleading errors.
        logger.warning(f"Error checking for existing PR: {pr_check_error}")
        return False, f"Cannot determine PR status: {pr_check_error}. Retry the operation."

    if pr_url:
        logger.info(f"Found existing PR: {pr_url}")
        # Post PR link for easy reference
        if issue_number and adw_id:
            try:
                make_issue_comment(issue_number, f"{adw_id}_ops: ✅ Pull request: {pr_url}")
            except Exception as e:
                # Non-fatal - log warning but don't fail
                logger.warning(f"Failed to post PR comment: {e}")
    else:
        # Create new PR - fetch issue data first
        pr_url = None
        error = None

        if not issue_number:
            error = "No issue number in state"
            logger.error(error)
            return False, error

        try:
            repo_url = get_repo_url()
            repo_path = extract_repo_path(repo_url)
            issue = fetch_issue(issue_number, repo_path)

            create_pr = _get_create_pull_request()
            pr_url, error = create_pr(branch_name, issue, state, logger, cwd)
        except Exception as e:
            logger.error(f"Failed to create PR: {e}")
            return False, f"Failed to create PR: {e}"

        if pr_url:
            logger.info(f"Created PR: {pr_url}")
            # Post new PR link
            if issue_number and adw_id:
                try:
                    make_issue_comment(
                        issue_number, f"{adw_id}_ops: ✅ Pull request created: {pr_url}"
                    )
                except Exception as e:
                    logger.warning(f"Failed to post PR comment: {e}")
        else:
            # BUG-092 fix: Handle case where error is None
            error_msg = error if error else "Unknown error creating PR"
            logger.error(f"Failed to create PR: {error_msg}")
            return False, f"Failed to create PR: {error_msg}"

    return True, None
