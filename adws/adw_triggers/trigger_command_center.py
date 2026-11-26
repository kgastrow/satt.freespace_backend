#!/usr/bin/env -S uv run
# /// script
# dependencies = ["websockets>=12.0", "watchdog>=4.0", "psutil>=5.9", "python-dotenv", "pydantic"]
# ///

"""
Command Center Agent - Ayzer ADW Trigger

Lightweight WebSocket agent that connects a codebase to the centralized
Ayzer Command Center. Runs as a long-lived process alongside the existing
webhook and cron triggers.

Features:
- Outbound WebSocket connection with first-message API key auth
- Reports ADW status changes and streams logs to the command center
- Receives work triggers (create issues, launch workflows)
- Receives control commands (cancel, resume)
- Automatic reconnection with exponential backoff
- Lockfile prevents duplicate instances per codebase

Usage:
    uv run trigger_command_center.py

Environment Requirements:
    COMMAND_CENTER_URL      - WebSocket URL (e.g., wss://agent-bridge.ayzer.ai/ws/agent)
    COMMAND_CENTER_API_KEY  - Per-codebase API key issued by the command center
    CODEBASE_NAME           - Human-readable codebase name
    MACHINE_NAME            - Human-readable machine name
    ANTHROPIC_API_KEY       - For running ADW workflows
    GITHUB_PAT              - For GitHub operations (gh CLI)
    CLAUDE_CODE_PATH        - Path to Claude CLI (default: "claude")
    ADW_CODEBASE_INDEX      - Port partition index (default: 0)
    ADW_MAX_CODEBASES       - Total port partitions (default: 1)

Optional:
    CC_AGENT_HEALTH_PORT    - Port for local health endpoint (default: disabled)
"""

import asyncio
import fcntl
import json
import logging
import os
import signal
import sys
import tempfile
import threading
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler

from dotenv import load_dotenv

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from adw_modules.command_center_client import CommandCenterClient

# Load environment variables
load_dotenv()

# Custom print with timestamps
_original_print = print


def print(*args, **kwargs):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    _original_print(f"[{timestamp}]", *args, **kwargs)


# Configuration
COMMAND_CENTER_URL = os.getenv("COMMAND_CENTER_URL", "")
COMMAND_CENTER_API_KEY = os.getenv("COMMAND_CENTER_API_KEY", "")
CODEBASE_NAME = os.getenv("CODEBASE_NAME", "")
MACHINE_NAME = os.getenv("MACHINE_NAME", "")
HEALTH_PORT = os.getenv("CC_AGENT_HEALTH_PORT", "")


def setup_logging():
    """Configure logging to stdout with timestamps."""
    logging.basicConfig(
        level=logging.INFO,
        format="[%(asctime)s] %(name)s %(levelname)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[logging.StreamHandler(sys.stdout)],
    )
    # Reduce noise from websockets library
    logging.getLogger("websockets").setLevel(logging.WARNING)


def acquire_lockfile(codebase_name: str) -> int:
    """Acquire a lockfile to prevent duplicate agent instances.

    Args:
        codebase_name: Used to construct lockfile path

    Returns:
        File descriptor of the lock (keep open for process lifetime)

    Raises:
        SystemExit: If another instance is already running
    """
    lock_path = os.path.join(tempfile.gettempdir(), f"cc-agent-{codebase_name}.lock")
    fd = os.open(lock_path, os.O_CREAT | os.O_RDWR)

    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except (IOError, OSError):
        print(f"ERROR: Another command center agent for '{codebase_name}' is already running.")
        print(f"Lock file: {lock_path}")
        os.close(fd)
        sys.exit(1)

    # Write PID to lock file for debugging
    os.truncate(fd, 0)
    os.lseek(fd, 0, os.SEEK_SET)
    os.write(fd, str(os.getpid()).encode())

    return fd


def validate_config():
    """Validate required environment variables."""
    missing = []
    if not COMMAND_CENTER_URL:
        missing.append("COMMAND_CENTER_URL")
    if not COMMAND_CENTER_API_KEY:
        missing.append("COMMAND_CENTER_API_KEY")
    if not CODEBASE_NAME:
        missing.append("CODEBASE_NAME")
    if not MACHINE_NAME:
        missing.append("MACHINE_NAME")

    if missing:
        print(f"ERROR: Missing required environment variables: {', '.join(missing)}")
        print("Set these in your .env file or environment.")
        sys.exit(1)


def start_health_server(client: CommandCenterClient, port: int):
    """Start a simple health check HTTP endpoint in a daemon thread."""

    class HealthHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == "/health":
                body = json.dumps({
                    "status": "connected" if client.is_connected else "disconnected",
                    "codebase": CODEBASE_NAME,
                    "machine": MACHINE_NAME,
                    "active_adws": client.active_adw_count,
                    "last_heartbeat": client.last_heartbeat_at,
                })
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(body.encode())
            else:
                self.send_response(404)
                self.end_headers()

        def log_message(self, format, *args):
            pass  # Suppress access logs

    server = HTTPServer(("127.0.0.1", port), HealthHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    print(f"Health endpoint: http://127.0.0.1:{port}/health")


async def main():
    """Entry point for the command center agent."""
    setup_logging()

    # Check if command center is configured
    if not COMMAND_CENTER_URL:
        print("COMMAND_CENTER_URL not set — command center agent not starting.")
        print("Set COMMAND_CENTER_URL in .env to enable command center connectivity.")
        return

    validate_config()

    # Acquire lockfile
    lock_fd = acquire_lockfile(CODEBASE_NAME)

    # Determine project root (parent of adws/ directory)
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    print(f"Ayzer Command Center Agent")
    print(f"  Codebase:  {CODEBASE_NAME}")
    print(f"  Machine:   {MACHINE_NAME}")
    print(f"  Server:    {COMMAND_CENTER_URL}")
    print(f"  Project:   {project_root}")
    print(f"  PID:       {os.getpid()}")

    # Create client
    client = CommandCenterClient(
        url=COMMAND_CENTER_URL,
        api_key=COMMAND_CENTER_API_KEY,
        codebase_name=CODEBASE_NAME,
        machine_name=MACHINE_NAME,
        project_root=project_root,
    )

    # Start health endpoint if configured
    if HEALTH_PORT:
        try:
            start_health_server(client, int(HEALTH_PORT))
        except Exception as e:
            print(f"Warning: Could not start health endpoint on port {HEALTH_PORT}: {e}")

    # Handle graceful shutdown — use request_stop() which is thread-safe
    # and closes the WebSocket to unblock the recv_loop
    def signal_handler(sig, frame):
        print(f"Received signal {sig}, shutting down...")
        client.request_stop()

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Run the client
    try:
        await client.run()
    finally:
        os.close(lock_fd)
        print("Command center agent stopped.")


if __name__ == "__main__":
    asyncio.run(main())
