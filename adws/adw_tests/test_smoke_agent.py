#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "python-dotenv",
#     "pydantic",
# ]
# ///

"""
Agent-Based Smoke Test Runner

This script tests the FULL smoke test workflow using Claude to generate
test definitions dynamically based on a spec file. This validates that:
1. The /smoke_test command works correctly
2. Claude generates valid test definitions with correct selectors
3. The smoke_test_runner.py executes the generated tests

Unlike test_smoke_standalone.py (which uses hardcoded tests for speed),
this test validates the complete agent-based test generation pipeline.

Usage:
  uv run adws/adw_tests/test_smoke_agent.py [--adw-id <id>] [--skip-cleanup]

Options:
  --adw-id        Custom ADW ID (default: auto-generated)
  --skip-cleanup  Keep test data after completion for debugging
  --skip-seed     Skip database seeding (use existing test data)
  --skip-app      Don't start/stop the app (assumes it's already running)

Example:
  uv run adws/adw_tests/test_smoke_agent.py
  uv run adws/adw_tests/test_smoke_agent.py --skip-app  # App already running
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
from adw_modules.agent import execute_template
from adw_modules.data_types import AgentTemplateRequest

import time
import urllib.request
import urllib.error


# Sample specification that describes what to test
# This simulates a real feature spec that would come from an ADW workflow
SAMPLE_SPEC = """# Feature: Dashboard and Profile Verification

## Feature Description
Verify that the core authenticated user experience works correctly, including
the dashboard page, sidebar navigation, and profile management.

## User Story
As an authenticated admin user
I want to access the dashboard and manage my profile
So that I can use the application's core features

## Expected UI Elements
- Dashboard page with sidebar navigation
- Sidebar with menu items (Dashboard, Files, etc.)
- Profile page with editable user information (firstName, lastName fields)
- Admin section with user management (table of users)

## Acceptance Criteria
1. Dashboard page loads with sidebar navigation visible
2. Sidebar menu items are clickable and navigate correctly
3. Profile page displays user form with firstName and lastName inputs
4. Admin users page shows a table of users

## Technical Notes
- Forms use react-hook-form with `name` attribute (not `id`)
- Sidebar uses `data-sidebar` attributes for structure
- Navigation uses standard `a[href='...']` links
"""


def generate_adw_id() -> str:
    """Generate a unique ADW ID for the smoke test."""
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    short_uuid = uuid.uuid4().hex[:8]
    return f"smoke-agent-{timestamp}-{short_uuid}"


def check_prerequisites() -> tuple[bool, list[str], list[str]]:
    """Check if all prerequisites are met for running smoke tests."""
    errors = []
    warnings = []

    # Check Chrome availability
    chrome_available, chrome_reason = is_chrome_available()
    if not chrome_available:
        errors.append(f"Chrome not available: {chrome_reason}")

    # Check if smoke_test_runner.py exists
    runner_script = Path(__file__).parent.parent / "smoke_test_runner.py"
    if not runner_script.exists():
        errors.append(f"Smoke test runner not found: {runner_script}")

    # Check if Claude Code is available
    claude_path = os.getenv("CLAUDE_CODE_PATH", "claude")
    try:
        result = subprocess.run(
            [claude_path, "--version"],
            capture_output=True,
            text=True,
            timeout=10
        )
        if result.returncode != 0:
            errors.append(f"Claude Code CLI not functional at '{claude_path}'")
    except FileNotFoundError:
        errors.append(f"Claude Code CLI not found at '{claude_path}'")
    except subprocess.TimeoutExpired:
        errors.append("Claude Code CLI timed out during version check")

    return len(errors) == 0, errors, warnings


def create_spec_file(adw_id: str) -> str:
    """Create a spec file for the smoke test."""
    agents_dir = Path(f"agents/{adw_id}")
    agents_dir.mkdir(parents=True, exist_ok=True)

    spec_file = agents_dir / "spec.md"
    spec_file.write_text(SAMPLE_SPEC)

    return str(spec_file)


def seed_smoke_test_data(adw_id: str) -> Optional[dict]:
    """Seed the database with smoke test organization and user."""
    print(f"\n📦 Seeding smoke test data for ADW ID: {adw_id}")

    project_root = Path.cwd()
    backend_dir = project_root / "app" / "backend"
    seed_script = backend_dir / "scripts" / "seed_smoke_test.py"

    if not seed_script.exists():
        print(f"❌ Seed script not found: {seed_script}")
        return None

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

    project_root = Path.cwd()
    backend_dir = project_root / "app" / "backend"
    teardown_script = backend_dir / "scripts" / "teardown_smoke_test.py"

    if not teardown_script.exists():
        print(f"⚠️ Teardown script not found: {teardown_script}")
        return False

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
    """Start the backend and frontend servers."""
    print("\n🚀 Starting application servers...")

    project_root = Path.cwd()
    backend_dir = project_root / "app" / "backend"
    frontend_dir = project_root / "app" / "frontend"

    backend_port, frontend_port = get_ports()

    if is_port_in_use(frontend_port):
        print(f"   ℹ️  Frontend already running on port {frontend_port}")
        if is_port_in_use(backend_port):
            print(f"   ℹ️  Backend already running on port {backend_port}")
            return True, None, None

    config_file = backend_dir / "config.json"
    if not config_file.exists():
        print(f"   ❌ Missing config.json in {backend_dir}")
        return False, None, None

    print(f"   Starting backend on port {backend_port}...")
    venv_python = backend_dir / ".venv" / "bin" / "python"

    backend_proc = subprocess.Popen(
        [str(venv_python), "main.py"],
        cwd=str(backend_dir),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    backend_url = f"http://localhost:{backend_port}/health"
    print(f"   Waiting for backend ({backend_url})...")
    if not wait_for_url(backend_url, timeout=30):
        print("   ❌ Backend failed to start")
        backend_proc.terminate()
        return False, None, None
    print("   ✅ Backend started")

    print(f"   Starting frontend on port {frontend_port}...")
    frontend_proc = subprocess.Popen(
        ["npm", "run", "dev"],
        cwd=str(frontend_dir),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

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


def run_smoke_test_with_agent(
    adw_id: str,
    spec_file: str,
    application_url: str
) -> dict:
    """Run smoke tests using the Claude agent to generate test definitions.

    This calls the /smoke_test command which:
    1. Reads the spec file
    2. Analyzes the codebase for correct selectors
    3. Generates a test definition JSON
    4. Executes tests with the direct Playwright runner
    """
    print(f"\n🤖 Running smoke test with Claude agent...")
    print(f"   Spec file: {spec_file}")
    print(f"   Application URL: {application_url}")

    # Create the agent request
    request = AgentTemplateRequest(
        agent_name="smoke_test_agent",
        slash_command="/smoke_test",
        args=[spec_file, adw_id, "smoke_test_agent", application_url],
        adw_id=adw_id,
        working_dir=str(Path.cwd()),
    )

    print(f"\n⏳ Claude is generating and executing smoke tests...")
    print(f"   (This may take 1-2 minutes as Claude analyzes the codebase)")

    try:
        response = execute_template(request)

        if not response.success:
            print(f"❌ Smoke test agent failed")
            return {
                "test_name": "Agent Smoke Test",
                "status": "failed",
                "test_description": "Claude agent execution failed",
                "screenshots": [],
                "error": response.output[:500] if response.output else "Unknown error"
            }

        # Parse the agent's output
        output = response.output
        print(f"\n📤 Agent output received ({len(output)} chars)")

        # Try to extract JSON results from the output
        try:
            # Look for JSON array in the output
            import re

            # Try to find JSON array
            json_match = re.search(r'\[\s*\{.*?\}\s*\]', output, re.DOTALL)
            if json_match:
                results_data = json.loads(json_match.group())

                all_passed = all(r.get("status") == "passed" for r in results_data)
                all_screenshots = []
                all_errors = []

                for r in results_data:
                    all_screenshots.extend(r.get("screenshots", []))
                    if r.get("error"):
                        all_errors.append(f"{r.get('test_name')}: {r.get('error')}")

                return {
                    "test_name": "Agent Smoke Test",
                    "status": "passed" if all_passed else "failed",
                    "test_description": f"Claude generated and executed {len(results_data)} smoke tests",
                    "screenshots": all_screenshots,
                    "error": "; ".join(all_errors) if all_errors else None,
                    "details": results_data
                }

            # Check for skip status
            if '"status": "skipped"' in output or "'status': 'skipped'" in output:
                return {
                    "test_name": "Agent Smoke Test",
                    "status": "skipped",
                    "test_description": "Smoke tests were skipped",
                    "screenshots": [],
                    "error": "Chrome not available or tests skipped"
                }

            # Couldn't parse structured output
            return {
                "test_name": "Agent Smoke Test",
                "status": "unknown",
                "test_description": "Could not parse agent output",
                "screenshots": [],
                "error": f"Unparseable output: {output[:300]}..."
            }

        except json.JSONDecodeError as e:
            return {
                "test_name": "Agent Smoke Test",
                "status": "failed",
                "test_description": "Failed to parse agent JSON output",
                "screenshots": [],
                "error": f"JSON parse error: {e}"
            }

    except Exception as e:
        print(f"❌ Error running smoke test agent: {e}")
        return {
            "test_name": "Agent Smoke Test",
            "status": "failed",
            "test_description": "Agent execution error",
            "screenshots": [],
            "error": str(e)
        }


def print_results(results: dict, adw_id: str):
    """Print the smoke test results in a formatted way."""
    print("\n" + "=" * 60)
    print("🤖 AGENT SMOKE TEST RESULTS")
    print("=" * 60)

    status_emoji = "✅" if results.get("status") == "passed" else "❌"
    if results.get("status") == "skipped":
        status_emoji = "⏭️"

    print(f"\n{status_emoji} Test: {results.get('test_name')}")
    print(f"   Status: {results.get('status', 'unknown').upper()}")
    print(f"   Description: {results.get('test_description')}")

    if results.get("error"):
        print(f"   Error: {results.get('error')}")

    if results.get("details"):
        print("\n📋 Individual Test Results:")
        for detail in results["details"]:
            status_icon = "✅" if detail.get("status") == "passed" else "❌"
            if detail.get("status") == "skipped":
                status_icon = "⏭️"
            print(f"   {status_icon} {detail.get('test_name')}: {detail.get('status')}")
            if detail.get("error"):
                print(f"      Error: {detail.get('error')[:100]}...")

    screenshots = results.get("screenshots", [])
    if screenshots:
        print(f"\n📸 Screenshots captured ({len(screenshots)}):")
        for screenshot in screenshots[:5]:  # Limit display
            print(f"   - {screenshot}")
        if len(screenshots) > 5:
            print(f"   ... and {len(screenshots) - 5} more")
    else:
        print("\n📸 No screenshots captured")

    print(f"\n📁 Test artifacts: agents/{adw_id}/smoke_test_agent/")
    print("=" * 60)


def main():
    """Main entry point."""
    load_dotenv()

    parser = argparse.ArgumentParser(
        description="Agent-Based Smoke Test Runner",
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
    args = parser.parse_args()

    print("=" * 60)
    print("🤖 AGENT-BASED SMOKE TEST RUNNER")
    print("=" * 60)
    print("\nThis test uses Claude to generate smoke tests dynamically.")
    print("It validates the full /smoke_test workflow.\n")

    # Generate or use provided ADW ID
    adw_id = args.adw_id or generate_adw_id()
    print(f"🆔 ADW ID: {adw_id}")

    # Check prerequisites
    print("\n📋 Checking prerequisites...")
    prereqs_ok, errors, warnings = check_prerequisites()

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
        print("   - Ensure Claude Code CLI is installed")
        print("   - Ensure adws/smoke_test_runner.py exists")
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
        auth_data = {
            "access_token": "SKIP_SEED_TOKEN",
            "refresh_token": "SKIP_SEED_TOKEN",
            "org_slug": f"smoke-test-{adw_id}"
        }

    # Get application URL
    application_url = get_application_url()
    print(f"\n🌐 Application URL: {application_url}")

    # Start application
    backend_proc = None
    frontend_proc = None
    app_started_by_us = False

    if not args.skip_app:
        success, backend_proc, frontend_proc = start_application()
        if not success:
            print("❌ Failed to start application")
            if not args.skip_cleanup and not args.skip_seed:
                teardown_smoke_test_data(adw_id)
            sys.exit(1)
        app_started_by_us = backend_proc is not None or frontend_proc is not None
    else:
        print("\n⏭️ Skipping app start (--skip-app)")

    # Run smoke test with agent
    results = None
    try:
        results = run_smoke_test_with_agent(adw_id, spec_file, application_url)
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
        print("\n✅ Agent smoke test passed!")
        sys.exit(0)
    elif results and results.get("status") == "skipped":
        print("\n⏭️ Agent smoke test skipped")
        sys.exit(0)
    else:
        print("\n❌ Agent smoke test failed")
        sys.exit(1)


if __name__ == "__main__":
    main()
