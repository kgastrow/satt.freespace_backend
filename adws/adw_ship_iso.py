#!/usr/bin/env -S uv run
# /// script
# dependencies = ["python-dotenv", "pydantic", "redis"]
# ///

"""
ADW Ship Iso - AI Developer Workflow for shipping (merging) to main

Usage:
  uv run adw_ship_iso.py <issue-number> <adw-id>

Workflow:
1. Load state and validate worktree exists
2. Validate ALL state fields are populated (not None)
3. Perform manual git merge in main repository:
   - Fetch latest from origin
   - Checkout main
   - Merge feature branch
   - Push to origin/main
4. Post success message to issue

This workflow REQUIRES that all previous workflows have been run and that
every field in ADWState has a value. This is our final approval step.

Note: Merge operations happen in the main repository root, not in the worktree,
to preserve the worktree's state.
"""

import sys
import os
import fcntl
import contextlib
import logging
import json
import subprocess
from typing import Optional, Dict, Any, Tuple, Iterator
from dotenv import load_dotenv

from adw_modules.state import ADWState
from adw_modules.github import (
    make_issue_comment,
    get_repo_url,
    extract_repo_path,
)
from adw_modules.workflow_ops import format_issue_message
from adw_modules.utils import setup_logger, check_env_vars
from adw_modules.worktree_ops import validate_worktree
from adw_modules.data_types import ADWStateData

# Agent name constant
AGENT_SHIPPER = "shipper"


def get_main_repo_root() -> str:
    """Get the main repository root directory (parent of adws)."""
    # This script is in adws/, so go up one level to get repo root
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _safe_stash_pop(repo_root: str, logger: logging.Logger) -> None:
    """Pop git stash and log warnings on failure instead of silently ignoring."""
    result = subprocess.run(
        ["git", "stash", "pop"],
        capture_output=True, text=True, cwd=repo_root
    )
    if result.returncode != 0:
        logger.warning(f"git stash pop failed (changes may remain in stash): {result.stderr.strip()}")


@contextlib.contextmanager
def _merge_lock(repo_root: str, logger: logging.Logger) -> Iterator[None]:
    """Serialize ADW ship merges via an exclusive flock on .git/adw_ship.lock.

    All ADW workflows share the same main repo working tree — one index,
    one stash stack, one ORIG_HEAD. Without serialization, two concurrent
    ship workflows would clobber each other (worker B's `git stash` would
    stash worker A's in-progress conflict resolution; checkout/merge
    interleavings would produce nonsensical history). Merges are usually
    seconds, so blocking is fine.
    """
    lock_path = os.path.join(repo_root, ".git", "adw_ship.lock")
    lock_fd = os.open(lock_path, os.O_CREAT | os.O_WRONLY, 0o600)
    try:
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            logger.debug(f"Acquired merge lock: {lock_path}")
        except BlockingIOError:
            logger.info(
                f"Another ADW merge is in progress; waiting for lock at {lock_path}"
            )
            fcntl.flock(lock_fd, fcntl.LOCK_EX)
            logger.info("Merge lock acquired")
        yield
    finally:
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_UN)
        except Exception:
            pass
        os.close(lock_fd)


def _git_error_detail(result: subprocess.CompletedProcess) -> str:
    """Combine stderr + stdout into a single error string for git command failures.

    git merge and git pull write conflict details (file names, the
    'CONFLICT (content):' lines) to stdout, not stderr. Other failures
    (fetch, checkout, push) usually use stderr. Surfacing both ensures the
    operator sees what actually went wrong instead of an empty
    'Failed to merge X:' message.
    """
    parts = [
        s.strip() for s in (result.stderr, result.stdout)
        if s and s.strip()
    ]
    return " | ".join(parts) if parts else "(no output)"


def _list_unmerged_files(repo_root: str) -> list[str]:
    """Return the list of files git considers unmerged (conflict markers
    or modify/delete or both-added etc.).

    Uses `git diff --diff-filter=U -z` which is authoritative (the index has
    multiple stages for these files) and robust against paths containing
    spaces, newlines, or special characters that `git status --porcelain`
    would quote and that simple line-slicing mis-parses.
    """
    result = subprocess.run(
        ["git", "diff", "--name-only", "--diff-filter=U", "-z"],
        capture_output=True, text=True, cwd=repo_root,
    )
    if result.returncode != 0:
        return []
    return [p for p in result.stdout.split("\0") if p]


def _validate_post_merge_python_syntax(
    repo_root: str, logger: logging.Logger
) -> Tuple[bool, str]:
    """After a merge commit lands on main, run `python -m py_compile` on every
    .py file changed by the merge. Catches syntactically-broken outputs from
    union-merge auto-resolution or from the resolver agent.

    Returns (ok, error_message). On False, caller should hard-reset the merge.
    """
    result = subprocess.run(
        ["git", "diff", "--name-only", "HEAD~1", "HEAD"],
        capture_output=True, text=True, cwd=repo_root,
    )
    if result.returncode != 0:
        # No prior commit (initial commit case) — nothing to validate against.
        logger.debug("Could not diff HEAD~1..HEAD; skipping post-merge syntax check")
        return True, ""

    py_files = [
        f for f in result.stdout.splitlines()
        if f.endswith(".py") and os.path.isfile(os.path.join(repo_root, f))
    ]
    if not py_files:
        return True, ""

    # Prefer the project's venv python if installed; this matches the runtime
    # the backend actually executes under. Fall back to whatever python is
    # invoking the script.
    venv_py = os.path.join(repo_root, "app/backend/.venv/bin/python")
    py_cmd = venv_py if os.path.isfile(venv_py) else sys.executable

    errors: list[str] = []
    for f in py_files:
        full_path = os.path.join(repo_root, f)
        check = subprocess.run(
            [py_cmd, "-m", "py_compile", full_path],
            capture_output=True, text=True, cwd=repo_root,
        )
        if check.returncode != 0:
            errors.append(f"{f}: {check.stderr.strip()[:200]}")

    if errors:
        return False, "Post-merge py_compile failures:\n  " + "\n  ".join(errors)
    return True, ""


def _validate_post_merge_no_conflict_markers(
    repo_root: str, logger: logging.Logger
) -> Tuple[bool, str]:
    """Scan changed text files for residual conflict markers.

    `py_compile` catches Python syntax breakage but doesn't run on `.ts`,
    `.tsx`, `.js`, `.jsx`, `.json`, `.md`, `.yaml`. A leftover `<<<<<<<` or
    `>>>>>>>` from the resolver agent (or from a `merge=union` driver
    interaction that produced text noise) would break the next build. This
    is a cheap grep — no tsc dependency — that catches the gap.
    """
    result = subprocess.run(
        ["git", "diff", "--name-only", "HEAD~1", "HEAD"],
        capture_output=True, text=True, cwd=repo_root,
    )
    if result.returncode != 0:
        return True, ""

    extensions = (".ts", ".tsx", ".js", ".jsx", ".json", ".md", ".yaml", ".yml")
    target_files = [
        f for f in result.stdout.splitlines()
        if f.endswith(extensions) and os.path.isfile(os.path.join(repo_root, f))
    ]

    errors: list[str] = []
    for f in target_files:
        full_path = os.path.join(repo_root, f)
        try:
            with open(full_path, "r", errors="replace") as fh:
                content = fh.read()
        except Exception as e:
            logger.debug(f"Could not read {f} for conflict-marker scan: {e}")
            continue
        if "<<<<<<<" in content or ">>>>>>>" in content:
            errors.append(f)

    if errors:
        return False, "Files contain residual merge conflict markers:\n  " + "\n  ".join(errors)
    return True, ""


def _rollback_merge(
    repo_root: str,
    pre_merge_sha: str,
    original_branch: str,
    stashed: bool,
    logger: logging.Logger,
) -> None:
    """Undo a just-created merge commit and restore the prior branch+stash.

    Called when post-merge validation fails after `git merge` succeeded.
    The merge commit is on local main only at this point (push hasn't run),
    so a hard reset is safe. Uses an explicit pre-merge SHA captured before
    the merge began rather than ORIG_HEAD — ORIG_HEAD can be silently
    clobbered by any intermediate merge/pull/reset (including ones a
    misbehaving resolver agent might run).
    """
    logger.info(f"Rolling back local merge commit (hard reset to {pre_merge_sha[:12]})")
    subprocess.run(
        ["git", "reset", "--hard", pre_merge_sha],
        cwd=repo_root, capture_output=True, text=True,
    )
    subprocess.run(
        ["git", "checkout", original_branch],
        cwd=repo_root, capture_output=True, text=True,
    )
    if stashed:
        _safe_stash_pop(repo_root, logger)


def attempt_merge_conflict_resolution(
    branch_name: str,
    adw_id: str,
    repo_root: str,
    logger: logging.Logger,
) -> Tuple[bool, str]:
    """Spawn the /resolve_merge_conflict agent to fix the in-progress merge.

    Called when ``git merge`` has stopped with conflict markers in the working
    tree. The agent reads `:1:`/`:2:`/`:3:` versions of each conflicted file,
    decides a per-file strategy (union for append-only registries; pick-one
    for semantic duplicates; careful combine for safe logic merges), writes
    resolved files and stages them.

    After the agent returns, this function verifies no unmerged files remain
    and creates the merge commit. The caller then runs post-merge syntax
    validation and pushes.

    Returns (resolved, error). On True: merge commit exists on local main.
    On False: caller should `git merge --abort` and bail.
    """
    # Lazy import — only loaded when we actually need to invoke an agent,
    # which is rare relative to the normal happy path.
    from adw_modules.agent import execute_template
    from adw_modules.data_types import AgentTemplateRequest

    conflicted = _list_unmerged_files(repo_root)
    if not conflicted:
        logger.warning(
            "attempt_merge_conflict_resolution invoked with no conflicted files"
        )
        return False, "No conflicted files detected"

    logger.info(
        f"Spawning /resolve_merge_conflict agent for {len(conflicted)} file(s): "
        f"{', '.join(conflicted[:5])}{'...' if len(conflicted) > 5 else ''}"
    )

    report_dir = os.path.join(repo_root, "agents", adw_id)
    os.makedirs(report_dir, exist_ok=True)
    safe_branch = branch_name.replace("/", "_").replace(" ", "_")[:60]
    report_path = os.path.join(
        report_dir, f"merge_conflict_resolution_{safe_branch}.json",
    )

    agent_name = "merge_conflict_resolver"
    request = AgentTemplateRequest(
        agent_name=agent_name,
        slash_command="/resolve_merge_conflict",
        args=[adw_id, branch_name, report_path],
        adw_id=adw_id,
        # The merge is in progress in the main repo root, NOT a worktree.
        # Agent must operate there to see the conflict markers.
        working_dir=repo_root,
    )

    response = execute_template(request)
    if not response.success:
        # Full output (not truncated) — subtle resolver failures need the
        # complete agent transcript to debug.
        logger.error(f"Resolver agent failed. Full output:\n{response.output}")
        return False, f"Resolver agent failed (see logs for full output): {response.output[:300]}"

    # Confirm no unmerged files remain. If the resolver gave up on any file,
    # this catches it.
    still_unmerged = _list_unmerged_files(repo_root)
    if still_unmerged:
        return False, (
            f"Resolver did not fully resolve conflicts. "
            f"Still unmerged: {', '.join(still_unmerged)}"
        )

    # The resolver MUST write a report and MUST report all_resolved. Missing
    # report or any other outcome is a hard failure — even if the filesystem
    # looks clean, an agent that bypassed its own contract is not trustworthy
    # to commit.
    if not os.path.isfile(report_path):
        return False, f"Resolver did not write required report at {report_path}"
    try:
        with open(report_path) as f:
            report = json.load(f)
    except Exception as e:
        return False, f"Resolver report unreadable at {report_path}: {e}"

    outcome = report.get("outcome", "")
    if outcome != "all_resolved":
        logger.error(f"Resolver report (full):\n{json.dumps(report, indent=2)}")
        skipped = report.get("skipped", [])
        return False, (
            f"Resolver report outcome={outcome!r} (expected 'all_resolved'). "
            f"Skipped {len(skipped)} file(s)."
        )

    # Defense-in-depth: verify the merge is still in progress (.git/MERGE_HEAD
    # exists). The resolver spec forbids `git merge --abort`, but enforcement
    # is prose-only. If the agent aborted the merge then staged something
    # else, `git commit --no-edit` would either fail or create a misleading
    # commit on main. Refuse in that case.
    merge_head_path = os.path.join(repo_root, ".git", "MERGE_HEAD")
    if not os.path.isfile(merge_head_path):
        return False, (
            "MERGE_HEAD is gone — agent appears to have aborted the merge "
            "despite spec ban. Refusing to commit."
        )

    # Complete the merge. Use --no-edit so we keep the default merge message
    # git prepared from the failed merge.
    commit_result = subprocess.run(
        ["git", "commit", "--no-edit"],
        capture_output=True, text=True, cwd=repo_root,
    )
    if commit_result.returncode != 0:
        return False, (
            f"Could not commit auto-resolved merge: {_git_error_detail(commit_result)}"
        )

    logger.info(
        f"Auto-resolved {len(conflicted)} merge conflict(s); merge committed."
    )
    return True, ""


def manual_merge_to_main(
    branch_name: str,
    logger: logging.Logger,
    adw_id: Optional[str] = None,
) -> Tuple[bool, Optional[str]]:
    """Manually merge a branch to main using git commands.
    
    This runs in the main repository root, not in a worktree.
    
    Args:
        branch_name: The feature branch to merge
        logger: Logger instance
        
    Returns:
        Tuple of (success, error_message)
    """
    repo_root = get_main_repo_root()
    logger.info(f"Performing manual merge in main repository: {repo_root}")

    # Serialize concurrent ADW ship workflows so they don't trample each
    # other's index/stash/ORIG_HEAD.
    with _merge_lock(repo_root, logger):
        stashed = False
        stash_applied = False  # Set when an explicit pop succeeded; prevents double-pop in finally.
        original_branch = ""

        try:
            # Save current branch to restore later
            result = subprocess.run(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                capture_output=True, text=True, cwd=repo_root
            )
            original_branch = result.stdout.strip()
            logger.debug(f"Original branch: {original_branch}")

            # Step 1: Fetch latest from origin
            logger.info("Fetching latest from origin...")
            result = subprocess.run(
                ["git", "fetch", "origin"],
                capture_output=True, text=True, cwd=repo_root
            )
            if result.returncode != 0:
                return False, f"Failed to fetch from origin: {_git_error_detail(result)}"

            # Step 2: Stash any uncommitted changes, then checkout main
            logger.info("Stashing any uncommitted changes...")
            stash_result = subprocess.run(
                ["git", "stash", "--include-untracked"],
                capture_output=True, text=True, cwd=repo_root
            )
            stashed = stash_result.returncode == 0 and "No local changes" not in stash_result.stdout

            logger.info("Checking out main branch...")
            result = subprocess.run(
                ["git", "checkout", "main"],
                capture_output=True, text=True, cwd=repo_root
            )
            if result.returncode != 0:
                return False, f"Failed to checkout main: {_git_error_detail(result)}"

            # Step 3: Pull latest main
            logger.info("Pulling latest main...")
            result = subprocess.run(
                ["git", "pull", "origin", "main"],
                capture_output=True, text=True, cwd=repo_root
            )
            if result.returncode != 0:
                return False, f"Failed to pull latest main: {_git_error_detail(result)}"

            # Capture HEAD SHA right before the merge so rollback can target it
            # explicitly. ORIG_HEAD would also work in the simple case but can
            # be silently overwritten by any intermediate merge/pull/reset
            # (including ones a misbehaving resolver agent might run).
            pre_merge_result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                capture_output=True, text=True, cwd=repo_root,
            )
            if pre_merge_result.returncode != 0:
                return False, f"Failed to capture pre-merge HEAD: {_git_error_detail(pre_merge_result)}"
            pre_merge_sha = pre_merge_result.stdout.strip()

            # Step 4: Merge the feature branch (no-ff to preserve all commits)
            logger.info(f"Merging branch {branch_name} (no-ff to preserve all commits)...")
            result = subprocess.run(
                ["git", "merge", branch_name, "--no-ff", "-m", f"Merge branch '{branch_name}' via ADW Ship workflow"],
                capture_output=True, text=True, cwd=repo_root
            )
            if result.returncode != 0:
                # Attempt auto-resolution via /resolve_merge_conflict agent before
                # giving up. The agent handles semantic conflicts that .gitattributes
                # merge=union can't safely produce (e.g., two branches independently
                # adding the same else: clause with different wording).
                initial_err = _git_error_detail(result)
                if adw_id:
                    resolved, resolve_err = attempt_merge_conflict_resolution(
                        branch_name, adw_id, repo_root, logger,
                    )
                else:
                    # Called from a context without an adw_id (e.g. ad-hoc). Don't
                    # spawn the resolver — it needs the adw_id for state/logging.
                    resolved, resolve_err = False, "no adw_id provided; resolver skipped"

                if not resolved:
                    # Abort the failed merge; branch/stash restore happens in finally.
                    subprocess.run(["git", "merge", "--abort"], cwd=repo_root)
                    return False, (
                        f"Failed to merge {branch_name}: {initial_err} | "
                        f"Auto-resolve: {resolve_err}"
                    )
                # Fall through — merge commit now exists on local main; continue to
                # post-merge validation and push.

            # Post-merge validation. Whether the merge auto-merged via
            # .gitattributes union, was resolved by the agent above, or applied
            # cleanly with no conflicts, we still validate the result.
            # py_compile catches Python syntax breakage; the conflict-marker
            # scan covers TS/JS/JSON/MD/YAML files (which py_compile ignores)
            # for the case where the agent left a `<<<<<<<` marker behind.
            # On either failure we hard-reset (push hasn't happened yet, so
            # local-only).
            syntax_ok, syntax_err = _validate_post_merge_python_syntax(repo_root, logger)
            if not syntax_ok:
                logger.error(f"Post-merge syntax validation failed:\n{syntax_err}")
                _rollback_merge(repo_root, pre_merge_sha, original_branch, stashed, logger)
                stash_applied = True  # _rollback_merge popped it
                return False, f"Post-merge syntax check failed: {syntax_err}"

            markers_ok, markers_err = _validate_post_merge_no_conflict_markers(repo_root, logger)
            if not markers_ok:
                logger.error(f"Post-merge conflict-marker scan failed:\n{markers_err}")
                _rollback_merge(repo_root, pre_merge_sha, original_branch, stashed, logger)
                stash_applied = True
                return False, f"Post-merge conflict-marker scan failed: {markers_err}"

            # Step 5: Push to origin/main (with retry for transient network errors)
            transient_patterns = [
                "unable to access", "could not resolve", "connection refused",
                "connection reset", "network unreachable", "timed out",
                "ssl", "temporarily unavailable", "remote end hung up",
            ]
            max_push_retries = 3
            push_success = False
            last_push_error = ""

            for push_attempt in range(max_push_retries):
                if push_attempt > 0:
                    import time
                    delay = 5 * (push_attempt + 1)
                    logger.info(f"Retrying push (attempt {push_attempt + 1}/{max_push_retries}) after {delay}s...")
                    time.sleep(delay)

                logger.info("Pushing to origin/main...")
                result = subprocess.run(
                    ["git", "push", "origin", "main"],
                    capture_output=True, text=True, cwd=repo_root,
                    timeout=120,
                )
                if result.returncode == 0:
                    push_success = True
                    break

                last_push_error = _git_error_detail(result)
                # Only retry on transient errors
                if not any(p in last_push_error.lower() for p in transient_patterns):
                    break

            if not push_success:
                # Undo the local merge to prevent phantom merge commit. Reset
                # to the captured pre-merge SHA, not origin/main — origin may
                # have advanced since `git pull` if another worker pushed
                # concurrently (the flock makes this rare but not impossible
                # across hosts).
                logger.info(f"Push failed - resetting local main to {pre_merge_sha[:12]}...")
                subprocess.run(
                    ["git", "reset", "--hard", pre_merge_sha],
                    capture_output=True, text=True, cwd=repo_root,
                )
                return False, f"Failed to push to origin/main: {last_push_error}"

            logger.info("✅ Successfully merged and pushed to main!")
            return True, None

        except Exception as e:
            logger.error(f"Unexpected error during merge: {e}")
            return False, str(e)
        finally:
            # Guarantee branch + stash restoration regardless of how we got
            # here (success, early return, exception). Each step is best-effort
            # and tolerant of the previous one failing.
            if original_branch:
                try:
                    subprocess.run(
                        ["git", "checkout", original_branch],
                        cwd=repo_root, capture_output=True, text=True,
                    )
                except Exception as e:
                    logger.warning(f"Final branch restore to {original_branch!r} failed: {e}")
            if stashed and not stash_applied:
                try:
                    _safe_stash_pop(repo_root, logger)
                except Exception as e:
                    logger.warning(f"Final stash pop failed: {e}")


def validate_state_completeness(state: ADWState, logger: logging.Logger) -> tuple[bool, list[str]]:
    """Validate that all fields in ADWState have values (not None).
    
    Returns:
        tuple of (is_valid, missing_fields)
    """
    # Get the expected fields from ADWStateData model
    expected_fields = {
        "adw_id",
        "issue_number",
        "branch_name",
        "plan_file",
        "issue_class",
        "worktree_path",
        "backend_port",
        "frontend_port",
    }
    
    missing_fields = []
    
    for field in expected_fields:
        value = state.get(field)
        if value is None:
            missing_fields.append(field)
            logger.warning(f"Missing required field: {field}")
        else:
            logger.debug(f"✓ {field}: {value}")
    
    return len(missing_fields) == 0, missing_fields


def main():
    """Main entry point."""
    # Load environment variables
    load_dotenv()
    
    # Parse command line args
    # INTENTIONAL: adw-id is REQUIRED - we need it to find the worktree and state
    if len(sys.argv) < 3:
        print("Usage: uv run adw_ship_iso.py <issue-number> <adw-id>")
        print("\nError: Both issue-number and adw-id are required")
        print("Run the complete SDLC workflow before shipping")
        sys.exit(1)
    
    issue_number = sys.argv[1]
    adw_id = sys.argv[2]
    
    # Try to load existing state
    temp_logger = setup_logger(adw_id, "adw_ship_iso")
    state = ADWState.load(adw_id, temp_logger)
    if not state:
        # No existing state found
        logger = setup_logger(adw_id, "adw_ship_iso")
        logger.error(f"No state found for ADW ID: {adw_id}")
        logger.error("Run the complete SDLC workflow before shipping")
        print(f"\nError: No state found for ADW ID: {adw_id}")
        print("Run the complete SDLC workflow before shipping")
        sys.exit(1)
    
    # Update issue number from state if available
    issue_number = state.get("issue_number", issue_number)
    
    # Track that this ADW workflow has run
    state.append_adw_id("adw_ship_iso")
    
    # Set up logger with ADW ID
    logger = setup_logger(adw_id, "adw_ship_iso")
    logger.info(f"ADW Ship Iso starting - ID: {adw_id}, Issue: {issue_number}")
    
    # Validate environment
    check_env_vars(logger)
    
    # Post initial status (non-critical — don't crash if comment fails)
    try:
        make_issue_comment(
            issue_number,
            format_issue_message(adw_id, "ops", f"🚢 Starting ship workflow\n"
                               f"📋 Validating state completeness...")
        )
    except Exception as e:
        logger.warning(f"Failed to post initial status comment: {e}")

    # Step 1: Validate state completeness
    logger.info("Validating state completeness...")
    is_valid, missing_fields = validate_state_completeness(state, logger)

    if not is_valid:
        error_msg = f"State validation failed. Missing fields: {', '.join(missing_fields)}"
        logger.error(error_msg)
        try:
            make_issue_comment(
                issue_number,
                format_issue_message(adw_id, AGENT_SHIPPER, f"❌ {error_msg}\n\n"
                                   "Please ensure all workflows have been run:\n"
                                   "- adw_plan_iso.py (creates plan_file, branch_name, issue_class)\n"
                                   "- adw_build_iso.py (implements the plan)\n"
                                   "- adw_test_iso.py (runs tests)\n"
                                   "- adw_review_iso.py (reviews implementation)\n"
                                   "- adw_document_iso.py (generates docs)")
            )
        except Exception as e:
            logger.warning(f"Failed to post validation failure comment: {e}")
        sys.exit(1)

    logger.info("✅ State validation passed - all fields have values")

    # Step 2: Validate worktree exists
    valid, error = validate_worktree(adw_id, state)
    if not valid:
        logger.error(f"Worktree validation failed: {error}")
        try:
            make_issue_comment(
                issue_number,
                format_issue_message(adw_id, AGENT_SHIPPER, f"❌ Worktree validation failed: {error}")
            )
        except Exception as e:
            logger.warning(f"Failed to post worktree validation comment: {e}")
        sys.exit(1)

    worktree_path = state.get("worktree_path")
    logger.info(f"✅ Worktree validated at: {worktree_path}")

    # Step 3: Get branch name
    branch_name = state.get("branch_name")
    logger.info(f"Preparing to merge branch: {branch_name}")

    try:
        make_issue_comment(
            issue_number,
            format_issue_message(adw_id, AGENT_SHIPPER, f"📋 State validation complete\n"
                               f"🔍 Preparing to merge branch: {branch_name}")
        )
    except Exception as e:
        logger.warning(f"Failed to post pre-merge comment: {e}")

    # Step 4: Perform manual merge
    logger.info(f"Starting manual merge of {branch_name} to main...")
    try:
        make_issue_comment(
            issue_number,
            format_issue_message(adw_id, AGENT_SHIPPER, f"🔀 Merging {branch_name} to main...\n"
                               "Using manual git operations in main repository")
        )
    except Exception as e:
        logger.warning(f"Failed to post merge-start comment: {e}")

    success, error = manual_merge_to_main(branch_name, logger, adw_id=adw_id)

    if not success:
        logger.error(f"Failed to merge: {error}")
        try:
            make_issue_comment(
                issue_number,
                format_issue_message(adw_id, AGENT_SHIPPER, f"❌ Failed to merge: {error}")
            )
        except Exception as e:
            logger.warning(f"Failed to post merge failure comment: {e}")
        sys.exit(1)

    logger.info(f"✅ Successfully merged {branch_name} to main")

    # BUG-GF-01 fix: Save state IMMEDIATELY after successful merge, before any
    # comments that could fail and cause a phantom failure (merge succeeded but
    # ship reports failure, leading to duplicate work on resume).
    state.save("adw_ship_iso")

    # Step 5: Post success message (non-critical — merge already succeeded)
    try:
        make_issue_comment(
            issue_number,
            format_issue_message(adw_id, AGENT_SHIPPER,
                               f"🎉 **Successfully shipped!**\n\n"
                               f"✅ Validated all state fields\n"
                               f"✅ Merged branch `{branch_name}` to main\n"
                               f"✅ Pushed to origin/main\n\n"
                               f"🚢 Code has been deployed to production!")
        )
    except Exception as e:
        logger.warning(f"Failed to post success comment: {e}")

    # Post final state summary (non-critical)
    try:
        make_issue_comment(
            issue_number,
            format_issue_message(adw_id, "ops", f"📋 Final ship state:\n```json\n{json.dumps(state.data, indent=2)}\n```")
        )
    except Exception as e:
        logger.warning(f"Failed to post final state comment: {e}")
    
    logger.info("Ship workflow completed successfully")


if __name__ == "__main__":
    main()