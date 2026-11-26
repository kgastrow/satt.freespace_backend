"""Multi-phase operations for ADW workflows.

Provides plan parsing, phase state management, and execution utilities
for large features that require multiple implementation phases.
"""

import os
import re
import json
import logging
from datetime import datetime
from typing import List, Optional, Dict, Any
from dataclasses import dataclass, field
from enum import Enum


class PhaseStatus(str, Enum):
    """Status of a phase in the multi-phase workflow."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class Phase:
    """Represents a single phase in a multi-phase plan."""
    id: str
    name: str
    description: str
    dependencies: List[str] = field(default_factory=list)
    scope: List[str] = field(default_factory=list)
    acceptance_criteria: List[str] = field(default_factory=list)
    test_scope: str = ""

    def has_dependencies(self) -> bool:
        """Check if this phase has dependencies."""
        return len(self.dependencies) > 0 and self.dependencies != ["none"]


@dataclass
class MultiPhasePlan:
    """Represents a parsed multi-phase implementation plan."""
    issue_number: str
    adw_id: str
    total_phases: int
    feature_description: str
    phases: List[Phase]
    execution_order: List[str]
    integration_validation: str
    plan_path: str


@dataclass
class PhaseState:
    """State tracking for a single phase."""
    status: PhaseStatus = PhaseStatus.PENDING
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    commit_sha: Optional[str] = None
    test_passed: Optional[bool] = None
    review_passed: Optional[bool] = None
    failure_stage: Optional[str] = None
    failure_reason: Optional[str] = None
    retry_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "status": self.status.value,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "commit_sha": self.commit_sha,
            "test_passed": self.test_passed,
            "review_passed": self.review_passed,
            "failure_stage": self.failure_stage,
            "failure_reason": self.failure_reason,
            "retry_count": self.retry_count,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PhaseState":
        """Create from dictionary."""
        return cls(
            status=PhaseStatus(data.get("status", "pending")),
            started_at=data.get("started_at"),
            completed_at=data.get("completed_at"),
            commit_sha=data.get("commit_sha"),
            test_passed=data.get("test_passed"),
            review_passed=data.get("review_passed"),
            failure_stage=data.get("failure_stage"),
            failure_reason=data.get("failure_reason"),
            retry_count=data.get("retry_count", 0),
        )


@dataclass
class IntegrationState:
    """State tracking for the integration validation phase."""
    status: PhaseStatus = PhaseStatus.PENDING
    full_test_passed: Optional[bool] = None
    smoke_passed: Optional[bool] = None
    final_review_passed: Optional[bool] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "status": self.status.value,
            "full_test_passed": self.full_test_passed,
            "smoke_passed": self.smoke_passed,
            "final_review_passed": self.final_review_passed,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "IntegrationState":
        """Create from dictionary."""
        return cls(
            status=PhaseStatus(data.get("status", "pending")),
            full_test_passed=data.get("full_test_passed"),
            smoke_passed=data.get("smoke_passed"),
            final_review_passed=data.get("final_review_passed"),
        )


class MultiPhaseState:
    """Extended state management for multi-phase workflows.

    This extends the base ADWState with multi-phase specific tracking.
    State is stored in agents/{adw_id}/multi_phase_state.json
    """

    STATE_FILENAME = "multi_phase_state.json"

    def __init__(self, adw_id: str):
        self.adw_id = adw_id
        self.workflow_type = "multi_phase_sdlc"
        self.multi_phase_plan: Optional[str] = None
        self.phases: Dict[str, PhaseState] = {}
        self.current_phase: Optional[str] = None
        self.phases_completed: int = 0
        self.phases_total: int = 0
        self.integration: IntegrationState = IntegrationState()
        self.logger = logging.getLogger(__name__)

    def initialize_phases(self, phase_ids: List[str]) -> None:
        """Initialize phase tracking for all phases."""
        self.phases = {pid: PhaseState() for pid in phase_ids}
        self.phases_total = len(phase_ids)
        self.phases_completed = 0

    def get_phase_state(self, phase_id: str) -> Optional[PhaseState]:
        """Get state for a specific phase."""
        return self.phases.get(phase_id)

    def update_phase(self, phase_id: str, **kwargs) -> None:
        """Update state for a specific phase."""
        if phase_id not in self.phases:
            self.phases[phase_id] = PhaseState()

        phase = self.phases[phase_id]
        for key, value in kwargs.items():
            if hasattr(phase, key):
                if key == "status" and isinstance(value, str):
                    value = PhaseStatus(value)
                setattr(phase, key, value)

    def mark_phase_started(self, phase_id: str) -> None:
        """Mark a phase as started."""
        # BUG-041 fix: Use timezone-aware UTC datetime
        self.update_phase(
            phase_id,
            status=PhaseStatus.IN_PROGRESS,
            started_at=datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
        )
        self.current_phase = phase_id

    def mark_phase_completed(self, phase_id: str, commit_sha: str) -> None:
        """Mark a phase as completed."""
        # BUG-041 fix: Use timezone-aware UTC datetime
        self.update_phase(
            phase_id,
            status=PhaseStatus.COMPLETED,
            completed_at=datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
            commit_sha=commit_sha,
            test_passed=True,
            review_passed=True
        )
        self.phases_completed += 1

    def mark_phase_failed(self, phase_id: str, stage: str, reason: str) -> None:
        """Mark a phase as failed."""
        self.update_phase(
            phase_id,
            status=PhaseStatus.FAILED,
            failure_stage=stage,
            failure_reason=reason
        )

    def get_first_incomplete_phase(self, phase_ids: List[str]) -> Optional[str]:
        """Get the first phase that is not completed (for resume)."""
        for pid in phase_ids:
            phase = self.phases.get(pid)
            if not phase or phase.status != PhaseStatus.COMPLETED:
                return pid
        return None

    def dependencies_met(self, phase: Phase) -> bool:
        """Check if all dependencies for a phase are completed."""
        if not phase.has_dependencies():
            return True

        for dep_id in phase.dependencies:
            dep_state = self.phases.get(dep_id)
            if not dep_state or dep_state.status != PhaseStatus.COMPLETED:
                return False
        return True

    def get_state_path(self) -> str:
        """Get path to multi-phase state file."""
        project_root = os.path.dirname(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        )
        return os.path.join(project_root, "agents", self.adw_id, self.STATE_FILENAME)

    def save(self) -> None:
        """Save multi-phase state to file."""
        state_path = self.get_state_path()
        os.makedirs(os.path.dirname(state_path), exist_ok=True)

        data = {
            "adw_id": self.adw_id,
            "workflow_type": self.workflow_type,
            "multi_phase_plan": self.multi_phase_plan,
            "phases": {pid: ps.to_dict() for pid, ps in self.phases.items()},
            "current_phase": self.current_phase,
            "phases_completed": self.phases_completed,
            "phases_total": self.phases_total,
            "integration": self.integration.to_dict(),
        }

        with open(state_path, "w") as f:
            json.dump(data, f, indent=2)

        self.logger.info(f"Saved multi-phase state to {state_path}")

    @classmethod
    def load(cls, adw_id: str, logger: Optional[logging.Logger] = None) -> Optional["MultiPhaseState"]:
        """Load multi-phase state from file if it exists."""
        project_root = os.path.dirname(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        )
        state_path = os.path.join(project_root, "agents", adw_id, cls.STATE_FILENAME)

        if not os.path.exists(state_path):
            return None

        try:
            with open(state_path, "r") as f:
                data = json.load(f)

            state = cls(data["adw_id"])
            state.workflow_type = data.get("workflow_type", "multi_phase_sdlc")
            state.multi_phase_plan = data.get("multi_phase_plan")
            state.phases = {
                pid: PhaseState.from_dict(ps)
                for pid, ps in data.get("phases", {}).items()
            }
            state.current_phase = data.get("current_phase")
            state.phases_completed = data.get("phases_completed", 0)
            state.phases_total = data.get("phases_total", 0)
            state.integration = IntegrationState.from_dict(
                data.get("integration", {})
            )

            if logger:
                logger.info(f"Loaded multi-phase state from {state_path}")

            return state
        except Exception as e:
            if logger:
                logger.error(f"Failed to load multi-phase state: {e}")
            return None


def parse_multi_phase_plan(plan_path: str, logger: Optional[logging.Logger] = None) -> Optional[MultiPhasePlan]:
    """Parse a multi-phase markdown plan into structured data.

    Includes validation to fail clearly on malformed plans (BUG-011 fix).

    Args:
        plan_path: Path to the multi-phase plan markdown file
        logger: Optional logger for debug output

    Returns:
        MultiPhasePlan object if parsing succeeds, None otherwise
    """
    if not os.path.exists(plan_path):
        if logger:
            logger.error(f"Plan file not found: {plan_path}")
        return None

    with open(plan_path, "r") as f:
        content = f.read()

    # Extract metadata
    issue_number = _extract_metadata_field(content, "issue_number")
    adw_id = _extract_metadata_field(content, "adw_id")
    total_phases_str = _extract_metadata_field(content, "total_phases")
    total_phases = int(total_phases_str) if total_phases_str else 0

    # Extract feature description
    feature_desc_match = re.search(
        r"## Feature Description\s*\n(.*?)(?=\n## |\Z)",
        content,
        re.DOTALL
    )
    feature_description = feature_desc_match.group(1).strip() if feature_desc_match else ""

    # Extract phases
    phases = _parse_phases(content, logger)

    # BUG-011 fix: Fail clearly if no phases found
    if not phases:
        if logger:
            logger.error("No phases found in plan - check plan format. Expected '## Phases' section with '### Phase N:' or '## Phase N:' subsections.")
        return None

    # Extract execution order
    execution_order = _extract_execution_order(content, phases)

    # BUG-011 fix: Fail clearly if no execution order
    if not execution_order:
        if logger:
            logger.error("No execution order found in plan - check plan format. Expected '## Execution Order' section or phases list.")
        return None

    # Extract integration validation
    integration_match = re.search(
        r"## Integration Validation\s*\n(.*?)(?=\n## |\Z)",
        content,
        re.DOTALL
    )
    integration_validation = integration_match.group(1).strip() if integration_match else ""

    return MultiPhasePlan(
        issue_number=issue_number or "",
        adw_id=adw_id or "",
        total_phases=total_phases or len(phases),
        feature_description=feature_description,
        phases=phases,
        execution_order=execution_order,
        integration_validation=integration_validation,
        plan_path=plan_path,
    )


def _extract_metadata_field(content: str, field_name: str) -> Optional[str]:
    """Extract a metadata field value from plan content."""
    pattern = rf"{field_name}:\s*`([^`]+)`"
    match = re.search(pattern, content)
    return match.group(1) if match else None


def _parse_phases(content: str, logger: Optional[logging.Logger] = None) -> List[Phase]:
    """Parse phase sections from plan content."""
    phases = []

    # Find the Phases section (strict format: ## Phases wrapper)
    phases_section_match = re.search(
        r"## Phases\s*\n(.*?)(?=\n## [^#]|\Z)",
        content,
        re.DOTALL
    )

    if phases_section_match:
        phases_content = phases_section_match.group(1)
    else:
        # Fallback: agent may have written phases directly without a
        # "## Phases" wrapper (e.g. "## Phase 1: ...", "## Phase 2: ...").
        # Use the full content starting from the first phase heading.
        first_phase = re.search(r'^(##+ Phase \d+)', content, re.MULTILINE)
        if first_phase:
            phases_content = content[first_phase.start():]
            if logger:
                logger.info("No '## Phases' wrapper found, parsing phases from top-level headings")
        else:
            if logger:
                logger.warning("No phase sections found in plan")
            return phases

    # Split by phase headers: accept both ## Phase N: and ### Phase N:
    phase_sections = re.split(r"##+ Phase (\d+)[:\s]+", phases_content)

    # Build mapping of phase number to phase ID as we parse
    phase_num_to_id = {}

    # phase_sections[0] is content before first phase, then alternates: num, content, num, content...
    for i in range(1, len(phase_sections), 2):
        phase_num = phase_sections[i]
        section = phase_sections[i + 1] if i + 1 < len(phase_sections) else ""

        if not section.strip():
            continue

        phase = _parse_single_phase(section, logger)
        if phase:
            phases.append(phase)
            phase_num_to_id[phase_num] = phase.id

    # Post-process: resolve "Phase N" dependencies to actual phase IDs
    for phase in phases:
        resolved_deps = []
        for dep in phase.dependencies:
            # Check if dependency is in "Phase N" format
            phase_ref_match = re.match(r"Phase\s*(\d+)", dep, re.IGNORECASE)
            if phase_ref_match:
                phase_num = phase_ref_match.group(1)
                if phase_num in phase_num_to_id:
                    resolved_deps.append(phase_num_to_id[phase_num])
                else:
                    if logger:
                        logger.warning(f"Could not resolve dependency '{dep}' - Phase {phase_num} not found")
                    resolved_deps.append(dep)  # Keep original if can't resolve
            else:
                resolved_deps.append(dep)  # Already a phase ID
        phase.dependencies = resolved_deps

    return phases


def _slugify_phase_id(text: str) -> str:
    """Convert a phase heading into a clean, filesystem-safe phase ID.

    Examples:
        'backend-websocket-infrastructure' -> 'backend-websocket-infrastructure'
        'Backend Models & Migration' -> 'backend-models-migration'
        'Frontend API Integration (Types)' -> 'frontend-api-integration-types'
    """
    slug = text.lower().strip()
    # Replace & and common separators with hyphens
    slug = re.sub(r'[&/\\]', '-', slug)
    # Remove parentheses but keep content
    slug = re.sub(r'[()]', '', slug)
    # Replace non-alphanumeric (except hyphens) with hyphens
    slug = re.sub(r'[^a-z0-9-]+', '-', slug)
    # Collapse multiple hyphens and strip leading/trailing
    slug = re.sub(r'-+', '-', slug).strip('-')
    return slug


def _parse_single_phase(section: str, logger: Optional[logging.Logger] = None) -> Optional[Phase]:
    """Parse a single phase section.

    Handles both strict format (**Name:**, **Description:**, **Scope:**)
    and agent-generated format (**Goal:**, ### Files to Create, etc.).
    """
    lines = section.strip().split("\n")
    if not lines:
        return None

    # First line is the phase ID or name
    raw_id = lines[0].strip()
    # If it already looks like a slug, use as-is; otherwise slugify
    if re.match(r'^[a-z0-9-]+$', raw_id):
        phase_id = raw_id
    else:
        phase_id = _slugify_phase_id(raw_id)

    # Extract fields - try multiple alternate names for each
    name = (_extract_phase_field(section, "Name")
            or raw_id.strip()
            or phase_id)
    description = (_extract_phase_field(section, "Description")
                   or _extract_phase_field(section, "Goal")
                   or "")
    dependencies = _extract_phase_list(section, "Dependencies")
    scope = (_extract_phase_list(section, "Scope")
             or _extract_phase_list(section, "Files"))
    acceptance_criteria = (_extract_phase_list(section, "Acceptance Criteria")
                          or _extract_phase_list(section, "Validation"))
    test_scope = (_extract_phase_field(section, "Test Scope")
                  or _extract_phase_field(section, "Tests")
                  or "")

    return Phase(
        id=phase_id,
        name=name,
        description=description,
        dependencies=dependencies,
        scope=scope,
        acceptance_criteria=acceptance_criteria,
        test_scope=test_scope,
    )


def _extract_phase_field(section: str, field_name: str) -> Optional[str]:
    """Extract a single-line field from a phase section."""
    pattern = rf"\*\*{field_name}:\*\*\s*(.+?)(?=\n\*\*|\n---|\Z)"
    match = re.search(pattern, section, re.DOTALL)
    if match:
        return match.group(1).strip()
    return None


def _extract_phase_list(section: str, field_name: str) -> List[str]:
    """Extract a list field from a phase section."""
    pattern = rf"\*\*{field_name}:\*\*\s*\n((?:[-*]\s+.+\n?)+)"
    match = re.search(pattern, section)
    if not match:
        # Try inline format: **Field:** value
        inline_pattern = rf"\*\*{field_name}:\*\*\s*(.+?)(?=\n\*\*|\n---|\Z)"
        inline_match = re.search(inline_pattern, section)
        if inline_match:
            value = inline_match.group(1).strip()
            if value.lower() == "none":
                return []
            return [value]
        return []

    list_content = match.group(1)
    items = []
    for line in list_content.strip().split("\n"):
        line = line.strip()
        if line.startswith("-") or line.startswith("*"):
            item = line[1:].strip().strip("`")
            if item and item.lower() != "none":
                items.append(item)

    return items


def _extract_execution_order(content: str, phases: List[Phase]) -> List[str]:
    """Extract execution order from plan content."""
    order_match = re.search(
        r"## Execution Order\s*\n(.*?)(?=\n## |\Z)",
        content,
        re.DOTALL
    )

    if order_match:
        order_content = order_match.group(1)
        # Extract phase IDs from numbered list
        order = []
        for line in order_content.strip().split("\n"):
            # Match patterns like "1. Phase 1: backend-websocket" or "1. backend-websocket"
            match = re.search(r"\d+\.\s*(?:Phase \d+:\s*)?(\S+)", line)
            if match:
                phase_id = match.group(1).strip()
                order.append(phase_id)

        if order:
            return order

    # Fall back to phase order as defined
    return [p.id for p in phases]


def get_phase_by_id(plan: MultiPhasePlan, phase_id: str) -> Optional[Phase]:
    """Get a phase from the plan by its ID."""
    for phase in plan.phases:
        if phase.id == phase_id:
            return phase
    return None


def format_phase_scope_for_prompt(phase: Phase) -> str:
    """Format phase scope for use in prompts."""
    if not phase.scope:
        return "No specific files listed"

    return "\n".join(f"- `{f}`" for f in phase.scope)


def format_acceptance_criteria_for_prompt(phase: Phase) -> str:
    """Format acceptance criteria for use in prompts."""
    if not phase.acceptance_criteria:
        return "No specific acceptance criteria listed"

    return "\n".join(f"- {c}" for c in phase.acceptance_criteria)
