"""State management for ADW composable architecture.

Provides persistent state management via file storage and
transient state passing between scripts via stdin/stdout.
"""

import fcntl
import json
import os
import sys
import logging
import tempfile
from typing import Dict, Any, Optional
from adw_modules.data_types import ADWStateData


class ADWState:
    """Container for ADW workflow state with file persistence."""

    STATE_FILENAME = "adw_state.json"

    def __init__(self, adw_id: str):
        """Initialize ADWState with a required ADW ID.
        
        Args:
            adw_id: The ADW ID for this state (required)
        """
        if not adw_id:
            raise ValueError("adw_id is required for ADWState")
        
        self.adw_id = adw_id
        # Start with minimal state
        self.data: Dict[str, Any] = {"adw_id": self.adw_id}
        self.logger = logging.getLogger(__name__)

    def update(self, **kwargs):
        """Update state with new key-value pairs."""
        # Filter to only our core fields
        core_fields = {"adw_id", "issue_number", "branch_name", "plan_file", "issue_class", "worktree_path", "backend_port", "frontend_port", "database_name", "model_set", "all_adws", "smoke_test_passed", "smoke_test_failed", "smoke_test_skipped", "smoke_test_screenshot_urls", "workflow_stage", "workflow_pid", "workflow_pgid", "context_files_loaded", "context_validation_passed", "context_violations_count", "orchestrator_session_id", "ore_run_dir"}
        for key, value in kwargs.items():
            if key in core_fields:
                self.data[key] = value

    def get(self, key: str, default=None):
        """Get value from state by key."""
        return self.data.get(key, default)

    def append_adw_id(self, adw_id: str):
        """Append an ADW ID to the all_adws list if not already present.

        BUG-STATE-001 fix: Uses copy-on-write to prevent race condition
        where concurrent calls could lose data due to non-atomic read-modify-write.
        """
        # Create a fresh copy to avoid modifying the original list reference
        all_adws = list(self.data.get("all_adws", []))
        if adw_id not in all_adws:
            all_adws.append(adw_id)
        # Always reassign to ensure the updated list is stored
        self.data["all_adws"] = all_adws

    def get_working_directory(self) -> str:
        """Get the working directory for this ADW instance.
        
        Returns worktree_path if set (for isolated workflows),
        otherwise returns the main repo path.
        """
        worktree_path = self.data.get("worktree_path")
        if worktree_path:
            return worktree_path
        
        # Return main repo path (parent of adws directory)
        return os.path.dirname(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        )

    def get_state_path(self) -> str:
        """Get path to state file."""
        project_root = os.path.dirname(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        )
        return os.path.join(project_root, "agents", self.adw_id, self.STATE_FILENAME)

    def save(self, workflow_step: Optional[str] = None) -> None:
        """Save state to file in agents/{adw_id}/adw_state.json.

        Uses atomic write with file locking to prevent corruption
        during concurrent workflows. Lock is on dedicated .lock file
        to match rescue_state.py pattern (BUG-001, BUG-002 fix).
        """
        state_path = self.get_state_path()
        state_dir = os.path.dirname(state_path)
        os.makedirs(state_dir, exist_ok=True)

        lock_path = state_path + ".lock"
        temp_path = state_path + ".tmp"

        # Create ADWStateData for validation
        state_data = ADWStateData(
            adw_id=self.data.get("adw_id"),
            issue_number=self.data.get("issue_number"),
            branch_name=self.data.get("branch_name"),
            plan_file=self.data.get("plan_file"),
            issue_class=self.data.get("issue_class"),
            worktree_path=self.data.get("worktree_path"),
            backend_port=self.data.get("backend_port"),
            frontend_port=self.data.get("frontend_port"),
            database_name=self.data.get("database_name"),
            model_set=self.data.get("model_set", "base"),
            all_adws=self.data.get("all_adws", []),
            smoke_test_passed=self.data.get("smoke_test_passed"),
            smoke_test_failed=self.data.get("smoke_test_failed"),
            smoke_test_skipped=self.data.get("smoke_test_skipped"),
            smoke_test_screenshot_urls=self.data.get("smoke_test_screenshot_urls", []),
            workflow_stage=self.data.get("workflow_stage"),
            workflow_pid=self.data.get("workflow_pid"),
            workflow_pgid=self.data.get("workflow_pgid"),
            context_files_loaded=self.data.get("context_files_loaded", []),
            context_validation_passed=self.data.get("context_validation_passed"),
            context_violations_count=self.data.get("context_violations_count"),
            orchestrator_session_id=self.data.get("orchestrator_session_id"),
            ore_run_dir=self.data.get("ore_run_dir"),
        )

        # Use atomic write with file locking on dedicated lock file
        # This matches rescue_state.py pattern for consistency
        lock_file = None
        try:
            lock_file = open(lock_path, "a")
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)

            # Write to temp file first
            with open(temp_path, "w") as f:
                json.dump(state_data.model_dump(), f, indent=2)

            # Atomic rename
            os.replace(temp_path, state_path)

        except Exception as e:
            # BUG-STATE-004 fix: Log error details before re-raising
            self.logger.error(f"Failed to save state to {state_path}: {type(e).__name__}: {e}")
            # Clean up temp file on error
            if os.path.exists(temp_path):
                try:
                    os.unlink(temp_path)
                except Exception:
                    pass
            raise
        finally:
            if lock_file:
                try:
                    fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
                    lock_file.close()
                except Exception:
                    pass

        self.logger.info(f"Saved state to {state_path}")
        if workflow_step:
            self.logger.info(f"State updated by: {workflow_step}")

    @classmethod
    def load(
        cls, adw_id: str, logger: Optional[logging.Logger] = None
    ) -> Optional["ADWState"]:
        """Load state from file if it exists.

        BUG-075 fix: Uses shared file locking to prevent reading during writes.
        This matches the locking in save() to ensure atomic read/write operations.
        """
        project_root = os.path.dirname(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        )
        state_path = os.path.join(project_root, "agents", adw_id, cls.STATE_FILENAME)
        lock_path = state_path + ".lock"

        if not os.path.exists(state_path):
            return None

        lock_file = None
        try:
            # Ensure lock directory exists
            lock_dir = os.path.dirname(lock_path)
            os.makedirs(lock_dir, exist_ok=True)

            # Acquire shared lock for reading (allows multiple readers, blocks writers)
            lock_file = open(lock_path, "a")
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_SH)

            with open(state_path, "r") as f:
                data = json.load(f)

            # Validate with ADWStateData
            state_data = ADWStateData(**data)

            # Create ADWState instance
            state = cls(state_data.adw_id)
            state.data = state_data.model_dump()

            if logger:
                logger.info(f"🔍 Found existing state from {state_path}")
                logger.info(f"State: {json.dumps(state_data.model_dump(), indent=2)}")

            return state
        except FileNotFoundError:
            # File was deleted between exists check and open
            return None
        except json.JSONDecodeError as e:
            if logger:
                logger.error(f"State file is corrupted (invalid JSON): {e}")
            return None
        except Exception as e:
            if logger:
                logger.error(f"Failed to load state from {state_path}: {e}")
            return None
        finally:
            if lock_file:
                try:
                    fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
                    lock_file.close()
                except Exception:
                    pass

    @classmethod
    def from_stdin(cls, logger: Optional[logging.Logger] = None) -> Optional["ADWState"]:
        """Read state from stdin if available (for piped input).

        Returns None if no piped input is available (stdin is a tty).
        Logs errors instead of silently ignoring them (BUG-032 fix).
        BUG-006 fix: Validates data against ADWStateData schema.
        """
        if sys.stdin.isatty():
            return None
        try:
            input_data = sys.stdin.read()
            if not input_data.strip():
                return None
            data = json.loads(input_data)
            adw_id = data.get("adw_id")
            if not adw_id:
                if logger:
                    logger.warning("from_stdin: No adw_id in piped state data")
                return None  # No valid state without adw_id

            # BUG-006 fix: Validate against schema to catch type errors early
            # BUG-STATE-003 fix: Don't silently fall back to unvalidated data -
            # log error and fail validation instead of propagating bad types
            try:
                state_data = ADWStateData(**data)
                state = cls(adw_id)
                state.data = state_data.model_dump()
            except (TypeError, ValueError) as e:
                if logger:
                    logger.error(f"from_stdin: Schema validation failed: {e}")
                # Return None instead of silently using invalid data
                # This prevents type errors from propagating through the workflow
                return None

            return state
        except json.JSONDecodeError as e:
            if logger:
                logger.error(f"from_stdin: Failed to parse JSON from stdin: {e}")
            return None
        except EOFError as e:
            if logger:
                logger.error(f"from_stdin: EOF error reading stdin: {e}")
            return None

    def to_stdout(self):
        """Write state to stdout as JSON (for piping to next script).

        BUG-007 fix: Include all critical fields for workflow resumption.
        BUG-STATE-002 fix: Include model_set, context_violations_count,
        smoke_test_screenshot_urls that were missing before.
        """
        # Output all core fields including workflow tracking info
        output_data = {
            "adw_id": self.data.get("adw_id"),
            "issue_number": self.data.get("issue_number"),
            "branch_name": self.data.get("branch_name"),
            "plan_file": self.data.get("plan_file"),
            "issue_class": self.data.get("issue_class"),
            "worktree_path": self.data.get("worktree_path"),
            "backend_port": self.data.get("backend_port"),
            "frontend_port": self.data.get("frontend_port"),
            "database_name": self.data.get("database_name"),
            "all_adws": self.data.get("all_adws", []),
            # BUG-STATE-002 fix: Include model_set for workflow resumption
            "model_set": self.data.get("model_set", "base"),
            # Include workflow tracking fields (BUG-007 fix)
            "workflow_stage": self.data.get("workflow_stage"),
            "workflow_pid": self.data.get("workflow_pid"),
            "workflow_pgid": self.data.get("workflow_pgid"),
            "context_files_loaded": self.data.get("context_files_loaded", []),
            "context_validation_passed": self.data.get("context_validation_passed"),
            # BUG-STATE-002 fix: Include context_violations_count
            "context_violations_count": self.data.get("context_violations_count"),
            "orchestrator_session_id": self.data.get("orchestrator_session_id"),
            "smoke_test_passed": self.data.get("smoke_test_passed"),
            "smoke_test_failed": self.data.get("smoke_test_failed"),
            "smoke_test_skipped": self.data.get("smoke_test_skipped"),
            # BUG-STATE-002 fix: Include smoke_test_screenshot_urls
            "smoke_test_screenshot_urls": self.data.get("smoke_test_screenshot_urls", []),
        }
        print(json.dumps(output_data, indent=2))
