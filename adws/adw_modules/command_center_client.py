"""WebSocket client for command center communication.

Manages the persistent outbound WebSocket connection from a codebase agent
to the centralized command center. Handles:
- First-message authentication with API key
- Protocol version negotiation
- Automatic reconnection with exponential backoff
- Heartbeat loop
- Message routing (incoming commands -> handlers)
- Event replay buffer for reconnection
- Outbound message queue with backpressure tracking
"""

import asyncio
import json
import logging
import os
import subprocess
import time
from collections import deque
from datetime import datetime, timezone
from typing import Any, Callable, Deque, Dict, List, Optional

import websockets
from websockets.asyncio.client import ClientConnection

from adw_modules.file_watcher import ADWFileWatcher, TERMINAL_STAGES
from adw_modules.github import check_gh_auth
from adw_modules.github_data_provider import fetch_github_data, fetch_pr_for_branch
from adw_modules.log_streamer import LogStreamer
from adw_modules.state import ADWState
from adw_modules.system_info import get_system_load, get_system_info
from adw_modules.utils import get_safe_subprocess_env, make_adw_id
from adw_modules.workflow_control import stop_workflow, is_process_running
from adw_modules.workflow_ops import AVAILABLE_ADW_WORKFLOWS, find_latest_adw_for_issue

logger = logging.getLogger(__name__)

PROTOCOL_VERSION = 1
HEARTBEAT_INTERVAL = 30  # seconds
RECONNECT_BASE_DELAY = 1  # seconds
RECONNECT_MAX_DELAY = 60  # seconds
RECONNECT_RESET_AFTER = 60  # reset backoff after this many seconds connected
AUTH_TIMEOUT = 10  # seconds
REPLAY_BUFFER_MAX = 500


def _parse_adw_id_timestamp(adw_id: str) -> Optional[float]:
    """Parse the timestamp prefix from an ADW ID into epoch seconds.

    ADW ID format: YYYYMMDDHHMMSS-<12-hex-chars>
    Note: make_adw_id() uses local time (datetime.now()), so we parse
    as local time here to match.
    Returns None if parsing fails.
    """
    try:
        ts_str = adw_id[:14]
        dt = datetime.strptime(ts_str, "%Y%m%d%H%M%S")
        # No timezone — matches make_adw_id() which uses datetime.now() (local time)
        return dt.timestamp()
    except (ValueError, IndexError):
        return None


def _update_env_file(env_path: str, updates: Dict[str, str]):
    """Update key=value pairs in a .env file, preserving comments and order.

    If a key exists, its value is updated in place. If a key does not exist,
    it is appended at the end. Handles both KEY=value and KEY= (empty) formats.
    Preserves commented-out lines and blank lines.
    """
    lines = []
    updated_keys = set()

    if os.path.isfile(env_path):
        with open(env_path, "r") as f:
            lines = f.readlines()

    new_lines = []
    for line in lines:
        stripped = line.strip()
        # Skip comments and blank lines — keep as-is
        if not stripped or stripped.startswith("#"):
            new_lines.append(line)
            continue

        # Parse KEY=value
        if "=" in stripped:
            key = stripped.split("=", 1)[0].strip()
            if key in updates:
                new_lines.append(f"{key}={updates[key]}\n")
                updated_keys.add(key)
                continue

        new_lines.append(line)

    # Append any keys that weren't found in the file
    for key, value in updates.items():
        if key not in updated_keys:
            new_lines.append(f"{key}={value}\n")

    with open(env_path, "w") as f:
        f.writelines(new_lines)


class CommandCenterClient:
    """Manages WebSocket connection to the command center.

    This is the core orchestrator for the command center agent. It:
    1. Connects to the command center via WebSocket
    2. Authenticates with an API key
    3. Registers the codebase with metadata
    4. Runs a heartbeat loop
    5. Routes incoming messages to handlers
    6. Manages a file watcher for ADW state changes
    7. Manages a log streamer for JSONL output
    8. Buffers events during disconnection for replay
    """

    def __init__(
        self,
        url: str,
        api_key: str,
        codebase_name: str,
        machine_name: str,
        project_root: str,
    ):
        self._url = url
        self._api_key = api_key
        self._codebase_name = codebase_name
        self._machine_name = machine_name
        self._project_root = project_root

        # Connection state
        self._ws: Optional[ClientConnection] = None
        self._connected = False
        self._codebase_id: Optional[str] = None
        self._should_stop = False
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._last_heartbeat_at: Optional[str] = None

        # Message queue (asyncio.Queue is only accessed via _enqueue_threadsafe / _send_loop)
        self._send_queue: asyncio.Queue = asyncio.Queue()

        # Reconnection
        self._reconnect_delay = RECONNECT_BASE_DELAY
        self._connected_since: Optional[float] = None

        # Event replay buffer (bounded deque)
        self._replay_buffer: Deque[dict] = deque(maxlen=REPLAY_BUFFER_MAX)

        # ADW tracking
        self._adw_workflow_types: Dict[str, str] = {}  # adw_id -> workflow_type

        # Components (initialized in run())
        self._file_watcher: Optional[ADWFileWatcher] = None
        self._log_streamer: Optional[LogStreamer] = None

    # ─── Public API ──────────────────────────────────────────────

    async def run(self):
        """Main run loop. Connects, authenticates, and processes messages.
        Reconnects on disconnection with exponential backoff.
        """
        self._loop = asyncio.get_running_loop()
        self._init_components()

        while not self._should_stop:
            try:
                await self._connect_and_run()
            except Exception as e:
                if self._should_stop:
                    break
                logger.error(f"Connection error: {e}")

            if self._should_stop:
                break

            # Exponential backoff
            logger.info(f"Reconnecting in {self._reconnect_delay}s...")
            await asyncio.sleep(self._reconnect_delay)
            self._reconnect_delay = min(
                self._reconnect_delay * 2, RECONNECT_MAX_DELAY
            )

        self._cleanup_components()

    async def stop(self):
        """Signal the client to stop and close the WebSocket."""
        self._should_stop = True
        if self._ws:
            await self._ws.close()

    def request_stop(self):
        """Thread-safe stop request (for use from signal handlers)."""
        self._should_stop = True
        if self._loop and self._ws:
            self._loop.call_soon_threadsafe(
                lambda: asyncio.ensure_future(self._ws.close())
            )

    def get_pending_count(self) -> int:
        """Return number of pending outbound messages (for backpressure)."""
        return self._send_queue.qsize()

    @property
    def is_connected(self) -> bool:
        return self._connected

    @property
    def last_heartbeat_at(self) -> Optional[str]:
        return self._last_heartbeat_at

    @property
    def active_adw_count(self) -> int:
        if self._log_streamer:
            return len(self._log_streamer.get_active_adw_ids())
        return 0

    # ─── Connection lifecycle ────────────────────────────────────

    async def _connect_and_run(self):
        """Single connection attempt: connect, auth, register, run message loops."""
        logger.info(f"Connecting to {self._url}...")

        async with websockets.connect(
            self._url,
            ping_interval=20,
            ping_timeout=20,
            close_timeout=10,
            max_size=2**20,  # 1MB max message size
        ) as ws:
            self._ws = ws

            # Authenticate
            if not await self._authenticate():
                logger.error("Authentication failed")
                return

            self._connected = True
            self._connected_since = time.monotonic()
            logger.info(f"Connected and authenticated (codebase_id={self._codebase_id})")

            # Register
            await self._send_register()

            # Replay buffered events
            await self._replay_events()

            # Start log streaming for active ADWs
            self._sync_log_streaming()

            # Run message loops concurrently
            try:
                await asyncio.gather(
                    self._recv_loop(),
                    self._send_loop(),
                    self._heartbeat_loop(),
                )
            except websockets.ConnectionClosed:
                logger.warning("WebSocket connection closed")
            finally:
                self._connected = False
                self._ws = None

                # Reset backoff only if we were connected long enough
                if (
                    self._connected_since
                    and time.monotonic() - self._connected_since > RECONNECT_RESET_AFTER
                ):
                    self._reconnect_delay = RECONNECT_BASE_DELAY

    async def _authenticate(self) -> bool:
        """Perform first-message authentication handshake.

        On success, the server assigns a codebase_index and max_codebases
        for this machine, ensuring unique port/database partitioning across
        all codebases. These are applied to os.environ and persisted to .env.
        """
        auth_msg = {
            "type": "auth",
            "payload": {
                "api_key": self._api_key,
                "protocol_version": PROTOCOL_VERSION,
            },
        }
        await self._ws.send(json.dumps(auth_msg))

        try:
            raw = await asyncio.wait_for(self._ws.recv(), timeout=AUTH_TIMEOUT)
            response = json.loads(raw)

            if response.get("type") != "auth_result":
                logger.error(f"Unexpected auth response type: {response.get('type')}")
                return False

            payload = response.get("payload", {})
            if payload.get("success"):
                self._codebase_id = payload.get("codebase_id")

                # Apply server-assigned codebase index for port/db isolation
                codebase_index = payload.get("codebase_index")
                max_codebases = payload.get("max_codebases")
                if codebase_index is not None and max_codebases is not None:
                    self._apply_codebase_index(codebase_index, max_codebases)

                return True
            else:
                logger.error(f"Auth rejected: {payload.get('error', 'unknown')}")
                return False

        except asyncio.TimeoutError:
            logger.error("Auth response timed out")
            return False

    def _apply_codebase_index(self, codebase_index: int, max_codebases: int):
        """Apply server-assigned codebase index to the environment.

        With the machine-wide resource registry (the default, adw_modules/resources.py) the index no longer
        decides ports or worktree Redis databases; it still names the isolated PostgreSQL databases and the
        Playwright e2e runs' ports and Redis database. With ADW_RESOURCES=static it partitions all of them.

        Sets os.environ so that get_safe_subprocess_env() passes the correct
        values to launched workflows. Also persists to .env so that webhook/cron
        triggers and manual ADW launches on this machine use the same index.
        """
        current_index = os.environ.get("ADW_CODEBASE_INDEX", "0")
        current_max = os.environ.get("ADW_MAX_CODEBASES", "1")

        idx_str = str(codebase_index)
        max_str = str(max_codebases)

        if current_index == idx_str and current_max == max_str:
            return  # No change needed

        logger.info(
            f"Codebase index assigned by server: "
            f"ADW_CODEBASE_INDEX={idx_str} ADW_MAX_CODEBASES={max_str} "
            f"(was {current_index}/{current_max})"
        )

        # Update os.environ for this process and all child processes
        os.environ["ADW_CODEBASE_INDEX"] = idx_str
        os.environ["ADW_MAX_CODEBASES"] = max_str

        # Persist to .env so webhook/cron triggers use the same values
        env_path = os.path.join(self._project_root, ".env")
        try:
            _update_env_file(env_path, {
                "ADW_CODEBASE_INDEX": idx_str,
                "ADW_MAX_CODEBASES": max_str,
            })
            logger.info(f"Persisted codebase index to {env_path}")
        except Exception as e:
            logger.warning(f"Could not persist codebase index to .env: {e}")

    # ─── Message loops ───────────────────────────────────────────

    async def _recv_loop(self):
        """Receive and route incoming messages from the command center."""
        async for raw in self._ws:
            try:
                message = json.loads(raw)
                msg_type = message.get("type")

                handler = self._get_handler(msg_type)
                if handler:
                    asyncio.create_task(handler(message))
                else:
                    logger.warning(f"Unhandled message type: {msg_type}")

            except json.JSONDecodeError:
                logger.warning("Received non-JSON message")
            except Exception as e:
                logger.error(f"Error processing message: {e}")

    async def _send_loop(self):
        """Send queued outbound messages."""
        while not self._should_stop:
            try:
                message = await asyncio.wait_for(
                    self._send_queue.get(), timeout=1.0
                )
                await self._ws.send(json.dumps(message))
            except asyncio.TimeoutError:
                continue
            except websockets.ConnectionClosed:
                raise

    async def _heartbeat_loop(self):
        """Send periodic heartbeat messages."""
        while not self._should_stop:
            await asyncio.sleep(HEARTBEAT_INTERVAL)
            if not self._connected:
                break

            self._last_heartbeat_at = datetime.now(timezone.utc).isoformat()
            active_ids = list(self._log_streamer.get_active_adw_ids()) if self._log_streamer else []
            heartbeat = {
                "type": "heartbeat",
                "payload": {
                    "active_adw_ids": active_ids,
                    "system_load": get_system_load(),
                },
            }
            self._enqueue_threadsafe(heartbeat)

    # ─── Message handlers ────────────────────────────────────────

    def _get_handler(self, msg_type: str) -> Optional[Callable]:
        handlers = {
            "trigger_adw": self._handle_trigger_adw,
            "control_adw": self._handle_control_adw,
            "request_status": self._handle_request_status,
            "request_logs": self._handle_request_logs,
            "request_github_data": self._handle_request_github_data,
            "apply_patch": self._handle_apply_patch,
        }
        return handlers.get(msg_type)

    async def _handle_trigger_adw(self, message: dict):
        """Handle trigger_adw: create GitHub issue if needed, launch workflow."""
        request_id = message.get("request_id")
        payload = message.get("payload", {})
        workflow = payload.get("workflow")
        prompt = payload.get("prompt", "")
        model_set = payload.get("model_set", "base")
        issue_number = payload.get("issue_number")
        loop = asyncio.get_running_loop()

        try:
            # Validate workflow name against known workflows to prevent path traversal
            if workflow not in AVAILABLE_ADW_WORKFLOWS:
                await self._send_response(request_id, False, error=f"Unknown workflow: {workflow}")
                return

            # Check gh auth in thread pool to avoid blocking the event loop
            auth_error = await loop.run_in_executor(None, check_gh_auth)
            if auth_error:
                await self._send_response(request_id, False, error=f"gh CLI not authenticated: {auth_error}")
                return

            if not issue_number:
                # Create GitHub issue in thread pool
                def _create_issue():
                    cmd = ["gh", "issue", "create", "--title", prompt[:100], "--body", prompt]
                    return subprocess.run(
                        cmd, capture_output=True, text=True, timeout=30,
                        cwd=self._project_root, env=get_safe_subprocess_env(),
                    )

                result = await loop.run_in_executor(None, _create_issue)
                if result.returncode != 0:
                    await self._send_response(request_id, False, error=f"Failed to create issue: {result.stderr}")
                    return

                # Extract issue number from URL: https://github.com/org/repo/issues/42
                issue_url = result.stdout.strip()
                issue_number = issue_url.rstrip("/").split("/")[-1]

            # Generate ADW ID and create state
            adw_id = make_adw_id()
            state = ADWState(adw_id)
            state.update(
                adw_id=adw_id,
                issue_number=str(issue_number),
                model_set=model_set,
            )
            state.save("command_center_trigger")

            # Track workflow type
            self._adw_workflow_types[adw_id] = workflow

            # Launch workflow subprocess (Popen is non-blocking, fine on event loop)
            adws_dir = os.path.join(self._project_root, "adws")
            script = os.path.join(adws_dir, f"{workflow}.py")
            cmd = ["uv", "run", script, str(issue_number), adw_id]

            process = subprocess.Popen(
                cmd,
                cwd=self._project_root,
                env=get_safe_subprocess_env(),
                start_new_session=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

            # Store PID/PGID in state
            workflow_pid = process.pid
            workflow_pgid = os.getpgid(process.pid)
            state.update(workflow_pid=workflow_pid, workflow_pgid=workflow_pgid)
            state.save("command_center_trigger")

            logger.info(f"Launched {workflow} for issue #{issue_number} (ADW: {adw_id}, PID: {workflow_pid})")

            # Start log streaming for this ADW
            if self._log_streamer:
                self._log_streamer.add_adw(adw_id)

            await self._send_response(request_id, True, payload={
                "adw_id": adw_id,
                "issue_number": str(issue_number),
                "workflow": workflow,
                "pid": workflow_pid,
            })

        except Exception as e:
            logger.error(f"Error triggering ADW: {e}")
            await self._send_response(request_id, False, error=str(e))

    async def _handle_control_adw(self, message: dict):
        """Handle control_adw: cancel or resume a workflow."""
        request_id = message.get("request_id")
        payload = message.get("payload", {})
        adw_id = payload.get("adw_id")
        action = payload.get("action")
        loop = asyncio.get_running_loop()

        try:
            if action == "cancel":
                # stop_workflow does file I/O and process signaling — run in executor
                success, msg = await loop.run_in_executor(None, stop_workflow, adw_id)
                if success and self._log_streamer:
                    self._log_streamer.remove_adw(adw_id)
                await self._send_response(request_id, success, payload={"message": msg})

            elif action == "resume":
                # Look up the workflow type from in-memory tracker
                workflow = self._adw_workflow_types.get(adw_id)

                if not workflow:
                    # File I/O — run in executor
                    def _find_workflow():
                        state = ADWState.load(adw_id)
                        if state:
                            issue_num = state.get("issue_number")
                            if issue_num:
                                _, found = find_latest_adw_for_issue(issue_num)
                                return found
                        return None

                    workflow = await loop.run_in_executor(None, _find_workflow)

                if not workflow:
                    await self._send_response(request_id, False, error=f"Cannot determine workflow type for {adw_id}")
                    return

                # Validate workflow name
                if workflow not in AVAILABLE_ADW_WORKFLOWS:
                    await self._send_response(request_id, False, error=f"Unknown workflow: {workflow}")
                    return

                # Load state to get issue number
                state = ADWState.load(adw_id)
                if not state:
                    await self._send_response(request_id, False, error=f"No state found for {adw_id}")
                    return

                issue_number = state.get("issue_number")
                if not issue_number:
                    await self._send_response(request_id, False, error=f"No issue number in state for {adw_id}")
                    return

                # Launch with --resume flag (Popen is non-blocking)
                adws_dir = os.path.join(self._project_root, "adws")
                script = os.path.join(adws_dir, f"{workflow}.py")
                cmd = ["uv", "run", script, str(issue_number), adw_id, "--resume"]

                process = subprocess.Popen(
                    cmd,
                    cwd=self._project_root,
                    env=get_safe_subprocess_env(),
                    start_new_session=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )

                # Update state with new PID
                state.update(
                    workflow_pid=process.pid,
                    workflow_pgid=os.getpgid(process.pid),
                    workflow_stage=None,  # Will be set by the workflow
                )
                state.save("command_center_resume")

                self._adw_workflow_types[adw_id] = workflow
                if self._log_streamer:
                    self._log_streamer.add_adw(adw_id)

                await self._send_response(request_id, True, payload={
                    "message": f"Resumed {workflow} for ADW {adw_id}",
                    "pid": process.pid,
                })

            else:
                await self._send_response(request_id, False, error=f"Unknown action: {action}")

        except Exception as e:
            logger.error(f"Error controlling ADW {adw_id}: {e}")
            await self._send_response(request_id, False, error=str(e))

    async def _handle_request_status(self, message: dict):
        """Handle request_status: return current state snapshot."""
        request_id = message.get("request_id")

        active_adws = []
        if self._file_watcher:
            for adw_id, state_data in self._file_watcher.scan_active_adws():
                if is_process_running(state_data.get("workflow_pid")):
                    active_adws.append(self._build_adw_status(adw_id, state_data))

        await self._send_response(request_id, True, payload={
            "codebase_name": self._codebase_name,
            "machine_name": self._machine_name,
            "active_adws": active_adws,
            "system_load": get_system_load(),
        })

    async def _handle_request_logs(self, message: dict):
        """Handle request_logs: return historical log lines."""
        request_id = message.get("request_id")
        payload = message.get("payload", {})
        adw_id = payload.get("adw_id")
        agent_name = payload.get("agent_name")
        tail_lines = payload.get("tail_lines", 100)

        if self._log_streamer:
            lines = self._log_streamer.read_logs(adw_id, agent_name, tail_lines)
        else:
            lines = []

        await self._send_response(request_id, True, payload={"lines": lines})

    async def _handle_request_github_data(self, message: dict):
        """Handle request_github_data: fetch via gh CLI and return."""
        request_id = message.get("request_id")
        payload = message.get("payload", {})
        data_type = payload.get("data_type")
        filters = payload.get("filters", {})

        # Run blocking gh CLI call in thread pool to avoid blocking the event loop
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(
            None, fetch_github_data, data_type, filters, self._project_root
        )
        await self._send_response(
            request_id, result["success"], payload=result.get("data"), error=result.get("error")
        )

    async def _handle_apply_patch(self, message: dict):
        """Handle apply_patch: apply a template drift patch via git apply."""
        request_id = message.get("request_id")
        payload = message.get("payload", {})
        patch_content = payload.get("patch_content", "")
        dry_run = payload.get("dry_run", True)

        try:
            cmd = ["git", "apply"]
            if dry_run:
                cmd.append("--check")
            cmd.append("-")

            result = subprocess.run(
                cmd,
                input=patch_content,
                capture_output=True,
                text=True,
                timeout=60,
                cwd=self._project_root,
            )

            if result.returncode == 0:
                mode = "dry run passed" if dry_run else "applied"
                await self._send_response(request_id, True, payload={"message": f"Patch {mode}"})
            else:
                await self._send_response(request_id, False, error=f"Patch failed: {result.stderr}")

        except Exception as e:
            await self._send_response(request_id, False, error=str(e))

    # ─── Registration & state reporting ──────────────────────────

    async def _send_register(self):
        """Send registration message with codebase metadata."""
        # Read template version
        template_commit = None
        version_path = os.path.join(
            self._project_root, "app", "frontend", "public", "version.json"
        )
        try:
            with open(version_path, "r") as f:
                version_data = json.load(f)
                template_commit = version_data.get("commit_hash")
        except Exception:
            pass

        # Get current branch
        current_branch = "unknown"
        try:
            result = subprocess.run(
                ["git", "branch", "--show-current"],
                capture_output=True, text=True, timeout=10,
                cwd=self._project_root,
            )
            if result.returncode == 0:
                current_branch = result.stdout.strip()
        except Exception:
            pass

        # Scan for active ADWs (with process liveness check)
        active_adws = []
        if self._file_watcher:
            for adw_id, state_data in self._file_watcher.scan_active_adws():
                pid = state_data.get("workflow_pid")
                if pid and is_process_running(pid):
                    active_adws.append(self._build_adw_status(adw_id, state_data))

        register_msg = {
            "type": "register",
            "payload": {
                "codebase_name": self._codebase_name,
                "machine_name": self._machine_name,
                "repo_url": self._get_repo_url(),
                "template_commit": template_commit,
                "current_branch": current_branch,
                "available_adws": list(AVAILABLE_ADW_WORKFLOWS),
                "active_adws": active_adws,
                "agent_version": "1.0.0",
                "gh_cli_authenticated": check_gh_auth() is None,
                "system_info": get_system_info(),
            },
        }
        self._enqueue_threadsafe(register_msg)

    def _build_adw_status(self, adw_id: str, state_data: dict) -> dict:
        """Build an adw_status payload from state data."""
        stage = state_data.get("workflow_stage")
        status = self._map_stage_to_status(stage)
        workflow_type = self._adw_workflow_types.get(adw_id, "unknown")

        return {
            "adw_id": adw_id,
            "status": status,
            "issue_number": state_data.get("issue_number"),
            "workflow_type": workflow_type,
            "workflow_stage": stage,
            "model_set": state_data.get("model_set", "base"),
            "branch_name": state_data.get("branch_name"),
            "smoke_test_passed": state_data.get("smoke_test_passed"),
            "smoke_test_failed": state_data.get("smoke_test_failed"),
            "smoke_test_skipped": state_data.get("smoke_test_skipped"),
            "smoke_test_screenshot_urls": state_data.get("smoke_test_screenshot_urls", []),
        }

    @staticmethod
    def _map_stage_to_status(stage: Optional[str]) -> str:
        """Map workflow_stage to a normalized status string."""
        if stage is None:
            return "queued"
        if stage in TERMINAL_STAGES:
            stage_map = {
                "completed": "completed",
                "failed": "failed",
                "stopped": "cancelled",
                "cancelled": "cancelled",
            }
            return stage_map.get(stage, "failed")
        if stage == "paused":
            return "paused"
        return "running"

    # ─── File watcher callback (called from watchdog thread) ─────

    def _on_state_change(self, adw_id: str, state_data: dict):
        """Called by file watcher when an adw_state.json changes.

        WARNING: This runs on the watchdog Timer thread, not the asyncio loop.
        All enqueue calls must use _enqueue_threadsafe().
        Blocking operations (subprocess, file I/O) are run in a thread pool
        via the asyncio loop to avoid blocking the watchdog thread.
        """
        stage = state_data.get("workflow_stage")
        is_terminal = stage in TERMINAL_STAGES

        if is_terminal:
            # Schedule completion building on the event loop's thread pool
            # to avoid blocking the watchdog thread with subprocess calls
            if self._loop and not self._loop.is_closed():
                self._loop.call_soon_threadsafe(
                    lambda aid=adw_id, sd=state_data: asyncio.ensure_future(
                        self._handle_terminal_state(aid, sd)
                    )
                )
            else:
                # Loop not available (early startup / late shutdown) — buffer a
                # simple completion without PR lookup or error extraction
                self._buffer_event({
                    "type": "adw_complete",
                    "payload": {
                        "adw_id": adw_id,
                        "status": self._map_stage_to_status(stage),
                        "workflow_type": self._adw_workflow_types.get(adw_id, "unknown"),
                        "workflow_stage": stage,
                        "issue_number": state_data.get("issue_number"),
                    },
                })
        else:
            status_msg = {
                "type": "adw_status",
                "payload": self._build_adw_status(adw_id, state_data),
            }
            if self._connected:
                self._enqueue_threadsafe(status_msg)
            else:
                self._buffer_event(status_msg)

            # Ensure log streaming is active
            if self._log_streamer:
                self._log_streamer.add_adw(adw_id)

    async def _handle_terminal_state(self, adw_id: str, state_data: dict):
        """Build and send completion message. Runs on the asyncio event loop
        so blocking calls (PR lookup, error extraction) use run_in_executor.
        """
        loop = asyncio.get_running_loop()
        completion = await loop.run_in_executor(
            None, self._build_completion, adw_id, state_data
        )

        if self._connected:
            self._enqueue_threadsafe(completion)
        else:
            self._buffer_event(completion)

        # Stop log streaming
        if self._log_streamer:
            self._log_streamer.remove_adw(adw_id)

        # Cleanup tracking
        self._adw_workflow_types.pop(adw_id, None)

    def _build_completion(self, adw_id: str, state_data: dict) -> dict:
        """Build an adw_complete message from final state data.

        May block on subprocess calls (PR lookup). Intended to be called
        via run_in_executor.
        """
        stage = state_data.get("workflow_stage")
        status = self._map_stage_to_status(stage)

        # Compute duration from ADW ID timestamp
        duration = None
        start_epoch = _parse_adw_id_timestamp(adw_id)
        if start_epoch:
            duration = int(time.time() - start_epoch)

        # Try to get error summary from the last JSONL result
        error_summary = None
        if status == "failed":
            error_summary = self._extract_error_summary(adw_id)

        # Try to get PR number
        pr_number = None
        branch_name = state_data.get("branch_name")
        if branch_name and status == "completed":
            pr_number = fetch_pr_for_branch(branch_name, self._project_root)

        return {
            "type": "adw_complete",
            "payload": {
                "adw_id": adw_id,
                "status": status,
                "error_summary": error_summary,
                "workflow_type": self._adw_workflow_types.get(adw_id, "unknown"),
                "workflow_stage": stage,
                "issue_number": state_data.get("issue_number"),
                "pr_number": pr_number,
                "duration_seconds": duration,
                "smoke_test_passed": state_data.get("smoke_test_passed"),
                "smoke_test_failed": state_data.get("smoke_test_failed"),
                "smoke_test_skipped": state_data.get("smoke_test_skipped"),
            },
        }

    def _extract_error_summary(self, adw_id: str) -> Optional[str]:
        """Try to extract error info from the last JSONL result message.

        Reads only the tail of the file to avoid loading entire JSONL into memory.
        """
        agents_dir = os.path.join(self._project_root, "agents", adw_id)
        if not os.path.isdir(agents_dir):
            return None

        for agent_name in os.listdir(agents_dir):
            jsonl_path = os.path.join(agents_dir, agent_name, "raw_output.jsonl")
            if not os.path.isfile(jsonl_path):
                continue

            try:
                # Read only last 32KB to find the result message
                file_size = os.path.getsize(jsonl_path)
                read_size = min(file_size, 32 * 1024)

                with open(jsonl_path, "r") as f:
                    if file_size > read_size:
                        f.seek(file_size - read_size)
                        f.readline()  # Skip partial first line
                    lines = f.readlines()

                for line in reversed(lines):
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                        if data.get("type") == "result" and data.get("is_error"):
                            result_text = data.get("result", "")
                            return result_text[:500] if result_text else None
                    except json.JSONDecodeError:
                        continue
            except Exception:
                continue

        return None

    # ─── Log streamer callback (called from log streamer thread) ─

    def _on_log_line(self, adw_id: str, agent_name: str, line_data: dict, timestamp: str):
        """Called by log streamer for each new JSONL line.

        WARNING: This runs on the log streamer thread, not the asyncio loop.
        """
        msg = {
            "type": "log_line",
            "payload": {
                "adw_id": adw_id,
                "agent_name": agent_name,
                "line": line_data,
                "timestamp": timestamp,
            },
        }
        if self._connected:
            self._enqueue_threadsafe(msg)
        # Log lines are NOT buffered during disconnection (too large)

    # ─── Event replay ────────────────────────────────────────────

    async def _replay_events(self):
        """Replay buffered events after reconnection."""
        if not self._replay_buffer:
            return

        count = len(self._replay_buffer)
        logger.info(f"Replaying {count} buffered events")

        while self._replay_buffer:
            event = self._replay_buffer.popleft()
            self._enqueue_threadsafe(event)

    # ─── Helpers ─────────────────────────────────────────────────

    def _enqueue_threadsafe(self, message: dict):
        """Thread-safe enqueue: schedule put_nowait on the event loop thread.

        Safe to call from any thread (watchdog, log streamer, or asyncio).
        """
        if self._loop and not self._loop.is_closed():
            self._loop.call_soon_threadsafe(self._send_queue.put_nowait, message)
        else:
            logger.debug("Event loop not available, dropping message")

    def _buffer_event(self, event: dict):
        """Thread-safe append to the replay buffer.

        Uses call_soon_threadsafe when the loop is available to ensure
        buffer operations are serialized on the event loop thread.
        Falls back to direct append (CPython GIL-safe) when the loop
        is not available.
        """
        if self._loop and not self._loop.is_closed():
            self._loop.call_soon_threadsafe(self._replay_buffer.append, event)
        else:
            # Fallback: direct append is safe under CPython's GIL
            self._replay_buffer.append(event)

    async def _send_response(
        self,
        request_id: str,
        success: bool,
        payload: Any = None,
        error: Optional[str] = None,
    ):
        """Send a response message to the command center."""
        msg = {
            "type": "response",
            "request_id": request_id,
            "success": success,
        }
        if payload is not None:
            msg["payload"] = payload
        if error:
            msg["error"] = error
        self._enqueue_threadsafe(msg)

    def _get_repo_url(self) -> str:
        """Get the repository URL from git remote."""
        try:
            result = subprocess.run(
                ["git", "remote", "get-url", "origin"],
                capture_output=True, text=True, timeout=10,
                cwd=self._project_root,
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except Exception:
            pass
        return ""

    def _init_components(self):
        """Initialize file watcher and log streamer."""
        self._file_watcher = ADWFileWatcher(
            project_root=self._project_root,
            callback=self._on_state_change,
        )
        self._file_watcher.start()

        self._log_streamer = LogStreamer(
            project_root=self._project_root,
            callback=self._on_log_line,
            pending_count_fn=self.get_pending_count,
        )
        self._log_streamer.start()

    def _cleanup_components(self):
        """Stop file watcher and log streamer."""
        if self._file_watcher:
            self._file_watcher.stop()
        if self._log_streamer:
            self._log_streamer.stop()

    def _sync_log_streaming(self):
        """Ensure log streaming is active for all non-terminal ADWs."""
        if not self._file_watcher or not self._log_streamer:
            return

        for adw_id, state_data in self._file_watcher.scan_active_adws():
            pid = state_data.get("workflow_pid")
            if pid and is_process_running(pid):
                self._log_streamer.add_adw(adw_id)
