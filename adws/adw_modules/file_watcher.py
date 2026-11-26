"""Filesystem watcher for ADW state changes.

Watches the agents/ directory for adw_state.json modifications using
the watchdog library. Uses FSEvents on macOS, inotify on Linux.
Debounces events (500ms window) to handle atomic-rename write patterns.
"""

import json
import logging
import os
import threading
import time
from typing import Callable, Dict, Optional

from watchdog.events import FileSystemEventHandler, FileSystemEvent
from watchdog.observers import Observer

from adw_modules.state import ADWState

logger = logging.getLogger(__name__)

# Terminal workflow stages — ADWs in these stages are considered finished
TERMINAL_STAGES = {"completed", "failed", "stopped", "cancelled"}

# Debounce window in seconds
DEBOUNCE_SECONDS = 0.5


class _DebouncedHandler(FileSystemEventHandler):
    """Handles filesystem events with debouncing for atomic-rename patterns.

    adw_state.json is written via atomic rename (write .tmp -> os.replace()),
    which can fire multiple events. We debounce by tracking the last event
    time per file and only processing after the debounce window elapses.
    """

    def __init__(self, callback: Callable[[str, dict], None]):
        super().__init__()
        self._callback = callback
        self._pending: Dict[str, float] = {}  # filepath -> last_event_time
        self._lock = threading.Lock()
        self._timer: Optional[threading.Timer] = None

    def on_any_event(self, event: FileSystemEvent):
        if event.is_directory:
            return

        src_path = event.src_path
        if not src_path.endswith("adw_state.json"):
            return

        with self._lock:
            self._pending[src_path] = time.monotonic()

            # Reset the debounce timer
            if self._timer is not None:
                self._timer.cancel()
            self._timer = threading.Timer(DEBOUNCE_SECONDS, self._flush_pending)
            self._timer.daemon = True
            self._timer.start()

    def _flush_pending(self):
        """Process all pending state file changes after debounce window."""
        with self._lock:
            paths = dict(self._pending)
            self._pending.clear()
            self._timer = None

        for path in paths:
            self._process_state_file(path)

    def _process_state_file(self, path: str):
        """Read and process a single adw_state.json file."""
        try:
            if not os.path.exists(path):
                return

            # Extract adw_id from path: agents/{adw_id}/adw_state.json
            parts = path.split(os.sep)
            state_idx = parts.index("adw_state.json")
            if state_idx < 1:
                return
            adw_id = parts[state_idx - 1]

            state = ADWState.load(adw_id)
            if state is None:
                logger.warning(f"Could not load state for {adw_id} at {path}")
                return

            self._callback(adw_id, state.data)

        except (ValueError, IndexError):
            logger.debug(f"Could not extract adw_id from path: {path}")
        except Exception as e:
            logger.error(f"Error processing state file {path}: {e}")

    def stop(self):
        """Cancel any pending timer."""
        with self._lock:
            if self._timer is not None:
                self._timer.cancel()
                self._timer = None


class ADWFileWatcher:
    """Watches the agents/ directory for ADW state changes.

    Usage:
        def on_state_change(adw_id: str, state_data: dict):
            print(f"ADW {adw_id} changed: stage={state_data.get('workflow_stage')}")

        watcher = ADWFileWatcher(project_root="/path/to/project", callback=on_state_change)
        watcher.start()
        # ... later ...
        watcher.stop()
    """

    def __init__(self, project_root: str, callback: Callable[[str, dict], None]):
        """Initialize the file watcher.

        Args:
            project_root: Root directory of the project (parent of agents/)
            callback: Function called with (adw_id, state_data) on state changes
        """
        self._project_root = project_root
        self._agents_dir = os.path.join(project_root, "agents")
        self._handler = _DebouncedHandler(callback)
        self._observer = Observer()
        self._started = False

    def start(self):
        """Start watching the agents/ directory."""
        os.makedirs(self._agents_dir, exist_ok=True)
        self._observer.schedule(self._handler, self._agents_dir, recursive=True)
        self._observer.start()
        self._started = True
        logger.info(f"File watcher started on {self._agents_dir}")

    def stop(self):
        """Stop watching and clean up."""
        if self._started:
            self._handler.stop()
            self._observer.stop()
            self._observer.join(timeout=5)
            self._started = False
            logger.info("File watcher stopped")

    def scan_active_adws(self) -> list:
        """Scan for currently active (non-terminal) ADWs.

        Reads all agents/*/adw_state.json files and returns state data
        for ADWs that are not in a terminal stage.

        Returns:
            List of (adw_id, state_data) tuples for active ADWs
        """
        active = []
        if not os.path.isdir(self._agents_dir):
            return active

        for entry in os.listdir(self._agents_dir):
            state_path = os.path.join(self._agents_dir, entry, "adw_state.json")
            if not os.path.isfile(state_path):
                continue

            try:
                state = ADWState.load(entry)
                if state is None:
                    continue

                stage = state.get("workflow_stage")
                if stage not in TERMINAL_STAGES:
                    active.append((entry, state.data))
            except Exception as e:
                logger.debug(f"Error scanning state for {entry}: {e}")

        return active
