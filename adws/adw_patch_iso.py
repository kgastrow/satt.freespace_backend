#!/usr/bin/env -S uv run
# /// script
# dependencies = ["python-dotenv", "pydantic", "redis"]
# ///

"""
ADW Plan Iso - AI Developer Workflow for agentic planning in isolated worktrees

Usage:
  uv run adw_plan_iso.py <issue-number> [adw-id]

Workflow:
1. Fetch GitHub issue details
2. Check/create worktree for isolated execution
3. Allocate unique ports for services
4. Setup worktree environment
5. Classify issue type (/chore, /bug, /feature)
6. Create feature branch in worktree
7. Generate implementation plan in worktree
8. Commit plan in worktree
9. Push and create/update PR

This workflow creates an isolated git worktree under trees/<adw_id>/ for
parallel execution without interference.
"""

import sys
import os
import re
import logging
import json
from typing import Optional
from dotenv import load_dotenv

from adw_modules.state import ADWState
from adw_modules.git_ops import commit_changes, finalize_git_operations
from adw_modules.github import (
    fetch_issue,
    make_issue_comment,
    get_repo_url,
    extract_repo_path,
)
from adw_modules.workflow_ops import (
    classify_issue,
    build_plan,
    generate_branch_name,
    create_commit,
    format_issue_message,
    ensure_adw_id,
    AGENT_PLANNER,
)
from adw_modules.utils import setup_logger, check_env_vars
from adw_modules.data_types import GitHubIssue, IssueClassSlashCommand, AgentTemplateRequest
from adw_modules.agent import execute_template
from adw_modules.worktree_ops import (
    create_worktree,
    validate_worktree,
    get_ports_for_adw,
    is_port_available,
    find_next_available_ports,
    setup_worktree_environment,
)




def _extract_plan_content(raw_output: str, logger: logging.Logger) -> Optional[str]:
    """Extract plan markdown content from agent output.

    The agent should return the plan content directly, starting with
    '# Feature:', '# Bug:', or '# Chore:'. This function handles cases
    where the agent may have added preamble text or wrapped the plan in
    a code block.

    Returns the extracted plan content or None if not found.
    """
    content = raw_output.strip()

    # Best case: output starts directly with a plan heading
    if re.match(r'^# (Feature|Bug|Chore):', content):
        logger.debug("Clean plan content returned by agent")
        return content

    # Agent may have wrapped the plan in a markdown code block
    code_block_match = re.search(
        r'```(?:md|markdown)?\s*\n(# (?:Feature|Bug|Chore):.*?)```',
        content,
        re.DOTALL,
    )
    if code_block_match:
        extracted = code_block_match.group(1).strip()
        logger.info("Extracted plan content from code block")
        return extracted

    # Agent may have added preamble before the plan heading
    heading_match = re.search(
        r'^(# (?:Feature|Bug|Chore):.*)$', content, re.MULTILINE | re.DOTALL
    )
    if heading_match:
        extracted = heading_match.group(1).strip()
        logger.info("Extracted plan content after preamble")
        return extracted

    logger.error(
        f"Could not extract plan content from agent output ({len(content)} chars). "
        f"Output starts with: {content[:200]}"
    )
    return None


def _generate_plan_filename(
    issue_number: str, adw_id: str, plan_content: str
) -> str:
    """Generate a descriptive plan filename from the plan content heading.

    Extracts the name from '# Feature: <name>' / '# Bug: <name>' / '# Chore: <name>'
    and slugifies it.
    """
    # Extract the name after the heading type
    match = re.match(r'^# (?:Feature|Bug|Chore):\s*(.+)$', plan_content, re.MULTILINE)
    if match:
        name = match.group(1).strip()
        # Slugify: lowercase, replace non-alphanumeric with hyphens, collapse multiples
        slug = re.sub(r'[^a-z0-9]+', '-', name.lower()).strip('-')
        # Truncate to keep filename reasonable
        slug = slug[:60].rstrip('-')
    else:
        slug = "plan"

    return f"specs/issue-{issue_number}-adw-{adw_id}-sdlc_planner-{slug}.md"


def main():
    """Main entry point."""
    # Load environment variables
    load_dotenv()

    # Parse command line args
    if len(sys.argv) < 2:
        print("Usage: uv run adw_plan_iso.py <issue-number> [adw-id]")
        sys.exit(1)

    issue_number = sys.argv[1]
    adw_id = sys.argv[2] if len(sys.argv) > 2 else None

    # Ensure ADW ID exists with initialized state
    temp_logger = setup_logger(adw_id, "adw_plan_iso") if adw_id else None
    adw_id = ensure_adw_id(issue_number, adw_id, temp_logger)

    # Load the state that was created/found by ensure_adw_id
    state = ADWState.load(adw_id, temp_logger)

    # Ensure state has the adw_id field
    if not state.get("adw_id"):
        state.update(adw_id=adw_id)
    
    # Track that this ADW workflow has run
    state.append_adw_id("adw_plan_iso")

    # Set up logger with ADW ID
    logger = setup_logger(adw_id, "adw_plan_iso")
    logger.info(f"ADW Plan Iso starting - ID: {adw_id}, Issue: {issue_number}")

    # Validate environment
    check_env_vars(logger)

    # Get repo information
    try:
        github_repo_url = get_repo_url()
        repo_path = extract_repo_path(github_repo_url)
    except ValueError as e:
        logger.error(f"Error getting repository URL: {e}")
        sys.exit(1)

    # Check if worktree already exists
    valid, error = validate_worktree(adw_id, state)
    if valid:
        logger.info(f"Using existing worktree for {adw_id}")
        worktree_path = state.get("worktree_path")
        backend_port = state.get("backend_port")
        frontend_port = state.get("frontend_port")
    else:
        # Allocate ports for this instance
        backend_port, frontend_port = get_ports_for_adw(adw_id)
        
        # Check port availability
        if not (is_port_available(backend_port) and is_port_available(frontend_port)):
            logger.warning(f"Deterministic ports {backend_port}/{frontend_port} are in use, finding alternatives")
            backend_port, frontend_port = find_next_available_ports(adw_id)
        
        logger.info(f"Allocated ports - Backend: {backend_port}, Frontend: {frontend_port}")
        state.update(backend_port=backend_port, frontend_port=frontend_port)
        state.save("adw_plan_iso")

    # Fetch issue details
    issue: GitHubIssue = fetch_issue(issue_number, repo_path)

    logger.debug(f"Fetched issue: {issue.model_dump_json(indent=2, by_alias=True)}")
    make_issue_comment(
        issue_number, format_issue_message(adw_id, "ops", "✅ Starting isolated planning phase")
    )

    make_issue_comment(
        issue_number,
        f"{adw_id}_ops: 🔍 Using state\n```json\n{json.dumps(state.data, indent=2)}\n```",
    )

    # Classify the issue
    issue_command, error = classify_issue(issue, adw_id, logger)

    if error:
        logger.error(f"Error classifying issue: {error}")
        make_issue_comment(
            issue_number,
            format_issue_message(adw_id, "ops", f"❌ Error classifying issue: {error}"),
        )
        sys.exit(1)

    state.update(issue_class=issue_command)
    state.save("adw_plan_iso")
    logger.info(f"Issue classified as: {issue_command}")
    make_issue_comment(
        issue_number,
        format_issue_message(adw_id, "ops", f"✅ Issue classified as: {issue_command}"),
    )

    # Generate branch name
    branch_name, error = generate_branch_name(issue, issue_command, adw_id, logger)

    if error:
        logger.error(f"Error generating branch name: {error}")
        make_issue_comment(
            issue_number,
            format_issue_message(
                adw_id, "ops", f"❌ Error generating branch name: {error}"
            ),
        )
        sys.exit(1)

    # Don't create branch here - let worktree create it
    # The worktree command will create the branch when we specify -b
    state.update(branch_name=branch_name)
    state.save("adw_plan_iso")
    logger.info(f"Will create branch in worktree: {branch_name}")

    # Create worktree if it doesn't exist
    if not valid:
        logger.info(f"Creating worktree for {adw_id}")
        worktree_path, actual_branch, error = create_worktree(adw_id, branch_name, logger)

        if error:
            logger.error(f"Error creating worktree: {error}")
            make_issue_comment(
                issue_number,
                format_issue_message(adw_id, "ops", f"❌ Error creating worktree: {error}"),
            )
            sys.exit(1)

        # Reconcile branch name with what the worktree actually has
        if actual_branch and actual_branch != branch_name:
            logger.warning(f"Worktree branch mismatch: state={branch_name}, actual={actual_branch}. Using actual.")
            branch_name = actual_branch
            state.update(branch_name=branch_name)

        state.update(worktree_path=worktree_path)
        state.save("adw_plan_iso")
        logger.info(f"Created worktree at {worktree_path}")
        
        # Setup worktree environment (ports, database, playwright dirs)
        db_name, backend_port, frontend_port, db_error = setup_worktree_environment(
            worktree_path, backend_port, frontend_port, adw_id, logger
        )
        # Update state with actual ports (may differ if originals were unavailable)
        state.update(backend_port=backend_port, frontend_port=frontend_port)
        if db_error:
            logger.error(f"Failed to setup worktree environment: {db_error}")
            make_issue_comment(
                issue_number,
                format_issue_message(
                    adw_id, "ops", f"❌ Failed to create isolated database: {db_error}"
                ),
            )
            sys.exit(1)

        # Store database name in state
        state.update(database_name=db_name)
        state.save("adw_plan_iso")

        # Run install_worktree command to set up the isolated environment
        logger.info("Setting up isolated environment with custom ports")
        install_request = AgentTemplateRequest(
            agent_name="ops",
            slash_command="/install_worktree",
            args=[worktree_path, str(backend_port), str(frontend_port), db_name],
            adw_id=adw_id,
            working_dir=worktree_path,  # Execute in worktree
        )
        
        install_response = execute_template(install_request)
        if not install_response.success:
            logger.error(f"Error setting up worktree: {install_response.output}")
            make_issue_comment(
                issue_number,
                format_issue_message(adw_id, "ops", f"❌ Error setting up worktree: {install_response.output}"),
            )
            sys.exit(1)
        
        logger.info("Worktree environment setup complete")

    make_issue_comment(
        issue_number,
        format_issue_message(adw_id, "ops", f"✅ Working in isolated worktree: {worktree_path}\n"
                           f"🔌 Ports - Backend: {backend_port}, Frontend: {frontend_port}"),
    )

    # Prime the agent with codebase context before planning
    logger.info("Priming agent with codebase context")
    prime_request = AgentTemplateRequest(
        agent_name="primer",
        slash_command="/prime",
        args=[],
        adw_id=adw_id,
        working_dir=worktree_path,
    )
    prime_response = execute_template(prime_request)
    if not prime_response.success:
        logger.warning(f"Prime step had issues (non-blocking): {prime_response.output[:200]}")
    else:
        logger.info("Agent primed with codebase context")

    # Build the implementation plan (now executing in worktree)
    logger.info("Building implementation plan in worktree")
    make_issue_comment(
        issue_number,
        format_issue_message(adw_id, AGENT_PLANNER, "✅ Building implementation plan in isolated environment"),
    )

    plan_response = build_plan(issue, issue_command, adw_id, logger, working_dir=worktree_path)

    if not plan_response.success:
        logger.error(f"Error building plan: {plan_response.output}")
        make_issue_comment(
            issue_number,
            format_issue_message(
                adw_id, AGENT_PLANNER, f"❌ Error building plan: {plan_response.output}"
            ),
        )
        sys.exit(1)

    logger.debug(f"Plan response: {plan_response.output}")
    make_issue_comment(
        issue_number,
        format_issue_message(adw_id, AGENT_PLANNER, "✅ Implementation plan created"),
    )

    # Extract plan content from agent response and write to disk
    logger.info("Extracting plan content from agent response")
    raw_output = plan_response.output.strip()
    plan_content = _extract_plan_content(raw_output, logger)

    if not plan_content:
        preview = raw_output[:200] + "..." if len(raw_output) > 200 else raw_output
        error = (
            f"Planning agent did not return valid plan content. "
            f"Expected markdown starting with '# Feature:', '# Bug:', or '# Chore:' but got: {preview}"
        )
        logger.error(error)
        make_issue_comment(
            issue_number,
            format_issue_message(adw_id, "ops", f"❌ {error}"),
        )
        sys.exit(1)

    # Validate plan has required structure
    if "## Metadata" not in plan_content:
        error = "Plan content missing required '## Metadata' section"
        logger.error(error)
        make_issue_comment(
            issue_number,
            format_issue_message(adw_id, "ops", f"❌ {error}"),
        )
        sys.exit(1)

    # Generate filename and write plan to disk
    plan_file_path = _generate_plan_filename(issue_number, adw_id, plan_content)
    worktree_plan_path = os.path.join(worktree_path, plan_file_path)
    os.makedirs(os.path.dirname(worktree_plan_path), exist_ok=True)

    with open(worktree_plan_path, "w") as f:
        f.write(plan_content)

    logger.info(f"Plan written to: {plan_file_path} ({len(plan_content)} bytes)")

    state.update(plan_file=plan_file_path)
    state.save("adw_plan_iso")
    logger.info(f"Plan file created: {plan_file_path}")
    make_issue_comment(
        issue_number,
        format_issue_message(adw_id, "ops", f"✅ Plan file created: {plan_file_path}"),
    )

    # Create commit message
    logger.info("Creating plan commit")
    commit_msg, error = create_commit(
        AGENT_PLANNER, issue, issue_command, adw_id, logger, worktree_path
    )

    if error:
        logger.error(f"Error creating commit message: {error}")
        make_issue_comment(
            issue_number,
            format_issue_message(
                adw_id, AGENT_PLANNER, f"❌ Error creating commit message: {error}"
            ),
        )
        sys.exit(1)

    # Commit the plan (in worktree)
    success, error = commit_changes(commit_msg, cwd=worktree_path)

    if not success:
        logger.error(f"Error committing plan: {error}")
        make_issue_comment(
            issue_number,
            format_issue_message(
                adw_id, AGENT_PLANNER, f"❌ Error committing plan: {error}"
            ),
        )
        sys.exit(1)

    logger.info(f"Committed plan: {commit_msg}")
    make_issue_comment(
        issue_number, format_issue_message(adw_id, AGENT_PLANNER, "✅ Plan committed")
    )

    # Finalize git operations (push and PR)
    # Note: This will work from the worktree context
    git_success, git_error = finalize_git_operations(state, logger, cwd=worktree_path)
    if not git_success:
        logger.error(f"Git finalization failed: {git_error}")
        # Continue with completion - PR creation failure shouldn't block the workflow

    logger.info("Isolated planning phase completed successfully")
    make_issue_comment(
        issue_number, format_issue_message(adw_id, "ops", "✅ Isolated planning phase completed")
    )

    # Save final state
    state.save("adw_plan_iso")
    
    # Post final state summary to issue
    make_issue_comment(
        issue_number,
        f"{adw_id}_ops: 📋 Final planning state:\n```json\n{json.dumps(state.data, indent=2)}\n```"
    )


if __name__ == "__main__":
    main()