#!/usr/bin/env -S uv run
# /// script
# dependencies = ["python-dotenv", "pydantic", "redis"]
# ///

"""
ADW Rescue Project Iso - Vibe Code Rescue Workflow

Usage: uv run adws/adw_rescue_project_iso.py <issue-number> <source-path> [adw-id] [--resume]

Rescues half-working "vibe coded" projects by preserving the frontend
and replacing the backend with production-ready template patterns.

Philosophy: "Save the face, replace the guts."

Workflow Phases:
1. Discovery - Analyze source project structure, features, UI components
2. Triage - Score components, classify backend, generate task graph
3. Execution - Execute rescue tasks (models, CRUD, APIs, components)
4. Validation - Run tests, visual comparison, feature parity check
5. Delivery - Create PR, documentation, cleanup

The workflow uses human checkpoints at triage and validation phases.
"""

import argparse
import logging
import os
import sys
import json
import shutil
import subprocess
import signal
import atexit
import time
from typing import Optional, Tuple, List

# Add the parent directory to Python path to import modules
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv

from adw_modules.state import ADWState
from adw_modules.rescue_state import (
    RescueState,
    RescuePhase,
    TaskStatus,
    RescueTask,
)
from adw_modules.worktree_ops import (
    create_worktree,
    setup_worktree_environment,
    get_ports_for_adw,
    validate_worktree,
    remove_worktree,
    release_ports,
)
from adw_modules.workflow_ops import ensure_adw_id
from adw_modules.agent import execute_template
from adw_modules.data_types import AgentTemplateRequest
from adw_modules.github import (
    post_issue_comment,
    poll_for_comment_response,
    poll_for_comment_response_with_status,
    PollResult,
)
from adw_modules.git_ops import finalize_git_operations
from adw_modules.utils import setup_logger, make_adw_id

load_dotenv()

# Agent name constants for rescue workflow
AGENT_RESCUE_DISCOVERY = "rescue_discovery"
AGENT_RESCUE_TRIAGE = "rescue_triage"
AGENT_RESCUE_EXECUTOR = "rescue_executor"
AGENT_RESCUE_VALIDATOR = "rescue_validator"
AGENT_RESCUE_PLANNER = "rescue_planner"

# Maximum retry attempts
MAX_TASK_RETRIES = 3
MAX_REPLANS = 3

# Checkpoint timeout (30 minutes)
CHECKPOINT_TIMEOUT_SECONDS = 1800

# Validation thresholds - validation can optionally block delivery if these aren't met
VALIDATION_MIN_TEST_PASS_RATE = 0.7  # 70% of tests must pass
VALIDATION_MIN_VISUAL_MATCH = 50.0  # 50% visual match required
VALIDATION_MIN_FEATURE_PARITY = 50.0  # 50% feature parity required
VALIDATION_BLOCK_ON_FAILURE = False  # Set True to block delivery on validation failures

# BUG-004 fix: Global list to track child processes for cleanup
# Note: Currently subprocess.run() is used (synchronous), so this list stays empty.
# If async Popen calls are added, use register_child_process() to track them.
_child_processes: list = []
_cleanup_done = False


def register_child_process(proc: subprocess.Popen) -> None:
    """Register a child process for cleanup on termination.

    Call this when starting async processes with Popen.
    """
    _child_processes.append(proc)


def _cleanup_child_processes(signum=None, frame=None):
    """Clean up child processes on termination."""
    global _cleanup_done
    if _cleanup_done:
        return
    _cleanup_done = True

    for proc in _child_processes:
        try:
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
        except Exception:
            pass

    if signum is not None:
        sys.exit(1)


# Register cleanup handlers
signal.signal(signal.SIGTERM, _cleanup_child_processes)
signal.signal(signal.SIGINT, _cleanup_child_processes)
atexit.register(_cleanup_child_processes)


def _cleanup_source_on_error(destination: str, logger: logging.Logger) -> None:
    """Clean up partially copied source directory on error."""
    if os.path.exists(destination):
        try:
            shutil.rmtree(destination)
            logger.info(f"Cleaned up partial source directory: {destination}")
        except Exception as e:
            logger.warning(f"Failed to clean up source directory {destination}: {e}")


def setup_source_project(
    source_path: str,
    worktree_path: str,
    logger: logging.Logger,
) -> str:
    """Copy source project into worktree for analysis.

    Args:
        source_path: Path to source project (local path or git URL)
        worktree_path: Path to the worktree
        logger: Logger instance

    Returns:
        Path to copied source project within worktree

    Raises:
        RuntimeError: If cloning or copying fails
        FileNotFoundError: If source path doesn't exist
    """
    destination = os.path.join(worktree_path, "source")

    # Handle different source types
    if source_path.startswith("http") or source_path.startswith("git@"):
        # Clone from URL
        logger.info(f"Cloning source project from {source_path}")
        try:
            result = subprocess.run(
                ["git", "clone", "--depth=1", source_path, destination],
                capture_output=True,
                text=True,
                timeout=300,  # 5 minute timeout for clone
            )
        except subprocess.TimeoutExpired:
            _cleanup_source_on_error(destination, logger)
            raise RuntimeError(f"Git clone timed out after 5 minutes: {source_path}")
        except Exception as e:
            _cleanup_source_on_error(destination, logger)
            raise RuntimeError(f"Git clone failed: {e}")
        if result.returncode != 0:
            _cleanup_source_on_error(destination, logger)
            raise RuntimeError(f"Failed to clone source: {result.stderr}")
    else:
        # Copy local directory
        if not os.path.exists(source_path):
            raise FileNotFoundError(f"Source project not found: {source_path}")

        # BUG-066 fix: Check if destination exists before copying
        if os.path.exists(destination):
            logger.warning(f"Destination {destination} already exists, removing first")
            shutil.rmtree(destination)

        logger.info(f"Copying source project from {source_path}")
        try:
            shutil.copytree(
                source_path,
                destination,
                ignore=shutil.ignore_patterns(
                    'node_modules', '.git', '__pycache__',
                    '.venv', 'venv', 'dist', 'build', '.next'
                )
            )
        except Exception as e:
            _cleanup_source_on_error(destination, logger)
            raise RuntimeError(f"Failed to copy source: {e}")

    logger.info(f"Source project copied to {destination}")
    return destination


def create_rescue_directories(worktree_path: str, logger: logging.Logger) -> None:
    """Create directory structure for rescue workflow outputs."""
    directories = [
        "discovery",
        "triage",
        "rescue",
        "rescue/screenshots",
        "rescue/screenshots/source",
        "rescue/screenshots/rescued",
    ]

    for dir_name in directories:
        dir_path = os.path.join(worktree_path, dir_name)
        os.makedirs(dir_path, exist_ok=True)
        logger.debug(f"Created directory: {dir_path}")


def execute_discovery_phase(
    adw_id: str,
    rescue_state: RescueState,
    worktree_path: str,
    logger: logging.Logger,
) -> bool:
    """Execute discovery phase tasks.

    Analyzes the source project to understand its structure, features,
    UI components, and identify red flags.
    """
    source_path = rescue_state.data.source_project_path
    logger.info("Starting discovery phase")

    discovery_tasks = [
        ("/rescue_scan_structure", [adw_id, source_path]),
        ("/rescue_map_features", [adw_id, source_path]),
        ("/rescue_extract_schema", [adw_id, source_path]),
        ("/rescue_catalog_ui", [adw_id, source_path]),
        ("/rescue_document_discovery", [adw_id]),
    ]

    for command, args in discovery_tasks:
        logger.info(f"Executing: {command}")

        request = AgentTemplateRequest(
            agent_name=f"{AGENT_RESCUE_DISCOVERY}_{command.replace('/', '')}",
            slash_command=command,
            args=args,
            adw_id=adw_id,
            working_dir=worktree_path,
        )

        response = execute_template(request)

        if not response.success:
            logger.error(f"Discovery task failed: {command}")
            logger.error(response.output)
            return False

        logger.info(f"Completed: {command}")

    # Load discovery results into state
    try:
        _load_discovery_results(rescue_state, worktree_path, logger)
    except Exception as e:
        logger.error(f"Failed to load discovery results into state: {e}")
        # Discovery results are critical for triage, fail if we can't load them
        return False

    rescue_state.mark_phase_complete(RescuePhase.DISCOVERY)
    try:
        rescue_state.save()
    except Exception as e:
        logger.error(f"Failed to save rescue state: {e}")
        raise
    return True


def _load_discovery_results(
    rescue_state: RescueState,
    worktree_path: str,
    logger: logging.Logger,
) -> None:
    """Load discovery phase JSON outputs into rescue state.

    BUG-067 fix: Added JSON validation and error handling.
    """
    # Load structure report
    structure_path = os.path.join(worktree_path, "discovery/structure_report.json")
    if os.path.exists(structure_path):
        try:
            with open(structure_path, "r") as f:
                structure = json.load(f)

            # Validate required keys exist
            if not isinstance(structure, dict):
                raise ValueError("Structure report must be a JSON object")

            from adw_modules.rescue_state import SourceStackInfo
            rescue_state.data.discovery.source_stack = SourceStackInfo(
                backend_framework=structure.get("backend", {}).get("framework"),
                database_type=structure.get("database", {}).get("type"),
                frontend_framework=structure.get("frontend", {}).get("framework"),
                state_management=structure.get("frontend", {}).get("state_management", []),
                styling_methods=structure.get("styling", {}).get("methods_detected", []),
                package_manager=structure.get("structure", {}).get("package_manager"),
            )
            logger.debug(f"Loaded structure report from {structure_path}")
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse structure report JSON: {e}")
            raise
        except (ValueError, TypeError) as e:
            logger.error(f"Invalid structure report format: {e}")
            raise

    # Load UI catalog
    ui_catalog_path = os.path.join(worktree_path, "discovery/ui_catalog.json")
    if os.path.exists(ui_catalog_path):
        try:
            with open(ui_catalog_path, "r") as f:
                ui_catalog = json.load(f)

            # Validate structure
            if not isinstance(ui_catalog, dict):
                raise ValueError("UI catalog must be a JSON object")

            from adw_modules.rescue_state import UIComponentSpec
            components = []
            for comp in ui_catalog.get("components", []):
                try:
                    components.append(UIComponentSpec(**comp))
                except (TypeError, ValueError) as e:
                    logger.warning(f"Skipping invalid component: {e}")
                    continue
            rescue_state.data.discovery.ui_components = components
            logger.debug(f"Loaded {len(components)} components from {ui_catalog_path}")
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse UI catalog JSON: {e}")
            raise
        except (ValueError, TypeError) as e:
            logger.error(f"Invalid UI catalog format: {e}")
            raise


def execute_triage_phase(
    adw_id: str,
    rescue_state: RescueState,
    worktree_path: str,
    logger: logging.Logger,
) -> bool:
    """Execute triage phase tasks.

    Scores components, classifies backend domains, and generates
    the complete task graph for execution.
    """
    logger.info("Starting triage phase")

    triage_tasks = [
        ("/rescue_score_components", [adw_id]),
        ("/rescue_classify_backend", [adw_id]),
        ("/rescue_plan_ui", [adw_id]),
        ("/rescue_generate_tasks", [adw_id]),
        ("/rescue_evaluate_feasibility", [adw_id]),
    ]

    for command, args in triage_tasks:
        logger.info(f"Executing: {command}")

        request = AgentTemplateRequest(
            agent_name=f"{AGENT_RESCUE_TRIAGE}_{command.replace('/', '')}",
            slash_command=command,
            args=args,
            adw_id=adw_id,
            working_dir=worktree_path,
        )

        response = execute_template(request)

        if not response.success:
            logger.error(f"Triage task failed: {command}")
            logger.error(response.output)
            return False

        logger.info(f"Completed: {command}")

    # Load task graph
    task_graph_path = os.path.join(worktree_path, "triage/task_graph.json")
    if os.path.exists(task_graph_path):
        rescue_state.add_tasks_from_graph(task_graph_path)

        # Validate task graph for cycles and invalid references before proceeding
        cycle = rescue_state.detect_cycles()
        if cycle:
            if cycle == ["INVALID_REFERENCES"]:
                # Invalid task references detected
                ref_errors = rescue_state.validate_task_references()
                logger.error(f"Task graph has invalid references: {ref_errors}")
                rescue_state.add_learning(f"Invalid task graph: {ref_errors}")
            else:
                cycle_str = " -> ".join(cycle)
                logger.error(f"Task graph contains cycle: {cycle_str}")
                rescue_state.add_learning(f"Invalid task graph: cycle detected {cycle_str}")
            return False
    else:
        logger.error(f"Task graph not found at {task_graph_path}")
        return False

    rescue_state.mark_phase_complete(RescuePhase.TRIAGE)
    try:
        rescue_state.save()
    except Exception as e:
        logger.error(f"Failed to save rescue state: {e}")
        raise
    return True


def execute_rescue_tasks(
    adw_id: str,
    rescue_state: RescueState,
    worktree_path: str,
    logger: logging.Logger,
) -> bool:
    """Execute rescue tasks from the task graph."""
    logger.info("Starting execution phase")

    # Check for cycles and invalid references before starting execution
    cycle = rescue_state.detect_cycles()
    if cycle:
        if cycle == ["INVALID_REFERENCES"]:
            ref_errors = rescue_state.validate_task_references()
            logger.error(f"Invalid task references in task graph: {ref_errors}")
            rescue_state.add_learning(f"Task graph has invalid references: {ref_errors}")
        else:
            cycle_str = " -> ".join(cycle)
            logger.error(f"Circular dependency detected in task graph: {cycle_str}")
            rescue_state.add_learning(f"Task graph cycle detected: {cycle_str}")
        return False

    replan_count = 0

    while rescue_state.has_pending_tasks():
        task = rescue_state.get_next_task()

        if task is None:
            # Check if stuck (cycle or orphaned dependencies)
            if rescue_state.is_stuck():
                logger.error("Workflow is stuck: pending tasks exist but none are executable")
                logger.error("This may indicate orphaned task dependencies or a logic error")
                # Try to re-plan as a last resort
                if replan_count < MAX_REPLANS:
                    logger.warning("Attempting re-plan to resolve stuck state")
                    if trigger_replan(adw_id, rescue_state, worktree_path, logger, "stuck"):
                        replan_count += 1
                        # Re-check for cycles and invalid references after replan
                        cycle = rescue_state.detect_cycles()
                        if cycle:
                            if cycle == ["INVALID_REFERENCES"]:
                                logger.error("Replan introduced invalid task references")
                            else:
                                logger.error(f"Replan introduced cycle: {' -> '.join(cycle)}")
                            return False
                        continue
                return False

            if rescue_state.is_blocked():
                # Try to re-plan
                if replan_count >= MAX_REPLANS:
                    logger.error("Max re-plans reached, cannot proceed")
                    return False

                logger.warning("All tasks blocked by failures, triggering re-plan")
                if not trigger_replan(adw_id, rescue_state, worktree_path, logger, "blocked"):
                    return False
                replan_count += 1
                continue

            # BUG-074 fix: Check if there are running tasks we should wait for
            running_tasks = [t for t in rescue_state.data.tasks if t.status == "running"]
            if running_tasks:
                logger.info(f"Waiting for {len(running_tasks)} running tasks to complete")
                time.sleep(5)  # Brief wait before re-checking
                continue

            # BUG-074 fix: If we have pending tasks but none are executable and we're not
            # stuck or blocked, this is an unexpected state - log details and fail gracefully
            pending_tasks = [t for t in rescue_state.data.tasks if t.status == "pending"]
            if pending_tasks:
                logger.error(f"Unexpected state: {len(pending_tasks)} pending tasks but none executable")
                for pt in pending_tasks[:5]:  # Log first 5 for debugging
                    logger.error(f"  - Task {pt.id}: inputs={pt.inputs}, status={pt.status}")
                rescue_state.add_learning(f"Unexpected execution state: {len(pending_tasks)} pending but not executable")
                return False

            # No pending, running, stuck, or blocked - we're actually done
            break

        # Execute task
        logger.info(f"Executing task: {task.id} - {task.description}")
        rescue_state.update_task_status(task.id, TaskStatus.RUNNING)
        rescue_state.data.execution.current_task = task.id
        rescue_state.save()

        request = AgentTemplateRequest(
            agent_name=f"{AGENT_RESCUE_EXECUTOR}_{task.id}",
            slash_command=task.slash_command,
            args=[adw_id] + task.args,
            adw_id=adw_id,
            working_dir=worktree_path,
        )

        response = execute_template(request)

        if response.success:
            # update_task_status auto-maintains completed_tasks list (review fix #2)
            rescue_state.update_task_status(task.id, TaskStatus.COMPLETED)
            logger.info(f"Task completed: {task.id}")
        else:
            # BUG-075 fix: Use increment method since get_next_task() returns a copy
            new_retry_count = rescue_state.increment_task_retry_count(task.id)
            if new_retry_count >= MAX_TASK_RETRIES:
                # update_task_status auto-maintains failed_tasks list (review fix #2)
                rescue_state.update_task_status(
                    task.id,
                    TaskStatus.FAILED,
                    error_message=response.output[:500]
                )
                logger.error(f"Task failed after {MAX_TASK_RETRIES} retries: {task.id}")

                # Add learning about the failure
                rescue_state.add_learning(f"Task {task.id} failed: {response.output[:200]}")

                # Review fix #21: Check trigger_replan return value.
                # If replan fails, don't silently increment replan_count.
                if replan_count < MAX_REPLANS:
                    replan_success = trigger_replan(
                        adw_id, rescue_state, worktree_path, logger,
                        f"task_failed:{task.id}"
                    )
                    if replan_success:
                        replan_count += 1
                    else:
                        logger.error("Replan failed after task failure, continuing with remaining tasks")
            else:
                # BUG-068 fix: Add delay before retry to avoid hammering
                retry_delay = 5 * new_retry_count  # Exponential backoff: 5s, 10s, 15s
                logger.warning(f"Task failed, retry {new_retry_count} in {retry_delay}s: {task.id}")
                time.sleep(retry_delay)
                rescue_state.update_task_status(task.id, TaskStatus.PENDING)

        rescue_state.save()

    rescue_state.data.execution.current_task = None
    rescue_state.mark_phase_complete(RescuePhase.EXECUTION)
    rescue_state.save()
    return True


def trigger_replan(
    adw_id: str,
    rescue_state: RescueState,
    worktree_path: str,
    logger: logging.Logger,
    reason: str,
) -> bool:
    """Trigger re-planning of the task graph."""
    logger.info(f"Triggering re-plan: {reason}")

    # Increment plan version
    rescue_state.data.plan_version += 1

    # Archive current plan
    current_plan = os.path.join(worktree_path, "triage/task_graph.json")
    archive_path = os.path.join(
        worktree_path,
        f"triage/task_graph_v{rescue_state.data.plan_version - 1}.json"
    )
    if os.path.exists(current_plan):
        shutil.copy(current_plan, archive_path)
        rescue_state.data.plan_history.append(archive_path)
        logger.info(f"Archived plan to {archive_path}")

    # Execute re-plan
    request = AgentTemplateRequest(
        agent_name=f"{AGENT_RESCUE_PLANNER}_replan_v{rescue_state.data.plan_version}",
        slash_command="/rescue_replan",
        args=[adw_id, reason],
        adw_id=adw_id,
        working_dir=worktree_path,
    )

    response = execute_template(request)

    if not response.success:
        logger.error(f"Re-plan failed: {response.output}")
        return False

    # Reload task graph
    if not reload_task_graph(rescue_state, worktree_path, logger):
        logger.error("Failed to reload task graph after re-plan")
        return False

    rescue_state.save()

    logger.info(f"Re-plan successful, now on version {rescue_state.data.plan_version}")
    return True


def reload_task_graph(
    rescue_state: RescueState,
    worktree_path: str,
    logger: logging.Logger,
) -> bool:
    """Reload task graph after re-planning.

    Returns:
        True if reload was successful, False otherwise.
    """
    task_graph_path = os.path.join(worktree_path, "triage/task_graph.json")

    if not os.path.exists(task_graph_path):
        logger.error("Task graph not found after re-plan")
        return False

    try:
        with open(task_graph_path, "r") as f:
            graph_data = json.load(f)
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse task graph JSON: {e}")
        return False
    except (IOError, OSError) as e:
        logger.error(f"Failed to read task graph file: {e}")
        return False

    # BUG-072 fix: Get BOTH completed AND skipped task IDs
    # SKIPPED tasks must be treated as completed for dependency checking
    # (documented in MEMORY.md as critical pattern)
    completed_ids = set(rescue_state.data.execution.completed_tasks)
    skipped_ids = set(rescue_state.data.execution.skipped_tasks)

    # Also capture retry counts from existing tasks before clearing
    existing_retry_counts = {
        task.id: task.retry_count
        for task in rescue_state.data.tasks
    }

    # Clear existing tasks and reload
    rescue_state.data.tasks = []

    tasks_loaded = 0
    tasks_skipped = 0
    for task_data in graph_data.get("tasks", []):
        try:
            task = RescueTask(**task_data)
            # Mark completed tasks
            # BUG-064 fix: Use TaskStatus enum value for consistency
            if task.id in completed_ids:
                task.status = TaskStatus.COMPLETED.value
            # BUG-072 fix: Mark skipped tasks as well
            elif task.id in skipped_ids:
                task.status = TaskStatus.SKIPPED.value
            # BUG-073 fix: Preserve retry counts for tasks that existed before replan
            # Only reset retry count for truly new tasks
            if task.id in existing_retry_counts:
                task.retry_count = existing_retry_counts[task.id]
            else:
                task.retry_count = 0
            rescue_state.add_task(task)
            tasks_loaded += 1
        except (TypeError, ValueError) as e:
            logger.warning(f"Skipping invalid task during reload: {e}")
            tasks_skipped += 1

    if tasks_loaded == 0:
        logger.error("No valid tasks loaded from task graph")
        return False

    logger.info(f"Reloaded {tasks_loaded} tasks from updated graph (skipped {tasks_skipped})")
    return True


def execute_validation_phase(
    adw_id: str,
    rescue_state: RescueState,
    worktree_path: str,
    logger: logging.Logger,
) -> bool:
    """Execute validation phase tasks."""
    logger.info("Starting validation phase")

    validation_tasks = [
        ("/rescue_validate_tests", [adw_id]),
        ("/rescue_validate_visual", [adw_id]),
        ("/rescue_validate_features", [adw_id]),
    ]

    for command, args in validation_tasks:
        logger.info(f"Executing: {command}")

        request = AgentTemplateRequest(
            agent_name=f"{AGENT_RESCUE_VALIDATOR}_{command.replace('/', '')}",
            slash_command=command,
            args=args,
            adw_id=adw_id,
            working_dir=worktree_path,
        )

        response = execute_template(request)

        if not response.success:
            logger.warning(f"Validation task failed: {command}")
            logger.warning(response.output)
            # Continue to run all validations even if some fail

        logger.info(f"Completed: {command}")

    # Load validation results
    _load_validation_results(rescue_state, worktree_path, logger)

    # Check validation thresholds
    validation = rescue_state.data.validation
    validation_issues = []

    # Test pass rate check
    total_tests = validation.tests_passed + validation.tests_failed
    if total_tests > 0:
        test_pass_rate = validation.tests_passed / total_tests
        if test_pass_rate < VALIDATION_MIN_TEST_PASS_RATE:
            validation_issues.append(
                f"Test pass rate {test_pass_rate:.1%} below threshold {VALIDATION_MIN_TEST_PASS_RATE:.1%}"
            )

    # Visual match check
    if validation.visual_match_percent < VALIDATION_MIN_VISUAL_MATCH:
        validation_issues.append(
            f"Visual match {validation.visual_match_percent}% below threshold {VALIDATION_MIN_VISUAL_MATCH}%"
        )

    # Feature parity check
    if validation.feature_parity_percent < VALIDATION_MIN_FEATURE_PARITY:
        validation_issues.append(
            f"Feature parity {validation.feature_parity_percent}% below threshold {VALIDATION_MIN_FEATURE_PARITY}%"
        )

    if validation_issues:
        for issue in validation_issues:
            logger.warning(f"Validation threshold not met: {issue}")
        rescue_state.add_learning(f"Validation issues: {'; '.join(validation_issues)}")

        if VALIDATION_BLOCK_ON_FAILURE:
            logger.error("Validation failed - blocking delivery (VALIDATION_BLOCK_ON_FAILURE=True)")
            return False

    rescue_state.mark_phase_complete(RescuePhase.VALIDATION)
    try:
        rescue_state.save()
    except Exception as e:
        logger.error(f"Failed to save rescue state: {e}")
        raise
    return True


def _load_validation_results(
    rescue_state: RescueState,
    worktree_path: str,
    logger: logging.Logger,
) -> None:
    """Load validation phase results into rescue state.

    BUG-070 fix: Added proper JSON parsing error handling.
    """
    # Load test results
    test_results_path = os.path.join(worktree_path, "rescue/test_results.json")
    if os.path.exists(test_results_path):
        try:
            with open(test_results_path, "r") as f:
                results = json.load(f)
            rescue_state.update_validation(
                tests_passed=results.get("passed", 0),
                tests_failed=results.get("failed", 0),
            )
            rescue_state.data.validation.test_results_path = test_results_path
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse test results JSON: {e}")
        except (IOError, OSError) as e:
            logger.warning(f"Failed to read test results file: {e}")

    # Load visual comparison results
    visual_path = os.path.join(worktree_path, "rescue/visual_comparison.json")
    if os.path.exists(visual_path):
        try:
            with open(visual_path, "r") as f:
                visual = json.load(f)
            rescue_state.update_validation(
                visual_match_percent=visual.get("overall_match_percent", 0.0),
            )
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse visual comparison JSON: {e}")
        except (IOError, OSError) as e:
            logger.warning(f"Failed to read visual comparison file: {e}")

    # Load feature parity results
    features_path = os.path.join(worktree_path, "rescue/feature_parity.json")
    if os.path.exists(features_path):
        try:
            with open(features_path, "r") as f:
                features = json.load(f)
            rescue_state.update_validation(
                feature_parity_percent=features.get("parity_percent", 0.0),
            )
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse feature parity JSON: {e}")
        except (IOError, OSError) as e:
            logger.warning(f"Failed to read feature parity file: {e}")


def execute_delivery_phase(
    adw_id: str,
    state: ADWState,
    rescue_state: RescueState,
    worktree_path: str,
    logger: logging.Logger,
) -> bool:
    """Execute delivery phase - commit, PR, documentation.

    BUG-069 fix: Uses finalize_git_operations for push and PR creation
    to avoid code duplication and ensure consistent behavior.
    """
    logger.info("Starting delivery phase")

    # Commit changes
    branch_name = state.get("branch_name")
    if not branch_name:
        logger.error("No branch name in state")
        return False

    # Stage all changes
    try:
        result = subprocess.run(
            ["git", "add", "-A"],
            capture_output=True,
            text=True,
            cwd=worktree_path,
            timeout=60,
        )
    except subprocess.TimeoutExpired:
        logger.error("Git add timed out")
        return False

    if result.returncode != 0:
        logger.error(f"Git add failed: {result.stderr}")
        return False

    # Create commit message with rescue workflow summary
    summary = rescue_state.get_summary()
    commit_message = f"""rescue({adw_id}): Rescue project from source

Discovery:
- Features: {summary['discovery']['features_count']}
- UI Components: {summary['discovery']['components_count']}
- Difficulty: {summary['discovery']['difficulty']}

Execution:
- Tasks completed: {summary['execution']['tasks_completed']}
- Tasks failed: {summary['execution']['tasks_failed']}

Validation:
- Tests: {summary['validation']['tests_passed']} passed, {summary['validation']['tests_failed']} failed
- Visual match: {summary['validation']['visual_match']}

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
"""

    try:
        result = subprocess.run(
            ["git", "commit", "-m", commit_message],
            capture_output=True,
            text=True,
            cwd=worktree_path,
            timeout=60,
        )
    except subprocess.TimeoutExpired:
        logger.error("Git commit timed out")
        return False

    if result.returncode != 0:
        # Check if nothing to commit
        if "nothing to commit" in result.stdout or "nothing to commit" in result.stderr:
            logger.warning("Nothing to commit")
        else:
            logger.error(f"Git commit failed: {result.stderr}")
            return False

    # BUG-069 fix: Use finalize_git_operations for push and PR creation
    # This avoids code duplication and ensures consistent error handling
    success, error = finalize_git_operations(state, logger, cwd=worktree_path)
    if not success:
        logger.error(f"Git finalization failed: {error}")
        # BUG-084 fix: Add git finalization errors to learnings for post-mortem analysis
        rescue_state.add_learning(f"Git finalization failed: {error}")
        rescue_state.save()
        return False

    logger.info("Delivery phase completed successfully")
    return True


def handle_not_recommended(
    adw_id: str,
    rescue_state: RescueState,
    state: ADWState,
    logger: logging.Logger,
) -> bool:
    """Handle case where project is not recommended for rescue."""
    logger.warning("Project not recommended for rescue due to complexity")

    # Post comment explaining why
    issue_number = state.get("issue_number")
    if issue_number:
        difficulty_reason = rescue_state.data.discovery.red_flags.difficulty_reason
        flags = rescue_state.data.discovery.red_flags

        message = f"""## Vibe Code Rescue: Not Recommended

**ADW:** `{adw_id}`

After analyzing the source project, this rescue is **not recommended** due to excessive complexity.

### Red Flags Detected

| Flag | Status |
|------|--------|
| CSS Chaos (3+ styling methods) | {'Yes' if flags.has_css_chaos else 'No'} |
| State Chaos (3+ state approaches) | {'Yes' if flags.has_state_chaos else 'No'} |
| Forked Libraries | {'Yes' if flags.has_forked_libraries else 'No'} |
| Undocumented Integrations | {'Yes' if flags.has_undocumented_integrations else 'No'} |
| Enterprise Complexity | {'Yes' if flags.enterprise_complexity else 'No'} |

**Reason:** {difficulty_reason}

### Recommendation

Consider:
1. Manual rewrite from scratch using the template
2. Incremental migration of features
3. Hiring specialized help for complex areas

---
*ADW Rescue Workflow | {adw_id}*
"""
        try:
            post_issue_comment(issue_number, message)
        except Exception as e:
            logger.error(f"Failed to post comment: {e}")

    return False


def await_triage_checkpoint(
    adw_id: str,
    rescue_state: RescueState,
    state: ADWState,
    worktree_path: str,
    logger: logging.Logger,
    skip_checkpoints: bool = False,
) -> bool:
    """Post triage summary and await human approval."""
    # BUG-071 fix: Honor skip_checkpoints flag
    if skip_checkpoints:
        logger.info("Skipping triage checkpoint (--skip-checkpoints flag)")
        rescue_state.add_checkpoint("triage", True, "auto-approved (skip_checkpoints)")
        return True

    issue_number = state.get("issue_number")
    if not issue_number:
        logger.warning("No issue number, skipping checkpoint")
        return True

    # Build checkpoint comment
    summary = rescue_state.get_summary()
    discovery = rescue_state.data.discovery
    triage = rescue_state.data.triage

    # Count components by tier
    tier_counts = {"auto": 0, "assisted": 0, "manual": 0}
    for comp in discovery.ui_components:
        tier = comp.migration_tier.lower()
        if tier in tier_counts:
            tier_counts[tier] += 1

    message = f"""## Vibe Code Rescue: Triage Complete

**ADW:** `{adw_id}`

---

### Discovery Summary

| Metric | Value |
|--------|-------|
| Features Detected | {summary['discovery']['features_count']} |
| UI Components | {summary['discovery']['components_count']} |
| Difficulty | {summary['discovery']['difficulty']} |

### Red Flags

| Flag | Status |
|------|--------|
| CSS Chaos | {'Yes' if discovery.red_flags.has_css_chaos else 'No'} |
| State Chaos | {'Yes' if discovery.red_flags.has_state_chaos else 'No'} |
| Dead Code | {'Yes' if discovery.red_flags.has_dead_code else 'No'} |
| Forked Libraries | {'Yes' if discovery.red_flags.has_forked_libraries else 'No'} |

---

### Rescue Plan

**Frontend Approach:**
- {tier_counts['auto']} components: AUTO (direct extraction)
- {tier_counts['assisted']} components: ASSISTED (needs review)
- {tier_counts['manual']} components: MANUAL (recreation required)

**Estimated Effort:**
- Tasks: {summary['triage']['estimated_tasks']}
- Time: {summary['triage']['estimated_hours']} hours

---

### Next Steps

Reply to this comment with:
- `approve` - Proceed with rescue
- `reduce scope: [features to exclude]` - Narrow scope
- `cancel` - Stop rescue (artifacts preserved)

---
*ADW Rescue Workflow | {adw_id}*
"""

    try:
        post_issue_comment(issue_number, message)
        logger.info("Posted triage checkpoint comment")
    except Exception as e:
        logger.error(f"Failed to post checkpoint: {e}")
        rescue_state.add_checkpoint("triage", True, f"comment post failed: {e}")
        return True  # Continue anyway

    # Poll for response with detailed status
    logger.info("Awaiting human approval...")
    response, poll_status = poll_for_comment_response_with_status(
        issue_number,
        ["approve", "reduce scope", "cancel"],
        timeout_seconds=CHECKPOINT_TIMEOUT_SECONDS,
        logger=logger,
    )

    # Handle different poll result types
    if poll_status == PollResult.TIMEOUT:
        logger.warning("Checkpoint timed out, proceeding with execution")
        rescue_state.add_checkpoint("triage", True, "timeout - auto-approved")
        return True
    elif poll_status == PollResult.ISSUE_DELETED:
        logger.error("Issue was deleted, cannot proceed")
        rescue_state.add_checkpoint("triage", False, "issue deleted")
        return False
    elif poll_status == PollResult.PERMISSION_DENIED:
        logger.error("Permission denied accessing issue")
        rescue_state.add_checkpoint("triage", False, "permission denied")
        return False
    elif poll_status == PollResult.AUTH_ERROR:
        logger.error("GitHub authentication error")
        rescue_state.add_checkpoint("triage", False, "auth error")
        return False
    elif poll_status == PollResult.INVALID_ISSUE:
        logger.error("Invalid issue number")
        rescue_state.add_checkpoint("triage", False, "invalid issue")
        return False

    if response is None:
        logger.warning("No response received, proceeding with execution")
        rescue_state.add_checkpoint("triage", True, "no response - auto-approved")
        return True

    response_lower = response.lower().strip()

    if response_lower == "cancel":
        logger.info("Rescue cancelled by user")
        rescue_state.add_checkpoint("triage", False, "cancelled by user")
        return False

    # BUG-083 fix: More robust scope reduction parsing
    # Handle both "reduce scope: features" and "reduce scope features"
    if response_lower.startswith("reduce scope"):
        # Handle scope reduction by triggering replan with scope changes
        # Try colon separator first, then space
        if ":" in response_lower:
            scope_changes = response_lower.split(":", 1)[1].strip()
        else:
            scope_changes = response_lower.replace("reduce scope", "", 1).strip()
        # Ensure we have actual scope changes
        if not scope_changes:
            scope_changes = "unspecified reduction"
        rescue_state.add_checkpoint("triage", True, f"scope reduced: {scope_changes}")
        if rescue_state.data.checkpoints:
            rescue_state.data.checkpoints[-1].scope_changes = [scope_changes]
        logger.info(f"Scope reduced: {scope_changes}")

        # Trigger replan with scope reduction reason
        replan_success = trigger_replan(
            adw_id, rescue_state, worktree_path, logger,
            f"scope_reduction:{scope_changes}"
        )
        if not replan_success:
            logger.error("Failed to replan after scope reduction")
            return False
        return True

    # approve
    rescue_state.add_checkpoint("triage", True, "approved by user")
    logger.info("Triage approved, proceeding with execution")
    return True


def await_validation_checkpoint(
    adw_id: str,
    rescue_state: RescueState,
    state: ADWState,
    worktree_path: str,
    logger: logging.Logger,
    skip_checkpoints: bool = False,
) -> bool:
    """Post validation results and await human approval."""
    # BUG-071 fix: Honor skip_checkpoints flag
    if skip_checkpoints:
        logger.info("Skipping validation checkpoint (--skip-checkpoints flag)")
        rescue_state.add_checkpoint("validation", True, "auto-approved (skip_checkpoints)")
        return True

    issue_number = state.get("issue_number")
    if not issue_number:
        logger.warning("No issue number, skipping checkpoint")
        return True

    summary = rescue_state.get_summary()
    validation = rescue_state.data.validation

    message = f"""## Vibe Code Rescue: Validation Complete

**ADW:** `{adw_id}`

---

### Test Results

| Metric | Value |
|--------|-------|
| Tests Passed | {validation.tests_passed} |
| Tests Failed | {validation.tests_failed} |
| Visual Match | {validation.visual_match_percent}% |
| Feature Parity | {validation.feature_parity_percent}% |

### Execution Summary

| Metric | Value |
|--------|-------|
| Tasks Completed | {summary['execution']['tasks_completed']} |
| Tasks Failed | {summary['execution']['tasks_failed']} |
| Plan Versions | {rescue_state.data.plan_version} |

### Learnings

{chr(10).join(f'- {l}' for l in rescue_state.data.learnings[:5]) if rescue_state.data.learnings else 'No learnings recorded'}

---

### Next Steps

Reply with:
- `approve` - Create PR and finish
- `fix: [issue]` - Request specific fix
- `ship partial` - Ship as-is with documented issues

---
*ADW Rescue Workflow | {adw_id}*
"""

    try:
        post_issue_comment(issue_number, message)
        logger.info("Posted validation checkpoint comment")
    except Exception as e:
        logger.error(f"Failed to post checkpoint: {e}")
        rescue_state.add_checkpoint("validation", True, f"comment post failed: {e}")
        return True

    # Poll for response with detailed status
    logger.info("Awaiting human approval...")
    response, poll_status = poll_for_comment_response_with_status(
        issue_number,
        ["approve", "fix:", "ship partial"],
        timeout_seconds=CHECKPOINT_TIMEOUT_SECONDS,
        logger=logger,
    )

    # Handle different poll result types
    if poll_status == PollResult.TIMEOUT:
        logger.warning("Checkpoint timed out, proceeding with delivery")
        rescue_state.add_checkpoint("validation", True, "timeout - auto-approved")
        return True
    elif poll_status == PollResult.ISSUE_DELETED:
        logger.error("Issue was deleted, cannot proceed with delivery")
        rescue_state.add_checkpoint("validation", False, "issue deleted")
        return False
    elif poll_status == PollResult.PERMISSION_DENIED:
        logger.error("Permission denied accessing issue")
        rescue_state.add_checkpoint("validation", False, "permission denied")
        return False
    elif poll_status == PollResult.AUTH_ERROR:
        logger.error("GitHub authentication error")
        rescue_state.add_checkpoint("validation", False, "auth error")
        return False
    elif poll_status == PollResult.INVALID_ISSUE:
        logger.error("Invalid issue number")
        rescue_state.add_checkpoint("validation", False, "invalid issue")
        return False

    if response is None:
        logger.warning("No response received, proceeding with delivery")
        rescue_state.add_checkpoint("validation", True, "no response - auto-approved")
        return True

    response_lower = response.lower().strip()

    # BUG-085 fix: More robust fix request parsing
    # Handle both "fix: issue" and "fix issue"
    if response_lower.startswith("fix"):
        # Handle fix request - trigger patch workflow
        if ":" in response_lower:
            fix_request = response_lower.split(":", 1)[1].strip()
        else:
            fix_request = response_lower.replace("fix", "", 1).strip()
        # Ensure we have an actual fix request
        if not fix_request:
            fix_request = "unspecified fix"
        rescue_state.add_checkpoint("validation", False, f"fix requested: {fix_request}")
        logger.info(f"Fix requested: {fix_request}")

        # Create and implement patch for the fix request
        from adw_modules.workflow_ops import create_and_implement_patch

        patch_file, patch_response = create_and_implement_patch(
            adw_id=adw_id,
            review_change_request=f"Fix request from validation checkpoint: {fix_request}",
            logger=logger,
            agent_name_planner="rescue_patch_planner",
            agent_name_implementor="rescue_patch_implementor",
            working_dir=worktree_path,
        )

        if not patch_response.success:
            logger.error(f"Failed to implement fix: {patch_response.output}")
            rescue_state.add_learning(f"Fix request failed: {fix_request}")
            # Continue to delivery anyway - user can iterate
        else:
            logger.info(f"Fix implemented via patch: {patch_file}")
            rescue_state.add_learning(f"Fix applied: {fix_request}")

        return True

    # approve or ship partial
    notes = "approved" if response_lower == "approve" else "shipped partial"
    rescue_state.add_checkpoint("validation", True, notes)
    logger.info(f"Validation checkpoint: {notes}")
    return True


def execute_rescue_workflow(
    adw_id: str,
    state: ADWState,
    rescue_state: RescueState,
    worktree_path: str,
    logger: logging.Logger,
    skip_checkpoints: bool = False,
) -> bool:
    """Execute the complete rescue workflow."""

    # Phase 1: Discovery
    if not rescue_state.data.discovery.discovery_complete:
        logger.info("=== Phase 1: Discovery ===")
        if not execute_discovery_phase(adw_id, rescue_state, worktree_path, logger):
            return False

        # Check Not Recommended gate
        if rescue_state.data.discovery.red_flags.estimated_difficulty == "not_recommended":
            return handle_not_recommended(adw_id, rescue_state, state, logger)

    # Phase 2: Triage
    if not rescue_state.data.triage.triage_complete:
        logger.info("=== Phase 2: Triage ===")
        if not execute_triage_phase(adw_id, rescue_state, worktree_path, logger):
            return False

        # Human checkpoint
        if not await_triage_checkpoint(adw_id, rescue_state, state, worktree_path, logger, skip_checkpoints):
            return False

    # Phase 3: Execution
    if not rescue_state.data.execution.execution_complete:
        logger.info("=== Phase 3: Execution ===")
        if not execute_rescue_tasks(adw_id, rescue_state, worktree_path, logger):
            return False

    # Phase 4: Validation
    if not rescue_state.data.validation.validation_complete:
        logger.info("=== Phase 4: Validation ===")
        if not execute_validation_phase(adw_id, rescue_state, worktree_path, logger):
            return False

        # Human checkpoint
        if not await_validation_checkpoint(adw_id, rescue_state, state, worktree_path, logger, skip_checkpoints):
            return False

    # Phase 5: Delivery
    logger.info("=== Phase 5: Delivery ===")
    return execute_delivery_phase(adw_id, state, rescue_state, worktree_path, logger)


def main():
    parser = argparse.ArgumentParser(description="Vibe Code Rescue Workflow")
    parser.add_argument("issue_number", help="GitHub issue number")
    parser.add_argument("source_path", help="Path to source project (local or git URL)")
    parser.add_argument("adw_id", nargs="?", help="Optional ADW ID to resume")
    parser.add_argument("--resume", action="store_true", help="Resume from last checkpoint")
    parser.add_argument("--skip-checkpoints", action="store_true", help="Skip human checkpoints")
    args = parser.parse_args()

    # Setup ADW ID
    adw_id = args.adw_id or make_adw_id()
    logger = setup_logger(adw_id, "rescue")
    logger.info(f"Starting Vibe Code Rescue: ADW {adw_id}")
    logger.info(f"Source project: {args.source_path}")

    # Initialize ADW state
    state = ADWState.load(adw_id) or ADWState(adw_id)
    state.update(
        adw_id=adw_id,
        issue_number=args.issue_number,
        workflow_stage="rescue_discovery"
    )
    state.append_adw_id("adw_rescue_project_iso")

    try:
        # Check if resuming with existing worktree
        worktree_path = state.get("worktree_path")
        branch_name = state.get("branch_name")

        if args.resume and worktree_path:
            # Validate existing worktree still exists
            is_valid, worktree_error = validate_worktree(adw_id, state)
            if not is_valid:
                logger.error(f"Cannot resume: {worktree_error}")
                logger.info("Worktree was deleted or corrupted. Starting fresh...")
                worktree_path = None
                branch_name = None

        if not worktree_path:
            # Generate branch name for rescue workflow
            branch_name = f"rescue-issue-{args.issue_number}-adw-{adw_id}"
            logger.info(f"Generated branch name: {branch_name}")

            # Create worktree
            logger.info("Creating isolated worktree...")
            worktree_path, actual_branch, worktree_error = create_worktree(
                adw_id=adw_id,
                branch_name=branch_name,
                logger=logger,
            )

            if worktree_error:
                raise RuntimeError(f"Failed to create worktree: {worktree_error}")

            # Reconcile branch name with what the worktree actually has
            if actual_branch and actual_branch != branch_name:
                logger.warning(f"Worktree branch mismatch: state={branch_name}, actual={actual_branch}. Using actual.")
                branch_name = actual_branch

            state.update(worktree_path=worktree_path, branch_name=branch_name)

            # Setup environment
            backend_port, frontend_port = get_ports_for_adw(adw_id)
            state.update(backend_port=backend_port, frontend_port=frontend_port)

            db_name, backend_port, frontend_port, db_error = setup_worktree_environment(
                worktree_path, backend_port, frontend_port, adw_id, logger
            )
            if db_error:
                # BUG-077 fix: Clean up worktree and release ports on environment setup failure
                # Review fix #9: Pass actual ports to remove_worktree to avoid
                # releasing wrong reservation files
                logger.warning(f"Environment setup failed, cleaning up worktree: {worktree_path}")
                try:
                    remove_worktree(
                        adw_id, logger,
                        backend_port=backend_port,
                        frontend_port=frontend_port,
                    )
                except Exception as cleanup_err:
                    logger.warning(f"Failed to remove worktree during cleanup: {cleanup_err}")
                raise RuntimeError(f"Failed to setup environment: {db_error}")

            # Update state with actual ports (may differ if originals were unavailable)
            state.update(database_name=db_name, backend_port=backend_port, frontend_port=frontend_port)
            try:
                state.save("rescue_worktree_created")
            except Exception as e:
                logger.error(f"Failed to save state: {e}")
                raise

            # Create rescue directories
            create_rescue_directories(worktree_path, logger)

            # Copy source project
            source_dest = setup_source_project(args.source_path, worktree_path, logger)
        else:
            logger.info(f"Using existing worktree at: {worktree_path}")
            # Source should already be in place
            source_dest = os.path.join(worktree_path, "source")
            if not os.path.exists(source_dest):
                # Need to re-copy source
                source_dest = setup_source_project(args.source_path, worktree_path, logger)

        # Initialize or load rescue state
        if args.resume:
            existing_rescue = RescueState.load(adw_id, logger)
            if existing_rescue:
                rescue_state = existing_rescue
                # Validate source path still matches
                if existing_rescue.data.source_project_path != source_dest:
                    logger.warning(
                        f"Source path changed from {existing_rescue.data.source_project_path} to {source_dest}"
                    )
                    existing_rescue.data.source_project_path = source_dest
                logger.info(f"Resuming from phase: {rescue_state.data.current_phase}")
            else:
                logger.warning("No existing rescue state found, starting fresh")
                rescue_state = RescueState(adw_id, source_dest)
        else:
            rescue_state = RescueState(adw_id, source_dest)

        try:
            rescue_state.save()
        except Exception as e:
            logger.error(f"Failed to save rescue state: {e}")
            raise

        # Execute workflow
        success = execute_rescue_workflow(
            adw_id=adw_id,
            state=state,
            rescue_state=rescue_state,
            worktree_path=worktree_path,
            logger=logger,
            skip_checkpoints=args.skip_checkpoints,
        )

        if success:
            logger.info("Rescue workflow completed successfully")
            state.update(workflow_stage="rescue_completed")
        else:
            logger.error("Rescue workflow failed")
            state.update(workflow_stage="rescue_failed")

        state.save("rescue_completed")

        # Print summary
        summary = rescue_state.get_summary()
        logger.info(f"Summary: {json.dumps(summary, indent=2)}")

        return 0 if success else 1

    except Exception as e:
        logger.exception(f"Rescue workflow error: {e}")
        state.update(workflow_stage="rescue_error")
        state.save("rescue_error")
        return 1


if __name__ == "__main__":
    sys.exit(main())
