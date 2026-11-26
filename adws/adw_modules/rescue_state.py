"""State management for Vibe Code Rescue workflow.

Extends ADWState with rescue-specific tracking.
State is stored in agents/{adw_id}/rescue_state.json
"""

import fcntl
import os
import json
import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any, Tuple
from enum import Enum
from pydantic import BaseModel, Field, field_validator

# State format version - bump when schema changes for backward compatibility
STATE_VERSION = 1


class RescuePhase(str, Enum):
    """Phases of the rescue workflow."""
    DISCOVERY = "discovery"
    TRIAGE = "triage"
    EXECUTION = "execution"
    VALIDATION = "validation"
    DELIVERY = "delivery"


class TaskStatus(str, Enum):
    """Status of individual rescue tasks."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"
    BLOCKED = "blocked"


class RescueTaskType(str, Enum):
    """Types of rescue tasks."""
    DISCOVERY = "discovery"
    TRIAGE = "triage"
    MODEL = "model"
    CRUD = "crud"
    API = "api"
    COMPONENT = "component"
    WIRE = "wire"
    TEST = "test"
    CONFIG = "config"
    VALIDATION = "validation"
    PLANNING = "planning"


class StylingMethod(str, Enum):
    """Detected styling methods in source project."""
    CSS_MODULES = "css_modules"
    TAILWIND = "tailwind"
    STYLED_COMPONENTS = "styled_components"
    EMOTION = "emotion"
    INLINE = "inline"
    GLOBAL_CSS = "global_css"
    SASS = "sass"


class UIMigrationTier(str, Enum):
    """Migration complexity tier for UI components."""
    AUTO = "auto"         # Can be fully automated
    ASSISTED = "assisted"  # Needs minor human review
    MANUAL = "manual"     # Requires human recreation


class DifficultyLevel(str, Enum):
    """Estimated rescue difficulty."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    VERY_HIGH = "very_high"
    NOT_RECOMMENDED = "not_recommended"


# -----------------------------------------------------------------------------
# Pydantic Models for JSON Serialization
# -----------------------------------------------------------------------------

class SourceStackInfo(BaseModel):
    """Information about the source project's tech stack."""
    backend_framework: Optional[str] = None
    database_type: Optional[str] = None
    frontend_framework: Optional[str] = None
    state_management: List[str] = Field(default_factory=list)
    styling_methods: List[str] = Field(default_factory=list)
    package_manager: Optional[str] = None


class FeatureSpec(BaseModel):
    """A detected feature from the source project."""
    name: str
    description: str
    endpoints: List[str] = Field(default_factory=list)
    components: List[str] = Field(default_factory=list)
    is_complete: bool = True


class UIComponentSpec(BaseModel):
    """Analysis of a single UI component."""
    path: str
    name: str
    line_count: int = 0
    styling_methods: List[str] = Field(default_factory=list)
    has_css_chaos: bool = False
    uses_context: bool = False
    uses_redux: bool = False
    uses_other_state: List[str] = Field(default_factory=list)
    api_calls: List[str] = Field(default_factory=list)
    has_animations: bool = False
    animation_library: Optional[str] = None
    dom_structure_locked: bool = False
    imports: List[str] = Field(default_factory=list)
    migration_tier: str = "auto"
    migration_notes: str = ""


class ExternalIntegration(BaseModel):
    """Detected external API integration."""
    name: str
    type: str  # "auth", "payment", "analytics", "storage", etc.
    is_documented: bool = False
    endpoints_used: List[str] = Field(default_factory=list)


class DiscoveryRedFlags(BaseModel):
    """Red flags detected during discovery."""
    has_css_chaos: bool = False
    has_state_chaos: bool = False
    has_dead_code: bool = False
    has_fake_endpoints: bool = False
    has_forked_libraries: bool = False
    has_undocumented_integrations: bool = False
    enterprise_complexity: bool = False
    total_serious_flags: int = 0
    estimated_difficulty: str = "medium"
    difficulty_reason: str = ""


class RescueTask(BaseModel):
    """A single atomic task in the rescue workflow."""
    id: str
    type: str  # RescueTaskType value
    phase: str
    description: str
    inputs: List[str] = Field(default_factory=list)  # Task IDs this depends on
    outputs: List[str] = Field(default_factory=list)  # Files this produces
    slash_command: str
    args: List[str] = Field(default_factory=list)
    status: str = "pending"
    retry_count: int = 0
    max_retries: int = Field(default=3, ge=1)  # Must be at least 1
    error_message: Optional[str] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None

    @field_validator('inputs')
    @classmethod
    def validate_inputs(cls, v, info):
        """Validate inputs list - check for duplicates and self-references."""
        if not isinstance(v, list):
            raise ValueError('inputs must be a list')
        # Check for duplicates
        if len(v) != len(set(v)):
            raise ValueError('inputs contains duplicate task IDs')
        # Check for self-reference (id may not be available during validation)
        return v

    @field_validator('id')
    @classmethod
    def validate_id(cls, v):
        """Validate task ID is not empty."""
        if not v or not v.strip():
            raise ValueError('task id cannot be empty')
        return v.strip()

    @field_validator('phase')
    @classmethod
    def validate_phase(cls, v):
        """Validate phase is a known RescuePhase value."""
        valid_phases = {p.value for p in RescuePhase}
        if v not in valid_phases:
            raise ValueError(f'phase must be one of {valid_phases}, got {v}')
        return v

    @field_validator('status')
    @classmethod
    def validate_status(cls, v):
        """Validate status is a known TaskStatus value."""
        valid_statuses = {s.value for s in TaskStatus}
        if v not in valid_statuses:
            raise ValueError(f'status must be one of {valid_statuses}, got {v}')
        return v


class CheckpointRecord(BaseModel):
    """Record of a human checkpoint."""
    checkpoint_type: str  # "triage", "validation"
    timestamp: str
    approved: bool = False
    notes: Optional[str] = None
    scope_changes: List[str] = Field(default_factory=list)


class DiscoveryState(BaseModel):
    """State from discovery phase."""
    source_stack: Optional[SourceStackInfo] = None
    features_detected: List[FeatureSpec] = Field(default_factory=list)
    schema_extracted: bool = False
    schema_path: Optional[str] = None
    ui_components: List[UIComponentSpec] = Field(default_factory=list)
    styling_methods_found: List[str] = Field(default_factory=list)
    integrations_detected: List[ExternalIntegration] = Field(default_factory=list)
    red_flags: DiscoveryRedFlags = Field(default_factory=DiscoveryRedFlags)
    discovery_summary_path: Optional[str] = None
    discovery_complete: bool = False


class TriageState(BaseModel):
    """State from triage phase."""
    backend_classification: Dict[str, str] = Field(default_factory=dict)
    ui_rescue_decisions: Dict[str, str] = Field(default_factory=dict)
    ui_rescue_plan_path: Optional[str] = None
    task_graph_path: Optional[str] = None
    estimated_tasks: int = 0
    estimated_hours_min: float = 0.0
    estimated_hours_max: float = 0.0
    feasibility_passed: bool = False
    triage_complete: bool = False


class ExecutionState(BaseModel):
    """State from execution phase."""
    current_task: Optional[str] = None
    completed_tasks: List[str] = Field(default_factory=list)
    failed_tasks: List[str] = Field(default_factory=list)
    skipped_tasks: List[str] = Field(default_factory=list)
    phase_checkpoints: Dict[str, str] = Field(default_factory=dict)
    execution_complete: bool = False


class ValidationState(BaseModel):
    """State from validation phase."""
    test_results_path: Optional[str] = None
    tests_passed: int = 0
    tests_failed: int = 0
    visual_match_percent: float = 0.0
    feature_parity_percent: float = 0.0
    validation_complete: bool = False


class RescueStateData(BaseModel):
    """Complete rescue workflow state for JSON serialization."""
    version: int = STATE_VERSION  # Schema version for backward compatibility
    adw_id: str
    source_project_path: str
    current_phase: str = "discovery"
    plan_version: int = 1
    plan_history: List[str] = Field(default_factory=list)
    learnings: List[str] = Field(default_factory=list)

    # Phase states
    discovery: DiscoveryState = Field(default_factory=DiscoveryState)
    triage: TriageState = Field(default_factory=TriageState)
    execution: ExecutionState = Field(default_factory=ExecutionState)
    validation: ValidationState = Field(default_factory=ValidationState)

    # Task graph (flattened for JSON)
    tasks: List[RescueTask] = Field(default_factory=list)

    # Checkpoints
    checkpoints: List[CheckpointRecord] = Field(default_factory=list)


# -----------------------------------------------------------------------------
# State Manager Class (follows MultiPhaseState pattern)
# -----------------------------------------------------------------------------

class RescueState:
    """State manager for rescue workflow.

    Persists to agents/{adw_id}/rescue_state.json
    """

    STATE_FILENAME = "rescue_state.json"

    def __init__(self, adw_id: str, source_project_path: str = ""):
        self.adw_id = adw_id
        self.data = RescueStateData(
            adw_id=adw_id,
            source_project_path=source_project_path
        )
        self.logger = logging.getLogger(__name__)

    def get_state_path(self) -> str:
        """Get path to rescue state file."""
        project_root = os.path.dirname(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        )
        return os.path.join(project_root, "agents", self.adw_id, self.STATE_FILENAME)

    def save(self) -> None:
        """Save rescue state to file atomically with file locking.

        Uses atomic write pattern: write to temp file, then rename.
        This prevents corruption from concurrent writes or crashes.
        """
        state_path = self.get_state_path()
        state_dir = os.path.dirname(state_path)
        os.makedirs(state_dir, exist_ok=True)

        temp_path = state_path + ".tmp"
        lock_path = state_path + ".lock"

        # Acquire exclusive lock for writing
        lock_file = None
        try:
            lock_file = open(lock_path, "a")
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)

            # Write to temp file first
            with open(temp_path, "w") as f:
                json.dump(self.data.model_dump(), f, indent=2)

            # Atomic rename
            os.replace(temp_path, state_path)
            self.logger.info(f"Saved rescue state to {state_path}")

        except Exception as e:
            self.logger.error(f"Failed to save rescue state: {e}")
            # Clean up temp file if it exists
            if os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
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

    @classmethod
    def load(cls, adw_id: str, logger: Optional[logging.Logger] = None) -> Optional["RescueState"]:
        """Load rescue state from file if it exists.

        Uses shared file locking to prevent reading during writes.
        Handles specific exceptions for better error diagnosis.
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
            # Acquire shared lock for reading
            # Use "a" mode (append) to avoid truncating the lock file
            lock_file = open(lock_path, "a")
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_SH)

            with open(state_path, "r") as f:
                data = json.load(f)

            # Check version compatibility
            file_version = data.get("version", 1)
            if file_version > STATE_VERSION:
                if logger:
                    logger.warning(
                        f"State file version {file_version} is newer than supported {STATE_VERSION}. "
                        "Some features may not work correctly."
                    )

            state = cls(data["adw_id"], data.get("source_project_path", ""))
            state.data = RescueStateData(**data)

            if logger:
                logger.info(f"Loaded rescue state from {state_path}")

            return state

        except FileNotFoundError:
            # File was deleted between exists check and open
            return None
        except json.JSONDecodeError as e:
            if logger:
                logger.error(f"State file is corrupted (invalid JSON): {e}")
            return None
        except (TypeError, ValueError) as e:
            if logger:
                logger.error(f"State file has invalid data format: {e}")
            return None
        except Exception as e:
            if logger:
                logger.error(f"Failed to load rescue state: {e}")
            return None
        finally:
            if lock_file:
                try:
                    fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
                    lock_file.close()
                except Exception:
                    pass

    # ---------------------------------------------------------------------
    # Task Graph Operations
    # ---------------------------------------------------------------------

    def add_task(self, task: RescueTask) -> bool:
        """Add a task to the task graph.

        Args:
            task: The task to add

        Returns:
            True if task was added, False if task with same ID already exists
        """
        # Check for duplicate ID
        if any(t.id == task.id for t in self.data.tasks):
            self.logger.warning(f"Task with ID {task.id} already exists, skipping")
            return False

        self.data.tasks.append(task)
        self.logger.debug(f"Added task: {task.id} ({task.type}) - {task.description}")
        return True

    def add_tasks_from_graph(self, task_graph_path: str, clear_existing: bool = False) -> Tuple[int, int]:
        """Load tasks from a task graph JSON file.

        Args:
            task_graph_path: Path to the task graph JSON file
            clear_existing: If True, clear existing tasks before loading

        Returns:
            Tuple of (tasks_added, tasks_skipped)
        """
        try:
            with open(task_graph_path, "r") as f:
                graph_data = json.load(f)

            if clear_existing:
                self.data.tasks.clear()
                self.logger.info("Cleared existing tasks before loading")

            tasks_added = 0
            tasks_skipped = 0

            for idx, task_data in enumerate(graph_data.get("tasks", [])):
                try:
                    task = RescueTask(**task_data)
                    if self.add_task(task):
                        tasks_added += 1
                    else:
                        tasks_skipped += 1
                except (TypeError, ValueError) as e:
                    self.logger.warning(f"Skipping invalid task at index {idx}: {e}")
                    tasks_skipped += 1

            self.data.triage.task_graph_path = task_graph_path
            self.data.triage.estimated_tasks = len(self.data.tasks)

            if tasks_skipped > 0:
                self.logger.warning(
                    f"Loaded {tasks_added} tasks from {task_graph_path}, "
                    f"skipped {tasks_skipped} invalid/duplicate tasks"
                )
            else:
                self.logger.info(f"Loaded {tasks_added} tasks from {task_graph_path}")

            return tasks_added, tasks_skipped

        except json.JSONDecodeError as e:
            self.logger.error(f"Invalid JSON in task graph: {e}")
            raise
        except FileNotFoundError:
            self.logger.error(f"Task graph file not found: {task_graph_path}")
            raise
        except Exception as e:
            self.logger.error(f"Failed to load task graph: {e}")
            raise

    def get_task(self, task_id: str) -> Optional[RescueTask]:
        """Get a task by ID."""
        for task in self.data.tasks:
            if task.id == task_id:
                return task
        return None

    def update_task_status(
        self,
        task_id: str,
        status: TaskStatus,
        error_message: Optional[str] = None
    ) -> bool:
        """Update task status and auto-maintain execution tracking lists.

        Automatically manages completed_tasks, failed_tasks, and skipped_tasks
        lists to prevent divergence between task status and tracking lists.

        Args:
            task_id: The task ID to update
            status: The new status
            error_message: Optional error message for failed tasks

        Returns:
            True if task was found and updated, False if task not found
        """
        task = self.get_task(task_id)
        if not task:
            self.logger.error(f"Cannot update status: task not found: {task_id}")
            return False

        task.status = status.value
        if status == TaskStatus.RUNNING:
            task.started_at = datetime.now(timezone.utc).isoformat()
        elif status in [TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.SKIPPED]:
            task.completed_at = datetime.now(timezone.utc).isoformat()
        if error_message:
            task.error_message = error_message

        # Auto-maintain execution tracking lists (prevents divergence - review fix #2)
        # Add to the appropriate list if not already present
        if status == TaskStatus.COMPLETED:
            if task_id not in self.data.execution.completed_tasks:
                self.data.execution.completed_tasks.append(task_id)
            # Remove from failed if it was previously failed (retry succeeded)
            if task_id in self.data.execution.failed_tasks:
                self.data.execution.failed_tasks.remove(task_id)
        elif status == TaskStatus.FAILED:
            if task_id not in self.data.execution.failed_tasks:
                self.data.execution.failed_tasks.append(task_id)
        elif status == TaskStatus.SKIPPED:
            if task_id not in self.data.execution.skipped_tasks:
                self.data.execution.skipped_tasks.append(task_id)
        elif status == TaskStatus.PENDING:
            # Task being retried - remove from failed list
            if task_id in self.data.execution.failed_tasks:
                self.data.execution.failed_tasks.remove(task_id)

        self.logger.debug(f"Task {task_id} status updated to {status.value}")
        return True

    def update_task_retry_count(self, task_id: str, retry_count: int) -> bool:
        """Update task retry count.

        BUG-075 fix: This method allows callers to sync retry count changes
        back to the actual task in state, since get_next_task() returns a copy.

        Args:
            task_id: The task ID to update
            retry_count: The new retry count

        Returns:
            True if task was found and updated, False if task not found
        """
        task = self.get_task(task_id)
        if not task:
            self.logger.error(f"Cannot update retry count: task not found: {task_id}")
            return False

        task.retry_count = retry_count
        self.logger.debug(f"Task {task_id} retry count updated to {retry_count}")
        return True

    def increment_task_retry_count(self, task_id: str) -> int:
        """Increment task retry count and return new value.

        BUG-075 fix: Convenience method to atomically increment and return
        the new retry count, ensuring the change is persisted to state.

        Args:
            task_id: The task ID to update

        Returns:
            New retry count, or -1 if task not found
        """
        task = self.get_task(task_id)
        if not task:
            self.logger.error(f"Cannot increment retry count: task not found: {task_id}")
            return -1

        task.retry_count += 1
        self.logger.debug(f"Task {task_id} retry count incremented to {task.retry_count}")
        return task.retry_count

    def timeout_stuck_tasks(self, max_running_minutes: int = 45) -> List[str]:
        """Mark stuck RUNNING tasks as FAILED after timeout.

        BUG-078 fix: Uses update_task_status() instead of direct assignment
        to ensure timestamps are properly managed and status updates are consistent.

        Args:
            max_running_minutes: Maximum minutes a task can run before being timed out

        Returns:
            List of task IDs that were timed out
        """
        timed_out = []
        max_seconds = max_running_minutes * 60

        for task in self.data.tasks:
            if task.status != "running" or not task.started_at:
                continue

            try:
                # BUG-9 fix: Use safe datetime parsing
                started = self._parse_iso_datetime(task.started_at)
                if not started:
                    continue
                elapsed = (datetime.now(timezone.utc) - started).total_seconds()

                if elapsed > max_seconds:
                    self.logger.warning(
                        f"Task {task.id} timed out after {elapsed/60:.1f} minutes"
                    )
                    # BUG-078 fix: Use update_task_status() for consistent behavior
                    self.update_task_status(
                        task.id,
                        TaskStatus.FAILED,
                        error_message=f"Task timed out after {elapsed/60:.1f} minutes"
                    )
                    timed_out.append(task.id)
            except (ValueError, TypeError) as e:
                self.logger.warning(f"Failed to parse started_at for task {task.id}: {e}")

        return timed_out

    def get_next_task(self) -> Optional[RescueTask]:
        """Get the next executable task (dependencies met, status pending).

        Also checks for and times out stuck RUNNING tasks that might be blocking progress.

        Note: SKIPPED tasks are treated as satisfied dependencies, allowing downstream
        tasks to proceed even if some dependencies were skipped.

        BUG-2 fix: Returns a copy of the task to prevent race conditions where
        multiple concurrent calls could return the same task object reference.
        """
        # First, timeout any stuck running tasks
        timed_out = self.timeout_stuck_tasks()
        if timed_out:
            self.logger.warning(f"Timed out stuck tasks: {timed_out}")

        # SKIPPED tasks are treated as satisfied dependencies - downstream tasks can proceed
        completed_ids = {t.id for t in self.data.tasks if t.status in ("completed", "skipped")}
        running_ids = {t.id for t in self.data.tasks if t.status == "running"}

        for task in self.data.tasks:
            if task.status != "pending":
                continue

            # Check all dependencies are completed
            deps_met = all(dep_id in completed_ids for dep_id in task.inputs)
            if deps_met:
                # BUG-2 fix: Return a copy to prevent race conditions
                # where multiple callers could modify the same task object
                return RescueTask(**task.model_dump())

            # Check if any dependency is stuck in RUNNING state
            for dep_id in task.inputs:
                if dep_id in running_ids:
                    dep_task = self.get_task(dep_id)
                    if dep_task and dep_task.started_at:
                        # Log warning for long-running tasks (not yet timed out)
                        try:
                            started = self._parse_iso_datetime(dep_task.started_at)
                            if started:
                                elapsed = (datetime.now(timezone.utc) - started).total_seconds()
                                if elapsed > 1800:  # 30 minutes
                                    self.logger.warning(
                                        f"Dependency {dep_id} has been RUNNING for {elapsed/60:.1f} minutes - "
                                        "may be stuck"
                                    )
                        except (ValueError, TypeError):
                            pass

        return None

    def _parse_iso_datetime(self, timestamp: str) -> Optional[datetime]:
        """Parse ISO datetime string, handling Z suffix correctly.

        BUG-9 fix: Safely handles Z suffix without affecting other characters.
        """
        if not timestamp:
            return None
        try:
            # Handle Z suffix properly - only replace trailing Z
            if timestamp.endswith('Z'):
                timestamp = timestamp[:-1] + '+00:00'
            return datetime.fromisoformat(timestamp)
        except (ValueError, TypeError):
            return None

    def has_pending_tasks(self) -> bool:
        """Check if there are pending tasks."""
        return any(t.status == "pending" for t in self.data.tasks)

    def validate_task_references(self) -> List[str]:
        """Validate all task references exist.

        Returns:
            List of error messages for invalid references
        """
        errors = []
        task_ids = {t.id for t in self.data.tasks}

        for task in self.data.tasks:
            for dep_id in task.inputs:
                if dep_id not in task_ids:
                    errors.append(f"Task {task.id} references non-existent dependency: {dep_id}")
            # Check for self-reference
            if task.id in task.inputs:
                errors.append(f"Task {task.id} has self-reference in inputs")

        return errors

    def detect_cycles(self) -> Optional[List[str]]:
        """Detect cycles in the task dependency graph.

        Also validates that all referenced tasks exist.

        Returns:
            List of task IDs forming a cycle if found, None if no cycles.
            Returns ["INVALID_REFERENCES"] if there are invalid task references -
            callers should check this and call validate_task_references() for details.

        BUG-1 fix: Uses per-branch path tracking instead of global path list
        to prevent incorrect cycle detection across DFS branches.
        """
        # First validate all references
        ref_errors = self.validate_task_references()
        if ref_errors:
            for error in ref_errors:
                self.logger.error(error)
            # Return error indicator so callers know there's a problem
            # This ensures callers handle the error case rather than assuming no cycles
            return ["INVALID_REFERENCES"]

        # Build adjacency list (task -> dependencies)
        task_deps: Dict[str, List[str]] = {}
        for task in self.data.tasks:
            task_deps[task.id] = list(task.inputs)

        # DFS to detect cycle with per-branch path tracking
        visited = set()
        rec_stack = set()

        def dfs(task_id: str, current_path: List[str]) -> Optional[List[str]]:
            """DFS with explicit path parameter to avoid global path corruption.

            BUG-1 fix: Pass path as parameter instead of using global list.
            """
            if task_id in rec_stack:
                # Found cycle - extract it from current path
                try:
                    cycle_start = current_path.index(task_id)
                    return current_path[cycle_start:] + [task_id]
                except ValueError:
                    # task_id not in current_path - shouldn't happen but handle gracefully
                    return [task_id, task_id]

            if task_id in visited:
                return None

            visited.add(task_id)
            rec_stack.add(task_id)

            for dep_id in task_deps.get(task_id, []):
                # Pass current path + task_id to recursive call
                cycle = dfs(dep_id, current_path + [task_id])
                if cycle:
                    return cycle

            rec_stack.remove(task_id)
            return None

        # Check all tasks
        for task in self.data.tasks:
            if task.id not in visited:
                cycle = dfs(task.id, [])
                if cycle:
                    return cycle

        return None

    def is_blocked(self) -> bool:
        """Check if all remaining tasks are blocked by failed or blocked dependencies.

        BUG-077 fix: A task is considered blocked by failures ONLY if ALL its unmet
        dependencies are failed/blocked. If a task has pending dependencies that
        could still complete, it's not truly blocked - it's just waiting.

        Returns True if:
        - There are pending tasks AND
        - There are failed or blocked tasks AND
        - Every pending task's unmet dependencies are ALL failed/blocked
          (not just waiting on pending dependencies)

        Returns False if:
        - No pending tasks exist (nothing to block)
        - No failed/blocked tasks exist (nothing causing blocks)
        - At least one pending task could proceed once pending deps complete
        """
        pending_tasks = [t for t in self.data.tasks if t.status == "pending"]
        if not pending_tasks:
            return False

        # Get sets of task IDs by status
        completed_ids = {t.id for t in self.data.tasks if t.status in ("completed", "skipped")}
        blocking_ids = {t.id for t in self.data.tasks if t.status in ("failed", "blocked")}
        pending_ids = {t.id for t in self.data.tasks if t.status == "pending"}
        running_ids = {t.id for t in self.data.tasks if t.status == "running"}

        if not blocking_ids:
            # Nothing failed or blocked, so not blocked
            return False

        # Check each pending task
        for task in pending_tasks:
            # Get unmet dependencies (not completed/skipped)
            unmet_deps = [dep_id for dep_id in task.inputs if dep_id not in completed_ids]

            if not unmet_deps:
                # All deps met - this task can run (shouldn't be pending, but handle gracefully)
                return False

            # Check if any unmet dependency is pending or running (could still complete)
            has_waiting_dep = any(
                dep_id in pending_ids or dep_id in running_ids
                for dep_id in unmet_deps
            )
            if has_waiting_dep:
                # This task is waiting on pending/running deps, not blocked by failures
                return False

            # All unmet deps must be failed/blocked - check this explicitly
            all_unmet_blocked = all(dep_id in blocking_ids for dep_id in unmet_deps)
            if not all_unmet_blocked:
                # Some unmet dep is in an unknown state
                self.logger.warning(
                    f"Task {task.id} has unmet deps not in known state: {unmet_deps}"
                )
                return False

        # All pending tasks have ALL their unmet deps failed/blocked
        self.logger.debug(
            f"Workflow is blocked: {len(pending_tasks)} pending tasks all blocked by failed dependencies"
        )
        return True

    def _has_executable_task(self) -> bool:
        """Check if any pending task has all dependencies met.

        Unlike get_next_task(), this is a pure predicate with no side effects
        (no timeout_stuck_tasks mutation). Safe to call from diagnostic methods.
        """
        completed_ids = {t.id for t in self.data.tasks if t.status in ("completed", "skipped")}
        for task in self.data.tasks:
            if task.status != "pending":
                continue
            if all(dep_id in completed_ids for dep_id in task.inputs):
                return True
        return False

    def is_stuck(self) -> bool:
        """Check if workflow is stuck (pending tasks but none executable).

        This differs from is_blocked() - stuck means no task can run, but not
        necessarily due to failures. Could be due to cycles or incomplete deps.

        Review fix #1: Uses _has_executable_task() instead of get_next_task()
        to avoid mutation side effects (timeout_stuck_tasks) in a predicate.

        Returns True if:
        - Has pending tasks
        - No task has all dependencies met
        - No tasks are blocked by failures (so replan won't help)
        """
        if not self.has_pending_tasks():
            return False

        if self._has_executable_task():
            return False

        # If blocked by failures, replan can help
        if self.is_blocked():
            return False

        # Stuck - likely a cycle or orphaned dependencies
        return True

    def get_tasks_by_phase(self, phase: str) -> List[RescueTask]:
        """Get all tasks for a specific phase."""
        return [t for t in self.data.tasks if t.phase == phase]

    def get_task_stats(self) -> Dict[str, int]:
        """Get task completion statistics.

        BUG-11 fix: Logs warning for unknown task statuses instead of silently skipping.
        """
        stats = {
            "total": len(self.data.tasks),
            "pending": 0,
            "running": 0,
            "completed": 0,
            "failed": 0,
            "skipped": 0,
            "blocked": 0,
        }
        for task in self.data.tasks:
            if task.status in stats:
                stats[task.status] += 1
            else:
                # BUG-11 fix: Log warning for unknown status instead of silently skipping
                self.logger.warning(f"Unknown task status '{task.status}' for task {task.id}")
        return stats

    # ---------------------------------------------------------------------
    # Phase Operations
    # ---------------------------------------------------------------------

    def mark_phase_complete(self, phase: RescuePhase) -> bool:
        """Mark a phase as complete.

        Args:
            phase: The phase to mark complete

        Returns:
            True if phase was marked complete, False if invalid phase
        """
        if not isinstance(phase, RescuePhase):
            self.logger.error(f"Invalid phase type: {type(phase)}")
            return False

        if phase == RescuePhase.DISCOVERY:
            self.data.discovery.discovery_complete = True
            self.data.current_phase = "triage"
        elif phase == RescuePhase.TRIAGE:
            self.data.triage.triage_complete = True
            self.data.current_phase = "execution"
        elif phase == RescuePhase.EXECUTION:
            self.data.execution.execution_complete = True
            self.data.current_phase = "validation"
        elif phase == RescuePhase.VALIDATION:
            self.data.validation.validation_complete = True
            self.data.current_phase = "delivery"
        elif phase == RescuePhase.DELIVERY:
            # Delivery is the final phase
            self.logger.info("Delivery phase marked complete - workflow finished")
        else:
            self.logger.error(f"Unknown phase: {phase}")
            return False

        self.logger.info(f"Phase {phase.value} marked complete, moving to {self.data.current_phase}")
        return True

    def add_checkpoint(
        self,
        checkpoint_type: str,
        approved: bool,
        notes: str = "",
        scope_changes: Optional[List[str]] = None
    ) -> None:
        """Record a checkpoint.

        Args:
            checkpoint_type: Type of checkpoint (e.g., "triage", "validation")
            approved: Whether the checkpoint was approved
            notes: Optional notes about the checkpoint
            scope_changes: Optional list of scope changes made at this checkpoint
        """
        self.data.checkpoints.append(CheckpointRecord(
            checkpoint_type=checkpoint_type,
            timestamp=datetime.now(timezone.utc).isoformat(),
            approved=approved,
            notes=notes,
            scope_changes=scope_changes or []
        ))
        self.logger.info(f"Checkpoint recorded: {checkpoint_type} - approved={approved}")

    def add_learning(self, learning: str) -> None:
        """Add a learning discovered during execution."""
        self.data.learnings.append(learning)

    # ---------------------------------------------------------------------
    # Discovery Phase Helpers
    # ---------------------------------------------------------------------

    def update_discovery(
        self,
        source_stack: Optional[SourceStackInfo] = None,
        features: Optional[List[FeatureSpec]] = None,
        ui_components: Optional[List[UIComponentSpec]] = None,
        red_flags: Optional[DiscoveryRedFlags] = None,
    ) -> None:
        """Update discovery phase data."""
        if source_stack:
            self.data.discovery.source_stack = source_stack
        if features:
            self.data.discovery.features_detected = features
        if ui_components:
            self.data.discovery.ui_components = ui_components
            # Auto-calculate styling methods
            all_methods = set()
            for comp in ui_components:
                all_methods.update(comp.styling_methods)
            self.data.discovery.styling_methods_found = list(all_methods)
        if red_flags:
            self.data.discovery.red_flags = red_flags

    # ---------------------------------------------------------------------
    # Triage Phase Helpers
    # ---------------------------------------------------------------------

    def update_triage(
        self,
        backend_classification: Optional[Dict[str, str]] = None,
        ui_rescue_decisions: Optional[Dict[str, str]] = None,
        estimated_hours: Optional[tuple] = None,
    ) -> None:
        """Update triage phase data."""
        if backend_classification:
            self.data.triage.backend_classification = backend_classification
        if ui_rescue_decisions:
            self.data.triage.ui_rescue_decisions = ui_rescue_decisions
        if estimated_hours:
            self.data.triage.estimated_hours_min = estimated_hours[0]
            self.data.triage.estimated_hours_max = estimated_hours[1]

    # ---------------------------------------------------------------------
    # Validation Phase Helpers
    # ---------------------------------------------------------------------

    def update_validation(
        self,
        tests_passed: Optional[int] = None,
        tests_failed: Optional[int] = None,
        visual_match_percent: Optional[float] = None,
        feature_parity_percent: Optional[float] = None,
    ) -> None:
        """Update validation phase data."""
        if tests_passed is not None:
            self.data.validation.tests_passed = tests_passed
        if tests_failed is not None:
            self.data.validation.tests_failed = tests_failed
        if visual_match_percent is not None:
            self.data.validation.visual_match_percent = visual_match_percent
        if feature_parity_percent is not None:
            self.data.validation.feature_parity_percent = feature_parity_percent

    # ---------------------------------------------------------------------
    # Summary and Reporting
    # ---------------------------------------------------------------------

    def get_summary(self) -> Dict[str, Any]:
        """Get a summary of the rescue state for reporting."""
        task_stats = self.get_task_stats()

        return {
            "adw_id": self.adw_id,
            "current_phase": self.data.current_phase,
            "plan_version": self.data.plan_version,
            "discovery": {
                "complete": self.data.discovery.discovery_complete,
                "features_count": len(self.data.discovery.features_detected),
                "components_count": len(self.data.discovery.ui_components),
                "difficulty": self.data.discovery.red_flags.estimated_difficulty,
            },
            "triage": {
                "complete": self.data.triage.triage_complete,
                "estimated_tasks": self.data.triage.estimated_tasks,
                "estimated_hours": f"{self.data.triage.estimated_hours_min}-{self.data.triage.estimated_hours_max}",
            },
            "execution": {
                "complete": self.data.execution.execution_complete,
                "tasks_completed": task_stats["completed"],
                "tasks_failed": task_stats["failed"],
                "tasks_pending": task_stats["pending"],
            },
            "validation": {
                "complete": self.data.validation.validation_complete,
                "tests_passed": self.data.validation.tests_passed,
                "tests_failed": self.data.validation.tests_failed,
                "visual_match": f"{self.data.validation.visual_match_percent}%",
            },
            "checkpoints": len(self.data.checkpoints),
            "learnings": len(self.data.learnings),
        }
