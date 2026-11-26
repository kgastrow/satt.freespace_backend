"""Log streamer for ADW raw_output.jsonl files.

Tails JSONL log files for active ADWs and emits log lines via a callback.
Always streams for active ADWs (server stores all lines for historical access).

Features:
- Seek position tracking to avoid re-reading on restart
- Rate limiting: max 50 lines/sec/ADW
- Backpressure: pause tailing when send queue exceeds threshold
- Thread-safe start/stop per ADW
"""

import json
import logging
import os
import threading
import time
from collections import defaultdict
from datetime import datetime, timezone
from typing import Callable, Dict, List, Optional, Set

logger = logging.getLogger(__name__)

# Rate limiting: 50 lines/sec/ADW. With 0.5s poll interval, that's 25 lines per poll cycle.
MAX_LINES_PER_SECOND_PER_ADW = 50
TAIL_POLL_INTERVAL = 0.5  # seconds
MAX_LINES_PER_CYCLE_PER_ADW = int(MAX_LINES_PER_SECOND_PER_ADW * TAIL_POLL_INTERVAL)

# Backpressure thresholds
BACKPRESSURE_PAUSE_THRESHOLD = 5000
BACKPRESSURE_RESUME_THRESHOLD = 2500


class _ADWLogTailer:
    """Tails all raw_output.jsonl files for a single ADW."""

    def __init__(self, adw_id: str, agents_dir: str, callback: Callable):
        self.adw_id = adw_id
        self._agents_dir = agents_dir
        self._callback = callback
        self._seek_positions: Dict[str, int] = {}  # filepath -> offset
        self._stopped = threading.Event()

    def get_jsonl_files(self) -> List[str]:
        """Find all raw_output.jsonl files for this ADW."""
        adw_dir = os.path.join(self._agents_dir, self.adw_id)
        if not os.path.isdir(adw_dir):
            return []

        files = []
        for agent_name in os.listdir(adw_dir):
            jsonl_path = os.path.join(adw_dir, agent_name, "raw_output.jsonl")
            if os.path.isfile(jsonl_path):
                files.append(jsonl_path)
        return files

    def extract_agent_name(self, filepath: str) -> str:
        """Extract agent name from filepath: agents/{adw_id}/{agent_name}/raw_output.jsonl"""
        parts = filepath.split(os.sep)
        try:
            jsonl_idx = parts.index("raw_output.jsonl")
            return parts[jsonl_idx - 1] if jsonl_idx >= 1 else "unknown"
        except (ValueError, IndexError):
            return "unknown"

    def tail_once(self) -> int:
        """Read new lines from all JSONL files for this ADW.

        Returns:
            Number of lines emitted
        """
        total_emitted = 0
        lines_this_cycle = 0

        for filepath in self.get_jsonl_files():
            if self._stopped.is_set():
                break

            try:
                file_size = os.path.getsize(filepath)
                current_pos = self._seek_positions.get(filepath, 0)

                # File was truncated or recreated
                if current_pos > file_size:
                    current_pos = 0

                if current_pos >= file_size:
                    continue

                agent_name = self.extract_agent_name(filepath)

                with open(filepath, "r") as f:
                    f.seek(current_pos)
                    for raw_line in f:
                        if self._stopped.is_set():
                            break

                        raw_line = raw_line.strip()
                        if not raw_line:
                            continue

                        # Rate limit per ADW per poll cycle
                        lines_this_cycle += 1
                        if lines_this_cycle > MAX_LINES_PER_CYCLE_PER_ADW:
                            break

                        try:
                            line_data = json.loads(raw_line)
                        except json.JSONDecodeError:
                            continue

                        self._callback(
                            self.adw_id,
                            agent_name,
                            line_data,
                            datetime.now(timezone.utc).isoformat(),
                        )
                        total_emitted += 1

                    self._seek_positions[filepath] = f.tell()

            except FileNotFoundError:
                self._seek_positions.pop(filepath, None)
            except Exception as e:
                logger.debug(f"Error tailing {filepath}: {e}")

        return total_emitted

    def read_tail(self, agent_name: Optional[str], tail_lines: int) -> List[dict]:
        """Read the last N lines from JSONL files.

        Args:
            agent_name: Filter by agent name (None = all agents)
            tail_lines: Number of lines to return

        Returns:
            List of log line entries. Timestamps are extracted from JSONL
            result messages where available, otherwise use file mtime.
        """
        all_lines = []
        for filepath in self.get_jsonl_files():
            file_agent = self.extract_agent_name(filepath)
            if agent_name and file_agent != agent_name:
                continue

            try:
                # Use file mtime as fallback timestamp
                file_mtime = datetime.fromtimestamp(
                    os.path.getmtime(filepath), tz=timezone.utc
                ).isoformat()

                # Read only last portion of file to avoid loading huge files
                file_size = os.path.getsize(filepath)
                max_read = 512 * 1024  # 512KB tail

                with open(filepath, "r") as f:
                    if file_size > max_read:
                        f.seek(file_size - max_read)
                        f.readline()  # Skip partial first line
                    lines = f.readlines()

                for raw_line in lines:
                    raw_line = raw_line.strip()
                    if not raw_line:
                        continue
                    try:
                        line_data = json.loads(raw_line)
                        all_lines.append({
                            "agent_name": file_agent,
                            "line": line_data,
                            "timestamp": file_mtime,
                        })
                    except json.JSONDecodeError:
                        continue
            except Exception as e:
                logger.debug(f"Error reading {filepath}: {e}")

        return all_lines[-tail_lines:]

    def stop(self):
        self._stopped.set()


class LogStreamer:
    """Manages log tailing for multiple ADWs concurrently.

    Usage:
        def on_log_line(adw_id, agent_name, line_data, timestamp):
            send_to_server({"type": "log_line", "payload": {...}})

        streamer = LogStreamer(project_root="/path/to/project", callback=on_log_line)
        streamer.start()
        streamer.add_adw("20260411-abc123")
        # ... later ...
        streamer.remove_adw("20260411-abc123")
        streamer.stop()
    """

    def __init__(
        self,
        project_root: str,
        callback: Callable[[str, str, dict, str], None],
        pending_count_fn: Optional[Callable[[], int]] = None,
    ):
        """Initialize the log streamer.

        Args:
            project_root: Root directory of the project
            callback: Called with (adw_id, agent_name, line_data, timestamp) for each log line
            pending_count_fn: Optional function returning current pending message count for backpressure
        """
        self._agents_dir = os.path.join(project_root, "agents")
        self._callback = callback
        self._pending_count_fn = pending_count_fn
        self._tailers: Dict[str, _ADWLogTailer] = {}
        self._lock = threading.Lock()
        self._stopped = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._paused = False

    def start(self):
        """Start the log streaming background thread."""
        self._stopped.clear()
        self._thread = threading.Thread(target=self._run, daemon=True, name="log-streamer")
        self._thread.start()
        logger.info("Log streamer started")

    def stop(self):
        """Stop all tailing and the background thread."""
        self._stopped.set()
        with self._lock:
            for tailer in self._tailers.values():
                tailer.stop()
            self._tailers.clear()
        if self._thread:
            self._thread.join(timeout=5)
        logger.info("Log streamer stopped")

    def add_adw(self, adw_id: str):
        """Start tailing logs for an ADW."""
        with self._lock:
            if adw_id not in self._tailers:
                self._tailers[adw_id] = _ADWLogTailer(
                    adw_id, self._agents_dir, self._callback
                )
                logger.debug(f"Started tailing logs for ADW {adw_id}")

    def remove_adw(self, adw_id: str):
        """Stop tailing logs for an ADW."""
        with self._lock:
            tailer = self._tailers.pop(adw_id, None)
            if tailer:
                tailer.stop()
                logger.debug(f"Stopped tailing logs for ADW {adw_id}")

    def get_active_adw_ids(self) -> Set[str]:
        """Return set of ADW IDs currently being tailed."""
        with self._lock:
            return set(self._tailers.keys())

    def read_logs(self, adw_id: str, agent_name: Optional[str], tail_lines: int) -> List[dict]:
        """Read historical log lines for an ADW.

        Args:
            adw_id: ADW ID to read logs for
            agent_name: Filter by agent name (None = all agents)
            tail_lines: Number of lines to return

        Returns:
            List of log line entries
        """
        tailer = _ADWLogTailer(adw_id, self._agents_dir, lambda *a: None)
        return tailer.read_tail(agent_name, tail_lines)

    def _run(self):
        """Background thread: periodically tail all active ADWs."""
        while not self._stopped.is_set():
            # Backpressure check
            if self._pending_count_fn:
                pending = self._pending_count_fn()
                if pending > BACKPRESSURE_PAUSE_THRESHOLD and not self._paused:
                    self._paused = True
                    logger.warning(
                        f"Backpressure: pausing log streaming ({pending} pending messages)"
                    )
                elif pending < BACKPRESSURE_RESUME_THRESHOLD and self._paused:
                    self._paused = False
                    logger.info("Backpressure: resuming log streaming")

            if not self._paused:
                with self._lock:
                    tailers = list(self._tailers.values())

                for tailer in tailers:
                    if self._stopped.is_set():
                        break
                    try:
                        tailer.tail_once()
                    except Exception as e:
                        logger.error(f"Error tailing ADW {tailer.adw_id}: {e}")

            self._stopped.wait(timeout=TAIL_POLL_INTERVAL)
