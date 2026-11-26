#!/usr/bin/env -S uv run
# /// script
# dependencies = ["python-dotenv", "pydantic", "redis"]
# ///

"""
ADW Domain Docs Iso - AI Developer Workflow for domain context documentation in isolated worktrees

Usage:
  uv run adw_domain_docs_iso.py <issue-number> <adw-id>

Workflow:
1. Load state and validate worktree exists
2. Detect whether the branch changed any business-domain files
3. Run /document_domains --changed to create/update affected ai_docs/domain/*.md docs
4. Commit the domain documentation in the worktree

Domain docs are *advisory* — this phase NEVER fails the surrounding workflow. Any
generation/commit error is logged and reported, and the script exits 0 so the SDLC
chain continues.

This workflow REQUIRES that adw_plan_iso.py or adw_patch_iso.py has been run first
to create the worktree. It cannot create worktrees itself.
"""

import sys
import os
import logging
import json
import subprocess
from typing import Optional
from dotenv import load_dotenv

from adw_modules.state import ADWState
from adw_modules.git_ops import commit_changes
from adw_modules.github import (
    fetch_issue,
    make_issue_comment,
    get_repo_url,
    extract_repo_path,
)
from adw_modules.workflow_ops import (
    create_commit,
    format_issue_message,
)
from adw_modules.utils import setup_logger, check_env_vars
from adw_modules.data_types import AgentTemplateRequest
from adw_modules.agent import execute_template
from adw_modules.worktree_ops import validate_worktree

# Agent name constant
AGENT_DOMAIN_DOCUMENTER = "domain_documenter"


def check_for_changes(logger: logging.Logger, cwd: Optional[str] = None) -> bool:
    """Check if there are any changes between current branch and origin/main."""
    try:
        result = subprocess.run(
            ["git", "diff", "origin/main", "--stat"],
            capture_output=True,
            text=True,
            check=True,
            cwd=cwd,
        )
        has_changes = bool(result.stdout.strip())
        if not has_changes:
            logger.info("No changes detected between current branch and origin/main")
        else:
            logger.info(f"Found changes:\n{result.stdout}")
        return has_changes
    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to check for changes: {e}")
        # If we can't check, assume there are changes and let the agent decide
        return True


def generate_domain_docs(
    issue_number: str,
    adw_id: str,
    logger: logging.Logger,
    working_dir: Optional[str] = None,
) -> bool:
    """Run /document_domains --changed. Returns True on success (advisory)."""
    request = AgentTemplateRequest(
        agent_name=AGENT_DOMAIN_DOCUMENTER,
        slash_command="/document_domains",
        args=["--changed"],
        adw_id=adw_id,
        working_dir=working_dir,
    )

    logger.debug(
        f"domain_docs_request: {request.model_dump_json(indent=2, by_alias=True)}"
    )

    response = execute_template(request)

    logger.debug(
        f"domain_docs_response: {response.model_dump_json(indent=2, by_alias=True)}"
    )

    if not response.success:
        logger.warning(f"Domain doc generation failed (advisory): {response.output}")
        make_issue_comment(
            issue_number,
            format_issue_message(
                adw_id,
                AGENT_DOMAIN_DOCUMENTER,
                f"⚠️ Domain doc generation failed (advisory, continuing): {response.output}",
            ),
        )
        return False

    logger.info(f"Domain doc generation output: {response.output.strip()}")
    return True


def main():
    """Main entry point."""
    load_dotenv()

    # adw-id is REQUIRED - we need it to find the worktree
    if len(sys.argv) < 3:
        print("Usage: uv run adw_domain_docs_iso.py <issue-number> <adw-id>")
        print("\nError: adw-id is required to locate the worktree")
        print("Run adw_plan_iso.py or adw_patch_iso.py first to create the worktree")
        sys.exit(1)

    issue_number = sys.argv[1]
    adw_id = sys.argv[2]

    temp_logger = setup_logger(adw_id, "adw_domain_docs_iso")
    state = ADWState.load(adw_id, temp_logger)
    if state:
        issue_number = state.get("issue_number", issue_number)
    else:
        temp_logger.error(f"No state found for ADW ID: {adw_id}")
        print(f"\nError: No state found for ADW ID: {adw_id}")
        print("Run adw_plan_iso.py or adw_patch_iso.py first to create the worktree and state")
        sys.exit(1)

    state.append_adw_id("adw_domain_docs_iso")

    logger = setup_logger(adw_id, "adw_domain_docs_iso")
    logger.info(f"ADW Domain Docs Iso starting - ID: {adw_id}, Issue: {issue_number}")

    check_env_vars(logger)

    # Validate worktree exists
    valid, error = validate_worktree(adw_id, state)
    if not valid:
        logger.error(f"Worktree validation failed: {error}")
        print(f"\nError: Worktree validation failed: {error}")
        sys.exit(1)

    worktree_path = state.get("worktree_path")
    logger.info(f"Using worktree at: {worktree_path}")

    make_issue_comment(
        issue_number,
        format_issue_message(
            adw_id,
            "ops",
            f"✅ Starting isolated domain documentation phase\n🏠 Worktree: {worktree_path}",
        ),
    )

    # Nothing changed -> nothing to document. Advisory, exit cleanly.
    if not check_for_changes(logger, cwd=worktree_path):
        logger.info("No changes detected - skipping domain documentation")
        make_issue_comment(
            issue_number,
            format_issue_message(
                adw_id,
                "ops",
                "ℹ️ No changes detected - skipping domain documentation",
            ),
        )
        state.save("adw_domain_docs_iso")
        return

    make_issue_comment(
        issue_number,
        format_issue_message(
            adw_id,
            AGENT_DOMAIN_DOCUMENTER,
            "📝 Updating domain context docs for changed domains...",
        ),
    )

    generated = generate_domain_docs(
        issue_number, adw_id, logger, working_dir=worktree_path
    )

    if not generated:
        # Advisory - do not fail the workflow
        state.save("adw_domain_docs_iso")
        return

    # Commit any domain doc changes (no-op if nothing was written)
    try:
        github_repo_url = get_repo_url()
        repo_path = extract_repo_path(github_repo_url)
        issue = fetch_issue(issue_number, repo_path)
        issue_command = state.get("issue_class", "/feature")

        commit_msg, error = create_commit(
            AGENT_DOMAIN_DOCUMENTER, issue, issue_command, adw_id, logger, worktree_path
        )
        if error:
            logger.warning(f"Skipping domain doc commit: {error}")
        else:
            success, commit_error = commit_changes(commit_msg, cwd=worktree_path)
            if success:
                logger.info(f"Committed domain docs: {commit_msg}")
                make_issue_comment(
                    issue_number,
                    format_issue_message(
                        adw_id, AGENT_DOMAIN_DOCUMENTER, "✅ Domain docs committed"
                    ),
                )
            else:
                logger.warning(f"No domain doc changes to commit: {commit_error}")
    except Exception as e:
        logger.warning(f"Domain doc commit step failed (advisory): {e}")

    logger.info("Isolated domain documentation phase completed")
    make_issue_comment(
        issue_number,
        format_issue_message(
            adw_id, "ops", "✅ Isolated domain documentation phase completed"
        ),
    )

    state.save("adw_domain_docs_iso")


if __name__ == "__main__":
    main()
