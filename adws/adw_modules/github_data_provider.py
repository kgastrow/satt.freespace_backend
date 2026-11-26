"""GitHub data provider for command center agent.

Fetches issues, PRs, and commits via the local `gh` CLI and returns
structured data for relay to the command center. All operations use
subprocess calls to `gh` — no GitHub API tokens are needed on the
server side.

Uses get_safe_subprocess_env() for all subprocess calls to ensure
the GH_TOKEN / GITHUB_PAT is available to the gh CLI.
"""

import json
import logging
import subprocess
from typing import Any, Dict, List, Optional

from adw_modules.github import check_gh_auth
from adw_modules.utils import get_safe_subprocess_env

logger = logging.getLogger(__name__)

GH_TIMEOUT = 30  # seconds


def is_gh_authenticated() -> bool:
    """Check if the gh CLI is authenticated.

    Returns:
        True if authenticated, False otherwise
    """
    return check_gh_auth() is None


def fetch_github_data(
    data_type: str,
    filters: Optional[Dict[str, Any]] = None,
    cwd: Optional[str] = None,
) -> Dict[str, Any]:
    """Fetch GitHub data via the gh CLI.

    Args:
        data_type: One of "issues", "prs", "commits"
        filters: Optional filters (state, limit, etc.)
        cwd: Working directory (must be inside a git repo for gh to work)

    Returns:
        Dictionary with "success" boolean and "data" or "error" key
    """
    if not filters:
        filters = {}

    auth_error = check_gh_auth()
    if auth_error:
        return {"success": False, "error": f"gh CLI not authenticated: {auth_error}"}

    try:
        if data_type == "issues":
            return _fetch_issues(filters, cwd)
        elif data_type == "prs":
            return _fetch_prs(filters, cwd)
        elif data_type == "commits":
            return _fetch_commits(filters, cwd)
        else:
            return {"success": False, "error": f"Unknown data_type: {data_type}"}
    except subprocess.TimeoutExpired:
        return {"success": False, "error": f"gh command timed out after {GH_TIMEOUT}s"}
    except Exception as e:
        return {"success": False, "error": f"Error fetching {data_type}: {str(e)}"}


def _fetch_issues(filters: Dict[str, Any], cwd: Optional[str]) -> Dict[str, Any]:
    """Fetch issues via gh issue list."""
    state = filters.get("state", "open")
    limit = min(filters.get("limit", 20), 100)

    cmd = [
        "gh", "issue", "list",
        "--state", state,
        "--limit", str(limit),
        "--json", "number,title,state,createdAt,updatedAt,labels,author,url",
    ]

    result = subprocess.run(
        cmd, capture_output=True, text=True, timeout=GH_TIMEOUT,
        cwd=cwd, env=get_safe_subprocess_env(),
    )

    if result.returncode != 0:
        return {"success": False, "error": result.stderr.strip()}

    data = json.loads(result.stdout)
    return {"success": True, "data": data, "data_type": "issues"}


def _fetch_prs(filters: Dict[str, Any], cwd: Optional[str]) -> Dict[str, Any]:
    """Fetch pull requests via gh pr list."""
    state = filters.get("state", "open")
    limit = min(filters.get("limit", 20), 100)

    cmd = [
        "gh", "pr", "list",
        "--state", state,
        "--limit", str(limit),
        "--json", "number,title,state,createdAt,updatedAt,labels,author,url,headRefName,isDraft",
    ]

    result = subprocess.run(
        cmd, capture_output=True, text=True, timeout=GH_TIMEOUT,
        cwd=cwd, env=get_safe_subprocess_env(),
    )

    if result.returncode != 0:
        return {"success": False, "error": result.stderr.strip()}

    data = json.loads(result.stdout)
    return {"success": True, "data": data, "data_type": "prs"}


def _fetch_commits(filters: Dict[str, Any], cwd: Optional[str]) -> Dict[str, Any]:
    """Fetch recent commits via git log with NUL-delimited format.

    Uses %x00 (NUL byte) as field delimiter to safely handle commit messages
    containing quotes, newlines, or other special characters.
    """
    limit = min(filters.get("limit", 20), 100)

    # Use NUL byte as field separator and record separator to handle
    # commit messages with quotes, backslashes, newlines, etc.
    cmd = [
        "git", "log",
        f"--max-count={limit}",
        "--format=%H%x00%h%x00%an%x00%aI%x00%s%x00",
    ]

    result = subprocess.run(
        cmd, capture_output=True, text=True, timeout=GH_TIMEOUT,
        cwd=cwd, env=get_safe_subprocess_env(),
    )

    if result.returncode != 0:
        return {"success": False, "error": result.stderr.strip()}

    commits = []
    for line in result.stdout.strip().split("\n"):
        line = line.strip()
        if not line:
            continue
        parts = line.split("\x00")
        if len(parts) >= 5:
            commits.append({
                "hash": parts[0],
                "short_hash": parts[1],
                "author": parts[2],
                "date": parts[3],
                "message": parts[4],
            })

    return {"success": True, "data": commits, "data_type": "commits"}


def fetch_pr_for_branch(branch_name: str, cwd: Optional[str] = None) -> Optional[str]:
    """Fetch the PR number for a branch, if one exists.

    Args:
        branch_name: Git branch name to look up
        cwd: Working directory (must be inside a git repo)

    Returns:
        PR number as string, or None if no PR exists
    """
    try:
        cmd = [
            "gh", "pr", "list",
            "--head", branch_name,
            "--json", "number",
            "--limit", "1",
        ]
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=GH_TIMEOUT,
            cwd=cwd, env=get_safe_subprocess_env(),
        )
        if result.returncode == 0:
            data = json.loads(result.stdout)
            if data:
                return str(data[0]["number"])
    except Exception as e:
        logger.debug(f"Error fetching PR for branch {branch_name}: {e}")

    return None
