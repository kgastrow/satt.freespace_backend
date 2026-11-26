#!/usr/bin/env -S uv run
# /// script
# dependencies = ["playwright>=1.40.0", "pydantic>=2.0.0", "requests>=2.31.0"]
# ///

"""
Direct Playwright Smoke Test Runner

Executes smoke tests defined in a JSON file WITHOUT MCP round-trips.
This is ~10x faster than the MCP-based approach because all browser
actions run at native speed without waiting for Claude to decide each step.

Usage:
    uv run adws/smoke_test_runner.py <test_definition.json> [--screenshot-dir <dir>] [--log-file <file>]

Input JSON format:
{
    "application_url": "http://localhost:5173",
    "auth": {
        "access_token": "...",
        "refresh_token": "..."
    },
    "tests": [
        {
            "name": "Test Name",
            "description": "What this test verifies",
            "steps": [
                {"action": "navigate", "url": "/dashboard"},
                {"action": "waitForSelector", "selector": "[data-testid='export-btn']", "timeout": 5000},
                {"action": "screenshot", "name": "01_export_visible.png"},
                {"action": "click", "selector": "[data-testid='export-btn']"},
                {"action": "assertVisible", "selector": ".export-modal"},
                {"action": "screenshot", "name": "02_modal_open.png"}
            ]
        }
    ]
}

Output JSON format (to stdout):
[
    {
        "test_name": "Test Name",
        "status": "passed|failed|skipped",
        "test_description": "...",
        "screenshots": ["/path/to/screenshot.png"],
        "error": null or "error message"
    }
]
"""

import argparse
import json
import os
import sys
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any, Optional
from pydantic import BaseModel


class PlaywrightLogger:
    """Logger for Playwright commands and output."""

    def __init__(self, log_file: Optional[Path] = None):
        self.log_file = log_file
        self._file = None
        if log_file:
            log_file.parent.mkdir(parents=True, exist_ok=True)
            self._file = open(log_file, "w")
            self._write_header()

    def _write_header(self):
        """Write log file header."""
        if self._file:
            self._file.write("# Playwright Smoke Test Log\n")
            self._file.write(f"# Started: {datetime.now().isoformat()}\n")
            self._file.write(f"# {'=' * 60}\n\n")
            self._file.flush()

    def log(self, message: str, level: str = "INFO"):
        """Log a message to the log file."""
        if self._file:
            timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
            self._file.write(f"[{timestamp}] [{level}] {message}\n")
            self._file.flush()

    def log_command(self, action: str, details: dict):
        """Log a Playwright command being executed."""
        details_str = ", ".join(f"{k}={v!r}" for k, v in details.items() if v is not None)
        self.log(f"EXECUTE: {action}({details_str})", "CMD")

    def log_result(self, action: str, success: bool, duration_ms: float, error: Optional[str] = None):
        """Log the result of a Playwright command."""
        status = "OK" if success else "FAIL"
        msg = f"RESULT: {action} -> {status} ({duration_ms:.0f}ms)"
        if error:
            msg += f" - {error}"
        self.log(msg, "RESULT")

    def log_auth_verification(self, success: bool, current_url: str, details: str):
        """Log authentication verification result."""
        status = "PASSED" if success else "FAILED"
        self.log(f"AUTH VERIFICATION: {status}", "AUTH")
        self.log(f"  Current URL: {current_url}", "AUTH")
        self.log(f"  Details: {details}", "AUTH")

    def log_test_start(self, test_name: str, description: str):
        """Log the start of a test."""
        self.log(f"\n{'=' * 60}", "TEST")
        self.log(f"TEST START: {test_name}", "TEST")
        self.log(f"Description: {description}", "TEST")
        self.log(f"{'=' * 60}", "TEST")

    def log_test_end(self, test_name: str, status: str, error: Optional[str] = None):
        """Log the end of a test."""
        self.log(f"TEST END: {test_name} -> {status.upper()}", "TEST")
        if error:
            self.log(f"Error: {error}", "TEST")
        self.log("", "TEST")

    def close(self):
        """Close the log file."""
        if self._file:
            self.log(f"\n# Finished: {datetime.now().isoformat()}", "INFO")
            self._file.close()
            self._file = None


# Global logger instance
_logger: Optional[PlaywrightLogger] = None


def get_logger() -> PlaywrightLogger:
    """Get the global logger instance."""
    global _logger
    if _logger is None:
        _logger = PlaywrightLogger()
    return _logger


def set_logger(logger: PlaywrightLogger):
    """Set the global logger instance."""
    global _logger
    _logger = logger


class TestStep(BaseModel):
    """A single step in a smoke test."""
    action: str
    selector: Optional[str] = None
    url: Optional[str] = None
    name: Optional[str] = None  # For screenshots
    text: Optional[str] = None  # For fill/type actions
    timeout: int = 5000  # ms
    key: Optional[str] = None  # For keyboard actions


class SmokeTest(BaseModel):
    """Definition of a single smoke test."""
    name: str
    description: str
    steps: list[TestStep]


class AuthConfig(BaseModel):
    """Authentication configuration."""
    access_token: str
    refresh_token: str


class TestDefinition(BaseModel):
    """Complete test definition file."""
    application_url: str
    backend_url: Optional[str] = None  # Optional explicit backend URL; if not provided, derived from application_url
    auth: Optional[AuthConfig] = None
    tests: list[SmokeTest]


class TestResult(BaseModel):
    """Result of a single test execution."""
    test_name: str
    status: str  # passed, failed, skipped
    test_description: str
    screenshots: list[str] = []
    error: Optional[str] = None


def ensure_playwright_browsers():
    """Ensure Playwright browsers are installed.
    
    Note: When running via `uv run`, sys.executable points to an ephemeral
    environment. We must use `uv run --with playwright` for the install
    subprocess to have access to the playwright module.
    """
    try:
        # Check if chromium is available
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            # Try to launch - this will fail fast if not installed
            browser = p.chromium.launch(headless=True)
            browser.close()
        return True
    except Exception as e:
        # Install browsers - use uv to ensure playwright is available
        print(f"Chromium not available ({e}), installing...", file=sys.stderr)
        
        # Try uv-based install first (works when script is run via uv run)
        result = subprocess.run(
            ["uv", "run", "--with", "playwright", "python", "-m", "playwright", "install", "chromium"],
            capture_output=True,
            text=True
        )
        
        if result.returncode != 0:
            # Fallback to direct install (works if playwright is in PATH)
            print(f"uv install failed, trying direct install...", file=sys.stderr)
            result = subprocess.run(
                [sys.executable, "-m", "playwright", "install", "chromium"],
                capture_output=True,
                text=True
            )
        
        if result.returncode != 0:
            print(f"Failed to install Playwright browsers.", file=sys.stderr)
            print(f"stdout: {result.stdout}", file=sys.stderr)
            print(f"stderr: {result.stderr}", file=sys.stderr)
            print(f"Run manually: uv run --with playwright python -m playwright install chromium", file=sys.stderr)
            return False
        
        print("Playwright browsers installed successfully.", file=sys.stderr)
        return True


def verify_authentication(page: Any, screenshot_dir: Path) -> tuple[bool, str]:
    """
    Verify authentication succeeded by checking we're NOT on the login page.

    Returns:
        Tuple of (success, details_message)
    """
    import time

    current_url = page.url

    # Wait a moment for any redirects to complete
    time.sleep(0.5)
    current_url = page.url

    # Check 1: URL should not contain /login
    if "/login" in current_url.lower():
        return False, "URL contains /login - redirected to login page"

    # Check 2: Login form elements should NOT be visible
    login_indicators = [
        "input[name='email']",
        "input[name='password']",
        "button[type='submit']:has-text('Login')",
        "form:has(input[name='email'])",
    ]

    for selector in login_indicators:
        try:
            element = page.query_selector(selector)
            if element and element.is_visible():
                # Double-check we're actually on login page by checking for dashboard elements
                dashboard_element = page.query_selector("[data-sidebar='sidebar'], nav, [data-testid='dashboard']")
                if not dashboard_element or not dashboard_element.is_visible():
                    return False, f"Login form element visible: {selector}"
        except Exception:
            pass  # Element not found, which is good

    # Check 3: Look for authenticated UI elements (at least one should be present)
    auth_indicators = [
        "[data-sidebar='sidebar']",  # Sidebar present
        "[data-sidebar='menu']",     # Sidebar menu
        "nav",                        # Navigation
        "[data-testid='user-menu']", # User menu
        "[data-testid='dashboard']", # Dashboard content
    ]

    for selector in auth_indicators:
        try:
            element = page.query_selector(selector)
            if element and element.is_visible():
                return True, f"Authenticated UI element found: {selector}"
        except Exception:
            pass

    # If we didn't find definitive evidence either way, check URL more carefully
    # Being on a non-login page is a good sign
    if not any(x in current_url.lower() for x in ["/login", "/register", "/signup", "/auth"]):
        return True, f"Not on auth page, URL: {current_url}"

    return False, f"Could not verify authentication, URL: {current_url}"


def find_ports_env() -> Optional[Path]:
    """
    Find .ports.env by walking up the directory tree.

    The smoke test runner may execute from a subdirectory like:
    {worktree}/agents/{adw_id}/smoke_test_runner/

    But .ports.env is at the worktree root, so we need to search upward.
    """
    current = Path.cwd().resolve()

    # Walk up to 10 levels (should be more than enough)
    for _ in range(10):
        ports_env = current / ".ports.env"
        if ports_env.exists():
            return ports_env

        # Stop at filesystem root
        parent = current.parent
        if parent == current:
            break
        current = parent

    return None


def get_backend_url(definition: TestDefinition) -> Optional[str]:
    """
    Get backend URL for health checks and data seeding.

    Priority:
    1. Explicit backend_url in test definition
    2. Read BACKEND_PORT from .ports.env (searching up directory tree)
    3. Return None (caller should handle gracefully)

    Note: The frontend already knows the backend URL via VITE_API_URL.
    This is only needed for health checks and API calls from the test runner itself.
    """
    # Use explicit backend_url if provided
    if definition.backend_url:
        return definition.backend_url.rstrip('/')

    # Find .ports.env by walking up directory tree
    ports_env_path = find_ports_env()
    if ports_env_path:
        try:
            with open(ports_env_path) as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("BACKEND_PORT="):
                        port = line.split("=")[1]
                        return f"http://localhost:{port}"
        except Exception:
            pass

    # No backend URL found - return None
    return None


def check_backend_health(backend_url: str, timeout: int = 5) -> tuple[bool, str]:
    """
    Check if the backend is healthy and reachable.

    Args:
        backend_url: Base URL of the backend (e.g., http://localhost:9112)
        timeout: Request timeout in seconds

    Returns:
        Tuple of (is_healthy, message)
    """
    import requests

    health_url = f"{backend_url}/health"

    try:
        response = requests.get(health_url, timeout=timeout)
        if response.status_code == 200:
            return True, f"Backend healthy at {backend_url}"
        else:
            return False, f"Backend unhealthy: HTTP {response.status_code} from {health_url}"
    except requests.exceptions.ConnectionError:
        return False, f"Backend unreachable: Connection refused at {backend_url}. Is the backend running?"
    except requests.exceptions.Timeout:
        return False, f"Backend unreachable: Timeout connecting to {backend_url}"
    except Exception as e:
        return False, f"Backend health check failed: {str(e)}"


def seed_test_data(definition: TestDefinition) -> dict[str, bool]:
    """
    Seed test data before running smoke tests.

    Returns:
        Dictionary mapping data type to success status.
        Example: {"announcements": True} if announcements were seeded successfully.
    """
    logger = get_logger()
    seed_status = {}

    if not definition.auth or not definition.auth.access_token:
        logger.log("Skipping test data seeding (no auth token provided)", "SETUP")
        return seed_status

    # Get backend URL using the centralized helper
    api_url = get_backend_url(definition)
    if not api_url:
        logger.log("Skipping test data seeding (no backend URL found)", "SETUP")
        return seed_status

    logger.log(f"Seeding test data via API: {api_url}", "SETUP")

    # Seed announcement data
    try:
        import requests
        from datetime import timedelta

        url = f"{api_url}/api/v1/announcements"
        headers = {
            "Authorization": f"Bearer {definition.auth.access_token}",
            "Content-Type": "application/json",
        }

        # Create announcement that's active now and for the next 24 hours
        now = datetime.utcnow()
        start_time = (now - timedelta(hours=1)).isoformat() + "Z"
        end_time = (now + timedelta(hours=24)).isoformat() + "Z"

        payload = {
            "title": "Test Announcement",
            "body": "This is a test announcement for smoke testing. It verifies that the announcement banner renders correctly.",
            "priority": "normal",
            "background_color": "#3b82f6",
            "is_dismissible": True,
            "start_time": start_time,
            "end_time": end_time,
            "is_platform_wide": False,
        }

        response = requests.post(url, headers=headers, json=payload, timeout=10)

        if response.status_code == 201:
            announcement = response.json()
            logger.log(f"Created test announcement: {announcement['id']}", "SETUP")
            seed_status["announcements"] = True
        elif response.status_code == 403:
            logger.log("Permission denied for announcement creation (announcements:write required)", "SETUP")
            seed_status["announcements"] = False
        else:
            logger.log(f"Failed to create announcement: HTTP {response.status_code} - {response.text}", "SETUP")
            seed_status["announcements"] = False

    except Exception as e:
        logger.log(f"Error seeding test data: {str(e)}", "SETUP")
        seed_status["announcements"] = False

    return seed_status


def run_tests(definition: TestDefinition, screenshot_dir: Path) -> list[TestResult]:
    """Execute all tests and return results."""
    from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout
    import time

    logger = get_logger()
    results: list[TestResult] = []

    logger.log(f"Starting test run with {len(definition.tests)} tests")
    logger.log(f"Application URL: {definition.application_url}")
    logger.log(f"Auth provided: {definition.auth is not None}")

    # FAIL-FAST: Check backend health before proceeding
    ports_env_path = find_ports_env()
    logger.log(f"Current working directory: {Path.cwd()}", "SETUP")
    logger.log(f"Found .ports.env at: {ports_env_path}", "SETUP")

    backend_url = get_backend_url(definition)
    if backend_url:
        logger.log(f"Backend URL: {backend_url}", "SETUP")
        logger.log("Checking backend health...", "SETUP")

        is_healthy, health_message = check_backend_health(backend_url)
        if is_healthy:
            logger.log(health_message, "SETUP")
        else:
            logger.log(f"BACKEND HEALTH CHECK FAILED: {health_message}", "ERROR")
            # Fail all tests immediately with clear error
            error_msg = f"Backend health check failed: {health_message}. " \
                        "Smoke tests require a running backend to validate authentication."
            for test in definition.tests:
                results.append(TestResult(
                    test_name=test.name,
                    status="failed",
                    test_description=test.description,
                    screenshots=[],
                    error=error_msg
                ))
            return results
    else:
        logger.log("No backend URL found (.ports.env missing or no BACKEND_PORT) - skipping health check", "SETUP")

    # Seed test data before running tests
    seed_status = seed_test_data(definition)

    with sync_playwright() as p:
        # Launch browser (headless for speed in CI, headed for local debugging)
        headless = os.environ.get("SMOKE_TEST_HEADLESS", "true").lower() == "true"
        logger.log(f"Launching browser (headless={headless})")
        
        browser = None
        context = None
        try:
            browser = p.chromium.launch(headless=headless)
        except Exception as e:
            # Browser launch can fail if previous instance didn't clean up
            logger.log(f"Browser launch failed: {e}, attempting cleanup and retry...", "WARN")
            
            # Kill any orphaned Chromium processes from previous runs
            try:
                subprocess.run(
                    ["pkill", "-f", "chromium.*--headless"],
                    capture_output=True,
                    timeout=5
                )
                time.sleep(1)  # Give processes time to terminate
            except Exception:
                pass
            
            # Retry launch
            try:
                browser = p.chromium.launch(headless=headless)
            except Exception as retry_error:
                logger.log(f"Browser launch failed after retry: {retry_error}", "ERROR")
                error_msg = f"Failed to launch Chromium browser: {retry_error}"
                for test in definition.tests:
                    results.append(TestResult(
                        test_name=test.name,
                        status="failed",
                        test_description=test.description,
                        screenshots=[],
                        error=error_msg
                    ))
                return results

        # Create context with reasonable viewport
        context = browser.new_context(
            viewport={"width": 1280, "height": 720},
            ignore_https_errors=True
        )

        page = context.new_page()

        # Wrap all test execution in try/finally for cleanup
        try:
            # Navigate to app and inject auth if provided
            logger.log_command("goto", {"url": definition.application_url, "wait_until": "networkidle"})
            start_time = time.time()
            page.goto(definition.application_url, wait_until="networkidle", timeout=30000)
            logger.log_result("goto", True, (time.time() - start_time) * 1000)

            if definition.auth:
                # Inject authentication tokens via both storage and httpOnly cookie
                logger.log_command("evaluate", {"action": "inject_auth_tokens"})
                start_time = time.time()
                page.evaluate(f"""() => {{
                    sessionStorage.setItem('access_token', '{definition.auth.access_token}');
                    localStorage.setItem('refresh_token', '{definition.auth.refresh_token}');
                }}""")
                logger.log_result("evaluate", True, (time.time() - start_time) * 1000)

                # Also set refresh token as httpOnly cookie (for cookie-based auth flows)
                from urllib.parse import urlparse
                parsed_url = urlparse(definition.application_url)
                logger.log_command("add_cookies", {"action": "set_refresh_cookie"})
                start_time = time.time()
                context.add_cookies([{
                    "name": "refresh_token",
                    "value": definition.auth.refresh_token,
                    "domain": parsed_url.hostname or "localhost",
                    "path": "/api/v1/auth",
                    "httpOnly": True,
                    "secure": False,
                    "sameSite": "Lax",
                }])
                logger.log_result("add_cookies", True, (time.time() - start_time) * 1000)

                logger.log_command("reload", {"wait_until": "networkidle"})
                start_time = time.time()
                page.reload(wait_until="networkidle", timeout=30000)
                logger.log_result("reload", True, (time.time() - start_time) * 1000)

                # Wait for auth state to initialize (AuthProvider needs time to fetch /auth/me)
                # This prevents race conditions where protected routes check auth before it's loaded
                logger.log("Waiting for auth state to initialize...", "AUTH")
                time.sleep(2)  # Give AuthProvider time to fetch user data from /auth/me

                # FAIL-FAST: Verify authentication worked
                logger.log("Verifying authentication...", "AUTH")
                auth_success, auth_details = verify_authentication(page, screenshot_dir)
                logger.log_auth_verification(auth_success, page.url, auth_details)

                if not auth_success:
                    # Take a screenshot for debugging
                    auth_fail_screenshot = screenshot_dir / "auth_verification_failed.png"
                    page.screenshot(path=str(auth_fail_screenshot))
                    logger.log(f"Auth failure screenshot: {auth_fail_screenshot}", "AUTH")

                    # Fail all tests immediately
                    error_msg = f"Authentication verification failed: {auth_details}. " \
                                f"Current URL: {page.url}. " \
                                f"This typically means the backend API is not running or tokens are invalid."

                    for test in definition.tests:
                        results.append(TestResult(
                            test_name=test.name,
                            status="failed",
                            test_description=test.description,
                            screenshots=[str(auth_fail_screenshot)],
                            error=error_msg
                        ))
                    browser.close()
                    logger.log(f"All {len(definition.tests)} tests failed due to auth verification failure", "AUTH")
                    return results

                logger.log("Authentication verified successfully", "AUTH")

        except Exception as e:
            # If we can't even load the app, all tests fail
            logger.log(f"Failed to load application: {str(e)}", "ERROR")
            for test in definition.tests:
                results.append(TestResult(
                    test_name=test.name,
                    status="failed",
                    test_description=test.description,
                    error=f"Failed to load application: {str(e)}"
                ))
            # Cleanup and return (finally block handles cleanup)
            if context:
                try:
                    context.close()
                except Exception:
                    pass
            if browser:
                try:
                    browser.close()
                except Exception:
                    pass
            return results

        # Execute each test
        try:
          for test in definition.tests:
            logger.log_test_start(test.name, test.description)
            test_screenshots: list[str] = []
            error: Optional[str] = None

            # Check if test requires data that couldn't be seeded
            # Tests with "Announcement" in the name require announcement data
            if "Announcement" in test.name and not seed_status.get("announcements", False):
                status = "skipped"
                error = "Test requires announcement data, but announcements could not be created (missing announcements:write permission). Grant this permission to the test user to enable announcement smoke tests."
                logger.log_test_end(test.name, status, error)
                results.append(TestResult(
                    test_name=test.name,
                    status=status,
                    test_description=test.description,
                    screenshots=test_screenshots,
                    error=error
                ))
                continue

            try:
                for step_idx, step in enumerate(test.steps):
                    execute_step(page, step, definition.application_url, screenshot_dir, test_screenshots, step_idx)

                status = "passed"
            except PlaywrightTimeout as e:
                status = "failed"
                error = f"Timeout: {str(e)}"
                # Capture failure screenshot for debugging
                failure_screenshot = screenshot_dir / f"{test.name.replace(' ', '_')}_FAILURE.png"
                try:
                    page.screenshot(path=str(failure_screenshot))
                    test_screenshots.append(str(failure_screenshot))
                    logger.log(f"Failure screenshot saved: {failure_screenshot}", "DEBUG")
                except Exception:
                    pass
            except AssertionError as e:
                status = "failed"
                error = f"Assertion failed: {str(e)}"
                # Capture failure screenshot for debugging
                failure_screenshot = screenshot_dir / f"{test.name.replace(' ', '_')}_FAILURE.png"
                try:
                    page.screenshot(path=str(failure_screenshot))
                    test_screenshots.append(str(failure_screenshot))
                    logger.log(f"Failure screenshot saved: {failure_screenshot}", "DEBUG")
                except Exception:
                    pass
            except Exception as e:
                status = "failed"
                error = f"Error: {str(e)}"
                # Capture failure screenshot for debugging
                failure_screenshot = screenshot_dir / f"{test.name.replace(' ', '_')}_FAILURE.png"
                try:
                    page.screenshot(path=str(failure_screenshot))
                    test_screenshots.append(str(failure_screenshot))
                    logger.log(f"Failure screenshot saved: {failure_screenshot}", "DEBUG")
                except Exception:
                    pass

            logger.log_test_end(test.name, status, error)

            results.append(TestResult(
                test_name=test.name,
                status=status,
                test_description=test.description,
                screenshots=test_screenshots,
                error=error
            ))

        # Explicit cleanup in correct order
        finally:
            if context:
                try:
                    context.close()
                except Exception as e:
                    logger.log(f"Warning: context.close() failed: {e}", "WARN")
            if browser:
                try:
                    browser.close()
                except Exception as e:
                    logger.log(f"Warning: browser.close() failed: {e}", "WARN")

    passed = sum(1 for r in results if r.status == "passed")
    failed = sum(1 for r in results if r.status == "failed")
    logger.log(f"Test run complete: {passed} passed, {failed} failed")

    return results


def execute_step(page: Any, step: TestStep, base_url: str, screenshot_dir: Path, screenshots: list[str], step_idx: int = 0):
    """Execute a single test step."""
    import time

    logger = get_logger()
    action = step.action.lower()

    # Build details dict for logging
    details = {
        "step": step_idx + 1,
        "selector": step.selector,
        "url": step.url,
        "text": step.text,
        "timeout": step.timeout,
        "key": step.key,
        "name": step.name,
    }
    # Filter out None values for cleaner logging
    details = {k: v for k, v in details.items() if v is not None}
    logger.log_command(action, details)

    start_time = time.time()

    try:
        if action == "navigate":
            url = step.url or "/"
            if not url.startswith("http"):
                url = f"{base_url.rstrip('/')}/{url.lstrip('/')}"
            page.goto(url, wait_until="networkidle", timeout=step.timeout)

        elif action == "click":
            if not step.selector:
                raise ValueError("click action requires selector")
            page.click(step.selector, timeout=step.timeout)

        elif action == "fill" or action == "type":
            if not step.selector or step.text is None:
                raise ValueError("fill action requires selector and text")
            page.fill(step.selector, step.text, timeout=step.timeout)

        elif action == "press":
            if not step.key:
                raise ValueError("press action requires key")
            if step.selector:
                page.press(step.selector, step.key, timeout=step.timeout)
            else:
                page.keyboard.press(step.key)

        elif action == "waitforselector":
            if not step.selector:
                raise ValueError("waitForSelector action requires selector")
            page.wait_for_selector(step.selector, timeout=step.timeout, state="visible")

        elif action == "waitforurl":
            if not step.url:
                raise ValueError("waitForUrl action requires url")
            # Support relative URLs by converting to glob pattern
            url_pattern = step.url
            if url_pattern.startswith("/"):
                # Relative path - convert to glob pattern that matches any host
                url_pattern = f"**{url_pattern}"
            # Use 'commit' wait_until for SPA navigation (React Router)
            # 'commit' fires when navigation is committed, before 'load' event
            page.wait_for_url(url_pattern, timeout=step.timeout, wait_until="commit")

        elif action == "screenshot":
            if not step.name:
                raise ValueError("screenshot action requires name")
            screenshot_path = screenshot_dir / step.name
            page.screenshot(path=str(screenshot_path))
            screenshots.append(str(screenshot_path))

        elif action == "assertvisible":
            if not step.selector:
                raise ValueError("assertVisible action requires selector")
            element = page.query_selector(step.selector)
            if not element or not element.is_visible():
                raise AssertionError(f"Step {step_idx + 1}: Element not visible: {step.selector}. Current URL: {page.url}")

        elif action == "asserthidden":
            if not step.selector:
                raise ValueError("assertHidden action requires selector")
            element = page.query_selector(step.selector)
            if element and element.is_visible():
                raise AssertionError(f"Step {step_idx + 1}: Element should be hidden: {step.selector}")

        elif action == "asserttext":
            if not step.selector or step.text is None:
                raise ValueError("assertText action requires selector and text")
            element = page.query_selector(step.selector)
            if not element:
                raise AssertionError(f"Step {step_idx + 1}: Element not found: {step.selector}. Current URL: {page.url}")
            actual_text = element.inner_text()
            if step.text not in actual_text:
                raise AssertionError(f"Step {step_idx + 1}: Expected text '{step.text}' not found in '{actual_text}'")

        elif action == "wait":
            # Simple delay (use sparingly)
            page.wait_for_timeout(step.timeout)

        elif action == "hover":
            if not step.selector:
                raise ValueError("hover action requires selector")
            page.hover(step.selector, timeout=step.timeout)

        elif action == "selectoption":
            if not step.selector or step.text is None:
                raise ValueError("selectOption action requires selector and text (value)")
            page.select_option(step.selector, step.text, timeout=step.timeout)

        elif action == "clearauth":
            # Clear authentication tokens from storage
            page.evaluate("""() => {
                sessionStorage.removeItem('access_token');
                localStorage.removeItem('refresh_token');
            }""")

        else:
            raise ValueError(f"Unknown action: {action}")

        # Log success
        duration_ms = (time.time() - start_time) * 1000
        logger.log_result(action, True, duration_ms)

    except Exception as e:
        # Log failure and re-raise
        duration_ms = (time.time() - start_time) * 1000
        logger.log_result(action, False, duration_ms, str(e))
        raise


def main():
    parser = argparse.ArgumentParser(description="Execute smoke tests from JSON definition")
    parser.add_argument("test_file", help="Path to test definition JSON file")
    parser.add_argument("--screenshot-dir", "-s", default="./smoke_screenshots",
                        help="Directory to save screenshots")
    parser.add_argument("--log-file", "-l", default=None,
                        help="Path to log file for Playwright commands and output")
    args = parser.parse_args()

    # Set up logging
    log_file = Path(args.log_file) if args.log_file else None
    logger = PlaywrightLogger(log_file)
    set_logger(logger)

    logger.log(f"Test file: {args.test_file}")
    logger.log(f"Screenshot dir: {args.screenshot_dir}")
    logger.log(f"Log file: {args.log_file or 'None (logging disabled)'}")

    # Ensure browsers are installed
    logger.log("Checking Playwright browser installation...")
    if not ensure_playwright_browsers():
        logger.log("Failed to install Playwright browsers", "ERROR")
        print(json.dumps([{
            "test_name": "setup",
            "status": "skipped",
            "test_description": "Browser setup",
            "screenshots": [],
            "error": "Failed to install Playwright browsers"
        }]))
        logger.close()
        sys.exit(0)
    logger.log("Playwright browsers available")

    # Load test definition
    logger.log(f"Loading test definition from: {args.test_file}")
    try:
        with open(args.test_file, "r") as f:
            data = json.load(f)
        definition = TestDefinition.model_validate(data)
        logger.log(f"Loaded {len(definition.tests)} test(s)")

        # Log the test definition (sanitize auth tokens)
        sanitized_data = data.copy()
        if "auth" in sanitized_data and sanitized_data["auth"]:
            sanitized_data["auth"] = {
                "access_token": f"{sanitized_data['auth'].get('access_token', '')[:20]}...[truncated]",
                "refresh_token": f"{sanitized_data['auth'].get('refresh_token', '')[:20]}...[truncated]"
            }
        logger.log(f"Test definition:\n{json.dumps(sanitized_data, indent=2)}")

    except Exception as e:
        logger.log(f"Failed to load test definition: {str(e)}", "ERROR")
        print(json.dumps([{
            "test_name": "setup",
            "status": "failed",
            "test_description": "Load test definition",
            "screenshots": [],
            "error": f"Failed to load test definition: {str(e)}"
        }]))
        logger.close()
        sys.exit(1)

    # Create screenshot directory
    screenshot_dir = Path(args.screenshot_dir)
    screenshot_dir.mkdir(parents=True, exist_ok=True)
    logger.log(f"Screenshot directory: {screenshot_dir.absolute()}")

    # Run tests
    results = run_tests(definition, screenshot_dir)

    # Log final results summary
    logger.log("\n" + "=" * 60)
    logger.log("FINAL RESULTS SUMMARY")
    logger.log("=" * 60)
    for result in results:
        status_emoji = "" if result.status == "passed" else ""
        logger.log(f"{status_emoji} {result.test_name}: {result.status.upper()}")
        if result.error:
            logger.log(f"   Error: {result.error}")
        if result.screenshots:
            logger.log(f"   Screenshots: {', '.join(result.screenshots)}")

    # Output results as JSON
    output_json = json.dumps([r.model_dump() for r in results], indent=2)
    logger.log(f"\nJSON Output:\n{output_json}")
    print(output_json)

    # Close logger
    logger.close()

    # Exit with error code if any tests failed
    failed_count = sum(1 for r in results if r.status == "failed")
    sys.exit(1 if failed_count > 0 else 0)


if __name__ == "__main__":
    main()
