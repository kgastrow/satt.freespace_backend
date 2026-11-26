#!/usr/bin/env -S uv run
# /// script
# dependencies = ["playwright>=1.40.0", "pydantic>=2.0.0"]
# ///

"""
Direct Playwright Review Screenshot Runner

Captures screenshots for review workflow WITHOUT MCP round-trips.
This is ~10x faster than the MCP-based approach because all browser
actions run at native speed without waiting for Claude to decide each step.

Usage:
    uv run adws/review_screenshot_runner.py <capture_definition.json> [--screenshot-dir <dir>]

Input JSON format:
{
    "application_url": "http://localhost:5173",
    "auth": {
        "access_token": "...",
        "refresh_token": "..."
    },
    "captures": [
        {
            "name": "01_dashboard.png",
            "description": "Dashboard with sidebar navigation",
            "url": "/dashboard",
            "wait_for": "[data-sidebar='sidebar']",
            "actions": [
                {"action": "click", "selector": ".some-button"},
                {"action": "wait", "timeout": 500}
            ]
        }
    ]
}

Output JSON format (to stdout):
{
    "success": true,
    "screenshots": ["/path/to/01_dashboard.png", ...],
    "issues": [
        {"screenshot": "01_dashboard.png", "description": "Element not found"}
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


class CaptureAction(BaseModel):
    """An optional action to perform before taking a screenshot."""
    action: str  # click, fill, hover, wait, scroll
    selector: Optional[str] = None
    text: Optional[str] = None  # For fill action
    timeout: int = 1000  # For wait action (ms)


class ScreenshotCapture(BaseModel):
    """Definition of a single screenshot to capture."""
    name: str  # Filename like "01_dashboard.png"
    description: str  # What this screenshot shows
    url: Optional[str] = None  # URL to navigate to (can be relative)
    wait_for: Optional[str] = None  # Selector to wait for before screenshot
    wait_timeout: int = 10000  # Timeout for wait_for (ms)
    actions: list[CaptureAction] = []  # Optional actions before screenshot
    full_page: bool = False  # Capture full page or viewport only


class AuthConfig(BaseModel):
    """Authentication configuration."""
    access_token: str
    refresh_token: str


class CaptureDefinition(BaseModel):
    """Complete capture definition file."""
    application_url: str
    auth: Optional[AuthConfig] = None
    captures: list[ScreenshotCapture]


class CaptureIssue(BaseModel):
    """An issue encountered during capture."""
    screenshot: str
    description: str


class CaptureResult(BaseModel):
    """Result of the capture execution."""
    success: bool
    screenshots: list[str] = []
    issues: list[CaptureIssue] = []


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


def execute_action(page: Any, action: CaptureAction) -> None:
    """Execute a single action on the page."""
    action_type = action.action.lower()

    if action_type == "click":
        if action.selector:
            page.click(action.selector, timeout=action.timeout)

    elif action_type == "fill":
        if action.selector and action.text is not None:
            page.fill(action.selector, action.text, timeout=action.timeout)

    elif action_type == "hover":
        if action.selector:
            page.hover(action.selector, timeout=action.timeout)

    elif action_type == "wait":
        page.wait_for_timeout(action.timeout)

    elif action_type == "scroll":
        if action.selector:
            page.locator(action.selector).scroll_into_view_if_needed()
        else:
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")


def run_captures(definition: CaptureDefinition, screenshot_dir: Path) -> CaptureResult:
    """Execute all captures and return results."""
    from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

    screenshots: list[str] = []
    issues: list[CaptureIssue] = []

    with sync_playwright() as p:
        # Launch browser
        headless = os.environ.get("REVIEW_HEADLESS", "true").lower() == "true"
        browser = p.chromium.launch(headless=headless)

        # Create context with reasonable viewport
        context = browser.new_context(
            viewport={"width": 1280, "height": 720},
            ignore_https_errors=True
        )

        page = context.new_page()

        # Navigate to app and inject auth if provided
        try:
            page.goto(definition.application_url, wait_until="networkidle", timeout=30000)

            if definition.auth:
                page.evaluate(f"""() => {{
                    sessionStorage.setItem('access_token', '{definition.auth.access_token}');
                    localStorage.setItem('refresh_token', '{definition.auth.refresh_token}');
                }}""")
                page.reload(wait_until="networkidle", timeout=30000)
        except Exception as e:
            browser.close()
            return CaptureResult(
                success=False,
                issues=[CaptureIssue(
                    screenshot="",
                    description=f"Failed to load application: {str(e)}"
                )]
            )

        # Execute each capture
        for capture in definition.captures:
            try:
                # Navigate if URL specified
                if capture.url:
                    url = capture.url
                    if not url.startswith("http"):
                        url = f"{definition.application_url.rstrip('/')}/{url.lstrip('/')}"
                    page.goto(url, wait_until="networkidle", timeout=30000)

                # Wait for element if specified
                if capture.wait_for:
                    page.wait_for_selector(
                        capture.wait_for,
                        timeout=capture.wait_timeout,
                        state="visible"
                    )

                # Execute any actions before screenshot
                for action in capture.actions:
                    execute_action(page, action)

                # Small delay to let animations settle
                page.wait_for_timeout(300)

                # Take screenshot
                screenshot_path = screenshot_dir / capture.name
                page.screenshot(
                    path=str(screenshot_path),
                    full_page=capture.full_page
                )
                screenshots.append(str(screenshot_path))

            except PlaywrightTimeout as e:
                issues.append(CaptureIssue(
                    screenshot=capture.name,
                    description=f"Timeout waiting for element: {str(e)}"
                ))
            except Exception as e:
                issues.append(CaptureIssue(
                    screenshot=capture.name,
                    description=f"Error: {str(e)}"
                ))

        browser.close()

    return CaptureResult(
        success=len(issues) == 0,
        screenshots=screenshots,
        issues=issues
    )


def main():
    parser = argparse.ArgumentParser(description="Capture review screenshots from JSON definition")
    parser.add_argument("capture_file", help="Path to capture definition JSON file")
    parser.add_argument("--screenshot-dir", "-s", default="./review_screenshots",
                        help="Directory to save screenshots")
    args = parser.parse_args()

    # Ensure browsers are installed
    if not ensure_playwright_browsers():
        print(json.dumps({
            "success": False,
            "screenshots": [],
            "issues": [{"screenshot": "", "description": "Failed to install Playwright browsers"}]
        }))
        sys.exit(1)

    # Load capture definition
    try:
        with open(args.capture_file, "r") as f:
            data = json.load(f)
        definition = CaptureDefinition.model_validate(data)
    except Exception as e:
        print(json.dumps({
            "success": False,
            "screenshots": [],
            "issues": [{"screenshot": "", "description": f"Failed to load capture definition: {str(e)}"}]
        }))
        sys.exit(1)

    # Create screenshot directory
    screenshot_dir = Path(args.screenshot_dir)
    screenshot_dir.mkdir(parents=True, exist_ok=True)

    # Run captures
    result = run_captures(definition, screenshot_dir)

    # Output results as JSON
    print(json.dumps(result.model_dump(), indent=2))

    # Exit with error code if any issues
    sys.exit(0 if result.success else 1)


if __name__ == "__main__":
    main()
