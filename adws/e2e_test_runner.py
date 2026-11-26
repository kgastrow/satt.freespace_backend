#!/usr/bin/env -S uv run
# /// script
# dependencies = ["playwright>=1.40.0", "pydantic>=2.0.0"]
# ///

"""
Direct Playwright E2E Test Runner

Executes E2E tests defined in a JSON file WITHOUT MCP round-trips.
This is ~10x faster than the MCP-based approach because all browser
actions run at native speed without waiting for Claude to decide each step.

Usage:
    uv run adws/e2e_test_runner.py <test_definition.json> [--screenshot-dir <dir>]

Input JSON format:
{
    "application_url": "http://localhost:5173",
    "auth": {
        "access_token": "...",
        "refresh_token": "..."
    },
    "test_name": "Basic Query Execution",
    "test_description": "Test basic query functionality",
    "steps": [
        {"action": "navigate", "url": "/"},
        {"action": "screenshot", "name": "01_initial.png"},
        {"action": "assertTitle", "text": "Natural Language SQL Interface"},
        {"action": "assertVisible", "selector": "[data-testid='query-input']"},
        {"action": "fill", "selector": "[data-testid='query-input']", "text": "Show me all users"},
        {"action": "screenshot", "name": "02_query_entered.png"},
        {"action": "click", "selector": "[data-testid='query-button']"},
        {"action": "waitForSelector", "selector": ".results-table"},
        {"action": "assertText", "selector": ".sql-display", "text": "SELECT"},
        {"action": "screenshot", "name": "03_results.png"}
    ]
}

Output JSON format (to stdout):
{
    "test_name": "Basic Query Execution",
    "status": "passed|failed",
    "test_description": "...",
    "screenshots": ["/path/to/screenshot.png"],
    "steps_passed": 10,
    "steps_failed": 0,
    "error": null or "error message",
    "step_results": [
        {"step": 1, "action": "navigate", "status": "passed"},
        {"step": 2, "action": "assertTitle", "status": "failed", "error": "Expected 'X' but got 'Y'"}
    ]
}
"""

import argparse
import json
import os
import sys
import subprocess
from pathlib import Path
from typing import Any, Optional
from pydantic import BaseModel


class TestStep(BaseModel):
    """A single step in an E2E test."""
    action: str
    selector: Optional[str] = None
    url: Optional[str] = None
    name: Optional[str] = None  # For screenshots
    text: Optional[str] = None  # For fill/type/assert actions
    timeout: int = 10000  # ms (longer default for E2E)
    key: Optional[str] = None  # For keyboard actions
    description: Optional[str] = None  # Human-readable step description


class AuthConfig(BaseModel):
    """Authentication configuration."""
    access_token: str
    refresh_token: str


class TestDefinition(BaseModel):
    """Complete E2E test definition."""
    application_url: str
    auth: Optional[AuthConfig] = None
    test_name: str
    test_description: str = ""
    steps: list[TestStep]


class StepResult(BaseModel):
    """Result of a single step execution."""
    step: int
    action: str
    status: str  # passed, failed
    description: Optional[str] = None
    error: Optional[str] = None


class TestResult(BaseModel):
    """Result of the E2E test execution."""
    test_name: str
    status: str  # passed, failed
    test_description: str
    screenshots: list[str] = []
    steps_passed: int = 0
    steps_failed: int = 0
    error: Optional[str] = None
    step_results: list[StepResult] = []


def ensure_playwright_browsers():
    """Ensure Playwright browsers are installed."""
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            browser.close()
        return True
    except Exception:
        print("Installing Playwright browsers...", file=sys.stderr)
        result = subprocess.run(
            [sys.executable, "-m", "playwright", "install", "chromium"],
            capture_output=True,
            text=True
        )
        if result.returncode != 0:
            print(f"Failed to install Playwright browsers: {result.stderr}", file=sys.stderr)
            return False
        return True


def execute_step(
    page: Any,
    step: TestStep,
    step_num: int,
    base_url: str,
    screenshot_dir: Path,
    screenshots: list[str]
) -> StepResult:
    """Execute a single test step and return the result."""
    action = step.action.lower()
    description = step.description or f"{action} {step.selector or step.url or step.text or ''}"

    try:
        if action == "navigate":
            url = step.url or "/"
            if not url.startswith("http"):
                url = f"{base_url.rstrip('/')}/{url.lstrip('/')}"
            page.goto(url, wait_until="domcontentloaded", timeout=step.timeout)
            # Brief settle for SPA client-side rendering
            page.wait_for_timeout(500)

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
            url_pattern = step.url
            if url_pattern.startswith("/"):
                url_pattern = f"**{url_pattern}"
            page.wait_for_url(url_pattern, timeout=step.timeout)

        elif action == "screenshot":
            if not step.name:
                raise ValueError("screenshot action requires name")
            screenshot_path = screenshot_dir / step.name
            page.screenshot(path=str(screenshot_path))
            screenshots.append(str(screenshot_path))

        elif action == "assertvisible":
            if not step.selector:
                raise ValueError("assertVisible action requires selector")
            try:
                page.locator(step.selector).first.wait_for(state="visible", timeout=step.timeout)
            except Exception:
                raise AssertionError(f"Element not visible: {step.selector}")

        elif action == "asserthidden":
            if not step.selector:
                raise ValueError("assertHidden action requires selector")
            try:
                page.locator(step.selector).first.wait_for(state="hidden", timeout=step.timeout)
            except Exception:
                raise AssertionError(f"Element should be hidden: {step.selector}")

        elif action == "asserttext":
            if not step.selector or step.text is None:
                raise ValueError("assertText action requires selector and text")
            try:
                page.locator(step.selector).first.wait_for(state="visible", timeout=step.timeout)
            except Exception:
                raise AssertionError(f"Element not found: {step.selector}")
            actual_text = page.locator(step.selector).first.inner_text()
            if step.text not in actual_text:
                raise AssertionError(f"Expected text '{step.text}' not found in '{actual_text[:100]}'")

        elif action == "asserttitle":
            if step.text is None:
                raise ValueError("assertTitle action requires text")
            actual_title = page.title()
            if step.text not in actual_title:
                raise AssertionError(f"Expected title '{step.text}' not found in '{actual_title}'")

        elif action == "asserturl":
            if step.text is None:
                raise ValueError("assertUrl action requires text (url pattern)")
            actual_url = page.url
            if step.text not in actual_url:
                raise AssertionError(f"Expected URL pattern '{step.text}' not found in '{actual_url}'")

        elif action == "assertcount":
            if not step.selector or step.text is None:
                raise ValueError("assertCount action requires selector and text (expected count)")
            locator = page.locator(step.selector)
            expected_count = int(step.text)
            actual_count = locator.count()
            if actual_count != expected_count:
                raise AssertionError(f"Expected {expected_count} elements, found {actual_count}")

        elif action == "wait":
            page.wait_for_timeout(step.timeout)

        elif action == "hover":
            if not step.selector:
                raise ValueError("hover action requires selector")
            page.hover(step.selector, timeout=step.timeout)

        elif action == "selectoption":
            if not step.selector or step.text is None:
                raise ValueError("selectOption action requires selector and text (value)")
            page.select_option(step.selector, step.text, timeout=step.timeout)

        elif action == "scroll":
            if step.selector:
                page.locator(step.selector).scroll_into_view_if_needed()
            else:
                page.evaluate("window.scrollTo(0, document.body.scrollHeight)")

        elif action == "clear":
            if not step.selector:
                raise ValueError("clear action requires selector")
            page.fill(step.selector, "", timeout=step.timeout)

        elif action == "check":
            if not step.selector:
                raise ValueError("check action requires selector")
            page.check(step.selector, timeout=step.timeout)

        elif action == "uncheck":
            if not step.selector:
                raise ValueError("uncheck action requires selector")
            page.uncheck(step.selector, timeout=step.timeout)

        else:
            raise ValueError(f"Unknown action: {action}")

        return StepResult(
            step=step_num,
            action=action,
            status="passed",
            description=description
        )

    except AssertionError as e:
        return StepResult(
            step=step_num,
            action=action,
            status="failed",
            description=description,
            error=str(e)
        )
    except Exception as e:
        return StepResult(
            step=step_num,
            action=action,
            status="failed",
            description=description,
            error=f"Error: {str(e)}"
        )


def run_test(definition: TestDefinition, screenshot_dir: Path) -> TestResult:
    """Execute the E2E test and return results."""
    from playwright.sync_api import sync_playwright

    screenshots: list[str] = []
    step_results: list[StepResult] = []

    with sync_playwright() as p:
        # Launch browser
        headless = os.environ.get("E2E_HEADLESS", "true").lower() == "true"
        browser = p.chromium.launch(headless=headless)

        # Create context with reasonable viewport
        context = browser.new_context(
            viewport={"width": 1280, "height": 720},
            ignore_https_errors=True
        )

        page = context.new_page()

        # Navigate to app and inject auth if provided
        try:
            if definition.auth:
                # Set refresh_token as httpOnly cookie BEFORE navigation
                # so AuthProvider's bootstrap refresh call finds the cookie.
                from urllib.parse import urlparse
                parsed = urlparse(definition.application_url)
                hostname = parsed.hostname or "localhost"
                context.add_cookies([{
                    "name": "refresh_token",
                    "value": definition.auth.refresh_token,
                    "domain": hostname,
                    "path": "/api/v1/auth",
                    "httpOnly": True,
                    "secure": parsed.scheme == "https",
                    "sameSite": "Lax",
                }])

            page.goto(definition.application_url, wait_until="domcontentloaded", timeout=30000)
            # Wait for SPA to bootstrap and render
            page.wait_for_timeout(2000)
        except Exception as e:
            browser.close()
            return TestResult(
                test_name=definition.test_name,
                status="failed",
                test_description=definition.test_description,
                error=f"Failed to load application: {str(e)}"
            )

        # Execute each step
        for i, step in enumerate(definition.steps, 1):
            result = execute_step(page, step, i, definition.application_url, screenshot_dir, screenshots)
            step_results.append(result)

            # Stop on first failure (E2E tests are sequential)
            if result.status == "failed":
                # Take a failure screenshot
                try:
                    failure_screenshot = screenshot_dir / f"FAILED_step_{i}.png"
                    page.screenshot(path=str(failure_screenshot))
                    screenshots.append(str(failure_screenshot))
                except Exception:
                    pass
                break

        browser.close()

    # Calculate results
    steps_passed = sum(1 for r in step_results if r.status == "passed")
    steps_failed = sum(1 for r in step_results if r.status == "failed")
    overall_status = "passed" if steps_failed == 0 else "failed"

    # Get first error if any
    first_error = None
    for r in step_results:
        if r.error:
            first_error = f"Step {r.step} ({r.action}): {r.error}"
            break

    return TestResult(
        test_name=definition.test_name,
        status=overall_status,
        test_description=definition.test_description,
        screenshots=screenshots,
        steps_passed=steps_passed,
        steps_failed=steps_failed,
        error=first_error,
        step_results=step_results
    )


def main():
    parser = argparse.ArgumentParser(description="Execute E2E test from JSON definition")
    parser.add_argument("test_file", help="Path to test definition JSON file")
    parser.add_argument("--screenshot-dir", "-s", default="./e2e_screenshots",
                        help="Directory to save screenshots")
    args = parser.parse_args()

    # Ensure browsers are installed
    if not ensure_playwright_browsers():
        print(json.dumps({
            "test_name": "setup",
            "status": "failed",
            "test_description": "Browser setup",
            "screenshots": [],
            "steps_passed": 0,
            "steps_failed": 1,
            "error": "Failed to install Playwright browsers",
            "step_results": []
        }))
        sys.exit(1)

    # Load test definition
    try:
        with open(args.test_file, "r") as f:
            data = json.load(f)
        definition = TestDefinition.model_validate(data)
    except Exception as e:
        print(json.dumps({
            "test_name": "setup",
            "status": "failed",
            "test_description": "Load test definition",
            "screenshots": [],
            "steps_passed": 0,
            "steps_failed": 1,
            "error": f"Failed to load test definition: {str(e)}",
            "step_results": []
        }))
        sys.exit(1)

    # Create screenshot directory
    screenshot_dir = Path(args.screenshot_dir)
    screenshot_dir.mkdir(parents=True, exist_ok=True)

    # Run test
    result = run_test(definition, screenshot_dir)

    # Output results as JSON
    print(json.dumps(result.model_dump(), indent=2))

    # Exit with error code if test failed
    sys.exit(0 if result.status == "passed" else 1)


if __name__ == "__main__":
    main()
