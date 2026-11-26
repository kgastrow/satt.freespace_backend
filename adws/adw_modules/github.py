#!/usr/bin/env -S uv run
# /// script
# dependencies = ["python-dotenv", "pydantic", "redis"]
# ///

"""
GitHub Operations Module - AI Developer Workflow (ADW)

This module contains all GitHub-related operations including:
- Issue fetching and manipulation
- Comment posting
- Repository path extraction
- Issue status management
"""

import hashlib
import random
import re
import subprocess
import sys
import os
import json
import time
import logging
from typing import Dict, List, Optional, Set, Tuple
from enum import Enum
from .data_types import GitHubIssue, GitHubIssueListItem, GitHubComment


class PollResult(str, Enum):
    """Result types for poll_for_comment_response."""
    SUCCESS = "success"
    TIMEOUT = "timeout"
    ISSUE_DELETED = "issue_deleted"
    ISSUE_CLOSED = "issue_closed"
    PERMISSION_DENIED = "permission_denied"
    AUTH_ERROR = "auth_error"
    INVALID_ISSUE = "invalid_issue"

# Module logger
logger = logging.getLogger(__name__)

# Bot identifier to prevent webhook loops and filter bot comments
ADW_BOT_IDENTIFIER = "[ADW-AGENTS]"
ADW_BOT_IDENTIFIER_LOWER = ADW_BOT_IDENTIFIER.lower()

# Default timeout for GitHub API calls
DEFAULT_GH_TIMEOUT = 60  # seconds

# Maximum retries for transient errors
MAX_GH_RETRIES = 3

# Maximum comment length (GitHub limit is 65536)
MAX_COMMENT_LENGTH = 65000

# Transient error indicators for retry logic
TRANSIENT_ERROR_INDICATORS = [
    "rate limit",
    "rate_limit",
    "502",
    "503",
    "504",
    "429",
    "temporarily unavailable",
    "service unavailable",
    "gateway timeout",
]


def check_gh_auth() -> Optional[str]:
    """Check if GitHub CLI is authenticated (BUG-007 fix).

    Returns:
        None if authenticated, error message string if not
    """
    try:
        # --active: only the account gh actually uses. Plain `gh auth status` also fails when any other
        # stored account can't be read, e.g. Keychain accounts over SSH on macOS while GH_TOKEN works.
        result = subprocess.run(
            ["gh", "auth", "status", "--active"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0 and "unknown flag" in (result.stderr or ""):  # gh older than 2.40
            result = subprocess.run(["gh", "auth", "status"], capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            return "GitHub CLI not authenticated. Run 'gh auth login' or set GITHUB_PAT environment variable."
        return None
    except FileNotFoundError:
        return "GitHub CLI (gh) is not installed."
    except subprocess.TimeoutExpired:
        return "GitHub CLI auth check timed out."


def get_github_env() -> Optional[Dict[str, str]]:
    """Get environment with GitHub token set up. Returns None if no GITHUB_PAT.

    Subprocess env behavior:
    - env=None → Inherits parent's environment (default)
    - env={} → Empty environment (no variables)
    - env=custom_dict → Only uses specified variables

    So this will work with gh authentication:
    # These are equivalent:
    result = subprocess.run(cmd, capture_output=True, text=True)
    result = subprocess.run(cmd, capture_output=True, text=True, env=None)

    But this will NOT work (no PATH, no auth):
    result = subprocess.run(cmd, capture_output=True, text=True, env={})
    """
    github_pat = os.getenv("GITHUB_PAT")
    if not github_pat:
        return None

    # Get PATH with fallback to common locations
    path = os.environ.get("PATH", "")
    if not path:
        # Provide reasonable defaults if PATH is somehow empty
        path = "/usr/local/bin:/usr/bin:/bin"

    # Only create minimal env with GitHub token
    env: Dict[str, str] = {
        "GH_TOKEN": github_pat,
        "PATH": path,
    }
    return env


def get_repo_url(cwd: Optional[str] = None) -> str:
    """Get GitHub repository URL from git remote."""
    try:
        result = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            capture_output=True,
            text=True,
            check=True,
            timeout=30,
            cwd=cwd,
        )
        return result.stdout.strip()
    except subprocess.TimeoutExpired:
        raise ValueError("git remote get-url command timed out")
    except subprocess.CalledProcessError:
        raise ValueError(
            "No git remote 'origin' found. Please ensure you're in a git repository with a remote."
        )
    except FileNotFoundError:
        raise ValueError("git command not found. Please ensure git is installed.")


def extract_repo_path(github_url: str) -> str:
    """Extract owner/repo from GitHub URL.

    Handles both HTTPS and SSH remote formats:
      - https://github.com/owner/repo.git
      - git@github.com:owner/repo.git
    """
    url = github_url.strip()
    # SSH format: git@github.com:owner/repo.git
    ssh_match = re.match(r"^git@github\.com:(.+?)(?:\.git)?$", url)
    if ssh_match:
        return ssh_match.group(1)
    # HTTPS format: https://github.com/owner/repo.git
    return url.replace("https://github.com/", "").replace(".git", "")


def fetch_issue(
    issue_number: str, repo_path: str, max_retries: int = 3, retry_delay: float = 5.0
) -> GitHubIssue:
    """Fetch GitHub issue using gh CLI and return typed model.

    Includes timeout to prevent indefinite blocking (BUG-006 fix).
    Retries on GraphQL "Could not resolve" errors to handle eventual
    consistency delays between GitHub's REST and GraphQL APIs.
    """
    # Use JSON output for structured data
    cmd = [
        "gh",
        "issue",
        "view",
        issue_number,
        "-R",
        repo_path,
        "--json",
        "number,title,body,state,author,assignees,labels,milestone,comments,createdAt,updatedAt,closedAt,url",
    ]

    # Set up environment with GitHub token if available
    env = get_github_env()

    for attempt in range(max_retries):
        try:
            # BUG-006 fix: Add timeout to prevent indefinite blocking
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                env=env,
                timeout=DEFAULT_GH_TIMEOUT,
            )

            if result.returncode == 0:
                # Parse JSON response into Pydantic model
                issue_data = json.loads(result.stdout)
                issue = GitHubIssue(**issue_data)

                return issue

            # Retry on GraphQL propagation delay (newly created issues
            # may not be immediately visible via the GraphQL API)
            if "Could not resolve" in result.stderr and attempt < max_retries - 1:
                print(
                    f"Issue #{issue_number} not yet available via GraphQL, "
                    f"retrying in {retry_delay}s (attempt {attempt + 1}/{max_retries})...",
                    file=sys.stderr,
                )
                time.sleep(retry_delay)
                continue

            print(result.stderr, file=sys.stderr)
            sys.exit(result.returncode)
        except subprocess.TimeoutExpired:
            print(f"Error: GitHub API call timed out after {DEFAULT_GH_TIMEOUT} seconds", file=sys.stderr)
            sys.exit(1)
        except FileNotFoundError:
            print("Error: GitHub CLI (gh) is not installed.", file=sys.stderr)
            print("\nTo install gh:", file=sys.stderr)
            print("  - Linux: sudo apt install gh", file=sys.stderr)
            print(
                "  - Linux: See https://github.com/cli/cli#installation",
                file=sys.stderr,
            )
            print(
                "  - Windows: See https://github.com/cli/cli#installation", file=sys.stderr
            )
            print("\nAfter installation, authenticate with: gh auth login", file=sys.stderr)
            sys.exit(1)
        except Exception as e:
            print(f"Error parsing issue data: {e}", file=sys.stderr)
            sys.exit(1)


def _record_progress(issue_id: str, comment: str) -> None:
    """Also keep every ADW comment locally, in agents/progress/issue-<n>.jsonl.

    Local tools (e.g. the Ore trigger, adw_triggers/trigger_ore.py) follow these files to show progress
    without polling GitHub. Never lets a local problem get in the way of posting the comment.
    """
    try:
        root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        path = os.path.join(root, "agents", "progress", f"issue-{issue_id}.jsonl")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        line = json.dumps({"ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "issue": str(issue_id), "comment": comment})
        with open(path, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception as e:  # noqa: BLE001 - progress is best effort
        logger.debug(f"Could not record progress for issue #{issue_id}: {e}")


def make_issue_comment(issue_id: str, comment: str, max_retries: int = MAX_GH_RETRIES) -> None:
    """Post a comment to a GitHub issue using gh CLI.

    Includes timeout and retry with exponential backoff for transient errors.
    Validates comment length and truncates if necessary.

    BUG-078 fix: Pre-checks authentication before attempting to post.
    """
    _record_progress(issue_id, comment)

    # BUG-078 fix: Pre-check authentication to fail fast
    auth_error = check_gh_auth()
    if auth_error:
        logger.error(f"GitHub authentication failed: {auth_error}")
        raise RuntimeError(f"GitHub auth error: {auth_error}")

    # Get repo information from git remote
    github_repo_url = get_repo_url()
    repo_path = extract_repo_path(github_repo_url)

    # Ensure comment has ADW_BOT_IDENTIFIER to prevent webhook loops
    if not comment.startswith(ADW_BOT_IDENTIFIER):
        comment = f"{ADW_BOT_IDENTIFIER} {comment}"

    # BUG-002 fix: Truncate with suffix length accounted for
    truncation_suffix = "\n\n...[truncated - message too long]"
    if len(comment) > MAX_COMMENT_LENGTH:
        logger.warning(f"Comment too long ({len(comment)} chars), truncating...")
        # Account for suffix length to stay within MAX_COMMENT_LENGTH
        comment = comment[:MAX_COMMENT_LENGTH - len(truncation_suffix)] + truncation_suffix

    # Build command
    cmd = [
        "gh",
        "issue",
        "comment",
        issue_id,
        "-R",
        repo_path,
        "--body",
        comment,
    ]

    # Set up environment with GitHub token if available
    env = get_github_env()

    last_error = None
    for attempt in range(max_retries):
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                env=env,
                timeout=DEFAULT_GH_TIMEOUT,
            )

            if result.returncode == 0:
                logger.info(f"Successfully posted comment to issue #{issue_id}")
                return
            else:
                error_msg = result.stderr.lower()
                # Check for transient errors that should be retried
                is_transient = any(indicator in error_msg for indicator in TRANSIENT_ERROR_INDICATORS)

                if is_transient and attempt < max_retries - 1:
                    last_error = RuntimeError(f"Transient error: {result.stderr}")
                    # Exponential backoff with jitter
                    wait_time = min((2 ** attempt) * 5 + random.uniform(0, 5), 60)
                    logger.warning(f"Transient error, retrying in {wait_time:.1f}s...")
                    time.sleep(wait_time)
                    continue

                logger.error(f"Error posting comment: {result.stderr}")
                raise RuntimeError(f"Failed to post comment: {result.stderr}")

        except subprocess.TimeoutExpired:
            last_error = RuntimeError(f"GitHub API timed out after {DEFAULT_GH_TIMEOUT}s")
            if attempt < max_retries - 1:
                wait_time = (2 ** attempt) * 5 + random.uniform(0, 5)
                logger.warning(f"Timeout, retrying in {wait_time:.1f}s...")
                time.sleep(wait_time)
                continue
            raise last_error
        except RuntimeError:
            raise
        except Exception as e:
            logger.error(f"Error posting comment: {e}")
            raise

    if last_error:
        raise last_error


def mark_issue_in_progress(issue_id: str) -> None:
    """Mark issue as in progress by adding label and comment."""
    # Get repo information from git remote
    github_repo_url = get_repo_url()
    repo_path = extract_repo_path(github_repo_url)

    # Add "in_progress" label
    cmd = [
        "gh",
        "issue",
        "edit",
        issue_id,
        "-R",
        repo_path,
        "--add-label",
        "in_progress",
    ]

    # Set up environment with GitHub token if available
    env = get_github_env()

    # Try to add label (may fail if label doesn't exist)
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, env=env, timeout=DEFAULT_GH_TIMEOUT
        )
        if result.returncode != 0:
            logger.warning(f"Could not add 'in_progress' label: {result.stderr}")
    except subprocess.TimeoutExpired:
        logger.warning("Timeout adding 'in_progress' label")

    # Assign to self (optional)
    cmd = [
        "gh",
        "issue",
        "edit",
        issue_id,
        "-R",
        repo_path,
        "--add-assignee",
        "@me",
    ]
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, env=env, timeout=DEFAULT_GH_TIMEOUT
        )
        if result.returncode == 0:
            logger.info(f"Assigned issue #{issue_id} to self")
    except subprocess.TimeoutExpired:
        logger.warning("Timeout assigning issue")


def fetch_open_issues(repo_path: str) -> List[GitHubIssueListItem]:
    """Fetch all open issues from the GitHub repository."""
    try:
        cmd = [
            "gh",
            "issue",
            "list",
            "--repo",
            repo_path,
            "--state",
            "open",
            "--json",
            "number,title,body,labels,createdAt,updatedAt",
            "--limit",
            "1000",
        ]

        # Set up environment with GitHub token if available
        env = get_github_env()

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=True,
            env=env,
            timeout=DEFAULT_GH_TIMEOUT,
        )

        issues_data = json.loads(result.stdout)
        issues = [GitHubIssueListItem(**issue_data) for issue_data in issues_data]
        logger.info(f"Fetched {len(issues)} open issues")
        return issues

    except subprocess.TimeoutExpired:
        logger.error(f"Timeout fetching open issues from {repo_path}")
        return []
    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to fetch issues: {e.stderr}")
        return []
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse issues JSON: {e}")
        return []


def fetch_issue_comments(repo_path: str, issue_number: int) -> List[Dict]:
    """Fetch all comments for a specific issue.

    Returns empty list on any error. For error-aware callers, use
    _fetch_issue_comments_with_error() instead.
    """
    comments, _ = _fetch_issue_comments_with_error(repo_path, issue_number)
    return comments


def _fetch_issue_comments_with_error(
    repo_path: str, issue_number: int
) -> Tuple[List[Dict], Optional[str]]:
    """Fetch all comments for a specific issue, with error reporting.

    Review fix #6: Returns error type so callers (e.g., poll loop) can
    distinguish between "no comments" and "issue deleted/forbidden".

    Returns:
        Tuple of (comments, error_type) where error_type is one of:
        None (success), "not_found", "permission", "timeout", "parse_error", "unknown"
    """
    try:
        cmd = [
            "gh",
            "issue",
            "view",
            str(issue_number),
            "--repo",
            repo_path,
            "--json",
            "comments",
        ]

        # Set up environment with GitHub token if available
        env = get_github_env()

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            env=env,
            timeout=DEFAULT_GH_TIMEOUT,
        )

        if result.returncode != 0:
            stderr_lower = result.stderr.lower()
            if "not found" in stderr_lower or "could not find" in stderr_lower:
                logger.error(f"Issue #{issue_number} not found")
                return [], "not_found"
            if "permission" in stderr_lower or "forbidden" in stderr_lower:
                logger.error(f"Permission denied for issue #{issue_number}")
                return [], "permission"
            logger.error(f"Failed to fetch comments for issue #{issue_number}: {result.stderr}")
            return [], "unknown"

        data = json.loads(result.stdout)
        comments = data.get("comments", [])

        # Sort comments by creation time
        comments.sort(key=lambda c: c.get("createdAt", ""))

        return comments, None

    except subprocess.TimeoutExpired:
        logger.error(f"Timeout fetching comments for issue #{issue_number}")
        return [], "timeout"
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse comments JSON for issue #{issue_number}: {e}")
        return [], "parse_error"


def find_keyword_from_comment(keyword: str, issue: GitHubIssue) -> Optional[GitHubComment]:
    """Find the latest comment containing a specific keyword.

    Args:
        keyword: The keyword to search for in comments
        issue: The GitHub issue containing comments

    Returns:
        The latest GitHubComment containing the keyword, or None if not found
    """
    # Sort comments by created_at date (newest first)
    sorted_comments = sorted(issue.comments, key=lambda c: c.created_at, reverse=True)

    # Search through sorted comments (newest first)
    for comment in sorted_comments:
        # Skip ADW bot comments to prevent loops
        if ADW_BOT_IDENTIFIER in comment.body:
            continue

        if keyword in comment.body:
            return comment

    return None


# Alias for backward compatibility with rescue workflow
post_issue_comment = make_issue_comment


def check_issue_state(repo_path: str, issue_number: int) -> Tuple[Optional[str], Optional[str]]:
    """Check if an issue exists and get its state.

    Args:
        repo_path: Repository path (owner/repo)
        issue_number: Issue number to check

    Returns:
        Tuple of (state, error_type) where:
        - state is "open", "closed", or None if error
        - error_type is None if successful, or one of:
          "not_found", "permission", "auth_error", "timeout"
    """
    cmd = [
        "gh", "issue", "view", str(issue_number),
        "--repo", repo_path,
        "--json", "state",
    ]

    env = get_github_env()

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            env=env,
            timeout=DEFAULT_GH_TIMEOUT,
        )

        if result.returncode == 0:
            data = json.loads(result.stdout)
            return data.get("state", "").lower(), None

        stderr_lower = result.stderr.lower()
        if "not found" in stderr_lower or "could not find" in stderr_lower:
            return None, "not_found"
        if "permission" in stderr_lower or "forbidden" in stderr_lower:
            return None, "permission"
        if "auth" in stderr_lower or "login" in stderr_lower:
            return None, "auth_error"

        return None, "unknown"

    except subprocess.TimeoutExpired:
        return None, "timeout"
    except json.JSONDecodeError:
        return None, "parse_error"
    except Exception:
        return None, "unknown"


def _keyword_matches(comment_body: str, keyword: str) -> bool:
    """Check if keyword matches in comment using word boundary matching.

    This prevents false positives like "unapproved" matching "approve".
    """
    keyword_lower = keyword.lower().strip()
    comment_lower = comment_body.lower().strip()

    # For multi-word keywords like "reduce scope:", use startswith
    if keyword_lower.endswith(':'):
        return comment_lower.startswith(keyword_lower)

    # For single words, use word boundary matching
    pattern = r'\b' + re.escape(keyword_lower) + r'\b'
    return bool(re.search(pattern, comment_lower))


def poll_for_comment_response(
    issue_number: str,
    keywords: List[str],
    timeout_seconds: int = 1800,
    poll_interval: int = 30,
    logger: Optional[logging.Logger] = None,
) -> Optional[str]:
    """Poll for a comment containing one of the expected keywords.

    Polls the issue for new comments containing any of the specified keywords.
    Used for human checkpoint approval in workflows.

    Args:
        issue_number: GitHub issue number to poll
        keywords: List of keywords to look for (e.g., ["approve", "cancel"])
        timeout_seconds: Maximum time to wait (default 30 minutes)
        poll_interval: Seconds between polls (default 30)
        logger: Optional logger for status updates

    Returns:
        The matching keyword/phrase found, or None if timeout/error.
        Use poll_for_comment_response_with_status for detailed error types.
    """
    result, _ = poll_for_comment_response_with_status(
        issue_number, keywords, timeout_seconds, poll_interval, logger
    )
    return result


def poll_for_comment_response_with_status(
    issue_number: str,
    keywords: List[str],
    timeout_seconds: int = 1800,
    poll_interval: int = 30,
    logger: Optional[logging.Logger] = None,
) -> Tuple[Optional[str], PollResult]:
    """Poll for a comment containing one of the expected keywords, with detailed status.

    Polls the issue for new comments containing any of the specified keywords.
    Used for human checkpoint approval in workflows.

    Args:
        issue_number: GitHub issue number to poll
        keywords: List of keywords to look for (e.g., ["approve", "cancel"])
        timeout_seconds: Maximum time to wait (default 30 minutes)
        poll_interval: Seconds between polls (default 30)
        logger: Optional logger for status updates

    Returns:
        Tuple of (comment_body, status) where:
        - comment_body is the matching comment or None
        - status is a PollResult enum indicating success or error type
    """
    # Use module logger if none provided
    log = logger if logger is not None else logging.getLogger(__name__)

    # Validate parameters
    if timeout_seconds <= 0:
        log.error("timeout_seconds must be positive")
        return None, PollResult.INVALID_ISSUE
    if poll_interval <= 0:
        log.error("poll_interval must be positive")
        return None, PollResult.INVALID_ISSUE
    if poll_interval >= timeout_seconds:
        log.warning(f"poll_interval ({poll_interval}) >= timeout_seconds ({timeout_seconds})")
    # BUG-010 fix: Validate keywords list is not empty
    if not keywords:
        log.error("keywords list cannot be empty")
        return None, PollResult.INVALID_ISSUE

    # Validate issue_number
    try:
        issue_num = int(issue_number)
    except (ValueError, TypeError):
        log.error(f"Invalid issue number: {issue_number}")
        return None, PollResult.INVALID_ISSUE

    # Get repo info
    # BUG-006 fix: get_repo_url() can fail for reasons unrelated to auth
    # (e.g., not in a git repo, no origin remote). Use INVALID_ISSUE instead of AUTH_ERROR.
    try:
        repo_url = get_repo_url()
        repo_path = extract_repo_path(repo_url)
    except ValueError as e:
        # Git-related errors (not in repo, no remote, etc.)
        log.error(f"Failed to get repo info: {e}")
        return None, PollResult.INVALID_ISSUE
    except FileNotFoundError:
        log.error("Git command not found")
        return None, PollResult.INVALID_ISSUE
    except Exception as e:
        log.error(f"Unexpected error getting repo info: {e}")
        return None, PollResult.INVALID_ISSUE

    # Pre-check authentication before starting poll loop
    auth_error = check_gh_auth()
    if auth_error:
        log.error(f"GitHub authentication failed: {auth_error}")
        return None, PollResult.AUTH_ERROR

    # Check issue state before polling
    issue_state, state_error = check_issue_state(repo_path, issue_num)
    if state_error:
        if state_error == "not_found":
            log.error(f"Issue #{issue_num} not found")
            return None, PollResult.ISSUE_DELETED
        if state_error == "permission":
            log.error(f"Permission denied for issue #{issue_num}")
            return None, PollResult.PERMISSION_DENIED
        if state_error == "auth_error":
            log.error("GitHub authentication error")
            return None, PollResult.AUTH_ERROR
        # BUG-080 fix: Handle timeout error type explicitly
        if state_error == "timeout":
            log.warning(f"Timeout checking issue #{issue_num} state, continuing anyway")
            # Continue - timeout is likely transient
        else:
            log.warning(f"Could not check issue state: {state_error}")
        # Continue anyway - might be a transient error

    if issue_state == "closed":
        log.warning(f"Issue #{issue_num} is closed - continuing to poll but response unlikely")
        # Don't fail - closed issues can still receive comments

    start_time = time.time()
    processed_comment_ids: Set[str] = set()

    # Get initial comments to establish baseline
    # BUG-079 fix: Only use "id" field, not createdAt as fallback.
    # createdAt can have timestamp collisions for rapid comments.
    initial_comments = fetch_issue_comments(repo_path, issue_num)
    for comment in initial_comments:
        comment_id = comment.get("id")
        if comment_id:
            processed_comment_ids.add(str(comment_id))

    log.info(f"Polling for response keywords: {keywords}")

    while True:
        elapsed = time.time() - start_time
        remaining = timeout_seconds - elapsed

        # Check timeout with proper boundary handling
        if remaining <= 0:
            break

        try:
            # Review fix #6: Use error-aware fetch to detect issue deletion
            # during polling (previously errors were swallowed, making the
            # poll loop unable to distinguish "no comments" from "issue deleted")
            comments, fetch_error = _fetch_issue_comments_with_error(repo_path, issue_num)

            if fetch_error:
                if fetch_error == "not_found":
                    log.error(f"Issue #{issue_num} was deleted during polling")
                    return None, PollResult.ISSUE_DELETED
                if fetch_error == "permission":
                    log.error(f"Permission denied for issue #{issue_num} during polling")
                    return None, PollResult.PERMISSION_DENIED
                # Transient errors (timeout, parse_error, unknown) - continue polling
                log.warning(f"Transient error fetching comments: {fetch_error}")
                sleep_time = min(poll_interval, max(0, remaining - 1))
                if sleep_time <= 0:
                    break
                time.sleep(sleep_time)
                continue

            # Check new comments (ones we haven't processed)
            for comment in comments:
                # BUG-001 fix: Use ID if available, else hash body+author as fallback
                # This prevents repeated processing of comments without IDs
                comment_id = comment.get("id")
                if comment_id:
                    comment_id_str = str(comment_id)
                else:
                    # Fallback: hash of body + author login for deduplication
                    # This handles edge case where GitHub API returns comment without ID
                    comment_body_raw = comment.get("body", "")
                    author_login = comment.get("author", {}).get("login", "unknown")
                    comment_id_str = f"hash:{hashlib.md5((comment_body_raw + author_login).encode()).hexdigest()}"

                # Skip if we've already processed this comment
                if comment_id_str in processed_comment_ids:
                    continue

                # Mark as processed
                processed_comment_ids.add(comment_id_str)

                comment_body = comment.get("body", "").strip()

                # Skip bot comments
                if ADW_BOT_IDENTIFIER_LOWER in comment_body.lower():
                    continue

                # Check for keywords using word boundary matching
                for keyword in keywords:
                    if _keyword_matches(comment_body, keyword):
                        log.info(f"Found matching response: {keyword}")
                        # Return the actual comment body for more context
                        return comment_body, PollResult.SUCCESS

            # Calculate sleep time, ensuring we don't exceed timeout
            # Leave a small buffer to avoid off-by-one errors
            sleep_time = min(poll_interval, max(0, remaining - 1))
            if sleep_time <= 0:
                break

            log.debug(f"No response yet, waiting {sleep_time:.0f}s ({remaining:.0f}s remaining)")
            time.sleep(sleep_time)

        except Exception as e:
            # Review fix #6: Error detection is now handled by
            # _fetch_issue_comments_with_error() above. This catch handles
            # any unexpected exceptions in the comment processing logic.
            log.warning(f"Error polling for comments: {e}")
            time.sleep(min(poll_interval, max(0, remaining - 1)))
            continue

    log.warning(f"Timeout after {timeout_seconds}s waiting for response")
    return None, PollResult.TIMEOUT
