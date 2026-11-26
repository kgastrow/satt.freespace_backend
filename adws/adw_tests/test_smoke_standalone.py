#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "python-dotenv",
#     "pydantic",
# ]
# ///

"""
Standalone Smoke Test Runner

This script allows testing the smoke test workflow without going through
a full build workflow. It creates a sample spec, seeds the database,
runs smoke tests with screenshots, and cleans up.

Uses DIRECT Playwright execution (no MCP) for ~10x faster performance.

Usage:
  uv run adws/adw_tests/test_smoke_standalone.py [--adw-id <id>] [--skip-cleanup] [--dry-run]

Options:
  --adw-id        Custom ADW ID (default: auto-generated)
  --skip-cleanup  Keep test data after completion for debugging
  --skip-seed     Skip database seeding (use existing test data)
  --skip-app      Don't start/stop the app (assumes it's already running)
  --dry-run       Run setup/teardown only, skip actual browser tests (useful for testing on WSL)

Example:
  uv run adws/adw_tests/test_smoke_standalone.py
  uv run adws/adw_tests/test_smoke_standalone.py --adw-id smoke-demo-001
  uv run adws/adw_tests/test_smoke_standalone.py --skip-cleanup
  uv run adws/adw_tests/test_smoke_standalone.py --skip-app  # App already running
  uv run adws/adw_tests/test_smoke_standalone.py --dry-run   # Test setup/teardown on WSL
"""

import argparse
import json
import os
import subprocess
import sys
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

# Add parent directory for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from adw_modules.utils import is_chrome_available, get_safe_subprocess_env

import time
import urllib.request
import urllib.error


# Sample specification for smoke testing
SAMPLE_SPEC = """# Feature: Dashboard Page Verification

## Feature Description
Verify that the dashboard page loads correctly and displays the expected UI elements
for an authenticated admin user.

## User Story
As an authenticated admin user
I want to see the dashboard with all available management cards
So that I can navigate to different sections of the application

## Acceptance Criteria
- Dashboard page loads without errors
- Welcome message displays user's first name
- "Your Profile" card is visible
- "User Management" card is visible for admin users
- "Role Management" card is visible for admin users
- "Audit Logs" card is visible for admin users
- All navigation buttons are clickable
"""


def generate_adw_id() -> str:
    """Generate a unique ADW ID for the smoke test."""
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    short_uuid = uuid.uuid4().hex[:8]
    return f"smoke-test-{timestamp}-{short_uuid}"


def check_prerequisites(skip_chrome_check: bool = False) -> tuple[bool, list[str], list[str]]:
    """Check if all prerequisites are met for running smoke tests.

    Returns:
        Tuple of (all_ok, errors, warnings)
    """
    errors = []
    warnings = []

    # Check Chrome availability
    chrome_available, chrome_reason = is_chrome_available()
    if not chrome_available:
        if skip_chrome_check:
            warnings.append(f"Chrome not available (skipped): {chrome_reason}")
        else:
            errors.append(f"Chrome not available: {chrome_reason}")

    # Check if smoke_test_runner.py exists
    runner_script = Path(__file__).parent.parent / "smoke_test_runner.py"
    if not runner_script.exists():
        errors.append(f"Smoke test runner not found: {runner_script}")

    return len(errors) == 0, errors, warnings


def create_spec_file(adw_id: str) -> str:
    """Create a temporary spec file for the smoke test."""
    # Create agents directory structure
    agents_dir = Path(f"agents/{adw_id}")
    agents_dir.mkdir(parents=True, exist_ok=True)

    spec_file = agents_dir / "spec.md"
    spec_file.write_text(SAMPLE_SPEC)

    return str(spec_file)


def seed_smoke_test_data(adw_id: str) -> Optional[dict]:
    """Seed the database with smoke test organization and user."""
    print(f"\n📦 Seeding smoke test data for ADW ID: {adw_id}")

    # Get project root (where this script is run from)
    project_root = Path.cwd()
    backend_dir = project_root / "app" / "backend"
    seed_script = backend_dir / "scripts" / "seed_smoke_test.py"

    if not seed_script.exists():
        print(f"❌ Seed script not found: {seed_script}")
        return None

    # Use the backend's virtual environment
    venv_python = backend_dir / ".venv" / "bin" / "python"
    python_cmd = str(venv_python) if venv_python.exists() else "python"

    try:
        result = subprocess.run(
            [python_cmd, "scripts/seed_smoke_test.py", "--adw-id", adw_id],
            capture_output=True,
            text=True,
            cwd=str(backend_dir),
            timeout=30
        )

        if result.returncode != 0:
            print(f"❌ Seed script failed: {result.stderr}")
            return None

        # Parse the JSON output
        auth_data = json.loads(result.stdout)
        print(f"✅ Created smoke test org: {auth_data.get('org_slug')}")
        print(f"✅ Created smoke test user: {auth_data.get('email')}")
        return auth_data

    except subprocess.TimeoutExpired:
        print("❌ Seed script timed out")
        return None
    except json.JSONDecodeError as e:
        print(f"❌ Failed to parse seed script output: {e}")
        return None
    except Exception as e:
        print(f"❌ Error running seed script: {e}")
        return None


def teardown_smoke_test_data(adw_id: str) -> bool:
    """Clean up smoke test data from the database."""
    print(f"\n🧹 Cleaning up smoke test data for ADW ID: {adw_id}")

    # Get project root (where this script is run from)
    project_root = Path.cwd()
    backend_dir = project_root / "app" / "backend"
    teardown_script = backend_dir / "scripts" / "teardown_smoke_test.py"

    if not teardown_script.exists():
        print(f"⚠️ Teardown script not found: {teardown_script}")
        return False

    # Use the backend's virtual environment
    venv_python = backend_dir / ".venv" / "bin" / "python"
    python_cmd = str(venv_python) if venv_python.exists() else "python"

    try:
        result = subprocess.run(
            [python_cmd, "scripts/teardown_smoke_test.py", "--adw-id", adw_id],
            capture_output=True,
            text=True,
            cwd=str(backend_dir),
            timeout=30
        )

        if result.returncode != 0:
            print(f"⚠️ Teardown script failed: {result.stderr}")
            return False

        print("✅ Smoke test data cleaned up")
        return True

    except subprocess.TimeoutExpired:
        print("⚠️ Teardown script timed out")
        return False
    except Exception as e:
        print(f"⚠️ Error running teardown script: {e}")
        return False


def get_application_url() -> str:
    """Determine the application URL from .ports.env or default."""
    ports_env = Path(".ports.env")
    if ports_env.exists():
        try:
            with open(ports_env) as f:
                for line in f:
                    if line.startswith("FRONTEND_PORT="):
                        port = line.strip().split("=")[1]
                        return f"http://localhost:{port}"
        except Exception:
            pass
    return "http://localhost:5173"


def get_ports() -> tuple[int, int]:
    """Get backend and frontend ports from .ports.env or defaults."""
    backend_port = 8000
    frontend_port = 5173

    ports_env = Path(".ports.env")
    if ports_env.exists():
        try:
            with open(ports_env) as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("BACKEND_PORT="):
                        backend_port = int(line.split("=")[1])
                    elif line.startswith("FRONTEND_PORT="):
                        frontend_port = int(line.split("=")[1])
        except Exception:
            pass

    return backend_port, frontend_port


def is_port_in_use(port: int) -> bool:
    """Check if a port is in use."""
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(('localhost', port)) == 0


def wait_for_url(url: str, timeout: int = 60, interval: float = 2.0) -> bool:
    """Wait for a URL to become available."""
    start_time = time.time()
    while time.time() - start_time < timeout:
        try:
            req = urllib.request.Request(url, method='GET')
            urllib.request.urlopen(req, timeout=5)
            return True
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError):
            time.sleep(interval)
    return False


def start_application() -> tuple[bool, Optional[subprocess.Popen], Optional[subprocess.Popen]]:
    """Start the backend and frontend servers.

    Returns:
        Tuple of (success, backend_process, frontend_process)
    """
    print("\n🚀 Starting application servers...")

    project_root = Path.cwd()
    backend_dir = project_root / "app" / "backend"
    frontend_dir = project_root / "app" / "frontend"

    backend_port, frontend_port = get_ports()

    # Check if already running
    if is_port_in_use(frontend_port):
        print(f"   ℹ️  Frontend already running on port {frontend_port}")
        if is_port_in_use(backend_port):
            print(f"   ℹ️  Backend already running on port {backend_port}")
            return True, None, None

    # Check for config.json
    config_file = backend_dir / "config.json"
    if not config_file.exists():
        print(f"   ❌ Missing config.json in {backend_dir}")
        print("      Run: cp app/backend/config.json.example app/backend/config.json")
        return False, None, None

    # Start backend
    print(f"   Starting backend on port {backend_port}...")
    venv_python = backend_dir / ".venv" / "bin" / "python"

    backend_proc = subprocess.Popen(
        [str(venv_python), "main.py"],
        cwd=str(backend_dir),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    # Wait for backend
    backend_url = f"http://localhost:{backend_port}/health"
    print(f"   Waiting for backend ({backend_url})...")
    if not wait_for_url(backend_url, timeout=30):
        print("   ❌ Backend failed to start")
        backend_proc.terminate()
        return False, None, None
    print("   ✅ Backend started")

    # Start frontend
    print(f"   Starting frontend on port {frontend_port}...")
    frontend_proc = subprocess.Popen(
        ["npm", "run", "dev"],
        cwd=str(frontend_dir),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    # Wait for frontend
    frontend_url = f"http://localhost:{frontend_port}"
    print(f"   Waiting for frontend ({frontend_url})...")
    if not wait_for_url(frontend_url, timeout=30):
        print("   ❌ Frontend failed to start")
        frontend_proc.terminate()
        backend_proc.terminate()
        return False, None, None
    print("   ✅ Frontend started")

    print("   ✅ Application servers running")
    return True, backend_proc, frontend_proc


def stop_application(backend_proc: Optional[subprocess.Popen], frontend_proc: Optional[subprocess.Popen]):
    """Stop the application servers."""
    print("\n🛑 Stopping application servers...")

    if frontend_proc:
        frontend_proc.terminate()
        try:
            frontend_proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            frontend_proc.kill()
        print("   ✅ Frontend stopped")

    if backend_proc:
        backend_proc.terminate()
        try:
            backend_proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            backend_proc.kill()
        print("   ✅ Backend stopped")


def create_test_definition(
    adw_id: str,
    auth_data: dict,
    application_url: str
) -> str:
    """Create a test definition JSON file for the direct Playwright runner.

    These tests are designed for the ayzer-webapp-template UI structure:
    - Login page with email/password form
    - Dashboard with admin cards (User Management, Role Management, etc.)
    - Sidebar navigation with user profile dropdown
    - Profile page with editable user information

    Returns the path to the created JSON file.
    """
    test_dir = Path(f"agents/{adw_id}/smoke_test")
    test_dir.mkdir(parents=True, exist_ok=True)

    test_definition = {
        "application_url": application_url,
        "auth": {
            "access_token": auth_data.get("access_token", ""),
            "refresh_token": auth_data.get("refresh_token", "")
        },
        "tests": [
            {
                "name": "Dashboard Loads After Auth",
                "description": "Verify authenticated user sees dashboard with sidebar navigation",
                "steps": [
                    {"action": "navigate", "url": "/dashboard"},
                    {"action": "wait", "timeout": 1500},
                    {"action": "screenshot", "name": "01_dashboard.png"},
                    {"action": "waitForSelector", "selector": "main", "timeout": 5000},
                    {"action": "waitForSelector", "selector": "[data-sidebar='sidebar']", "timeout": 5000},
                    {"action": "screenshot", "name": "02_dashboard_loaded.png"}
                ]
            },
            {
                "name": "Sidebar Navigation Works",
                "description": "Verify sidebar menu items are visible and Files link works",
                "steps": [
                    {"action": "navigate", "url": "/dashboard"},
                    {"action": "wait", "timeout": 1000},
                    {"action": "waitForSelector", "selector": "[data-sidebar='menu']", "timeout": 5000},
                    {"action": "screenshot", "name": "03_sidebar.png"},
                    {"action": "click", "selector": "a[href='/files']"},
                    {"action": "wait", "timeout": 1000},
                    {"action": "screenshot", "name": "04_files_page.png"}
                ]
            },
            {
                "name": "Profile Page Accessible",
                "description": "Verify profile page loads with user form fields",
                "steps": [
                    {"action": "navigate", "url": "/profile"},
                    {"action": "wait", "timeout": 1500},
                    {"action": "screenshot", "name": "05_profile_page.png"},
                    {"action": "waitForSelector", "selector": "input[name='firstName']", "timeout": 5000},
                    {"action": "waitForSelector", "selector": "input[name='lastName']", "timeout": 5000},
                    {"action": "screenshot", "name": "06_profile_loaded.png"}
                ]
            },
            {
                "name": "Admin Users Page",
                "description": "Verify admin can access user management page",
                "steps": [
                    {"action": "navigate", "url": "/admin/users"},
                    {"action": "wait", "timeout": 1500},
                    {"action": "screenshot", "name": "07_admin_users.png"},
                    {"action": "waitForSelector", "selector": "table", "timeout": 5000},
                    {"action": "screenshot", "name": "08_users_table.png"}
                ]
            }
        ]
    }

    test_file = test_dir / "smoke_tests.json"
    with open(test_file, "w") as f:
        json.dump(test_definition, f, indent=2)

    return str(test_file)


def run_smoke_test(
    adw_id: str,
    spec_file: str,
    auth_data: dict,
    application_url: str
) -> dict:
    """Run the smoke test using the DIRECT Playwright runner (no MCP).

    This is ~10x faster than the old MCP-based approach.
    """
    print(f"\n🔥 Running smoke test (direct Playwright execution)...")
    print(f"   Spec file: {spec_file}")
    print(f"   Application URL: {application_url}")

    # Create screenshot directory
    screenshot_dir = Path(f"agents/{adw_id}/smoke_test/img")
    screenshot_dir.mkdir(parents=True, exist_ok=True)

    # Create test definition JSON
    print("   Creating test definition...")
    test_definition_path = create_test_definition(adw_id, auth_data, application_url)
    print(f"   ✅ Test definition: {test_definition_path}")

    # Get path to the direct Playwright runner
    runner_script = Path(__file__).parent.parent / "smoke_test_runner.py"

    if not runner_script.exists():
        return {
            "test_name": "Dashboard Page Verification",
            "status": "failed",
            "test_description": "Smoke test runner not found",
            "screenshots": [],
            "error": f"Runner script not found: {runner_script}"
        }

    # Run the direct Playwright runner
    cmd = [
        "uv", "run", str(runner_script),
        test_definition_path,
        "--screenshot-dir", str(screenshot_dir)
    ]

    print(f"\n⏳ Executing smoke tests directly (this should be fast ~10-20s)...")

    try:
        env = os.environ.copy()
        env["SMOKE_TEST_HEADLESS"] = "false"  # Show browser for debugging

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120,  # 2 minute timeout (should complete much faster)
            env=env,
        )

        # Parse JSON output from runner
        if result.stdout:
            try:
                results_data = json.loads(result.stdout)

                # Aggregate results
                all_passed = all(r.get("status") == "passed" for r in results_data)
                all_screenshots = []
                all_errors = []

                for r in results_data:
                    all_screenshots.extend(r.get("screenshots", []))
                    if r.get("error"):
                        all_errors.append(f"{r.get('test_name')}: {r.get('error')}")

                return {
                    "test_name": "Dashboard Page Verification",
                    "status": "passed" if all_passed else "failed",
                    "test_description": f"Executed {len(results_data)} smoke tests",
                    "screenshots": all_screenshots,
                    "error": "; ".join(all_errors) if all_errors else None,
                    "details": results_data  # Include individual test results
                }
            except json.JSONDecodeError as e:
                print(f"⚠️ Failed to parse runner output: {e}")
                print(f"   stdout: {result.stdout[:500]}")

        # If we get here, something went wrong
        return {
            "test_name": "Dashboard Page Verification",
            "status": "failed",
            "test_description": "Smoke test execution failed",
            "screenshots": list(str(s) for s in screenshot_dir.glob("*.png")),
            "error": result.stderr or "Unknown error"
        }

    except subprocess.TimeoutExpired:
        print("❌ Smoke test timed out after 2 minutes")
        return {
            "test_name": "Dashboard Page Verification",
            "status": "failed",
            "test_description": "Smoke test timed out",
            "screenshots": [],
            "error": "Execution timed out after 2 minutes"
        }
    except Exception as e:
        print(f"❌ Error running smoke test: {e}")
        return {
            "test_name": "Dashboard Page Verification",
            "status": "failed",
            "test_description": "Smoke test execution error",
            "screenshots": [],
            "error": str(e)
        }


def print_results(results: dict, adw_id: str):
    """Print the smoke test results in a formatted way."""
    print("\n" + "=" * 60)
    print("🔥 SMOKE TEST RESULTS")
    print("=" * 60)

    status_emoji = "✅" if results.get("status") == "passed" else "❌"
    print(f"\n{status_emoji} Test: {results.get('test_name')}")
    print(f"   Status: {results.get('status', 'unknown').upper()}")
    print(f"   Description: {results.get('test_description')}")

    if results.get("error"):
        print(f"   Error: {results.get('error')}")

    # Print individual test results if available
    if results.get("details"):
        print("\n📋 Individual Test Results:")
        for detail in results["details"]:
            status_icon = "✅" if detail.get("status") == "passed" else "❌"
            print(f"   {status_icon} {detail.get('test_name')}: {detail.get('status')}")
            if detail.get("error"):
                print(f"      Error: {detail.get('error')}")

    screenshots = results.get("screenshots", [])
    if screenshots:
        print(f"\n📸 Screenshots captured ({len(screenshots)}):")
        for screenshot in screenshots:
            print(f"   - {screenshot}")
    else:
        print("\n📸 No screenshots captured")

    print(f"\n📁 Test artifacts: agents/{adw_id}/smoke_test/")
    print("=" * 60)


def main():
    """Main entry point."""
    load_dotenv()

    parser = argparse.ArgumentParser(
        description="Standalone Smoke Test Runner",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    parser.add_argument(
        "--adw-id",
        help="Custom ADW ID (default: auto-generated)"
    )
    parser.add_argument(
        "--skip-cleanup",
        action="store_true",
        help="Keep test data after completion for debugging"
    )
    parser.add_argument(
        "--skip-seed",
        action="store_true",
        help="Skip database seeding (use existing test data)"
    )
    parser.add_argument(
        "--skip-app",
        action="store_true",
        help="Don't start/stop the app (assumes it's already running)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run setup/teardown only, skip actual browser tests (useful for WSL)"
    )
    args = parser.parse_args()

    print("=" * 60)
    print("🔥 STANDALONE SMOKE TEST RUNNER (Direct Playwright)")
    print("=" * 60)

    # Generate or use provided ADW ID
    adw_id = args.adw_id or generate_adw_id()
    print(f"\n🆔 ADW ID: {adw_id}")

    # Check prerequisites
    print("\n📋 Checking prerequisites...")
    prereqs_ok, errors, warnings = check_prerequisites(skip_chrome_check=args.dry_run)

    if warnings:
        print("⚠️ Warnings:")
        for warning in warnings:
            print(f"   - {warning}")

    if not prereqs_ok:
        print("❌ Prerequisites not met:")
        for error in errors:
            print(f"   - {error}")
        print("\n💡 Tips:")
        print("   - Ensure Chrome is installed (macOS only)")
        print("   - Ensure adws/smoke_test_runner.py exists")
        print("   - Use --dry-run to test setup/teardown without browser tests")
        sys.exit(1)
    print("✅ Prerequisites check passed")

    # Create spec file
    print("\n📝 Creating sample spec file...")
    spec_file = create_spec_file(adw_id)
    print(f"✅ Spec file created: {spec_file}")

    # Seed database
    auth_data = None
    if not args.skip_seed:
        auth_data = seed_smoke_test_data(adw_id)
        if not auth_data:
            print("❌ Failed to seed smoke test data")
            print("   Make sure the backend database is running")
            sys.exit(1)
    else:
        print("\n⏭️ Skipping database seeding (--skip-seed)")
        # Use placeholder auth data
        auth_data = {
            "access_token": "SKIP_SEED_TOKEN",
            "refresh_token": "SKIP_SEED_TOKEN",
            "org_slug": f"smoke-test-{adw_id}"
        }

    # Get application URL
    application_url = get_application_url()
    print(f"\n🌐 Application URL: {application_url}")

    # Start application (unless dry-run or skip-app)
    backend_proc = None
    frontend_proc = None
    app_started_by_us = False

    if not args.dry_run and not args.skip_app:
        success, backend_proc, frontend_proc = start_application()
        if not success:
            print("❌ Failed to start application")
            if not args.skip_cleanup and not args.skip_seed:
                teardown_smoke_test_data(adw_id)
            sys.exit(1)
        app_started_by_us = backend_proc is not None or frontend_proc is not None
    elif args.skip_app:
        print("\n⏭️ Skipping app start (--skip-app)")

    # Run smoke test (or dry-run)
    results = None
    try:
        if args.dry_run:
            print("\n🏃 DRY RUN MODE - Skipping browser tests")
            print("   ✅ Spec file created")
            print("   ✅ Database seeded" if not args.skip_seed else "   ⏭️ Database seeding skipped")
            print(f"   📁 Test artifacts would be in: agents/{adw_id}/smoke_test/")
            print("\n💡 On macOS, run without --dry-run to execute browser tests")
            results = {
                "test_name": "Dry Run",
                "status": "passed",
                "test_description": "Setup/teardown verification completed",
                "screenshots": [],
                "error": None
            }
        else:
            results = run_smoke_test(adw_id, spec_file, auth_data, application_url)
            print_results(results, adw_id)
    finally:
        # Stop application if we started it
        if app_started_by_us:
            stop_application(backend_proc, frontend_proc)

        # Cleanup database
        if not args.skip_cleanup and not args.skip_seed:
            teardown_smoke_test_data(adw_id)
        elif args.skip_cleanup:
            print(f"\n⏭️ Skipping cleanup (--skip-cleanup)")
            print(f"   Run manually: python app/backend/scripts/teardown_smoke_test.py --adw-id {adw_id}")

    # Exit with appropriate code
    if results and results.get("status") == "passed":
        print("\n✅ Smoke test passed!")
        sys.exit(0)
    else:
        print("\n❌ Smoke test failed")
        sys.exit(1)


if __name__ == "__main__":
    main()
