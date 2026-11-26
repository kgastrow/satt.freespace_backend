#!/usr/bin/env -S uv run
# /// script
# dependencies = ["python-dotenv", "pydantic", "redis"]
# ///

"""
ADW Assimilate Design Iso - Assimilate a design handoff into the project's frontend
agent context (one-time per project, or re-run after handoff updates).

Usage:
  uv run adw_assimilate_design_iso.py <handoff-path> [adw-id] [--no-pr]

What it does:
1. Validates the handoff path contains a README.md and src/ directory
2. Creates an isolated worktree on branch chore/assimilate-design-<adw_id>
3. Runs /assimilate_design which:
   - Rewrites ai_docs/frontend/baseline_context.md "Brand Design System" section
   - Creates ai_docs/frontend/context/design_system.md (full token + screen catalog)
   - Seeds app/frontend/src/index.css if scaffold exists, else writes design_system_seed.md
4. Commits the ai_docs / index.css changes
5. Unless --no-pr: creates a tracking GitHub issue and opens a PR

Run this once before adw_greenfield_iso.py --design <handoff-path>.
"""

import sys
import os
import json
import logging
import subprocess
import re
from typing import Optional
from dotenv import load_dotenv

# Add the parent directory to Python path to import modules
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from adw_modules.state import ADWState
from adw_modules.git_ops import commit_changes, finalize_git_operations
from adw_modules.github import (
    fetch_issue,
    make_issue_comment,
    get_repo_url,
    extract_repo_path,
)
from adw_modules.workflow_ops import (
    create_commit,
    format_issue_message,
    ensure_adw_id,
)
from adw_modules.utils import setup_logger, check_env_vars
from adw_modules.data_types import AgentTemplateRequest, GitHubIssue
from adw_modules.agent import execute_template
from adw_modules.worktree_ops import (
    create_worktree,
    validate_worktree,
    get_ports_for_adw,
    is_port_available,
    find_next_available_ports,
    setup_worktree_environment,
)


AGENT_ASSIMILATOR = "design_assimilator"


def create_tracking_issue(
    handoff_path: str,
    repo_path: str,
    logger: logging.Logger,
) -> Optional[str]:
    """Create a GitHub issue to track the assimilation run.

    Returns the issue number on success, None on failure.
    """
    handoff_basename = os.path.basename(os.path.normpath(handoff_path))
    title = f"[Chore] Assimilate design handoff: {handoff_basename}"
    body = (
        f"## Design Handoff Assimilation\n\n"
        f"This issue tracks the one-time assimilation of the design handoff at "
        f"`{handoff_path}` into the project's frontend agent context.\n\n"
        f"The workflow rewrites:\n"
        f"- `ai_docs/frontend/baseline_context.md` (Brand Design System section)\n"
        f"- `ai_docs/frontend/context/design_system.md` (full token + screen catalog)\n"
        f"- Either `app/frontend/src/index.css` (if scaffold exists) or "
        f"`ai_docs/frontend/context/design_system_seed.md` (for true greenfield)\n\n"
        f"After this merges, greenfield runs invoking `--design {handoff_path}` "
        f"will receive design-aware module decomposition and visual-validation gates.\n\n"
        f"_Auto-created by `adw_assimilate_design_iso.py`._"
    )

    cmd = ["gh", "issue", "create", "-R", repo_path, "--title", title, "--body", body]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    if result.returncode != 0:
        logger.error(f"Failed to create tracking issue: {result.stderr}")
        return None

    issue_url = result.stdout.strip()
    m = re.search(r"/issues/(\d+)", issue_url)
    if not m:
        logger.error(f"Could not extract issue number from: {issue_url}")
        return None
    return m.group(1)


def main():
    """Main entry point."""
    load_dotenv()

    # Parse flags
    no_pr = "--no-pr" in sys.argv
    if no_pr:
        sys.argv.remove("--no-pr")

    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    handoff_path_arg = sys.argv[1]
    adw_id = sys.argv[2] if len(sys.argv) > 2 else None

    # Resolve handoff path (absolute or workspace-relative).
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if os.path.isabs(handoff_path_arg):
        handoff_abs = handoff_path_arg
    else:
        handoff_abs = os.path.join(project_root, handoff_path_arg)

    if not os.path.isdir(handoff_abs):
        print(f"Error: handoff path is not a directory: {handoff_abs}")
        sys.exit(1)
    if not os.path.isfile(os.path.join(handoff_abs, "README.md")):
        print(f"Error: handoff at {handoff_abs} has no README.md")
        sys.exit(1)
    if not os.path.isdir(os.path.join(handoff_abs, "src")):
        print(f"Error: handoff at {handoff_abs} has no src/ directory")
        sys.exit(1)

    handoff_rel = os.path.relpath(handoff_abs, project_root)

    # Set up logger / state. For this workflow we don't have a GitHub issue yet
    # unless we create one — the tracking issue is created after env validation.
    temp_logger = setup_logger(adw_id or "preliminary", "adw_assimilate_design_iso")

    # Use a synthetic "issue_number" of 0 until/unless we create a real tracking issue.
    # ensure_adw_id needs an issue_number; we'll set the real one later if --no-pr is off.
    synthetic_issue = "0"
    adw_id = ensure_adw_id(synthetic_issue, adw_id, temp_logger)
    logger = setup_logger(adw_id, "adw_assimilate_design_iso")
    logger.info(f"ADW Assimilate Design Iso starting - ID: {adw_id}, Handoff: {handoff_rel}")

    state = ADWState.load(adw_id, logger)
    if not state.get("adw_id"):
        state.update(adw_id=adw_id)
    state.append_adw_id("adw_assimilate_design_iso")
    state.update(issue_class="/chore", design_handoff_path=handoff_rel)
    state.save("adw_assimilate_design_iso")

    # Validate environment (gh CLI, env vars).
    check_env_vars(logger)

    # Tracking issue (skip when --no-pr is set; then we just commit locally).
    issue_number: Optional[str] = None
    repo_path: Optional[str] = None
    if not no_pr:
        try:
            github_repo_url = get_repo_url()
            repo_path = extract_repo_path(github_repo_url)
        except ValueError as e:
            logger.error(f"Error getting repository URL: {e}")
            sys.exit(1)

        issue_number = create_tracking_issue(handoff_rel, repo_path, logger)
        if not issue_number:
            logger.error("Failed to create tracking issue; aborting (use --no-pr to skip)")
            sys.exit(1)
        logger.info(f"Created tracking issue #{issue_number}")
        state.update(issue_number=issue_number)
        state.save("adw_assimilate_design_iso")

    # Worktree creation.
    valid, error = validate_worktree(adw_id, state)
    if valid:
        worktree_path = state.get("worktree_path")
        backend_port = state.get("backend_port")
        frontend_port = state.get("frontend_port")
        logger.info(f"Reusing existing worktree at {worktree_path}")
    else:
        backend_port, frontend_port = get_ports_for_adw(adw_id)
        if not (is_port_available(backend_port) and is_port_available(frontend_port)):
            logger.warning(f"Deterministic ports {backend_port}/{frontend_port} are in use, finding alternatives")
            backend_port, frontend_port = find_next_available_ports(adw_id)
        logger.info(f"Allocated ports - Backend: {backend_port}, Frontend: {frontend_port}")
        state.update(backend_port=backend_port, frontend_port=frontend_port)

        branch_name = f"chore-assimilate-design-{adw_id}"
        state.update(branch_name=branch_name)
        state.save("adw_assimilate_design_iso")

        logger.info(f"Creating worktree on branch {branch_name}")
        worktree_path, actual_branch, wt_error = create_worktree(adw_id, branch_name, logger)
        if wt_error:
            logger.error(f"Error creating worktree: {wt_error}")
            if issue_number:
                make_issue_comment(issue_number, format_issue_message(adw_id, "ops", f"❌ Worktree creation failed: {wt_error}"))
            sys.exit(1)

        if actual_branch and actual_branch != branch_name:
            logger.warning(f"Worktree branch mismatch: state={branch_name}, actual={actual_branch}. Using actual.")
            branch_name = actual_branch
            state.update(branch_name=branch_name)

        state.update(worktree_path=worktree_path)
        state.save("adw_assimilate_design_iso")

        # Worktree environment setup (database, ports, .ports.env). The assimilation
        # itself doesn't run the app, but we keep parity with other iso workflows so
        # the worktree can be reused for follow-up work and downstream tools find
        # the expected files.
        db_name, backend_port, frontend_port, db_error = setup_worktree_environment(
            worktree_path, backend_port, frontend_port, adw_id, logger
        )
        state.update(backend_port=backend_port, frontend_port=frontend_port)
        if db_error:
            logger.warning(f"Worktree env setup had issues (non-fatal for assimilation): {db_error}")
        else:
            state.update(database_name=db_name)
        state.save("adw_assimilate_design_iso")

    if issue_number:
        make_issue_comment(
            issue_number,
            format_issue_message(adw_id, "ops", f"✅ Worktree ready at {worktree_path}"),
        )

    # Run /assimilate_design in the worktree. The skill rewrites files inside the
    # worktree, which is what we'll commit and push.
    logger.info("Running /assimilate_design")
    if issue_number:
        make_issue_comment(
            issue_number,
            format_issue_message(adw_id, AGENT_ASSIMILATOR, "🎨 Assimilating design handoff..."),
        )

    # Resolve the handoff path relative to the worktree so paths in agent output
    # are stable across re-runs.
    handoff_in_worktree = os.path.join(worktree_path, handoff_rel)
    assimilate_request = AgentTemplateRequest(
        agent_name=AGENT_ASSIMILATOR,
        slash_command="/assimilate_design",
        args=[handoff_in_worktree, adw_id],
        adw_id=adw_id,
        working_dir=worktree_path,
    )

    response = execute_template(assimilate_request)
    if not response.success:
        logger.error(f"Assimilation failed: {response.output[:500]}")
        if issue_number:
            make_issue_comment(
                issue_number,
                format_issue_message(adw_id, AGENT_ASSIMILATOR, f"❌ Assimilation failed: {response.output[:500]}"),
            )
        sys.exit(1)

    logger.info("Assimilation complete")
    logger.debug(f"Assimilation output: {response.output}")
    if issue_number:
        make_issue_comment(
            issue_number,
            format_issue_message(adw_id, AGENT_ASSIMILATOR, "✅ Design handoff assimilated into ai_docs/"),
        )

    # Verify the expected outputs exist.
    expected_doc = os.path.join(worktree_path, "ai_docs/frontend/context/design_system.md")
    if not os.path.exists(expected_doc):
        logger.error(f"Expected output missing: {expected_doc}")
        if issue_number:
            make_issue_comment(
                issue_number,
                format_issue_message(adw_id, AGENT_ASSIMILATOR, f"❌ design_system.md was not written"),
            )
        sys.exit(1)

    # Commit the changes.
    commit_msg = (
        f"chore(design): assimilate design handoff `{handoff_rel}`\n\n"
        f"Rewrites ai_docs/frontend/baseline_context.md Brand Design System section "
        f"and creates ai_docs/frontend/context/design_system.md with the full token "
        f"reference and screen catalog. Seeds index.css if the frontend scaffold "
        f"exists, else writes design_system_seed.md for the first UI module to apply.\n\n"
        f"ADW: {adw_id}"
    )
    success, commit_error = commit_changes(commit_msg, cwd=worktree_path)
    if not success:
        logger.error(f"Commit failed: {commit_error}")
        if issue_number:
            make_issue_comment(
                issue_number,
                format_issue_message(adw_id, AGENT_ASSIMILATOR, f"❌ Commit failed: {commit_error}"),
            )
        sys.exit(1)

    logger.info(f"Committed: {commit_msg.splitlines()[0]}")
    if issue_number:
        make_issue_comment(
            issue_number,
            format_issue_message(adw_id, AGENT_ASSIMILATOR, "✅ Changes committed in worktree"),
        )

    # Push and open PR unless --no-pr.
    if not no_pr and issue_number:
        git_success, git_error = finalize_git_operations(state, logger, cwd=worktree_path)
        if not git_success:
            logger.error(f"Git finalization failed: {git_error}")
            # Non-fatal — assimilation succeeded locally.
            make_issue_comment(
                issue_number,
                format_issue_message(adw_id, "ops", f"⚠️ PR creation failed: {git_error}\nLocal commit is still present in worktree {worktree_path}"),
            )
        else:
            make_issue_comment(
                issue_number,
                format_issue_message(adw_id, "ops", "✅ Branch pushed, PR opened/updated"),
            )

    state.save("adw_assimilate_design_iso")

    print("\n=== ASSIMILATION COMPLETE ===")
    print(f"ADW ID:           {adw_id}")
    print(f"Handoff:          {handoff_rel}")
    print(f"Worktree:         {worktree_path}")
    print(f"Branch:           {state.get('branch_name')}")
    if issue_number:
        print(f"Tracking issue:   #{issue_number}")
    print()
    print("Next step:")
    print(f"  uv run adws/adw_greenfield_iso.py \"<spec-glob>\" --design {handoff_rel}")


if __name__ == "__main__":
    main()
