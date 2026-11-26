#!/usr/bin/env -S uv run
# /// script
# dependencies = ["fastapi", "uvicorn", "python-dotenv"]
# ///

"""
GitHub Webhook Trigger - AI Developer Workflow (ADW)

FastAPI webhook endpoint that receives GitHub issue events and triggers ADW workflows.
Responds immediately to meet GitHub's 10-second timeout by launching workflows
in the background. Supports both standard and isolated workflows.

Usage: uv run trigger_webhook.py

Environment Requirements:
- PORT: Server port (default: 8001)
- All workflow requirements (GITHUB_PAT, ANTHROPIC_API_KEY, etc.)
"""

import os
import re
import subprocess
import sys
import logging
from datetime import datetime
from typing import Optional
from fastapi import FastAPI, Request
from dotenv import load_dotenv
import uvicorn


# Custom print function that adds timestamps
_original_print = print
def print(*args, **kwargs):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    _original_print(f"[{timestamp}]", *args, **kwargs)

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from adw_modules.utils import make_adw_id, setup_logger, get_safe_subprocess_env
from adw_modules.github import make_issue_comment, ADW_BOT_IDENTIFIER
from adw_modules.workflow_ops import (
    extract_adw_info,
    AVAILABLE_ADW_WORKFLOWS,
    find_latest_adw_for_issue,
    get_workflow_from_state,
)
from adw_modules.state import ADWState
from adw_modules.workflow_control import stop_workflow

# Load environment variables
load_dotenv()

# Configuration
PORT = int(os.getenv("PORT", "8001"))

# Dependent workflows that require existing worktrees
# These cannot be triggered directly via webhook
DEPENDENT_WORKFLOWS = [
    "adw_build_iso",
    "adw_test_iso",
    "adw_review_iso",
    "adw_document_iso",
    "adw_ship_iso",
]

# Pattern to detect --resume with optional ADW ID
# Matches: "--resume" or "--resume 20260113151700-27f6eca8"
RESUME_PATTERN = re.compile(
    r"^\s*--resume(?:\s+(\d{14}-[a-f0-9]{8}))?\s*$",
    re.IGNORECASE | re.MULTILINE
)

# Pattern to detect --stop with optional ADW ID
# Matches: "--stop" or "--stop 20260113151700-27f6eca8"
STOP_PATTERN = re.compile(
    r"^\s*--stop(?:\s+(\d{14}-[a-f0-9]{8}))?\s*$",
    re.IGNORECASE | re.MULTILINE
)

# stop_workflow is imported from adw_modules.workflow_control


# Create FastAPI app
app = FastAPI(
    title="ADW Webhook Trigger", description="GitHub webhook endpoint for ADW"
)

print(f"Starting ADW Webhook Trigger on port {PORT}")


@app.post("/gh-webhook")
async def github_webhook(request: Request):
    """Handle GitHub webhook events."""
    try:
        # Get event type from header
        event_type = request.headers.get("X-GitHub-Event", "")

        # Parse webhook payload
        payload = await request.json()

        # Extract event details
        action = payload.get("action", "")
        issue = payload.get("issue", {})
        issue_number = issue.get("number")

        print(
            f"Received webhook: event={event_type}, action={action}, issue_number={issue_number}"
        )

        workflow = None
        provided_adw_id = None
        model_set = None
        resume_mode = False
        trigger_reason = ""
        content_to_check = ""

        # Check if this is an issue opened event
        if event_type == "issues" and action == "opened" and issue_number:
            issue_body = issue.get("body", "")
            content_to_check = issue_body

            # Ignore issues from ADW bot to prevent loops
            if ADW_BOT_IDENTIFIER in issue_body:
                print(f"Ignoring ADW bot issue to prevent loop")
                workflow = None
            # Check if body contains "adw_"
            elif "adw_" in issue_body.lower():
                # Use temporary ID for classification
                temp_id = make_adw_id()
                extraction_result = extract_adw_info(issue_body, temp_id)
                if extraction_result.has_workflow:
                    workflow = extraction_result.workflow_command
                    provided_adw_id = extraction_result.adw_id
                    model_set = extraction_result.model_set
                    # Check for --resume flag
                    resume_mode = "--resume" in issue_body.lower()
                    trigger_reason = f"New issue with {workflow} workflow" + (" (resume)" if resume_mode else "")

        # Check if this is an issue comment
        elif event_type == "issue_comment" and action == "created" and issue_number:
            comment = payload.get("comment", {})
            comment_body = comment.get("body", "")
            content_to_check = comment_body

            print(f"Comment body: '{comment_body}'")

            # Ignore comments from ADW bot to prevent loops
            if ADW_BOT_IDENTIFIER in comment_body:
                print(f"Ignoring ADW bot comment to prevent loop")
                workflow = None
            # Check for standalone --stop command (with optional ADW ID)
            elif STOP_PATTERN.search(comment_body):
                stop_match = STOP_PATTERN.search(comment_body)
                explicit_adw_id = stop_match.group(1) if stop_match else None

                if explicit_adw_id:
                    # Use the explicitly provided ADW ID
                    print(f"Stop with explicit ADW ID: {explicit_adw_id}")
                    target_adw_id = explicit_adw_id
                else:
                    # Find most recent ADW for this issue
                    print(f"Stop without ADW ID - finding latest for issue #{issue_number}")
                    target_adw_id, _ = find_latest_adw_for_issue(str(issue_number))

                if target_adw_id:
                    success, message = stop_workflow(target_adw_id)
                    status_icon = "✅" if success else "❌"
                    try:
                        make_issue_comment(
                            str(issue_number),
                            f"{status_icon} **Workflow Stop Request**\n\n"
                            f"ADW ID: `{target_adw_id}`\n"
                            f"Result: {message}",
                        )
                    except Exception as e:
                        print(f"Failed to post stop comment: {e}")

                    return {
                        "status": "stopped" if success else "stop_failed",
                        "adw_id": target_adw_id,
                        "message": message,
                    }
                else:
                    print(f"No ADW found for issue #{issue_number} to stop")
                    try:
                        make_issue_comment(
                            str(issue_number),
                            "❌ No ADW workflow found for this issue to stop.\n\n"
                            "To stop a specific workflow, provide the ADW ID: `--stop <adw-id>`",
                        )
                    except Exception as e:
                        print(f"Failed to post error comment: {e}")

                    return {
                        "status": "stop_failed",
                        "message": "No ADW found for this issue",
                    }

            # Check for standalone --resume command (with optional ADW ID)
            elif RESUME_PATTERN.search(comment_body):
                resume_match = RESUME_PATTERN.search(comment_body)
                explicit_adw_id = resume_match.group(1) if resume_match else None

                if explicit_adw_id:
                    # Use the explicitly provided ADW ID
                    print(f"Resume with explicit ADW ID: {explicit_adw_id}")
                    provided_adw_id = explicit_adw_id
                    workflow = get_workflow_from_state(explicit_adw_id)
                    if not workflow:
                        print(f"No workflow found in state for ADW ID: {explicit_adw_id}")
                        try:
                            make_issue_comment(
                                str(issue_number),
                                f"❌ No workflow found for ADW ID `{explicit_adw_id}`.\n\n"
                                f"Please check the ADW ID is correct.",
                            )
                        except Exception as e:
                            print(f"Failed to post error comment: {e}")
                else:
                    # Find most recent ADW for this issue
                    print(f"Resume without ADW ID - finding latest for issue #{issue_number}")
                    found_adw_id, workflow = find_latest_adw_for_issue(str(issue_number))
                    if found_adw_id and workflow:
                        provided_adw_id = found_adw_id
                        print(f"Found ADW ID: {found_adw_id}, workflow: {workflow}")
                    else:
                        print(f"No ADW found for issue #{issue_number}")
                        try:
                            make_issue_comment(
                                str(issue_number),
                                "❌ No ADW workflow found for this issue to resume.\n\n"
                                "To start a new workflow, use a command like `adw_sdlc_router_iso`",
                            )
                        except Exception as e:
                            print(f"Failed to post error comment: {e}")

                if workflow:
                    resume_mode = True
                    # Load model_set from existing state
                    state = ADWState.load(provided_adw_id)
                    model_set = state.get("model_set", "base") if state else "base"
                    trigger_reason = f"Resume command for {workflow}"

            # Check if comment contains "adw_"
            elif "adw_" in comment_body.lower():
                # Use temporary ID for classification
                temp_id = make_adw_id()
                extraction_result = extract_adw_info(comment_body, temp_id)
                if extraction_result.has_workflow:
                    workflow = extraction_result.workflow_command
                    provided_adw_id = extraction_result.adw_id
                    model_set = extraction_result.model_set
                    # Check for --resume flag
                    resume_mode = "--resume" in comment_body.lower()
                    trigger_reason = f"Comment with {workflow} workflow" + (" (resume)" if resume_mode else "")

        # Validate workflow constraints
        if workflow in DEPENDENT_WORKFLOWS:
            if not provided_adw_id:
                print(
                    f"{workflow} is a dependent workflow that requires an existing ADW ID"
                )
                print(f"Cannot trigger {workflow} directly via webhook without ADW ID")
                workflow = None
                # Post error comment to issue
                try:
                    make_issue_comment(
                        str(issue_number),
                        f"❌ Error: `{workflow}` is a dependent workflow that requires an existing ADW ID.\n\n"
                        f"To run this workflow, you must provide the ADW ID in your comment, for example:\n"
                        f"`{workflow} adw-12345678`\n\n"
                        f"The ADW ID should come from a previous workflow run (like `adw_plan_iso` or `adw_patch_iso`).",
                    )
                except Exception as e:
                    print(f"Failed to post error comment: {e}")

        if workflow:
            # Use provided ADW ID or generate a new one
            adw_id = provided_adw_id or make_adw_id()

            # If ADW ID was provided, update/create state file
            if provided_adw_id:
                # Try to load existing state first
                state = ADWState.load(provided_adw_id)
                if state:
                    # Update issue_number and model_set if state exists
                    state.update(issue_number=str(issue_number), model_set=model_set)
                else:
                    # Only create new state if it doesn't exist
                    state = ADWState(provided_adw_id)
                    state.update(
                        adw_id=provided_adw_id,
                        issue_number=str(issue_number),
                        model_set=model_set,
                    )
                state.save("webhook_trigger")
            else:
                # Create new state for newly generated ADW ID
                state = ADWState(adw_id)
                state.update(
                    adw_id=adw_id, issue_number=str(issue_number), model_set=model_set
                )
                state.save("webhook_trigger")

            # Set up logger
            logger = setup_logger(adw_id, "webhook_trigger")
            logger.info(
                f"Detected workflow: {workflow} from content: {content_to_check[:100]}..."
            )
            if provided_adw_id:
                logger.info(f"Using provided ADW ID: {provided_adw_id}")

            # Post comment to issue about detected workflow
            try:
                resume_indicator = "🔄 Resuming" if resume_mode else "Starting"
                make_issue_comment(
                    str(issue_number),
                    f"🤖 ADW Webhook: Detected `{workflow}` workflow request\n\n"
                    f"{resume_indicator} workflow with ID: `{adw_id}`\n"
                    f"Workflow: `{workflow}` 🏗️\n"
                    f"Mode: `{'resume' if resume_mode else 'fresh'}` {'🔄' if resume_mode else '🆕'}\n"
                    f"Model Set: `{model_set}` ⚙️\n"
                    f"Reason: {trigger_reason}\n\n"
                    f"Logs will be available at: `agents/{adw_id}/{workflow}/`",
                )
            except Exception as e:
                logger.warning(f"Failed to post issue comment: {e}")

            # Build command to run the appropriate workflow
            script_dir = os.path.dirname(os.path.abspath(__file__))
            adws_dir = os.path.dirname(script_dir)
            repo_root = os.path.dirname(adws_dir)  # Go up to repository root
            trigger_script = os.path.join(adws_dir, f"{workflow}.py")

            cmd = ["uv", "run", trigger_script, str(issue_number), adw_id]
            if resume_mode:
                cmd.append("--resume")

            print(f"Launching {workflow} for issue #{issue_number}" + (" (resuming)" if resume_mode else ""))
            print(f"Command: {' '.join(cmd)} (reason: {trigger_reason})")
            print(f"Working directory: {repo_root}")

            # Launch in background using Popen with filtered environment
            # Redirect stdout and stderr to a combined log file
            log_file_path = "/tmp/adw-webhook-trigger.log"
            with open(log_file_path, "a") as log_file:
                # Write a separator with timestamp for this run
                log_file.write(f"\n{'='*60}\n")
                log_file.write(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Starting {workflow} for issue #{issue_number}\n")
                log_file.write(f"ADW ID: {adw_id}\n")
                log_file.write(f"Command: {' '.join(cmd)}\n")
                log_file.write(f"{'='*60}\n")
                log_file.flush()

            # Open log file for subprocess (append mode, unbuffered)
            log_handle = open(log_file_path, "a")
            process = subprocess.Popen(
                cmd,
                cwd=repo_root,  # Run from repository root where .claude/commands/ is located
                env=get_safe_subprocess_env(),  # Pass only required environment variables
                start_new_session=True,
                stdout=log_handle,
                stderr=log_handle,  # Both stdout and stderr to same file
            )
            # Note: log_handle intentionally not closed here - subprocess owns it

            # Store PID and PGID in state for stop functionality
            try:
                workflow_pid = process.pid
                # Get process group ID (same as PID when start_new_session=True)
                workflow_pgid = os.getpgid(process.pid)
                state.update(workflow_pid=workflow_pid, workflow_pgid=workflow_pgid)
                state.save("webhook_trigger")
                print(f"Stored process tracking: PID={workflow_pid}, PGID={workflow_pgid}")
            except Exception as e:
                print(f"Warning: Failed to store process tracking: {e}")

            print(
                f"Background process started for issue #{issue_number} with ADW ID: {adw_id}"
            )
            print(f"Workflow logs: agents/{adw_id}/{workflow}/execution.log")
            print(f"Combined stdout/stderr: {log_file_path}")

            # Return immediately
            return {
                "status": "accepted",
                "issue": issue_number,
                "adw_id": adw_id,
                "workflow": workflow,
                "message": f"ADW {workflow} triggered for issue #{issue_number}",
                "reason": trigger_reason,
                "logs": f"agents/{adw_id}/{workflow}/",
            }
        else:
            print(
                f"Ignoring webhook: event={event_type}, action={action}, issue_number={issue_number}"
            )
            return {
                "status": "ignored",
                "reason": f"Not a triggering event (event={event_type}, action={action})",
            }

    except Exception as e:
        print(f"Error processing webhook: {e}")
        # Always return 200 to GitHub to prevent retries
        return {"status": "error", "message": "Internal error processing webhook"}


@app.get("/health")
async def health():
    """Health check endpoint - runs comprehensive system health check."""
    try:
        # Run the health check script
        script_dir = os.path.dirname(os.path.abspath(__file__))
        # Health check is in adw_tests, not adw_triggers
        health_check_script = os.path.join(
            os.path.dirname(script_dir), "adw_tests", "health_check.py"
        )

        # Run health check with timeout
        result = subprocess.run(
            ["uv", "run", health_check_script],
            capture_output=True,
            text=True,
            timeout=30,
            cwd=os.path.dirname(script_dir),  # Run from adws directory
        )

        # Print the health check output for debugging
        print("=== Health Check Output ===")
        print(result.stdout)
        if result.stderr:
            print("=== Health Check Errors ===")
            print(result.stderr)

        # Parse the output - look for the overall status
        output_lines = result.stdout.strip().split("\n")
        is_healthy = result.returncode == 0

        # Extract key information from output
        warnings = []
        errors = []

        capturing_warnings = False
        capturing_errors = False

        for line in output_lines:
            if "⚠️  Warnings:" in line:
                capturing_warnings = True
                capturing_errors = False
                continue
            elif "❌ Errors:" in line:
                capturing_errors = True
                capturing_warnings = False
                continue
            elif "📝 Next Steps:" in line:
                break

            if capturing_warnings and line.strip().startswith("-"):
                warnings.append(line.strip()[2:])
            elif capturing_errors and line.strip().startswith("-"):
                errors.append(line.strip()[2:])

        return {
            "status": "healthy" if is_healthy else "unhealthy",
            "service": "adw-webhook-trigger",
            "health_check": {
                "success": is_healthy,
                "warnings": warnings,
                "errors": errors,
                "details": "Run health_check.py directly for full report",
            },
        }

    except subprocess.TimeoutExpired:
        return {
            "status": "unhealthy",
            "service": "adw-webhook-trigger",
            "error": "Health check timed out",
        }
    except Exception as e:
        return {
            "status": "unhealthy",
            "service": "adw-webhook-trigger",
            "error": f"Health check failed: {str(e)}",
        }


if __name__ == "__main__":
    print(f"Starting server on http://0.0.0.0:{PORT}")
    print(f"Webhook endpoint: POST /gh-webhook")
    print(f"Health check: GET /health")

    # Configure uvicorn logging with timestamps
    log_config = uvicorn.config.LOGGING_CONFIG
    log_config["formatters"]["default"]["fmt"] = "%(asctime)s - %(levelprefix)s %(message)s"
    log_config["formatters"]["access"]["fmt"] = '%(asctime)s - %(levelprefix)s %(client_addr)s - "%(request_line)s" %(status_code)s'

    uvicorn.run(app, host="0.0.0.0", port=PORT, log_config=log_config)
