#!/usr/bin/env -S uv run
# /// script
# dependencies = ["python-dotenv", "pydantic", "redis"]
# ///

"""
ADW SDLC Router - Intelligent SDLC workflow router

Usage: uv run adw_sdlc_router_iso.py <issue-number> [adw-id] [--skip-e2e] [--skip-resolution] [--skip-smoke]

This workflow acts as a unified entry point for SDLC workflows:
1. Fetches the GitHub issue
2. Classifies issue type (/feature, /bug, /chore)
3. For features: analyzes complexity to determine single-phase vs multi-phase
4. Routes to the appropriate SDLC workflow

Routing logic:
- By default every issue goes to adw_orchestrated_sdlc_iso.py (Orchestrated SDLC).
- ADW_ORCHESTRATED=0 brings back the classic routing:
- /bug and /chore: Always use adw_sdlc_iso.py (single-phase)
- /feature with low complexity: Use adw_sdlc_iso.py (single-phase)
- /feature with high complexity: Use adw_multi_phase_sdlc_iso.py (multi-phase)

All command-line flags are forwarded to the target workflow.
"""

import subprocess
import sys
import os

# Add the parent directory to Python path to import modules
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from adw_modules.workflow_ops import (
    ensure_adw_id,
    format_issue_message,
    classify_issue,
    classify_sdlc_complexity,
)
from adw_modules.state import ADWState
from adw_modules import steps
from adw_modules.github import make_issue_comment, fetch_issue, get_repo_url, extract_repo_path
from adw_modules.utils import setup_logger


def orchestrated_enabled() -> bool:
    """Orchestrated SDLC for every issue, unless ADW_ORCHESTRATED is 0 / false / no / off."""
    return os.getenv("ADW_ORCHESTRATED", "").strip().lower() not in ("0", "false", "no", "off")


def main():
    """Main entry point."""
    # Collect flags to forward to target workflow
    flags = [arg for arg in sys.argv[1:] if arg.startswith("--")]

    # Remove flags from argv for parsing
    args = [arg for arg in sys.argv[1:] if not arg.startswith("--")]

    if len(args) < 1:
        print("Usage: uv run adw_sdlc_router_iso.py <issue-number> [adw-id] [--skip-e2e] [--skip-resolution] [--skip-smoke]")
        print("\nThis is the intelligent SDLC router that automatically selects:")
        print("  - Single-phase SDLC for bugs, chores, and simple features")
        print("  - Multi-phase SDLC for complex features")
        sys.exit(1)

    issue_number = args[0]

    # BUG-018 fix: Validate issue number format
    if not issue_number.isdigit():
        print(f"Error: Issue number must be numeric, got: {issue_number}")
        sys.exit(1)

    adw_id = args[1] if len(args) > 1 else None

    # Ensure ADW ID exists with initialized state
    adw_id = ensure_adw_id(issue_number, adw_id)
    print(f"Using ADW ID: {adw_id}")

    # Set up logger
    logger = setup_logger(adw_id, "adw_sdlc_router_iso")
    logger.info(f"SDLC Router starting - Issue: {issue_number}, ADW ID: {adw_id}")

    # Load or create state
    state = ADWState.load(adw_id)
    if state:
        state.append_adw_id("adw_sdlc_router_iso")
    else:
        state = ADWState(adw_id)
        state.append_adw_id("adw_sdlc_router_iso")
    # Always update issue_number from args (may differ on retry with new issue)
    state.update(adw_id=adw_id, issue_number=issue_number)
    state.save("router_start")
    steps.record(adw_id, "route", "running", label="Route")

    # Get repo information
    try:
        github_repo_url = get_repo_url()
        repo_path = extract_repo_path(github_repo_url)
    except ValueError as e:
        logger.error(f"Error getting repository URL: {e}")
        sys.exit(1)

    # Fetch issue
    logger.info("Fetching issue data")
    issue = fetch_issue(issue_number, repo_path)

    # Classify issue type
    logger.info("Classifying issue type")
    issue_class, error = classify_issue(issue, adw_id, logger)

    if error:
        logger.error(f"Error classifying issue: {error}")
        steps.record(adw_id, "route", "failed", label="Route", note=f"Couldn't classify the issue: {error}")
        make_issue_comment(
            issue_number,
            format_issue_message(adw_id, "router", f"❌ Failed to classify issue: {error}")
        )
        sys.exit(1)

    logger.info(f"Issue classified as: {issue_class}")

    # Determine target workflow based on issue type and complexity
    complexity = "single-phase"  # Default for bugs and chores
    orchestrated = orchestrated_enabled()   # one orchestrator agent decides the workflow (the default)

    if orchestrated:
        complexity = "dynamic"
    elif issue_class == "/feature":
        # Only features get complexity analysis
        logger.info("Analyzing feature complexity")
        complexity, error = classify_sdlc_complexity(issue, adw_id, logger)

        if error:
            logger.warning(f"Complexity classification failed, defaulting to single-phase: {error}")
            complexity = "single-phase"

    # Save routing decision to state
    state.update(
        issue_class=issue_class,
        sdlc_complexity=complexity,
    )
    state.save("router_classified")

    # Post routing decision to issue
    if orchestrated:
        target_workflow = "adw_orchestrated_sdlc_iso.py"
        workflow_desc = "Orchestrated SDLC (an orchestrator agent plans the work; subagents run it in parallel)"
    elif complexity == "multi-phase":
        target_workflow = "adw_multi_phase_sdlc_iso.py"
        workflow_desc = "Multi-Phase SDLC (large feature with multiple phases)"
    else:
        target_workflow = "adw_sdlc_iso.py"
        workflow_desc = "Single-Phase SDLC"

    logger.info(f"Routing to {complexity} workflow: {target_workflow}")
    # The decision, durably (state.update() keeps only its core fields, so sdlc_complexity isn't saved there)
    steps.route(adw_id, issue_class, complexity, "Orchestrated SDLC" if orchestrated else
                "Multi-phase SDLC" if complexity == "multi-phase" else "SDLC")

    try:
        make_issue_comment(
            issue_number,
            format_issue_message(
                adw_id, "router",
                f"🔀 **Routing Decision**\n\n"
                f"- Issue type: `{issue_class}`\n"
                f"- Complexity: `{complexity}`\n"
                f"- Target: **{workflow_desc}**"
            )
        )
    except Exception as e:
        logger.warning(f"Failed to post routing comment: {e}")

    # Get the directory where this script is located
    script_dir = os.path.dirname(os.path.abspath(__file__))

    # Build command for target workflow
    cmd = [
        "uv",
        "run",
        os.path.join(script_dir, target_workflow),
        issue_number,
        adw_id,
    ] + flags

    print(f"\n=== ROUTING TO {complexity.upper()} SDLC ===")
    print(f"Running: {' '.join(cmd)}")

    # Execute target workflow and forward exit code
    result = subprocess.run(cmd)
    sys.exit(result.returncode)


if __name__ == "__main__":
    steps.run_main(main)
