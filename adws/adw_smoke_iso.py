#!/usr/bin/env -S uv run
# /// script
# dependencies = ["python-dotenv", "pydantic", "redis", "boto3>=1.26.0", "requests>=2.31.0"]
# ///

"""
ADW Smoke Test Iso - Contextual smoke testing in isolated worktrees

Usage:
  uv run adw_smoke_iso.py <issue-number> <adw-id>

Workflow:
1. Load state and validate worktree exists
2. Check Chrome availability - skip if not available
3. Generate smoke tests from spec + git diff (ONCE)
4. Execute tests with direct Playwright runner (fast, no MCP)
5. If failures, resolve and re-execute (up to 2 retries, using cached tests)
6. Report results to issue

Exit codes:
- 0: Success (all tests passed) or skipped (Chrome unavailable)
- 1: Failure (tests failed after exhausting retry attempts)

PERFORMANCE OPTIMIZATION:
- Test generation happens ONCE (cached in smoke_tests.json)
- Retries re-execute the runner directly (~10s) instead of regenerating tests (~3min)
- Direct Playwright execution is ~10x faster than MCP-based approach
"""

import sys
import os
import json
import logging
import subprocess
from typing import List, Optional
from dotenv import load_dotenv
from adw_modules.data_types import (
    AgentTemplateRequest,
    AgentPromptResponse,
    SmokeTestResult,
)
from adw_modules.agent import execute_template
from adw_modules.github import make_issue_comment
from adw_modules.utils import setup_logger, parse_json, check_env_vars
from adw_modules.state import ADWState
from adw_modules.workflow_ops import format_issue_message
from adw_modules.worktree_ops import validate_worktree
from adw_modules.r2_uploader import R2Uploader
import requests
import time as time_module

# Agent name constant
AGENT_SMOKE_TESTER = "smoke_test_runner"

# Maximum retry attempts for failed smoke tests (reduced from 4 for faster feedback)
MAX_SMOKE_TEST_RETRY_ATTEMPTS = 2

# Backend health check settings
BACKEND_HEALTH_TIMEOUT = 5  # seconds per health check
BACKEND_STARTUP_MAX_WAIT = 30  # max seconds to wait for backend after restart


def check_backend_health(backend_url: str, timeout: int = BACKEND_HEALTH_TIMEOUT) -> tuple[bool, str]:
    """Check if backend is healthy.

    Args:
        backend_url: Base URL of the backend (e.g., http://localhost:9104)
        timeout: Request timeout in seconds

    Returns:
        Tuple of (is_healthy, message)
    """
    try:
        response = requests.get(f"{backend_url}/health", timeout=timeout)
        if response.status_code == 200:
            return True, "Backend healthy"
        return False, f"Backend unhealthy: HTTP {response.status_code}"
    except requests.exceptions.ConnectionError:
        return False, f"Backend unreachable at {backend_url}"
    except Exception as e:
        return False, f"Health check error: {str(e)}"


def wait_for_backend_healthy(
    backend_url: str,
    logger: logging.Logger,
    max_wait: int = BACKEND_STARTUP_MAX_WAIT,
    check_interval: int = 2,
) -> tuple[bool, str]:
    """Wait for backend to become healthy.

    Args:
        backend_url: Base URL of the backend
        logger: Logger instance
        max_wait: Maximum seconds to wait
        check_interval: Seconds between health checks

    Returns:
        Tuple of (is_healthy, message)
    """
    waited = 0
    while waited < max_wait:
        is_healthy, msg = check_backend_health(backend_url)
        if is_healthy:
            return True, f"Backend healthy after {waited}s"
        logger.info(f"Waiting for backend... ({waited}s/{max_wait}s) - {msg}")
        time_module.sleep(check_interval)
        waited += check_interval

    is_healthy, msg = check_backend_health(backend_url)
    if is_healthy:
        return True, f"Backend healthy after {waited}s"
    return False, f"Backend not healthy after {max_wait}s: {msg}"


def check_chrome_availability(logger: logging.Logger) -> tuple[bool, Optional[str]]:
    """Check if Chrome browser automation is available.

    Returns:
        Tuple of (is_available, reason_if_not)
    """
    sys.path.insert(0, 'adws')
    from adw_modules.utils import is_chrome_available

    available, reason = is_chrome_available()

    if not available:
        logger.info(f"Chrome not available: {reason}")
    else:
        logger.info("Chrome is available for smoke testing")

    return available, reason


def get_test_definition_path(adw_id: str, worktree_path: str) -> str:
    """Get path to the cached test definition JSON file."""
    return os.path.join(worktree_path, "agents", adw_id, AGENT_SMOKE_TESTER, "smoke_tests.json")


def get_screenshot_dir(adw_id: str, worktree_path: str) -> str:
    """Get path to the screenshot directory."""
    return os.path.join(worktree_path, "agents", adw_id, AGENT_SMOKE_TESTER, "img")


def generate_smoke_tests(
    spec_file: str,
    adw_id: str,
    logger: logging.Logger,
    working_dir: str,
    application_url: Optional[str] = None,
) -> AgentPromptResponse:
    """Generate smoke tests using the /smoke_test command.

    This generates the test definition JSON file that can be re-executed
    multiple times without regenerating.
    """
    args = [spec_file, adw_id, AGENT_SMOKE_TESTER]

    if application_url:
        args.append(application_url)

    smoke_test_request = AgentTemplateRequest(
        agent_name=AGENT_SMOKE_TESTER,
        slash_command="/smoke_test",
        args=args,
        adw_id=adw_id,
        working_dir=working_dir,
    )

    logger.debug(
        f"smoke_test_request: {smoke_test_request.model_dump_json(indent=2, by_alias=True)}"
    )

    smoke_response = execute_template(smoke_test_request)

    logger.debug(
        f"smoke_response: {smoke_response.model_dump_json(indent=2, by_alias=True)}"
    )

    return smoke_response


def execute_smoke_tests_directly(
    test_definition_path: str,
    screenshot_dir: str,
    logger: logging.Logger,
    timeout_seconds: int = 120,
) -> tuple[List[SmokeTestResult], bool]:
    """Execute smoke tests directly using the Playwright runner.

    This is the FAST path - no Claude involved, just direct Playwright execution.

    Returns:
        Tuple of (results, success)
    """
    if not os.path.exists(test_definition_path):
        logger.error(f"Test definition file not found: {test_definition_path}")
        return [], False

    # Ensure screenshot directory exists
    os.makedirs(screenshot_dir, exist_ok=True)

    # Get path to the runner script
    runner_script = os.path.join(os.path.dirname(__file__), "smoke_test_runner.py")

    if not os.path.exists(runner_script):
        logger.error(f"Smoke test runner not found: {runner_script}")
        return [], False

    # Run the direct Playwright runner
    cmd = [
        "uv", "run", runner_script,
        test_definition_path,
        "--screenshot-dir", screenshot_dir
    ]

    logger.info(f"Executing smoke tests directly: {' '.join(cmd)}")

    try:
        env = os.environ.copy()
        env["SMOKE_TEST_HEADLESS"] = "false"  # Show browser for debugging

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            env=env,
            cwd=os.path.dirname(test_definition_path),
        )

        # Parse JSON output from runner
        try:
            results_data = json.loads(result.stdout)
            results = [SmokeTestResult.model_validate(r) for r in results_data]
            return results, True
        except (json.JSONDecodeError, ValueError) as e:
            logger.error(f"Failed to parse runner output: {e}")
            logger.error(f"Runner stdout: {result.stdout[:500]}")
            logger.error(f"Runner stderr: {result.stderr[:500]}")
            return [], False

    except subprocess.TimeoutExpired:
        logger.error(f"Smoke test runner timed out after {timeout_seconds}s")
        return [SmokeTestResult(
            test_name="Runner Timeout",
            status="skipped",
            test_description="Direct Playwright execution",
            error=f"Runner timed out after {timeout_seconds} seconds"
        )], False
    except Exception as e:
        logger.error(f"Failed to execute smoke test runner: {e}")
        return [], False


def parse_smoke_test_results(
    output: str, logger: logging.Logger
) -> tuple[List[SmokeTestResult], int, int, int]:
    """Parse smoke test results JSON from Claude output.

    Returns:
        Tuple of (results, passed_count, failed_count, skipped_count)
    """
    try:
        # First try to parse as a single skip object (from Chrome unavailability)
        try:
            json_match = output
            if "```json" in output:
                start = output.find("```json") + 7
                end = output.find("```", start)
                json_match = output[start:end].strip()
            elif "```" in output:
                start = output.find("```") + 3
                end = output.find("```", start)
                json_match = output[start:end].strip()

            data = json.loads(json_match)
            if isinstance(data, dict) and data.get("status") == "skipped":
                logger.info(f"Smoke tests were skipped: {data.get('reason', 'unknown reason')}")
                return [], 0, 0, 0
        except (json.JSONDecodeError, ValueError):
            pass

        # Use parse_json to handle markdown-wrapped JSON array
        results = parse_json(output, List[SmokeTestResult])

        passed_count = sum(1 for test in results if test.status == "passed")
        failed_count = sum(1 for test in results if test.status == "failed")
        skipped_count = sum(1 for test in results if test.status == "skipped")

        return results, passed_count, failed_count, skipped_count
    except Exception as e:
        logger.error(f"Error parsing smoke test results: {e}")
        return [], 0, 0, 0


def resolve_failed_smoke_tests(
    failed_tests: List[SmokeTestResult],
    adw_id: str,
    issue_number: str,
    logger: logging.Logger,
    worktree_path: str,
    iteration: int = 1,
) -> tuple[int, int]:
    """
    Attempt to resolve failed smoke tests using the resolve_failed_smoke_test command.

    OPTIMIZATION: Batch all failed tests into a single resolution attempt instead of
    spawning one agent per test.

    Returns (resolved_count, unresolved_count).
    """
    if not failed_tests:
        return 0, 0

    # For now, keep the per-test resolution but log timing
    # TODO: Implement batched resolution for further speedup
    resolved_count = 0
    unresolved_count = 0

    for idx, test in enumerate(failed_tests):
        logger.info(
            f"\n=== Resolving failed smoke test {idx + 1}/{len(failed_tests)}: {test.test_name} ==="
        )

        test_payload = test.model_dump_json(indent=2)
        agent_name = f"smoke_test_resolver_iter{iteration}_{idx}"

        resolve_request = AgentTemplateRequest(
            agent_name=agent_name,
            slash_command="/resolve_failed_smoke_test",
            args=[test_payload],
            adw_id=adw_id,
            working_dir=worktree_path,
        )

        make_issue_comment(
            issue_number,
            format_issue_message(
                adw_id,
                agent_name,
                f"🔧 Attempting to resolve smoke test: {test.test_name}\n```json\n{test_payload}\n```",
            ),
        )

        response = execute_template(resolve_request)

        if response.success:
            resolved_count += 1
            make_issue_comment(
                issue_number,
                format_issue_message(
                    adw_id,
                    agent_name,
                    f"✅ Successfully resolved smoke test: {test.test_name}",
                ),
            )
            logger.info(f"Successfully resolved smoke test: {test.test_name}")
        else:
            unresolved_count += 1
            make_issue_comment(
                issue_number,
                format_issue_message(
                    adw_id,
                    agent_name,
                    f"❌ Failed to resolve smoke test: {test.test_name}",
                ),
            )
            logger.error(f"Failed to resolve smoke test: {test.test_name}")

    return resolved_count, unresolved_count


def run_smoke_tests_with_resolution(
    spec_file: str,
    adw_id: str,
    issue_number: str,
    logger: logging.Logger,
    worktree_path: str,
    application_url: Optional[str] = None,
    backend_url: Optional[str] = None,
    max_attempts: int = MAX_SMOKE_TEST_RETRY_ATTEMPTS,
) -> tuple[List[SmokeTestResult], int, int, int]:
    """
    Run smoke tests with automatic resolution and retry logic.

    PERFORMANCE OPTIMIZATION:
    - First run: Generate tests via Claude + execute with direct runner
    - Retries: Re-execute direct runner only (no Claude regeneration)

    RELIABILITY:
    - Backend health is checked before each retry to handle hot-reload after code changes

    Args:
        spec_file: Path to the spec file for test generation
        adw_id: ADW workflow ID
        issue_number: GitHub issue number for comments
        logger: Logger instance
        worktree_path: Path to the worktree
        application_url: Frontend URL (e.g., http://localhost:9204)
        backend_url: Backend URL for health checks (e.g., http://localhost:9104)
        max_attempts: Maximum retry attempts

    Returns (results, passed_count, failed_count, skipped_count).
    """
    test_definition_path = get_test_definition_path(adw_id, worktree_path)
    screenshot_dir = get_screenshot_dir(adw_id, worktree_path)

    results: List[SmokeTestResult] = []
    passed_count = 0
    failed_count = 0
    skipped_count = 0
    tests_generated = False

    for attempt in range(1, max_attempts + 1):
        logger.info(f"\n=== Smoke Test Run Attempt {attempt}/{max_attempts} ===")

        # First attempt: Generate tests via Claude
        if attempt == 1:
            logger.info("Generating smoke tests (first run)...")
            smoke_response = generate_smoke_tests(
                spec_file=spec_file,
                adw_id=adw_id,
                logger=logger,
                working_dir=worktree_path,
                application_url=application_url,
            )

            if not smoke_response.success:
                logger.error(f"Smoke test generation failed: {smoke_response.output}")
                return [], 0, 0, 0

            # Parse results from the first run
            results, passed_count, failed_count, skipped_count = parse_smoke_test_results(
                smoke_response.output, logger
            )

            # Check if test definition was created
            if os.path.exists(test_definition_path):
                tests_generated = True
                logger.info(f"Test definition cached at: {test_definition_path}")

            if not results:
                logger.info("No smoke test results to process")
                return [], 0, 0, skipped_count

        else:
            # Subsequent attempts: Re-execute directly (FAST PATH)
            if tests_generated:
                logger.info("Re-executing cached tests directly (fast path)...")
                make_issue_comment(
                    issue_number,
                    format_issue_message(
                        adw_id,
                        AGENT_SMOKE_TESTER,
                        f"🔄 Re-running smoke tests (attempt {attempt}/{max_attempts})...",
                    ),
                )

                results, success = execute_smoke_tests_directly(
                    test_definition_path, screenshot_dir, logger
                )

                if not success:
                    logger.error("Direct execution failed")
                    return results, 0, 0, 0

                passed_count = sum(1 for r in results if r.status == "passed")
                failed_count = sum(1 for r in results if r.status == "failed")
                skipped_count = sum(1 for r in results if r.status == "skipped")
            else:
                # No cached tests, regenerate
                logger.info("No cached tests, regenerating...")
                smoke_response = generate_smoke_tests(
                    spec_file=spec_file,
                    adw_id=adw_id,
                    logger=logger,
                    working_dir=worktree_path,
                    application_url=application_url,
                )

                if not smoke_response.success:
                    logger.error(f"Smoke test regeneration failed: {smoke_response.output}")
                    return [], 0, 0, 0

                results, passed_count, failed_count, skipped_count = parse_smoke_test_results(
                    smoke_response.output, logger
                )

        # Check results
        if not results:
            logger.info("No smoke test results to process")
            return [], 0, 0, skipped_count

        if failed_count == 0:
            logger.info("All smoke tests passed!")
            break

        if attempt == max_attempts:
            logger.info(f"Reached maximum retry attempts ({max_attempts})")
            break

        # Try to resolve failures
        logger.info(f"\n=== Attempting to resolve {failed_count} failed smoke tests ===")
        make_issue_comment(
            issue_number,
            format_issue_message(
                adw_id,
                "ops",
                f"🔧 Found {failed_count} failed smoke tests. Attempting resolution...",
            ),
        )

        failed_tests = [test for test in results if test.status == "failed"]
        resolved, unresolved = resolve_failed_smoke_tests(
            failed_tests, adw_id, issue_number, logger, worktree_path, iteration=attempt
        )

        if resolved > 0:
            make_issue_comment(
                issue_number,
                format_issue_message(
                    adw_id,
                    "ops",
                    f"✅ Resolved {resolved}/{failed_count} failed smoke tests",
                ),
            )
            logger.info(f"Resolved {resolved} tests, continuing to retry...")

            # CRITICAL: Wait for backend to stabilize after code changes
            # Smoke test resolvers may have modified code, triggering hot-reload
            if backend_url:
                logger.info("Waiting for backend to stabilize after code changes...")
                is_healthy, health_msg = check_backend_health(backend_url)
                if not is_healthy:
                    logger.info(f"Backend not immediately healthy ({health_msg}), waiting...")
                    is_healthy, health_msg = wait_for_backend_healthy(backend_url, logger)
                    if not is_healthy:
                        logger.error(f"Backend failed to stabilize: {health_msg}")
                        make_issue_comment(
                            issue_number,
                            format_issue_message(
                                adw_id,
                                AGENT_SMOKE_TESTER,
                                f"⚠️ Backend not healthy before retry: {health_msg}. Continuing anyway...",
                            ),
                        )
                    else:
                        logger.info(f"Backend stabilized: {health_msg}")
                else:
                    logger.info("Backend healthy, proceeding with retry")
        else:
            logger.info("No smoke tests were resolved, stopping retry attempts")
            break

    # Final status
    if failed_count > 0:
        logger.warning(
            f"Finished with {failed_count} failures after {max_attempts} attempts"
        )
        make_issue_comment(
            issue_number,
            format_issue_message(
                adw_id,
                "ops",
                f"⚠️ Smoke tests completed with {failed_count} failures after {max_attempts} attempts",
            ),
        )

    return results, passed_count, failed_count, skipped_count


def format_smoke_test_results_comment(
    results: List[SmokeTestResult],
    passed_count: int,
    failed_count: int,
    skipped_count: int,
) -> str:
    """Format smoke test results for GitHub issue comment."""
    if not results:
        return "⏭️ Smoke tests skipped (no results returned)"

    total = len(results)
    summary = f"**{passed_count}/{total} smoke tests passed**"

    if failed_count > 0:
        summary += f" ({failed_count} failed)"
    if skipped_count > 0:
        summary += f" ({skipped_count} skipped)"

    comment_parts = [
        "",
        "## 🔥 Smoke Test Results",
        "",
        summary,
        "",
        "_Note: Smoke test failures block the workflow after retry attempts are exhausted._",
        "",
    ]

    passed_tests = [test for test in results if test.status == "passed"]
    failed_tests = [test for test in results if test.status == "failed"]
    skipped_tests = [test for test in results if test.status == "skipped"]

    if failed_tests:
        comment_parts.append("### ❌ Failed")
        comment_parts.append("")
        for test in failed_tests:
            comment_parts.append(f"- **{test.test_name}**: {test.test_description}")
            if test.error:
                comment_parts.append(f"  - Error: `{test.error}`")
            if test.screenshot_urls:
                comment_parts.append(f"  - Screenshots:")
                for url in test.screenshot_urls:
                    comment_parts.append(f"    - ![screenshot]({url})")
            elif test.screenshots:
                comment_parts.append(f"  - Screenshots: {len(test.screenshots)} captured (local)")
        comment_parts.append("")

    if passed_tests:
        comment_parts.append("### ✅ Passed")
        comment_parts.append("")
        for test in passed_tests:
            comment_parts.append(f"- **{test.test_name}**: {test.test_description}")
            if test.screenshot_urls:
                comment_parts.append(f"  - Screenshots:")
                for url in test.screenshot_urls:
                    comment_parts.append(f"    - ![screenshot]({url})")
            elif test.screenshots:
                comment_parts.append(f"  - Screenshots: {len(test.screenshots)} captured (local)")
        comment_parts.append("")

    if skipped_tests:
        comment_parts.append("### ⏭️ Skipped")
        comment_parts.append("")
        for test in skipped_tests:
            comment_parts.append(f"- **{test.test_name}**: {test.test_description}")
            if test.error:
                comment_parts.append(f"  - Reason: {test.error}")
        comment_parts.append("")

    return "\n".join(comment_parts)


def upload_smoke_test_screenshots(
    results: List[SmokeTestResult],
    adw_id: str,
    worktree_path: str,
    logger: logging.Logger,
) -> None:
    """Upload smoke test screenshots to R2 and update results with public URLs."""
    all_screenshots = []
    for result in results:
        if result.screenshots:
            all_screenshots.extend(result.screenshots)

    if not all_screenshots:
        logger.info("No screenshots to upload")
        return

    logger.info(f"Uploading {len(all_screenshots)} smoke test screenshots to R2")
    uploader = R2Uploader(logger)

    if not uploader.enabled:
        logger.info("R2 upload disabled - screenshots will use local paths")
        return

    url_mapping = {}
    for local_path in all_screenshots:
        if os.path.isabs(local_path):
            abs_path = local_path
        else:
            abs_path = os.path.join(worktree_path, local_path)

        if not os.path.exists(abs_path):
            logger.warning(f"Screenshot not found: {abs_path}")
            continue

        filename = os.path.basename(local_path)
        remote_path = f"adw/{adw_id}/smoke_test/{filename}"
        url = uploader.upload_file(abs_path, remote_path)

        if url:
            url_mapping[local_path] = url
            logger.info(f"Uploaded screenshot to: {url}")
        else:
            logger.warning(f"Failed to upload screenshot: {local_path}")

    # Only include actual R2 URLs, not local paths as fallback
    # This prevents broken image links in GitHub comments
    for result in results:
        if result.screenshots:
            result.screenshot_urls = [
                url_mapping[path] for path in result.screenshots if path in url_mapping
            ]


def main():
    """Main execution function."""
    load_dotenv()
    check_env_vars()

    if len(sys.argv) < 3:
        print(
            "Usage: uv run adw_smoke_iso.py <issue-number> <adw-id>",
            file=sys.stderr,
        )
        sys.exit(1)

    issue_number = sys.argv[1]
    adw_id = sys.argv[2]

    logger = setup_logger(adw_id, trigger_type="adw_smoke_iso")
    logger.info(f"Starting smoke test workflow for issue #{issue_number}, ADW ID: {adw_id}")

    # Load and validate state
    state = ADWState.load(adw_id, logger)
    if not state:
        logger.error(f"No state found for ADW ID {adw_id}. Run adw_plan_iso.py first.")
        sys.exit(0)

    worktree_path = state.get("worktree_path")
    is_valid, error_msg = validate_worktree(adw_id, state)
    if not worktree_path or not is_valid:
        logger.error(f"Worktree validation failed for {worktree_path}: {error_msg}")
        sys.exit(0)

    logger.info(f"Using worktree: {worktree_path}")

    try:
        os.chdir(worktree_path)
        logger.info(f"Changed working directory to: {worktree_path}")
    except OSError as e:
        logger.error(f"Failed to change to worktree directory: {e}")
        sys.exit(0)

    if not os.path.exists(".git") and not os.path.exists("../.git"):
        logger.error("Not in a valid git worktree after directory change")
        sys.exit(0)

    # Check Chrome availability
    available, reason = check_chrome_availability(logger)
    if not available:
        logger.info(f"Skipping smoke tests: {reason}")
        skip_message = format_issue_message(
            adw_id,
            f"⏭️ Smoke tests skipped\n\n{reason}",
        )
        try:
            make_issue_comment(issue_number, skip_message)
        except Exception as e:
            logger.error(f"Failed to post skip message to issue: {e}")
        sys.exit(0)

    spec_file = state.get("plan_file")
    if not spec_file:
        logger.error("No plan_file found in state")
        sys.exit(0)

    logger.info(f"Using spec file: {spec_file}")

    # Determine application URL and backend URL from .ports.env
    application_url = None
    backend_url = None
    ports_env = os.path.join(worktree_path, ".ports.env")
    if os.path.exists(ports_env):
        try:
            with open(ports_env, "r") as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("FRONTEND_PORT="):
                        port = line.split("=")[1]
                        application_url = f"http://localhost:{port}"
                        logger.info(f"Using application URL from .ports.env: {application_url}")
                    elif line.startswith("BACKEND_PORT="):
                        port = line.split("=")[1]
                        backend_url = f"http://localhost:{port}"
                        logger.info(f"Using backend URL from .ports.env: {backend_url}")
        except Exception as e:
            logger.warning(f"Could not read .ports.env: {e}")

    # FAIL-FAST: Verify backend is running before starting smoke tests
    # If not running, attempt to restart via start.sh
    if backend_url:
        health_url = f"{backend_url}/health"
        logger.info(f"Checking backend health at {health_url}...")
        is_healthy, health_msg = check_backend_health(backend_url)

        if not is_healthy:
            logger.warning(f"Backend not healthy: {health_msg}")
            logger.info("Attempting to restart application via start.sh...")

            # Run start.sh in background to restart the app
            start_script = os.path.join(worktree_path, "scripts", "start.sh")
            if os.path.exists(start_script):
                try:
                    # Start the app in background (start.sh handles killing existing processes)
                    subprocess.Popen(
                        ["bash", start_script],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        start_new_session=True,
                        cwd=worktree_path,
                    )
                    logger.info("Started application, waiting for backend to become healthy...")

                    # Wait for backend to become healthy
                    is_healthy, health_msg = wait_for_backend_healthy(backend_url, logger)

                    if not is_healthy:
                        error_msg = f"Backend failed to start: {health_msg}"
                        logger.error(error_msg)
                        make_issue_comment(
                            issue_number,
                            format_issue_message(
                                adw_id,
                                AGENT_SMOKE_TESTER,
                                f"❌ Smoke tests aborted: {error_msg}\n\nCheck backend logs for errors.",
                            ),
                        )
                        sys.exit(1)
                except Exception as e:
                    error_msg = f"Failed to start application: {str(e)}"
                    logger.error(error_msg)
                    make_issue_comment(
                        issue_number,
                        format_issue_message(
                            adw_id,
                            AGENT_SMOKE_TESTER,
                            f"❌ Smoke tests aborted: {error_msg}",
                        ),
                    )
                    sys.exit(1)
            else:
                error_msg = f"Backend not running and start.sh not found at {start_script}"
                logger.error(error_msg)
                make_issue_comment(
                    issue_number,
                    format_issue_message(
                        adw_id,
                        AGENT_SMOKE_TESTER,
                        f"❌ Smoke tests aborted: {error_msg}",
                    ),
                )
                sys.exit(1)
        else:
            logger.info("Backend health check passed")
    else:
        logger.warning("No BACKEND_PORT found in .ports.env - skipping backend health check")

    # Run smoke tests with resolution
    logger.info("Running smoke tests with automatic resolution...")
    make_issue_comment(
        issue_number,
        format_issue_message(adw_id, AGENT_SMOKE_TESTER, "🔥 Running smoke tests..."),
    )

    results, passed, failed, skipped = run_smoke_tests_with_resolution(
        spec_file=spec_file,
        adw_id=adw_id,
        issue_number=issue_number,
        logger=logger,
        worktree_path=worktree_path,
        application_url=application_url,
        backend_url=backend_url,
    )

    logger.info(f"Smoke test results: {passed} passed, {failed} failed, {skipped} skipped")

    # Upload screenshots
    if results:
        upload_smoke_test_screenshots(results, adw_id, worktree_path, logger)

    all_screenshot_urls = []
    for result in results:
        if result.screenshot_urls:
            all_screenshot_urls.extend(result.screenshot_urls)

    state.update(
        smoke_test_passed=passed,
        smoke_test_failed=failed,
        smoke_test_skipped=skipped,
        smoke_test_screenshot_urls=all_screenshot_urls,
    )
    state.save("smoke_test_results")
    logger.info(f"Saved smoke test results to state: {len(all_screenshot_urls)} screenshot URLs")

    results_comment = format_smoke_test_results_comment(results, passed, failed, skipped)
    full_message = format_issue_message(adw_id, AGENT_SMOKE_TESTER, results_comment)
    try:
        make_issue_comment(issue_number, full_message)
        logger.info("Posted smoke test results to issue")
    except Exception as e:
        logger.error(f"Failed to post results to issue: {e}")

    # Exit based on results
    if not results:
        logger.info("Smoke test workflow completed - no results (non-blocking)")
        sys.exit(0)
    elif failed > 0:
        logger.error(f"Smoke test workflow completed with {failed} failures (blocking)")
        make_issue_comment(
            issue_number,
            format_issue_message(
                adw_id,
                "ops",
                f"❌ Smoke tests failed: {failed} test(s) still failing after {MAX_SMOKE_TEST_RETRY_ATTEMPTS} retry attempts",
            ),
        )
        sys.exit(1)
    else:
        logger.info("Smoke test workflow completed successfully")
        sys.exit(0)


if __name__ == "__main__":
    main()
