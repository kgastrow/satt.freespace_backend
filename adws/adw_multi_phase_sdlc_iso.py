#!/usr/bin/env -S uv run
# /// script
# dependencies = ["python-dotenv", "pydantic", "redis"]
# ///

"""
ADW Multi-Phase SDLC Iso - Multi-phase Software Development Life Cycle workflow

Usage: uv run adw_multi_phase_sdlc_iso.py <issue-number> [adw-id] [--resume] [--skip-smoke]

This workflow is designed for large features that would exceed a single agent's
context window. It breaks work into multiple phases, where each phase runs through:
  build -> test -> review -> commit

Workflow:
1. Multi-Phase Planning (Opus) - Creates detailed plan with phases
2. Phase Execution Loop - For each phase:
   a. Implement phase (scoped to phase files)
   b. Run scoped tests
   c. Review against phase criteria
   d. Commit phase atomically
3. Integration Validation - Full test suite, smoke tests, final review
4. Documentation - Generate docs for entire feature

The scripts are chained together via persistent state (multi_phase_state.json).
Each phase runs in the same git worktree with dedicated ports.
"""

import subprocess
import sys
import os
import json
import logging
import re
import signal
import atexit

# Add the parent directory to Python path to import modules
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


# BUG-004 fix: Global list to track child processes for cleanup
_child_processes: list = []
_cleanup_done = False


def _cleanup_child_processes(signum=None, frame=None):
    """Clean up child processes on termination (BUG-004 fix).

    Kills all tracked child processes to prevent zombies when the
    parent process is terminated.
    """
    global _cleanup_done
    if _cleanup_done:
        return
    _cleanup_done = True

    for proc in _child_processes:
        try:
            if proc.poll() is None:  # Still running
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
        except Exception:
            pass

    if signum is not None:
        # Re-raise the signal after cleanup
        sys.exit(1)


def _register_child_process(proc: subprocess.Popen):
    """Register a child process for cleanup tracking."""
    _child_processes.append(proc)


# Register cleanup handlers
signal.signal(signal.SIGTERM, _cleanup_child_processes)
signal.signal(signal.SIGINT, _cleanup_child_processes)
atexit.register(_cleanup_child_processes)

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, ValidationError
from typing import List as TypingList
from adw_modules.state import ADWState
from adw_modules import steps


# BUG-016 fix: Schema for review response validation
class ReviewIssue(BaseModel):
    """Schema for a single review issue."""
    model_config = ConfigDict(extra="allow")

    severity: str = "warning"
    description: str = ""
    file: str = ""
    resolution: str = ""


class ReviewResponse(BaseModel):
    """Schema for review phase response validation (BUG-016 fix)."""
    model_config = ConfigDict(extra="allow")

    review_passed: bool
    issues: TypingList[dict] = []
    summary: str = ""
    scope_compliance: dict = {}
from adw_modules.workflow_ops import (
    ensure_adw_id,
    format_issue_message,
    classify_issue,
    generate_branch_name,
    implement_plan,
)
from adw_modules.git_ops import (
    check_pr_exists_with_error,
    finalize_git_operations,
    push_branch,
)
from adw_modules.github import (
    fetch_issue,
    make_issue_comment,
    get_repo_url,
    extract_repo_path,
)
from adw_modules.agent import execute_template
from adw_modules.data_types import AgentTemplateRequest
from adw_modules.utils import setup_logger, check_env_vars
from adw_modules.worktree_ops import (
    create_worktree,
    setup_worktree_environment,
    get_ports_for_adw,
    find_next_available_ports,
    is_port_available,
)
from adw_modules.multi_phase_ops import (
    parse_multi_phase_plan,
    MultiPhaseState,
    PhaseStatus,
    get_phase_by_id,
)
from adw_modules.test_ops import (
    run_scoped_tests,
    run_full_test_suite,
    run_full_test_suite_with_resolution,
    run_build_validation,
    parse_build_errors,
    BuildValidationResult,
)


# Agent name constants for multi-phase workflow
AGENT_MULTI_PHASE_PLANNER = "multi_phase_planner"
AGENT_PHASE_IMPLEMENTOR = "phase_implementor"
AGENT_PHASE_REVIEWER = "phase_reviewer"
AGENT_ORCHESTRATOR = "orchestrator"
AGENT_PHASE_PATCH_PLANNER = "phase_patch_planner"

# Maximum retry attempts for phase failures
MAX_PHASE_RETRIES = 3
MAX_TEST_RETRIES = 3
MAX_REVIEW_RETRIES = 3
MAX_BUILD_RETRIES = 3

# Agent for build error resolution
AGENT_BUILD_RESOLVER = "build_resolver"


def _looks_like_plan(content: str) -> bool:
    """Check if content looks like a multi-phase plan (has phase sections)."""
    return bool(re.search(r'##+ Phase \d+', content))


def _extract_plan_content(output: str) -> str:
    """Extract plan markdown content from agent output.

    The agent should return the plan content directly, starting with a
    plan heading. This function handles cases where the agent may have
    added preamble text, wrapped the plan in a code block, or used
    various heading formats.

    Returns:
        The extracted plan content, or empty string if not found.
    """
    content = output.strip()

    # Heading patterns the agent might use (broadest match)
    # - "# Multi-Phase Feature: ..."
    # - "# Multi-Phase Implementation Plan: ..."
    # - "# Feature Name - Multi-Phase Plan"
    # - "# Feature Name — Multi-Phase Plan"
    _PLAN_HEADING = r'# .*(?:Multi-Phase|multi-phase)'

    # Best case: output starts with a plan heading
    if re.match(_PLAN_HEADING, content):
        return content

    # Agent may have wrapped the plan in a markdown code block
    code_block_match = re.search(
        r'```(?:md|markdown)?\s*\n(' + _PLAN_HEADING + r'.*?)```',
        content,
        re.DOTALL,
    )
    if code_block_match:
        return code_block_match.group(1).strip()

    # Agent may have added preamble before the plan heading
    heading_match = re.search(r'^(' + _PLAN_HEADING + r'.*)$', content, re.MULTILINE | re.DOTALL)
    if heading_match:
        return heading_match.group(1).strip()

    # Last resort: no recognizable heading, but content has phase sections
    if _looks_like_plan(content):
        # Find the first h1 heading and take everything from there
        h1_match = re.search(r'^(# .+)', content, re.MULTILINE)
        if h1_match:
            return content[h1_match.start():].strip()

    return ""


def _extract_plan_from_jsonl(jsonl_path: str, logger: logging.Logger) -> str:
    """Extract plan content from the raw JSONL output.

    Searches both Write tool calls (agent wrote plan to file) and assistant
    text blocks (agent output plan as text). Keeps the longest matching
    content found across all sources.

    Returns:
        The plan content, or empty string if not found.
    """
    if not os.path.exists(jsonl_path):
        return ""

    best_content = ""
    try:
        with open(jsonl_path, "r") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    d = json.loads(line)
                    msg = d.get("message", {})
                    if not isinstance(msg, dict):
                        continue
                    for block in msg.get("content", []):
                        if not isinstance(block, dict):
                            continue

                        # Check Write tool calls
                        if block.get("type") == "tool_use" and block.get("name") == "Write":
                            inp = block.get("input", {})
                            content = inp.get("content", "")
                            file_path = inp.get("file_path", "")
                            is_plan = (
                                re.search(r'(?:multi-phase|Multi-Phase)', content)
                                or _looks_like_plan(content)
                                or file_path.endswith("plan.md")
                            )
                            if is_plan and len(content) > len(best_content):
                                best_content = content

                        # Check assistant text blocks
                        if block.get("type") == "text":
                            content = block.get("text", "")
                            is_plan = (
                                re.search(r'(?:multi-phase|Multi-Phase)', content)
                                and _looks_like_plan(content)
                            )
                            if is_plan and len(content) > len(best_content):
                                best_content = content

                except json.JSONDecodeError:
                    continue
    except Exception as e:
        logger.debug(f"Error reading JSONL for plan extraction: {e}")

    return best_content.strip()


def _validate_plan_structure(content: str) -> list[str]:
    """Validate that plan content has the required structural markers.

    Accepts both strict format (### Phase 1:) and agent-generated
    format (## Phase 1:) since both are parseable downstream.

    Returns:
        List of validation errors (empty if valid).
    """
    errors = []
    # Accept either ## Phase 1 or ### Phase 1 (with or without colon)
    if not re.search(r'##+ Phase 1', content):
        errors.append("Missing Phase 1 section")
    return errors


def run_multi_phase_planning(
    issue_number: str,
    adw_id: str,
    issue_json: str,
    logger: logging.Logger,
    working_dir: str,
) -> tuple[bool, str]:
    """Run the multi-phase planning using Opus.

    The agent returns plan content as markdown in its response output.
    This function extracts, validates, and writes the plan to disk.

    Returns:
        Tuple of (success, plan_file_path)
    """
    logger.info("Starting multi-phase planning with Opus")

    request = AgentTemplateRequest(
        agent_name=AGENT_MULTI_PHASE_PLANNER,
        slash_command="/plan_multi_phase",
        args=[issue_number, adw_id, issue_json],
        adw_id=adw_id,
        working_dir=working_dir,
    )

    response = execute_template(request)

    if not response.success:
        logger.error(f"Multi-phase planning failed: {response.output}")
        return False, ""

    # === Extraction fallback chain ===
    # 1. Try extracting from agent response output (happy path)
    plan_content = _extract_plan_content(response.output)

    if not plan_content:
        # 2. Try extracting from JSONL Write tool calls (agent entered plan mode)
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        jsonl_path = os.path.join(
            project_root, "agents", adw_id,
            AGENT_MULTI_PHASE_PLANNER, "raw_output.jsonl",
        )
        logger.info(f"Response extraction failed, trying JSONL fallback: {jsonl_path}")
        plan_content = _extract_plan_from_jsonl(jsonl_path, logger)

    if not plan_content:
        # 3. Try reading plan.md that agent may have written to worktree
        plan_md_path = os.path.join(working_dir, "plan.md")
        if os.path.exists(plan_md_path):
            logger.info(f"JSONL extraction failed, trying plan.md fallback: {plan_md_path}")
            try:
                with open(plan_md_path, "r") as f:
                    candidate = f.read().strip()
                if candidate:
                    plan_content = _extract_plan_content(candidate)
                    if not plan_content and _looks_like_plan(candidate):
                        plan_content = candidate
            except Exception as e:
                logger.debug(f"Error reading plan.md: {e}")

    if not plan_content:
        logger.error(
            f"Could not extract plan content from any source. "
            f"Response starts with: {response.output[:200]}"
        )
        return False, ""

    logger.info(f"Plan content extracted ({len(plan_content)} chars)")

    # Validate plan has required structure
    validation_errors = _validate_plan_structure(plan_content)
    if validation_errors:
        logger.error(
            f"Plan content missing required sections: {', '.join(validation_errors)}. "
            f"Content starts with: {plan_content[:200]}"
        )
        return False, ""

    # Write plan to disk
    plan_file = f"specs/multi-phase/issue-{issue_number}-adw-{adw_id}-multi-phase.md"
    plan_path = os.path.join(working_dir, plan_file)
    os.makedirs(os.path.dirname(plan_path), exist_ok=True)

    with open(plan_path, "w") as f:
        f.write(plan_content)

    logger.info(f"Multi-phase plan written to: {plan_file} ({len(plan_content)} bytes)")
    return True, plan_file


def implement_phase(
    phase_id: str,
    plan_file: str,
    adw_id: str,
    logger: logging.Logger,
    working_dir: str,
) -> tuple[bool, str]:
    """Implement a single phase.

    Returns:
        Tuple of (success, output_message)
    """
    logger.info(f"Implementing phase: {phase_id}")

    request = AgentTemplateRequest(
        agent_name=f"{AGENT_PHASE_IMPLEMENTOR}_{phase_id}",
        slash_command="/implement_phase",
        args=[phase_id, plan_file],
        adw_id=adw_id,
        working_dir=working_dir,
    )

    response = execute_template(request)

    if not response.success:
        logger.error(f"Phase implementation failed: {response.output}")
        return False, response.output

    logger.info(f"Phase {phase_id} implemented successfully")
    return True, response.output


def review_phase(
    phase_id: str,
    plan_file: str,
    adw_id: str,
    logger: logging.Logger,
    working_dir: str,
) -> tuple[bool, dict]:
    """Review a phase implementation against its criteria.

    Returns:
        Tuple of (success, review_result_dict)
    """
    logger.info(f"Reviewing phase: {phase_id}")

    request = AgentTemplateRequest(
        agent_name=f"{AGENT_PHASE_REVIEWER}_{phase_id}",
        slash_command="/review_phase",
        args=[phase_id, plan_file],
        adw_id=adw_id,
        working_dir=working_dir,
    )

    response = execute_template(request)

    if not response.success:
        logger.error(f"Phase review failed: {response.output}")
        return False, {"error": response.output}

    # Parse JSON response - extract JSON from response even if there's surrounding text
    review_result = None

    # First try direct parse
    try:
        review_result = json.loads(response.output)
    except json.JSONDecodeError:
        # Try to extract JSON from markdown code block
        json_match = re.search(r'```json\s*([\s\S]*?)\s*```', response.output)
        if json_match:
            try:
                review_result = json.loads(json_match.group(1))
            except json.JSONDecodeError:
                pass

        # If still no result, try to find JSON object pattern
        if review_result is None:
            json_match = re.search(r'\{[\s\S]*"review_passed"[\s\S]*\}', response.output)
            if json_match:
                try:
                    review_result = json.loads(json_match.group(0))
                except json.JSONDecodeError:
                    pass

    if review_result is None:
        logger.error(f"Failed to parse review response as JSON: {response.output[:200]}")
        return False, {"error": "Invalid JSON response", "raw": response.output}

    # BUG-016 fix: Validate review response against schema
    try:
        validated_result = ReviewResponse.model_validate(review_result)
        review_result = validated_result.model_dump()
    except ValidationError as e:
        logger.warning(f"Review response schema validation failed (continuing with raw data): {e}")
        # Continue with raw data if validation fails - it may still be usable

    passed = review_result.get("review_passed", False)

    if passed:
        logger.info(f"Phase {phase_id} review passed")
    else:
        logger.warning(f"Phase {phase_id} review failed: {review_result.get('summary', 'Unknown')}")

    return passed, review_result


def resolve_phase_blockers(
    phase_id: str,
    blockers: list[dict],
    issue_number: str,
    adw_id: str,
    logger: logging.Logger,
    working_dir: str,
    phase_scope: list[str] | None = None,
) -> bool:
    """Resolve blocker issues found during phase review.

    Creates patch plans for each blocker and implements them.

    Args:
        phase_id: The phase being reviewed
        blockers: List of blocker issue dicts from review
        issue_number: GitHub issue number
        adw_id: ADW workflow ID
        working_dir: Path to the worktree
        logger: Logger instance
        phase_scope: Optional list of files in the phase's scope (used to
            constrain patches to only touch in-scope files)

    Returns:
        True if at least one blocker was resolved, False otherwise
    """
    logger.info(f"Resolving {len(blockers)} blocker(s) for phase {phase_id}")

    make_issue_comment(
        issue_number,
        format_issue_message(
            adw_id,
            AGENT_PHASE_PATCH_PLANNER,
            f"🔧 Found {len(blockers)} blocker(s) in phase `{phase_id}`, creating resolution plans..."
        )
    )

    # Build scope constraint text for the patch planner
    scope_constraint = ""
    if phase_scope:
        scope_files = "\n".join(f"  - `{f}`" for f in phase_scope)
        scope_constraint = (
            f"\n\nSCOPE CONSTRAINT (CRITICAL): This patch is for phase `{phase_id}`. "
            f"You MUST only modify or create files listed in the phase scope below. "
            f"Do NOT create new files outside this list. If the blocker cannot be resolved "
            f"within scope, state that clearly instead of creating out-of-scope files.\n"
            f"Phase scope:\n{scope_files}"
        )

    resolved_count = 0

    for i, blocker in enumerate(blockers, 1):
        description = blocker.get("description", blocker.get("issue", "Unknown issue"))
        resolution = blocker.get("resolution", blocker.get("fix", "Fix the issue"))

        logger.info(f"Resolving blocker {i}/{len(blockers)}: {description[:100]}")

        # Create patch plan with scope constraints
        patch_args = [
            f"Phase {phase_id} - Issue #{i}: {description}",
            f"Resolution: {resolution}{scope_constraint}",
            f"Severity: blocker",
        ]

        request = AgentTemplateRequest(
            agent_name=f"{AGENT_PHASE_PATCH_PLANNER}_{phase_id}_{i}",
            slash_command="/patch",
            args=patch_args,
            adw_id=adw_id,
            working_dir=working_dir,
        )

        plan_response = execute_template(request)

        if not plan_response.success:
            logger.error(f"Failed to create patch plan for blocker {i}: {plan_response.output}")
            continue

        # Extract plan file path
        plan_file = plan_response.output.strip()

        # Implement the patch
        logger.info(f"Implementing patch from plan: {plan_file}")
        impl_response = implement_plan(plan_file, adw_id, logger, working_dir=working_dir)

        if not impl_response.success:
            logger.error(f"Failed to implement patch for blocker {i}: {impl_response.output}")
            continue

        resolved_count += 1
        logger.info(f"Successfully resolved blocker {i}")

    make_issue_comment(
        issue_number,
        format_issue_message(
            adw_id,
            AGENT_PHASE_PATCH_PLANNER,
            f"✅ Resolved {resolved_count}/{len(blockers)} blocker(s) for phase `{phase_id}`"
        )
    )

    return resolved_count > 0


def commit_phase_changes(
    phase_id: str,
    issue_number: str,
    adw_id: str,
    logger: logging.Logger,
    working_dir: str,
) -> tuple[bool, str]:
    """Commit changes for a phase.

    Returns:
        Tuple of (success, commit_sha)
    """
    logger.info(f"Committing phase: {phase_id}")

    # Create commit message
    commit_msg = f"feat: implement {phase_id}\n\nPart of multi-phase implementation for #{issue_number}\nADW ID: {adw_id}"

    # Stage all changes
    stage_result = subprocess.run(
        ["git", "add", "-A"],
        capture_output=True,
        text=True,
        cwd=working_dir,
    )

    if stage_result.returncode != 0:
        logger.error(f"Failed to stage changes: {stage_result.stderr}")
        return False, ""

    # Check if there are changes to commit
    status_result = subprocess.run(
        ["git", "status", "--porcelain"],
        capture_output=True,
        text=True,
        cwd=working_dir,
    )

    if not status_result.stdout.strip():
        logger.warning("No changes to commit for this phase")
        return True, "no_changes"

    # Commit
    commit_result = subprocess.run(
        ["git", "commit", "-m", commit_msg],
        capture_output=True,
        text=True,
        cwd=working_dir,
    )

    if commit_result.returncode != 0:
        logger.error(f"Failed to commit: {commit_result.stderr}")
        return False, ""

    # Get commit SHA
    sha_result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        cwd=working_dir,
    )

    commit_sha = sha_result.stdout.strip()[:8]
    logger.info(f"Phase {phase_id} committed: {commit_sha}")

    return True, commit_sha


def push_changes(branch_name: str, working_dir: str, logger: logging.Logger) -> bool:
    """Push committed changes to remote using git_ops.push_branch."""
    success, error = push_branch(branch_name, cwd=working_dir)

    if not success:
        logger.error(f"Failed to push: {error}")
        return False

    logger.info(f"Changes pushed to remote (branch: {branch_name})")
    return True


def run_smoke_tests(
    issue_number: str,
    adw_id: str,
    working_dir: str,
    logger: logging.Logger,
) -> bool:
    """Run smoke tests."""
    logger.info("Running smoke tests")

    script_dir = os.path.dirname(os.path.abspath(__file__))
    smoke_cmd = [
        "uv", "run",
        os.path.join(script_dir, "adw_smoke_iso.py"),
        issue_number,
        adw_id,
    ]

    result = subprocess.run(smoke_cmd, cwd=working_dir, env=steps.child_env("integration"))
    return result.returncode == 0


def run_final_review(
    issue_number: str,
    adw_id: str,
    working_dir: str,
    logger: logging.Logger,
) -> bool:
    """Run final review of entire implementation."""
    logger.info("Running final review")

    script_dir = os.path.dirname(os.path.abspath(__file__))
    review_cmd = [
        "uv", "run",
        os.path.join(script_dir, "adw_review_iso.py"),
        issue_number,
        adw_id,
        "--skip-resolution",  # Don't auto-resolve in final review
    ]

    result = subprocess.run(review_cmd, cwd=working_dir, env=steps.child_env("integration"))
    return result.returncode == 0


def run_documentation(
    issue_number: str,
    adw_id: str,
    working_dir: str,
    logger: logging.Logger,
) -> bool:
    """Generate documentation for the feature."""
    logger.info("Generating documentation")

    script_dir = os.path.dirname(os.path.abspath(__file__))
    doc_cmd = [
        "uv", "run",
        os.path.join(script_dir, "adw_document_iso.py"),
        issue_number,
        adw_id,
    ]

    result = subprocess.run(doc_cmd, cwd=working_dir, env=steps.child_env("integration"))
    return result.returncode == 0


def run_build_with_resolution(
    issue_number: str,
    adw_id: str,
    working_dir: str,
    logger: logging.Logger,
    max_attempts: int = MAX_BUILD_RETRIES,
) -> tuple[bool, str]:
    """Run build validation with automatic error resolution.

    Attempts to build the project and automatically fix any TypeScript/build
    errors using the /resolve_build_error agent.

    Args:
        issue_number: GitHub issue number for status updates
        adw_id: ADW workflow ID
        working_dir: Root working directory (worktree path)
        logger: Logger instance
        max_attempts: Maximum number of build/fix cycles (default 3)

    Returns:
        Tuple of (success, summary_message)
    """
    attempt = 0

    while attempt < max_attempts:
        attempt += 1
        logger.info(f"Build validation attempt {attempt}/{max_attempts}")
        if attempt > 1:
            steps.record(adw_id, "build", "running", note=f"Attempt {attempt}", parent="integration")

        # Run build validation
        build_result = run_build_validation(working_dir, logger)

        if build_result.passed:
            logger.info("Build validation passed")
            return True, "Build validation passed"
        steps.record(adw_id, "build", "failed", parent="integration",
                     note=f"{len(build_result.errors)} build error(s)" if build_result.errors else "Unparseable build errors")

        # Build failed - check if we have parseable errors
        if not build_result.errors:
            logger.error("Build failed but no parseable errors found")
            make_issue_comment(
                issue_number,
                format_issue_message(adw_id, AGENT_BUILD_RESOLVER,
                    f"❌ Build failed but could not parse errors:\n```\n{build_result.raw_output[:2000]}\n```"
                )
            )
            return False, "Build failed with unparseable errors"

        # Report errors found
        error_summary = "\n".join([
            f"- {e.file_path}:{e.line} - {e.error_code}: {e.message[:100]}"
            for e in build_result.errors[:10]  # Limit to first 10 for readability
        ])
        total_errors = len(build_result.errors)

        make_issue_comment(
            issue_number,
            format_issue_message(adw_id, AGENT_BUILD_RESOLVER,
                f"🔧 Build validation failed with {total_errors} error(s) (attempt {attempt}/{max_attempts})\n"
                f"Attempting automatic resolution...\n\n"
                f"Errors found:\n{error_summary}"
            )
        )

        # Group errors by file for more efficient resolution
        errors_by_file: dict[str, list] = {}
        for error in build_result.errors:
            if error.file_path not in errors_by_file:
                errors_by_file[error.file_path] = []
            errors_by_file[error.file_path].append(error)

        # Resolve errors file by file
        files_resolved = 0
        for file_path, file_errors in errors_by_file.items():
            logger.info(f"Resolving {len(file_errors)} error(s) in {file_path}")

            # Create payload with all errors for this file
            error_payloads = "\n\n---\n\n".join([
                e.to_resolution_payload() for e in file_errors
            ])

            # Create agent request
            agent_name = f"{AGENT_BUILD_RESOLVER}_attempt{attempt}_{file_path.replace('/', '_')[:30]}"
            request = AgentTemplateRequest(
                agent_name=agent_name,
                slash_command="/resolve_build_error",
                args=[error_payloads],
                adw_id=adw_id,
                working_dir=working_dir,
            )

            # Execute resolution
            response = execute_template(request)

            if response.success:
                files_resolved += 1
                logger.info(f"Successfully resolved errors in {file_path}")
            else:
                logger.warning(f"Failed to resolve errors in {file_path}: {response.output[:200]}")

        if files_resolved == 0:
            logger.error("No files were successfully resolved, stopping attempts")
            make_issue_comment(
                issue_number,
                format_issue_message(adw_id, AGENT_BUILD_RESOLVER,
                    f"❌ Failed to resolve any build errors after attempt {attempt}"
                )
            )
            break

        make_issue_comment(
            issue_number,
            format_issue_message(adw_id, AGENT_BUILD_RESOLVER,
                f"✅ Resolved errors in {files_resolved}/{len(errors_by_file)} files, retrying build..."
            )
        )

    # Final check
    steps.record(adw_id, "build", "running", note="Final check", parent="integration")
    final_result = run_build_validation(working_dir, logger)
    if final_result.passed:
        make_issue_comment(
            issue_number,
            format_issue_message(adw_id, AGENT_BUILD_RESOLVER,
                "✅ Build validation passed after resolution"
            )
        )
        return True, "Build validation passed after resolution"

    make_issue_comment(
        issue_number,
        format_issue_message(adw_id, AGENT_BUILD_RESOLVER,
            f"❌ Build validation still failing after {max_attempts} attempts\n"
            f"Remaining errors: {len(final_result.errors)}"
        )
    )
    return False, f"Build validation failed after {max_attempts} attempts with {len(final_result.errors)} errors"


def _tail(output: str) -> str:
    """The last non-empty line of a command's output, for a step note."""
    lines = [ln.strip() for ln in (output or "").splitlines() if ln.strip()]
    return lines[-1][:200] if lines else ""


def _record_pr(adw_id: str, branch_name: str, ok: bool, error: str) -> None:
    """Step "pr": its URL when finalize_git_operations made or found one, else why not."""
    if not ok:
        steps.record(adw_id, "pr", "failed", label="Pull request", note=error or "")
        return
    try:
        url, _ = check_pr_exists_with_error(branch_name) if branch_name else (None, None)
    except Exception:  # noqa: BLE001 - reporting only
        url = None
    steps.record(adw_id, "pr", "done", label="Pull request",
                 note=f"PR #{url.rstrip('/').rsplit('/', 1)[-1]}: {url}" if url else "")


def main():
    """Main entry point."""
    load_dotenv()

    # Check for flags
    resume_mode = "--resume" in sys.argv
    skip_smoke = "--skip-smoke" in sys.argv

    # Remove flags from argv
    if resume_mode:
        sys.argv.remove("--resume")
    if skip_smoke:
        sys.argv.remove("--skip-smoke")

    if len(sys.argv) < 2:
        print("Usage: uv run adw_multi_phase_sdlc_iso.py <issue-number> [adw-id] [--resume] [--skip-smoke]")
        print("\nThis workflow handles large features requiring multiple implementation phases.")
        print("\nWorkflow:")
        print("  1. Multi-Phase Planning (Opus)")
        print("  2. Phase Execution Loop (build -> test -> review -> commit)")
        print("  3. Integration Validation")
        print("  4. Documentation")
        print("\nFlags:")
        print("  --resume      Resume from last incomplete phase")
        print("  --skip-smoke  Skip smoke tests in integration validation")
        sys.exit(1)

    issue_number = sys.argv[1]
    adw_id = sys.argv[2] if len(sys.argv) > 2 else None

    # Ensure ADW ID exists with initialized state
    adw_id = ensure_adw_id(issue_number, adw_id)
    print(f"Using ADW ID: {adw_id}")

    # Set up logger
    logger = setup_logger(adw_id, "adw_multi_phase_sdlc_iso")
    logger.info(f"Starting Multi-Phase SDLC - Issue: {issue_number}, ADW ID: {adw_id}")

    # Validate environment
    check_env_vars(logger)

    # Load or create base state
    state = ADWState.load(adw_id, logger)
    if not state:
        state = ADWState(adw_id)

    # Always update issue_number from args (may differ on retry with new issue)
    state.update(adw_id=adw_id, issue_number=issue_number)

    # Track this workflow
    state.append_adw_id("adw_multi_phase_sdlc_iso")

    # Load or create multi-phase state
    mp_state = MultiPhaseState.load(adw_id, logger)

    # Get repo information
    try:
        github_repo_url = get_repo_url()
        repo_path = extract_repo_path(github_repo_url)
    except ValueError as e:
        logger.error(f"Error getting repository URL: {e}")
        sys.exit(1)

    # Fetch issue data
    logger.info("Fetching issue data")
    issue = fetch_issue(issue_number, repo_path)
    issue_json = issue.model_dump_json(by_alias=True, include={"number", "title", "body"})

    # Check if we're resuming or starting fresh
    if resume_mode and mp_state and mp_state.multi_phase_plan:
        logger.info("Resuming from previous state")
        make_issue_comment(
            issue_number,
            format_issue_message(adw_id, AGENT_ORCHESTRATOR,
                f"🔄 Resuming multi-phase SDLC\n"
                f"Phases completed: {mp_state.phases_completed}/{mp_state.phases_total}"
            )
        )
        plan_file = mp_state.multi_phase_plan
        worktree_path = state.get("worktree_path")

        if not worktree_path:
            logger.error("No worktree path in state - cannot resume")
            steps.record(adw_id, "setup", "failed", label="Setup", note="No worktree path in state - cannot resume")
            sys.exit(1)
        steps.record(adw_id, "setup", "done", label="Setup", note="Resumed")

        # Ensure app is running when resuming
        logger.info("Preparing application for resumed workflow")
        prepare_request = AgentTemplateRequest(
            agent_name="ops",
            slash_command="/prepare_app",
            args=[],
            adw_id=adw_id,
            working_dir=worktree_path,
        )
        prepare_response = execute_template(prepare_request)
        if not prepare_response.success:
            logger.warning(f"prepare_app failed on resume: {prepare_response.output}")

        # Regenerate frontend types on resume (api-generated.ts is gitignored)
        logger.info("Generating frontend types from backend OpenAPI schema")
        generate_types_result = subprocess.run(
            ["npm", "run", "generate:types"],
            cwd=os.path.join(worktree_path, "app", "frontend"),
            capture_output=True,
            text=True,
            timeout=60,
        )
        if generate_types_result.returncode == 0:
            logger.info("Frontend types generated successfully")
        else:
            logger.warning(
                f"Frontend type generation failed (non-fatal): {generate_types_result.stderr[:300]}"
            )
    else:
        # === SETUP: Create worktree and branch ===
        make_issue_comment(
            issue_number,
            format_issue_message(adw_id, AGENT_ORCHESTRATOR,
                "🚀 Starting Multi-Phase SDLC workflow\n"
                "This workflow handles large features by breaking them into phases."
            )
        )

        steps.record(adw_id, "setup", "running", label="Setup")

        # Classify issue first (needed for branch name)
        logger.info("Classifying issue")
        issue_class, error = classify_issue(issue, adw_id, logger)
        if error:
            logger.error(f"Failed to classify issue: {error}")
            issue_class = "/feature"  # Default to feature for large tasks

        state.update(issue_class=issue_class)

        # Generate branch name before worktree creation
        logger.info("Generating branch name")
        branch_name, error = generate_branch_name(issue, issue_class, adw_id, logger)
        if error:
            logger.error(f"Failed to generate branch name: {error}")
            branch_name = f"multi-phase-issue-{issue_number}-adw-{adw_id}"

        state.update(branch_name=branch_name)

        # Allocate ports for this ADW
        backend_port, frontend_port = get_ports_for_adw(adw_id)
        if not is_port_available(backend_port) or not is_port_available(frontend_port):
            logger.warning(f"Preferred ports {backend_port}/{frontend_port} not available, finding alternatives")
            backend_port, frontend_port = find_next_available_ports(adw_id)
        logger.info(f"Allocated ports - Backend: {backend_port}, Frontend: {frontend_port}")

        # Create isolated worktree with branch
        logger.info("Creating isolated worktree")
        worktree_path, actual_branch, error = create_worktree(adw_id, branch_name, logger)

        if error:
            logger.error(f"Failed to create worktree: {error}")
            steps.record(adw_id, "setup", "failed", label="Setup", note=f"Failed to create worktree: {error}")
            make_issue_comment(
                issue_number,
                format_issue_message(adw_id, AGENT_ORCHESTRATOR, f"❌ Failed to create isolated worktree: {error}")
            )
            sys.exit(1)

        # Reconcile branch name with what the worktree actually has
        if actual_branch and actual_branch != branch_name:
            logger.warning(f"Worktree branch mismatch: state={branch_name}, actual={actual_branch}. Using actual.")
            branch_name = actual_branch
            state.update(branch_name=branch_name)

        # Update state with worktree info
        state.update(
            worktree_path=worktree_path,
            backend_port=backend_port,
            frontend_port=frontend_port,
        )

        # Setup worktree environment (ports, database, playwright dirs)
        db_name, backend_port, frontend_port, db_error = setup_worktree_environment(
            worktree_path, backend_port, frontend_port, adw_id, logger
        )
        # Update state with actual ports (may differ if originals were unavailable)
        state.update(backend_port=backend_port, frontend_port=frontend_port)
        if db_error:
            logger.error(f"Failed to setup worktree environment: {db_error}")
            steps.record(adw_id, "setup", "failed", label="Setup", note=f"Failed to create database: {db_error}")
            make_issue_comment(
                issue_number,
                format_issue_message(
                    adw_id,
                    AGENT_ORCHESTRATOR,
                    f"❌ Failed to create isolated database: {db_error}",
                ),
            )
            sys.exit(1)

        # Store database name in state
        state.update(database_name=db_name)

        # Run install_worktree command to set up the isolated environment
        logger.info("Setting up isolated environment with custom ports")
        install_request = AgentTemplateRequest(
            agent_name="ops",
            slash_command="/install_worktree",
            args=[worktree_path, str(backend_port), str(frontend_port), db_name],
            adw_id=adw_id,
            working_dir=worktree_path,
        )

        install_response = execute_template(install_request)
        if not install_response.success:
            logger.error(f"Error setting up worktree: {install_response.output}")
            steps.record(adw_id, "setup", "failed", label="Setup",
                         note=f"Error setting up worktree: {install_response.output[:200]}")
            make_issue_comment(
                issue_number,
                format_issue_message(adw_id, AGENT_ORCHESTRATOR, f"❌ Error setting up worktree: {install_response.output}"),
            )
            sys.exit(1)

        logger.info("Worktree environment setup complete")

        # Start app for integration/e2e tests (auto-reload enabled via DEBUG=true)
        logger.info("Preparing application for tests")
        prepare_request = AgentTemplateRequest(
            agent_name="ops",
            slash_command="/prepare_app",
            args=[],
            adw_id=adw_id,
            working_dir=worktree_path,
        )
        prepare_response = execute_template(prepare_request)
        if not prepare_response.success:
            logger.warning(f"prepare_app failed: {prepare_response.output}")
            # Continue anyway - some tests may not need the app running
        else:
            logger.info("Application prepared and ready")

        # Generate frontend TypeScript types from running backend's OpenAPI schema.
        # api-generated.ts is gitignored, so every new worktree needs to regenerate it.
        logger.info("Generating frontend types from backend OpenAPI schema")
        generate_types_result = subprocess.run(
            ["npm", "run", "generate:types"],
            cwd=os.path.join(worktree_path, "app", "frontend"),
            capture_output=True,
            text=True,
            timeout=60,
        )
        if generate_types_result.returncode == 0:
            logger.info("Frontend types generated successfully")
        else:
            logger.warning(
                f"Frontend type generation failed (non-fatal): {generate_types_result.stderr[:300]}"
            )

        state.save("adw_multi_phase_sdlc_iso")

        steps.record(adw_id, "setup", "done", label="Setup", note=f"Worktree {os.path.basename(worktree_path)}")

        # === PHASE 1: MULTI-PHASE PLANNING ===
        print("\n=== MULTI-PHASE PLANNING (Opus) ===")
        steps.record(adw_id, "plan", "running", label="Plan")
        make_issue_comment(
            issue_number,
            format_issue_message(adw_id, AGENT_MULTI_PHASE_PLANNER,
                "📋 Creating multi-phase implementation plan with Opus..."
            )
        )

        success, plan_file = run_multi_phase_planning(
            issue_number, adw_id, issue_json, logger, worktree_path
        )

        if not success:
            logger.error("Multi-phase planning failed")
            steps.record(adw_id, "plan", "failed", label="Plan", note="Multi-phase planning failed")
            make_issue_comment(
                issue_number,
                format_issue_message(adw_id, AGENT_MULTI_PHASE_PLANNER,
                    "❌ Multi-phase planning failed"
                )
            )
            sys.exit(1)

        state.update(plan_file=plan_file)
        state.save("adw_multi_phase_sdlc_iso")

        # Initialize multi-phase state
        mp_state = MultiPhaseState(adw_id)
        mp_state.multi_phase_plan = plan_file

    # Get worktree path and resolve absolute plan file path
    worktree_path = state.get("worktree_path")

    # BUG-008 fix: Validate path is within worktree (prevent path traversal)
    abs_worktree = os.path.abspath(worktree_path)
    abs_plan_path = os.path.abspath(os.path.join(worktree_path, plan_file))
    if not abs_plan_path.startswith(abs_worktree):
        error = f"Plan file path escapes worktree (potential path traversal): {plan_file}"
        logger.error(error)
        make_issue_comment(
            issue_number,
            format_issue_message(adw_id, AGENT_ORCHESTRATOR, f"❌ {error}")
        )
        sys.exit(1)

    worktree_plan_path = abs_plan_path

    # Validate plan file exists in worktree
    if not os.path.exists(worktree_plan_path):
        error = f"Plan file does not exist in worktree: {plan_file}"
        logger.error(error)
        make_issue_comment(
            issue_number,
            format_issue_message(adw_id, AGENT_ORCHESTRATOR, f"❌ {error}")
        )
        sys.exit(1)

    # Parse the plan using absolute path
    plan = parse_multi_phase_plan(worktree_plan_path, logger)
    if not plan:
        logger.error(f"Failed to parse plan file: {plan_file}")
        steps.record(adw_id, "plan", "failed", label="Plan", note=f"Couldn't parse the plan: {plan_file}")
        make_issue_comment(
            issue_number,
            format_issue_message(adw_id, AGENT_ORCHESTRATOR,
                f"❌ Failed to parse multi-phase plan: {plan_file}"
            )
        )
        sys.exit(1)

    names = {p.id: p.name for p in plan.phases}
    order = list(plan.execution_order) + [p.id for p in plan.phases if p.id not in plan.execution_order]
    steps.plan(adw_id, [(pid, names.get(pid, pid)) for pid in order])
    steps.record(adw_id, "plan", "done", label="Plan",
                 note=f"{len(plan.phases)} phase{'s' if len(plan.phases) != 1 else ''}")

    # Initialize phase tracking if not resuming
    if not resume_mode or not mp_state.phases:
        mp_state.initialize_phases([p.id for p in plan.phases])

    mp_state.save()

    make_issue_comment(
        issue_number,
        format_issue_message(adw_id, AGENT_ORCHESTRATOR,
            f"✅ Multi-phase plan created: `{plan_file}`\n"
            f"📊 Total phases: {len(plan.phases)}\n"
            f"Execution order: {', '.join(plan.execution_order)}"
        )
    )

    # === PHASE 2: EXECUTE EACH PHASE ===
    print("\n=== PHASE EXECUTION ===")

    # Baseline build check: record pre-existing errors so we only fail on NEW ones
    logger.info("Running baseline build check (build:only) to detect pre-existing errors")
    baseline_frontend_dir = os.path.join(worktree_path, "app", "frontend")
    baseline_build = subprocess.run(
        ["npm", "run", "build:only"],
        cwd=baseline_frontend_dir,
        capture_output=True,
        text=True,
        timeout=300,
    )
    baseline_build_output = baseline_build.stdout + baseline_build.stderr
    baseline_errors = set()
    if baseline_build.returncode != 0:
        for err in parse_build_errors(baseline_build_output):
            baseline_errors.add((err.file_path, err.line, err.error_code))
        logger.warning(
            f"Baseline build has {len(baseline_errors)} pre-existing error(s) — "
            f"post-commit checks will only fail on NEW errors"
        )
    else:
        logger.info("Baseline build passes cleanly")

    # Check if we're resuming from integration phase (all phases completed)
    skip_phases = False
    if resume_mode and mp_state.integration.status == PhaseStatus.IN_PROGRESS:
        # All phases completed, failed during integration - skip to integration
        logger.info("Resuming from integration phase (all phases completed)")
        make_issue_comment(
            issue_number,
            format_issue_message(adw_id, AGENT_ORCHESTRATOR,
                "⏭️ Skipping phase execution - resuming from integration validation"
            )
        )
        skip_phases = True

    # Find starting point (for resume within phases)
    start_phase_id = None
    if resume_mode and not skip_phases:
        # Reset any phases that show IN_PROGRESS but have completed_at (from previous interrupted resume)
        for pid in plan.execution_order:
            phase_state = mp_state.phases.get(pid)
            if phase_state and phase_state.status == PhaseStatus.IN_PROGRESS and phase_state.completed_at:
                # This phase was completed before but marked in_progress by an interrupted resume
                logger.info(f"Restoring completed status for phase {pid}")
                phase_state.status = PhaseStatus.COMPLETED
                mp_state.save()

        start_phase_id = mp_state.get_first_incomplete_phase(plan.execution_order)
        if start_phase_id:
            logger.info(f"Resuming from phase: {start_phase_id}")

    # Resume-mode short-circuit when all phases are already complete.
    #
    # get_first_incomplete_phase returns None when every phase is COMPLETED.
    # The original phase-loop semantics had a bug here: the line
    #   started = not resume_mode or start_phase_id is None or skip_phases
    # set `started = True` in this case, which the loop interprets as
    # "no skipping, run every phase" rather than "all done, run nothing".
    # The result: every implementor agent was re-invoked on resume
    # (~60-90 min and ~$20-40 wasted per verify-gate-failure retry).
    #
    # Fix: when phases are done, decide based on integration status.
    if resume_mode and start_phase_id is None:
        if mp_state.integration.status == PhaseStatus.COMPLETED:
            # Phases + integration both done. The greenfield orchestrator
            # re-invoked us after pre-merge verify-gate failure; the SDLC has
            # nothing useful to redo. Exit cleanly so the parent re-runs the
            # verifier against the patched branch.
            logger.info(
                "Resume detected fully-complete state: all phases and "
                "integration already completed. Exiting cleanly; parent "
                "orchestrator will proceed to pre-merge verify."
            )
            try:
                make_issue_comment(
                    issue_number,
                    format_issue_message(adw_id, AGENT_ORCHESTRATOR,
                        "🔄 Resuming — all phases and integration already "
                        "completed on prior run. Exiting cleanly so the "
                        "parent workflow can re-run pre-merge verification."
                    )
                )
            except Exception as e:
                logger.warning(f"Failed to post fully-complete resume comment: {e}")
            state.save("adw_multi_phase_sdlc_iso")
            mp_state.save()
            return
        # Phases done but integration not yet complete (NOT_STARTED, IN_PROGRESS,
        # or FAILED). Skip the phase loop; integration validation below will run.
        # This also handles the originally-broken case where the existing
        # IN_PROGRESS-only check at line ~1238 didn't fire because integration
        # was NOT_STARTED.
        logger.info(
            "Resume detected all phases complete; integration not finished. "
            "Skipping phase loop; running integration validation only."
        )
        skip_phases = True

    started = not resume_mode or start_phase_id is None or skip_phases

    for phase_id in plan.execution_order:
        # Skip all phases if resuming from integration
        if skip_phases:
            continue
        # Skip completed phases when resuming
        if not started:
            if phase_id == start_phase_id:
                started = True
            else:
                continue

        phase = get_phase_by_id(plan, phase_id)
        if not phase:
            logger.error(f"Phase not found in plan: {phase_id}")
            continue

        print(f"\n--- Phase: {phase_id} ---")
        steps.record(adw_id, phase_id, "running", label=phase.name, parent="phases")

        # Check dependencies
        if not mp_state.dependencies_met(phase):
            logger.error(f"Dependencies not met for phase: {phase_id}")
            steps.record(adw_id, phase_id, "failed", label=phase.name, parent="phases",
                         note=f"Blocked: needs {', '.join(phase.dependencies)}")
            make_issue_comment(
                issue_number,
                format_issue_message(adw_id, AGENT_ORCHESTRATOR,
                    f"❌ Phase `{phase_id}` blocked: dependencies not met\n"
                    f"Required: {', '.join(phase.dependencies)}"
                )
            )
            sys.exit(1)

        # Mark phase started
        mp_state.mark_phase_started(phase_id)
        mp_state.save()

        make_issue_comment(
            issue_number,
            format_issue_message(adw_id, AGENT_ORCHESTRATOR,
                f"🔨 Starting phase: `{phase_id}`\n"
                f"Description: {phase.description}\n"
                f"Files: {len(phase.scope)}"
            )
        )

        # === BUILD: Implement phase ===
        logger.info(f"BUILD: Implementing phase {phase_id}")
        steps.record(adw_id, "build", "running", parent=phase_id)
        impl_success, impl_output = implement_phase(
            phase_id, plan_file, adw_id, logger, worktree_path
        )

        if not impl_success:
            mp_state.mark_phase_failed(phase_id, "build", impl_output[:500])
            steps.record(adw_id, "build", "failed", parent=phase_id, note=impl_output[:200])
            mp_state.save()
            make_issue_comment(
                issue_number,
                format_issue_message(adw_id, AGENT_ORCHESTRATOR,
                    f"❌ Phase `{phase_id}` failed at BUILD stage\n"
                    f"Error: {impl_output[:300]}\n\n"
                    f"Use `--resume` to retry from this phase."
                )
            )
            sys.exit(1)

        steps.record(adw_id, "build", "done", parent=phase_id)

        # === TEST: Run scoped tests ===
        if phase.test_scope:
            logger.info(f"TEST: Running scoped tests for {phase_id}")
            steps.record(adw_id, "test", "running", parent=phase_id)
            test_success, test_output = run_scoped_tests(
                phase.test_scope, worktree_path, logger
            )

            if not test_success:
                steps.record(adw_id, "test", "failed", parent=phase_id, note=_tail(test_output))
                # Try to resolve test failures
                retry_count = 0
                while not test_success and retry_count < MAX_TEST_RETRIES:
                    retry_count += 1
                    logger.warning(f"Test retry {retry_count}/{MAX_TEST_RETRIES}")
                    steps.record(adw_id, "test", "running", parent=phase_id, note=f"Retry {retry_count}")

                    # TODO: Could call /resolve_failed_test here
                    test_success, test_output = run_scoped_tests(
                        phase.test_scope, worktree_path, logger
                    )
                    if not test_success:
                        steps.record(adw_id, "test", "failed", parent=phase_id, note=_tail(test_output))

                if not test_success:
                    mp_state.mark_phase_failed(phase_id, "test", test_output[:500])
                    mp_state.save()
                    make_issue_comment(
                        issue_number,
                        format_issue_message(adw_id, AGENT_ORCHESTRATOR,
                            f"❌ Phase `{phase_id}` failed at TEST stage\n"
                            f"Use `--resume` to retry from this phase."
                        )
                    )
                    sys.exit(1)

            mp_state.update_phase(phase_id, test_passed=True)
            steps.record(adw_id, "test", "done", parent=phase_id)
        else:
            steps.record(adw_id, "test", "skipped", parent=phase_id, note="No test scope in the plan")

        # === REVIEW: Validate against criteria (with retry and resolution) ===
        review_attempt = 0
        review_passed = False
        infrastructure_backfills = []  # Track backfills for reporting

        while review_attempt < MAX_REVIEW_RETRIES:
            review_attempt += 1
            logger.info(f"REVIEW: Reviewing phase {phase_id} (attempt {review_attempt}/{MAX_REVIEW_RETRIES})")
            steps.record(adw_id, "review", "running", parent=phase_id,
                         note=f"Attempt {review_attempt}" if review_attempt > 1 else "")

            review_success, review_result = review_phase(
                phase_id, plan_file, adw_id, logger, worktree_path
            )

            if review_success:
                review_passed = True
                steps.record(adw_id, "review", "done", parent=phase_id)
                # Check for infrastructure backfills and log them
                scope_compliance = review_result.get("scope_compliance", {})
                infrastructure_backfills = scope_compliance.get("infrastructure_backfills", [])
                if infrastructure_backfills:
                    logger.info(f"Phase {phase_id} passed with {len(infrastructure_backfills)} infrastructure backfill(s)")
                    for backfill in infrastructure_backfills:
                        logger.info(f"  Backfill: {backfill}")
                break

            # Check for blockers
            issues = review_result.get("issues", [])
            blockers = [i for i in issues if i.get("severity") == "blocker"]

            if not blockers:
                # No blockers, just warnings - consider it passed
                logger.info(f"Phase {phase_id} review has warnings but no blockers, continuing")
                review_passed = True
                steps.record(adw_id, "review", "done", parent=phase_id, note=f"{len(issues)} warning(s), no blockers")
                break

            # We have blockers - try to resolve them
            logger.warning(f"Phase {phase_id} has {len(blockers)} blocker(s), attempting resolution")
            steps.record(adw_id, "review", "failed", parent=phase_id,
                         note=f"{len(blockers)} blocker(s): {str(blockers[0].get('description') or blockers[0].get('issue') or '')[:120]}")

            # Don't try to resolve on the last attempt - just fail
            if review_attempt >= MAX_REVIEW_RETRIES:
                break

            # Attempt to resolve blockers (pass phase scope to constrain patches)
            resolved = resolve_phase_blockers(
                phase_id, blockers, issue_number, adw_id, logger, worktree_path,
                phase_scope=phase.scope,
            )

            if not resolved:
                logger.error(f"Failed to resolve any blockers for phase {phase_id}")
                break

            # Retry review after resolution
            logger.info(f"Retrying review after resolving blockers for phase {phase_id}")
            make_issue_comment(
                issue_number,
                format_issue_message(adw_id, AGENT_ORCHESTRATOR,
                    f"🔄 Retrying review for phase `{phase_id}` after resolution..."
                )
            )

        if not review_passed:
            # Final failure after all retries
            issues = review_result.get("issues", [])
            blockers = [i for i in issues if i.get("severity") == "blocker"]
            mp_state.mark_phase_failed(phase_id, "review", json.dumps(blockers)[:500])
            steps.record(adw_id, "review", "failed", parent=phase_id,
                         note=f"{len(blockers)} blocker(s) remaining after {review_attempt} attempt(s)")
            mp_state.save()
            make_issue_comment(
                issue_number,
                format_issue_message(adw_id, AGENT_ORCHESTRATOR,
                    f"❌ Phase `{phase_id}` failed at REVIEW stage after {review_attempt} attempt(s)\n"
                    f"Blockers remaining: {len(blockers)}\n"
                    f"Use `--resume` to retry from this phase."
                )
            )
            sys.exit(1)

        mp_state.update_phase(phase_id, review_passed=True)

        # === COMMIT: Atomic commit for phase ===
        logger.info(f"COMMIT: Committing phase {phase_id}")
        steps.record(adw_id, "commit", "running", parent=phase_id)
        commit_success, commit_sha = commit_phase_changes(
            phase_id, issue_number, adw_id, logger, worktree_path
        )

        if not commit_success:
            mp_state.mark_phase_failed(phase_id, "commit", "Failed to commit")
            steps.record(adw_id, "commit", "failed", parent=phase_id, note="Failed to commit")
            mp_state.save()
            make_issue_comment(
                issue_number,
                format_issue_message(adw_id, AGENT_ORCHESTRATOR,
                    f"❌ Phase `{phase_id}` failed at COMMIT stage"
                )
            )
            sys.exit(1)

        # === POST-COMMIT BUILD CHECK: Catch forward references early ===
        # Only run frontend build validation if this phase touches frontend files
        phase_touches_frontend = any(
            "app/frontend" in s for s in (phase.scope or [])
        )
        if not phase_touches_frontend:
            logger.info(f"POST-COMMIT BUILD CHECK: Skipping for backend-only phase {phase_id}")

        if phase_touches_frontend:
            logger.info(f"POST-COMMIT BUILD CHECK: Validating build after phase {phase_id}")

        post_commit_build_failed = False
        if phase_touches_frontend:
            # Use build:only (tsc + vite) instead of build (which re-runs generate:types
            # and fails if the backend isn't responding to health checks)
            frontend_dir = os.path.join(worktree_path, "app", "frontend")
            build_only_result = subprocess.run(
                ["npm", "run", "build:only"],
                cwd=frontend_dir,
                capture_output=True,
                text=True,
                timeout=300,
            )
            if build_only_result.returncode != 0:
                # Filter out pre-existing baseline errors
                build_output = build_only_result.stdout + build_only_result.stderr
                all_errors = parse_build_errors(build_output)
                new_errors = [
                    e for e in all_errors
                    if (e.file_path, e.line, e.error_code) not in baseline_errors
                ]
                if new_errors:
                    post_commit_build_failed = True
                    post_commit_build = BuildValidationResult(
                        passed=False, errors=new_errors, raw_output=build_output
                    )
                else:
                    logger.info(
                        f"Build has {len(all_errors)} error(s) but all are pre-existing — phase OK"
                    )

        if post_commit_build_failed:
            new_error_count = len(post_commit_build.errors)
            logger.warning(
                f"Build broken after phase {phase_id} commit with {new_error_count} new error(s). "
                f"Attempting resolution..."
            )

            # Try to resolve the new errors using /resolve_build_error agent
            errors_by_file: dict[str, list] = {}
            for error in post_commit_build.errors:
                if error.file_path not in errors_by_file:
                    errors_by_file[error.file_path] = []
                errors_by_file[error.file_path].append(error)

            for file_path, file_errors in errors_by_file.items():
                logger.info(f"Resolving {len(file_errors)} error(s) in {file_path}")
                error_payloads = "\n\n---\n\n".join([
                    e.to_resolution_payload() for e in file_errors
                ])
                resolve_request = AgentTemplateRequest(
                    agent_name=f"post_commit_resolver_{phase_id}_{file_path.replace('/', '_')[:30]}",
                    slash_command="/resolve_build_error",
                    args=[error_payloads],
                    adw_id=adw_id,
                    working_dir=worktree_path,
                )
                resolve_response = execute_template(resolve_request)
                if resolve_response.success:
                    logger.info(f"Resolved errors in {file_path}")
                else:
                    logger.warning(f"Failed to resolve errors in {file_path}")

            # Re-check build with build:only
            recheck = subprocess.run(
                ["npm", "run", "build:only"],
                cwd=os.path.join(worktree_path, "app", "frontend"),
                capture_output=True,
                text=True,
                timeout=300,
            )
            recheck_output = recheck.stdout + recheck.stderr
            recheck_errors = parse_build_errors(recheck_output)
            still_new = [
                e for e in recheck_errors
                if (e.file_path, e.line, e.error_code) not in baseline_errors
            ]

            if not still_new:
                # Resolution worked — amend the commit with the fix
                logger.info(f"Build fixed after resolution for phase {phase_id}")
                subprocess.run(
                    ["git", "add", "-A"],
                    cwd=worktree_path, capture_output=True, text=True,
                )
                amend_result = subprocess.run(
                    ["git", "commit", "--amend", "--no-edit"],
                    cwd=worktree_path, capture_output=True, text=True,
                )
                if amend_result.returncode == 0:
                    sha_result = subprocess.run(
                        ["git", "rev-parse", "HEAD"],
                        cwd=worktree_path, capture_output=True, text=True,
                    )
                    commit_sha = sha_result.stdout.strip()[:12]
                    logger.info(f"Amended commit with build fix: {commit_sha}")
            else:
                # Resolution failed
                error_preview = recheck_output[-500:]
                mp_state.mark_phase_failed(phase_id, "post_commit_build", error_preview[:500])
                steps.record(adw_id, "commit", "failed", parent=phase_id,
                             note=f"The commit broke the build: {len(still_new)} new error(s)")
                mp_state.save()
                make_issue_comment(
                    issue_number,
                    format_issue_message(adw_id, AGENT_ORCHESTRATOR,
                        f"❌ Phase `{phase_id}` broke the build after commit\n"
                        f"New errors: {len(still_new)} (after resolution attempt)\n"
                        f"```\n{error_preview[:400]}\n```\n\n"
                        f"Use `--resume` to retry from this phase."
                    )
                )
                sys.exit(1)

        # Mark phase completed
        mp_state.mark_phase_completed(phase_id, commit_sha)
        steps.record(adw_id, "commit", "done", parent=phase_id, note=str(commit_sha or ""))
        steps.record(adw_id, phase_id, "done", label=phase.name, parent="phases")
        mp_state.save()

        # Build completion message
        completion_msg = (
            f"✅ Phase `{phase_id}` completed\n"
            f"Commit: `{commit_sha}`\n"
            f"Progress: {mp_state.phases_completed}/{mp_state.phases_total}"
        )
        if infrastructure_backfills:
            backfill_list = "\n".join(f"  - {b}" for b in infrastructure_backfills[:5])  # Limit to 5
            completion_msg += f"\n\n📦 Infrastructure backfills applied:\n{backfill_list}"
            if len(infrastructure_backfills) > 5:
                completion_msg += f"\n  ... and {len(infrastructure_backfills) - 5} more"

        make_issue_comment(
            issue_number,
            format_issue_message(adw_id, AGENT_ORCHESTRATOR, completion_msg)
        )

        # Push after each phase
        branch_name = state.get("branch_name")
        push_changes(branch_name, worktree_path, logger)

    # === PHASE 3: INTEGRATION VALIDATION ===
    print("\n=== INTEGRATION VALIDATION ===")
    mp_state.integration.status = PhaseStatus.IN_PROGRESS
    mp_state.save()
    steps.record(adw_id, "integration", "running", label="Integration")
    integration_problems = []

    make_issue_comment(
        issue_number,
        format_issue_message(adw_id, AGENT_ORCHESTRATOR,
            "🔍 Starting integration validation..."
        )
    )

    # Build validation with automatic resolution
    logger.info("Running build validation with resolution")
    steps.record(adw_id, "build", "running", parent="integration")
    build_success, build_summary = run_build_with_resolution(
        issue_number, adw_id, worktree_path, logger
    )
    steps.record(adw_id, "build", "done" if build_success else "failed", parent="integration",
                 note="" if build_success else build_summary)
    if not build_success:
        integration_problems.append("build")

    if not build_success:
        logger.error(f"Build validation failed: {build_summary}")
        # Continue to tests anyway - they will likely fail but provide more context

    # Full test suite with automatic resolution
    logger.info("Running full test suite")
    steps.record(adw_id, "tests", "running", parent="integration")
    test_success, test_output = run_full_test_suite_with_resolution(
        issue_number, adw_id, worktree_path, logger, step=("tests", "integration")
    )
    steps.record(adw_id, "tests", "done" if test_success else "failed", parent="integration")
    if not test_success:
        integration_problems.append("tests")
    mp_state.integration.full_test_passed = test_success

    if not test_success:
        logger.error("Full test suite failed after resolution attempts")
        make_issue_comment(
            issue_number,
            format_issue_message(adw_id, AGENT_ORCHESTRATOR,
                f"⚠️ Integration tests failed after resolution attempts\n```\n{test_output}\n```"
            )
        )
        # Continue to gather more diagnostic info

    # Smoke tests
    if not skip_smoke:
        logger.info("Running smoke tests")
        steps.record(adw_id, "smoke", "running", parent="integration")
        smoke_success = run_smoke_tests(issue_number, adw_id, worktree_path, logger)
        steps.record(adw_id, "smoke", "done" if smoke_success else "failed", parent="integration",
                     note="" if smoke_success else "Smoke tests failed; continuing")
        if not smoke_success:
            integration_problems.append("smoke")
        mp_state.integration.smoke_passed = smoke_success

        if not smoke_success:
            logger.error("Smoke tests failed")
            make_issue_comment(
                issue_number,
                format_issue_message(adw_id, AGENT_ORCHESTRATOR,
                    "⚠️ Smoke tests failed - see smoke test output for details"
                )
            )
    else:
        logger.info("Skipping smoke tests")
        steps.record(adw_id, "smoke", "skipped", parent="integration", note="--skip-smoke")
        mp_state.integration.smoke_passed = True

    # Final review
    logger.info("Running final review")
    steps.record(adw_id, "review", "running", parent="integration")
    review_success = run_final_review(issue_number, adw_id, worktree_path, logger)
    steps.record(adw_id, "review", "done" if review_success else "failed", parent="integration",
                 note="" if review_success else "Needs attention; continuing")
    if not review_success:
        integration_problems.append("review")
    mp_state.integration.final_review_passed = review_success

    if not review_success:
        logger.warning("Final review did not pass completely")

    mp_state.integration.status = PhaseStatus.COMPLETED
    mp_state.save()

    # Documentation
    logger.info("Generating documentation")
    steps.record(adw_id, "docs", "running", parent="integration")
    doc_success = run_documentation(issue_number, adw_id, worktree_path, logger)
    steps.record(adw_id, "docs", "done" if doc_success else "failed", parent="integration",
                 note="" if doc_success else "Documentation had issues; continuing")
    if not doc_success:
        integration_problems.append("docs")
    steps.record(adw_id, "integration", "done", label="Integration",
                 note=f"Needs attention: {', '.join(integration_problems)}" if integration_problems else "")

    if not doc_success:
        logger.warning("Documentation generation had issues")

    # Final push
    branch_name = state.get("branch_name")
    push_changes(branch_name, worktree_path, logger)

    # Finalize git operations (create/update PR)
    steps.record(adw_id, "pr", "running", label="Pull request")
    git_success, git_error = finalize_git_operations(state, logger, cwd=worktree_path)
    _record_pr(adw_id, state.get("branch_name"), git_success, git_error)
    if not git_success:
        logger.error(f"Git finalization failed: {git_error}")
        # Continue with completion - PR creation failure shouldn't block the workflow

    # Save final state
    state.save("adw_multi_phase_sdlc_iso")
    mp_state.save()

    # Summary
    print("\n=== MULTI-PHASE SDLC COMPLETED ===")
    print(f"ADW ID: {adw_id}")
    print(f"Phases completed: {mp_state.phases_completed}/{mp_state.phases_total}")
    print(f"Integration tests: {'PASS' if mp_state.integration.full_test_passed else 'FAIL'}")
    print(f"Smoke tests: {'PASS' if mp_state.integration.smoke_passed else 'FAIL/SKIPPED'}")
    print(f"Final review: {'PASS' if mp_state.integration.final_review_passed else 'NEEDS ATTENTION'}")
    print(f"\nWorktree location: {worktree_path}")
    print(f"To clean up: ./scripts/purge_tree.sh {adw_id}")

    make_issue_comment(
        issue_number,
        format_issue_message(adw_id, AGENT_ORCHESTRATOR,
            f"🎉 Multi-Phase SDLC completed!\n\n"
            f"**Summary:**\n"
            f"- Phases: {mp_state.phases_completed}/{mp_state.phases_total} completed\n"
            f"- Integration tests: {'✅' if mp_state.integration.full_test_passed else '❌'}\n"
            f"- Smoke tests: {'✅' if mp_state.integration.smoke_passed else '⚠️'}\n"
            f"- Final review: {'✅' if mp_state.integration.final_review_passed else '⚠️'}\n\n"
            f"PR is ready for human review."
        )
    )


if __name__ == "__main__":
    steps.run_main(main)
