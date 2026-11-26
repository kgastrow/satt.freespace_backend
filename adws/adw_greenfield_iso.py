#!/usr/bin/env -S uv run
# /// script
# dependencies = ["python-dotenv", "pydantic", "redis"]
# ///

"""
ADW Greenfield Orchestrator - Multi-module implementation from specifications

Usage: uv run adw_greenfield_iso.py <spec-files-glob> [adw-id] [--resume] [--skip-smoke] [--skip-verify] [--skip-e2e] [--dry-run] [--preserve-on-failure] [--no-auto-rescue] [--rescue-min-criteria-pct N] [--design <handoff-dir>]

Flags:
  --resume                Pick up where a prior run left off (uses adw-id).
  --skip-smoke            Skip smoke testing inside each module's SDLC.
  --skip-verify           Skip BOTH pre-merge per-module verification and the
                          final whole-app verification step.
  --skip-e2e              Skip the E2E validation phase after modules merge.
  --dry-run               Decompose and print the plan; do not implement.
  --preserve-on-failure   On module failure, keep the worktree + state so the
                          next --resume can pick up at the failed phase
                          instead of replaying the entire child SDLC.
  --no-auto-rescue        Disable the auto-rescue loop. When the pre-merge
                          verifier returns "partial", the workflow normally
                          spawns ONE /rescue_verification pass to patch
                          met:false criteria and re-verifies. Use this flag to
                          fall straight through to the failure branch instead.
  --rescue-min-criteria-pct N
                          Only auto-rescue when at least N% of criteria are
                          already met (default 25). Below this, a "partial"
                          verdict is treated as a planning bust and escalated
                          to the operator without burning a patch budget.
                          The 25% floor was tuned down from 40% after a real
                          run where a module sat at 3/8 (37.5%) and was wrongly
                          skipped — the verifier's pass/fail binary scored
                          near-complete partials the same as zero-progress.
  --design <dir>          Use a design handoff bundle (see top of file).

This workflow orchestrates greenfield implementation of entire projects from specifications:
1. Consumes one or more specification files (functional specs, user stories)
2. Decomposes specifications into functional modules/sub-modules
3. Creates a tracking sheet with implementation status for each module
4. For each module, invokes the SDLC router workflow (single or multi-phase)
5. Tracks progress across all modules with resume capability

Designed for one-shot implementation of complete greenfield projects while
managing context effectively by splitting work into bounded modules.

When --design is provided, the workflow:
- Phase 0 (auto): if `ai_docs/frontend/context/design_system.md` is missing, spawns
  `adw_assimilate_design_iso.py` automatically, then merges its branch into main and
  pushes so child module worktrees pick up the rewritten ai_docs/. Skipped if the
  handoff was already assimilated (re-runs are cheap and idempotent).
- Adds the handoff dir's README.md to the spec set passed to /decompose_specs so each
  UI-bearing module receives design_references and design_screens.
- Per-module review activates the /validate_design_match gate against prototype screens.

Without --design, the workflow runs unchanged — every design-aware step is a no-op.
Running `adw_assimilate_design_iso.py` manually first is still supported (and
recommended if you want to review the ai_docs rewrite as its own PR).

Example:
    uv run adw_greenfield_iso.py "specs/*.md" greenfield-001
    uv run adw_greenfield_iso.py "specs/functional-spec.md,specs/user-stories.md"
    uv run adw_greenfield_iso.py "specs/legacy_sports_prd.md" --design specs/design_handoff_legacy_sports
"""

import subprocess
import sys
import os
import json
import logging
import re
import signal
import shutil
import time
import glob as glob_module
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum

# Add the parent directory to Python path to import modules
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
from pydantic import BaseModel

from adw_modules.state import ADWState
from adw_modules.workflow_ops import format_issue_message
from adw_modules.git_ops import push_branch
from adw_modules.github import check_gh_auth, make_issue_comment, get_repo_url, extract_repo_path
from adw_modules.agent import execute_template
from adw_modules.data_types import AgentTemplateRequest
from adw_modules.utils import setup_logger, check_env_vars, parse_json, make_adw_id
from adw_modules.cost_tracker import CostTracker
from adw_modules.worktree_ops import (
    create_worktree,
    setup_worktree_environment,
    get_ports_for_adw,
    find_next_available_ports,
    is_port_available,
    remove_worktree,
)
# Reuse the proven merge-to-main implementation from the ship workflow rather
# than duplicating it. Phase-0 assimilation merges its branch to main here so
# subsequent module worktrees (branched from origin/main) pick up the rewritten
# ai_docs/ files.
from adw_ship_iso import manual_merge_to_main


# Agent name constants for greenfield workflow
AGENT_DECOMPOSER = "spec_decomposer"
AGENT_ORCHESTRATOR = "greenfield_orchestrator"
AGENT_MODULE_ISSUE_CREATOR = "module_issue_creator"
AGENT_VERIFIER = "spec_verifier"
AGENT_DOMAIN_DOCUMENTER = "domain_documenter"

# Process cleanup tracking
_cleanup_done = False
_active_gf_state: Optional["GreenfieldState"] = None

# Usage limit / server error detection for subprocess output
_WAIT_PATTERNS_USAGE = ["hit your limit", "you've hit your limit", "extra-usage", "usage limit"]
_WAIT_PATTERNS_SERVER = ["internal server error", "500 internal", "overloaded_error", "overloaded error", "api error: 500"]
_MAX_WAIT_RETRIES = 12  # 12 x 15 min = 3 hours
_WAIT_INTERVAL_SECONDS = 15 * 60  # 15 minutes


def _detect_wait_error(stdout: str, stderr: str) -> Optional[str]:
    """Check subprocess output for usage limit or server errors.

    Returns 'usage_limit', 'server_error', or None.
    """
    combined = (stdout + stderr).lower()
    for p in _WAIT_PATTERNS_USAGE:
        if p in combined:
            return "usage_limit"
    for p in _WAIT_PATTERNS_SERVER:
        if p in combined:
            return "server_error"
    return None


def _detect_wait_error_in_child_state(child_adw_id: str, logger: logging.Logger) -> Optional[str]:
    """Check the child module's multi_phase_state.json for usage limit / server errors.

    The actual error text often lives in JSONL output and gets recorded in the
    phase failure_reason field, but doesn't appear in subprocess stderr.
    """
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    state_path = os.path.join(project_root, "agents", child_adw_id, "multi_phase_state.json")
    try:
        if not os.path.exists(state_path):
            return None
        with open(state_path, "r") as f:
            state = json.load(f)
        for phase_id, phase in state.get("phases", {}).items():
            reason = phase.get("failure_reason") or ""
            result = _detect_wait_error(reason, "")
            if result:
                logger.info(f"Detected {result} in child state phase {phase_id}: {reason[:100]}")
                return result
    except Exception as e:
        logger.debug(f"Could not read child state for {child_adw_id}: {e}")
    return None


class ModuleStatus(str, Enum):
    """Status of a module in the greenfield workflow."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class ModulePriority(str, Enum):
    """Priority level for module implementation."""
    CRITICAL = "critical"  # Must be implemented first, blocks others
    HIGH = "high"          # Should be early, may have dependents
    MEDIUM = "medium"      # Standard priority
    LOW = "low"            # Can be deferred, nice-to-have


@dataclass
class ModuleDefinition:
    """Definition of a functional module extracted from specs."""
    id: str
    name: str
    description: str
    priority: ModulePriority = ModulePriority.MEDIUM
    dependencies: List[str] = field(default_factory=list)
    target_audience: str = "end_user"  # end_user, admin, platform_admin, backend_only
    user_stories: List[str] = field(default_factory=list)
    acceptance_criteria: List[str] = field(default_factory=list)
    estimated_complexity: str = "medium"  # small, medium, large, xl
    spec_references: List[str] = field(default_factory=list)
    # Design handoff integration — populated by /decompose_specs when a design
    # bundle is included in the input spec set. Empty when no handoff is provided.
    design_references: List[Dict[str, Any]] = field(default_factory=list)
    design_screens: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "priority": self.priority.value,
            "dependencies": self.dependencies,
            "target_audience": self.target_audience,
            "user_stories": self.user_stories,
            "acceptance_criteria": self.acceptance_criteria,
            "estimated_complexity": self.estimated_complexity,
            "spec_references": self.spec_references,
            "design_references": self.design_references,
            "design_screens": self.design_screens,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ModuleDefinition":
        return cls(
            id=data["id"],
            name=data["name"],
            description=data["description"],
            priority=ModulePriority(data.get("priority", "medium")),
            dependencies=data.get("dependencies", []),
            target_audience=data.get("target_audience", "end_user"),
            user_stories=data.get("user_stories", []),
            acceptance_criteria=data.get("acceptance_criteria", []),
            estimated_complexity=data.get("estimated_complexity", "medium"),
            spec_references=data.get("spec_references", []),
            design_references=data.get("design_references", []),
            design_screens=data.get("design_screens", []),
        )


@dataclass
class ModuleState:
    """Runtime state for a module during implementation."""
    status: ModuleStatus = ModuleStatus.PENDING
    issue_number: Optional[str] = None
    child_adw_id: Optional[str] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    commit_sha: Optional[str] = None
    error_message: Optional[str] = None
    retry_count: int = 0
    merged_to_main: bool = False
    # Auto-rescue tracking. Set when /rescue_verification runs after a partial
    # verdict so that --resume cannot trigger a second rescue attempt.
    rescue_attempts: int = 0
    rescue_outcome: Optional[str] = None  # upgraded_to_pass|still_partial|errored|skipped_low_criteria

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status.value,
            "issue_number": self.issue_number,
            "child_adw_id": self.child_adw_id,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "commit_sha": self.commit_sha,
            "error_message": self.error_message,
            "retry_count": self.retry_count,
            "merged_to_main": self.merged_to_main,
            "rescue_attempts": self.rescue_attempts,
            "rescue_outcome": self.rescue_outcome,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ModuleState":
        return cls(
            status=ModuleStatus(data.get("status", "pending")),
            issue_number=data.get("issue_number"),
            child_adw_id=data.get("child_adw_id"),
            started_at=data.get("started_at"),
            completed_at=data.get("completed_at"),
            commit_sha=data.get("commit_sha"),
            error_message=data.get("error_message"),
            retry_count=data.get("retry_count", 0),
            merged_to_main=data.get("merged_to_main", False),
            rescue_attempts=data.get("rescue_attempts", 0),
            rescue_outcome=data.get("rescue_outcome"),
        )


class GreenfieldState:
    """State management for greenfield orchestration workflow."""
    
    STATE_FILENAME = "greenfield_state.json"
    TRACKING_FILENAME = "MODULE_TRACKING.md"
    
    def __init__(self, adw_id: str, logger: Optional[logging.Logger] = None):
        self.adw_id = adw_id
        self.spec_files: List[str] = []
        self.modules: Dict[str, ModuleDefinition] = {}
        self.module_states: Dict[str, ModuleState] = {}
        self.execution_order: List[str] = []
        self.user_personas: List[Dict[str, Any]] = []
        self.current_module: Optional[str] = None
        self.modules_completed: int = 0
        self.modules_total: int = 0
        self.decomposition_plan_path: Optional[str] = None
        self.created_at: Optional[str] = None
        self.updated_at: Optional[str] = None
        self.logger = logger or logging.getLogger(__name__)
    
    def initialize_modules(self, modules: List[ModuleDefinition], execution_order: List[str]) -> None:
        """Initialize module tracking from decomposition."""
        self.modules = {m.id: m for m in modules}
        self.module_states = {m.id: ModuleState() for m in modules}
        self.execution_order = execution_order
        self.modules_total = len(modules)
        self.modules_completed = 0
        self.created_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    
    def mark_module_started(self, module_id: str, issue_number: str, child_adw_id: str) -> None:
        """Mark a module as started with its issue and child ADW ID."""
        if module_id in self.module_states:
            self.module_states[module_id].status = ModuleStatus.IN_PROGRESS
            self.module_states[module_id].issue_number = issue_number
            self.module_states[module_id].child_adw_id = child_adw_id
            self.module_states[module_id].started_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            self.current_module = module_id
            self.updated_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    
    def mark_module_completed(self, module_id: str, commit_sha: Optional[str] = None) -> None:
        """Mark a module as completed."""
        if module_id in self.module_states:
            # Guard against double-counting if called twice for same module
            was_already_completed = self.module_states[module_id].status == ModuleStatus.COMPLETED
            self.module_states[module_id].status = ModuleStatus.COMPLETED
            self.module_states[module_id].completed_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            self.module_states[module_id].commit_sha = commit_sha
            if not was_already_completed:
                self.modules_completed += 1
            self.updated_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    
    def mark_module_merged(self, module_id: str) -> None:
        """Mark a module as merged to main."""
        if module_id in self.module_states:
            self.module_states[module_id].merged_to_main = True
            self.updated_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    MAX_MODULE_RETRIES = 3

    def mark_module_failed(self, module_id: str, error: str) -> None:
        """Mark a module as failed."""
        if module_id in self.module_states:
            self.module_states[module_id].status = ModuleStatus.FAILED
            self.module_states[module_id].error_message = error
            self.module_states[module_id].retry_count += 1
            if self.module_states[module_id].retry_count >= self.MAX_MODULE_RETRIES:
                self.module_states[module_id].status = ModuleStatus.SKIPPED
                self.module_states[module_id].error_message = (
                    f"Skipped after {self.MAX_MODULE_RETRIES} retries. Last error: {error}"
                )
                self.logger.error(
                    f"Module '{module_id}' exceeded max retries ({self.MAX_MODULE_RETRIES}), marking as skipped"
                )
            self.updated_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    
    def get_next_module(self) -> Optional[str]:
        """Get the next module to implement based on execution order and dependencies."""
        for module_id in self.execution_order:
            state = self.module_states.get(module_id)
            if not state or state.status != ModuleStatus.PENDING:
                continue
            
            # Check dependencies
            module = self.modules.get(module_id)
            if module and self._dependencies_met(module):
                return module_id
        
        return None
    
    def _dependencies_met(self, module: ModuleDefinition) -> bool:
        """Check if all dependencies for a module are completed."""
        for dep_id in module.dependencies:
            dep_state = self.module_states.get(dep_id)
            if not dep_state:
                self.logger.warning(
                    f"Module '{module.id}' depends on '{dep_id}' which does not exist in the module list"
                )
                return False
            if dep_state.status != ModuleStatus.COMPLETED:
                return False
        return True
    
    def validate_module_consistency(self) -> List[str]:
        """Validate that modules, execution_order, and dependencies are consistent.

        Returns list of warning messages (empty if all OK).
        """
        warnings: List[str] = []
        module_ids = set(self.modules.keys())
        order_ids = set(self.execution_order)

        # Modules in execution_order but not in modules dict
        extra_in_order = order_ids - module_ids
        if extra_in_order:
            warnings.append(
                f"execution_order references non-existent modules: {', '.join(sorted(extra_in_order))}"
            )

        # Modules defined but missing from execution_order (will never execute)
        missing_from_order = module_ids - order_ids
        if missing_from_order:
            warnings.append(
                f"Modules defined but missing from execution_order (will never execute): "
                f"{', '.join(sorted(missing_from_order))}"
            )
            # Auto-fix: append missing modules to execution_order
            for mid in sorted(missing_from_order):
                self.execution_order.append(mid)
                self.logger.warning(f"Auto-appended missing module '{mid}' to execution_order")

        # Dependencies referencing non-existent modules - auto-remove them
        for mid, module in self.modules.items():
            invalid_deps = [dep_id for dep_id in module.dependencies if dep_id not in module_ids]
            for dep_id in invalid_deps:
                warnings.append(
                    f"Module '{mid}' depends on non-existent module '{dep_id}' (auto-removed)"
                )
                module.dependencies.remove(dep_id)
                self.logger.warning(f"Auto-removed invalid dependency '{dep_id}' from module '{mid}'")

        # Check for circular dependencies
        visited: set = set()
        path: set = set()

        def has_cycle(mod_id: str) -> bool:
            if mod_id in path:
                return True
            if mod_id in visited:
                return False
            visited.add(mod_id)
            path.add(mod_id)
            module = self.modules.get(mod_id)
            if module:
                for dep in module.dependencies:
                    if dep in module_ids and has_cycle(dep):
                        return True
            path.discard(mod_id)
            return False

        for mid in module_ids:
            if mid not in visited and has_cycle(mid):
                warnings.append(f"Circular dependency detected involving module '{mid}'")

        return warnings

    def get_state_path(self) -> str:
        """Get path to greenfield state file."""
        project_root = os.path.dirname(
            os.path.dirname(os.path.abspath(__file__))
        )
        return os.path.join(project_root, "agents", self.adw_id, self.STATE_FILENAME)
    
    def get_tracking_path(self, working_dir: str) -> str:
        """Get path to tracking markdown file."""
        return os.path.join(working_dir, "specs", self.TRACKING_FILENAME)
    
    def save(self) -> None:
        """Save greenfield state to file atomically (temp file + os.replace)."""
        state_path = self.get_state_path()
        os.makedirs(os.path.dirname(state_path), exist_ok=True)

        data = {
            "adw_id": self.adw_id,
            "spec_files": self.spec_files,
            "modules": {mid: m.to_dict() for mid, m in self.modules.items()},
            "module_states": {mid: s.to_dict() for mid, s in self.module_states.items()},
            "execution_order": self.execution_order,
            "user_personas": self.user_personas,
            "current_module": self.current_module,
            "modules_completed": self.modules_completed,
            "modules_total": self.modules_total,
            "decomposition_plan_path": self.decomposition_plan_path,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

        # Atomic write: write to temp file then rename
        tmp_path = state_path + ".tmp"
        try:
            with open(tmp_path, "w") as f:
                json.dump(data, f, indent=2)
            os.replace(tmp_path, state_path)
        except Exception:
            # Clean up temp file on failure
            if os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except OSError:
                    pass
            raise

        self.logger.info(f"Saved greenfield state to {state_path}")
    
    @classmethod
    def load(cls, adw_id: str, logger: Optional[logging.Logger] = None) -> Optional["GreenfieldState"]:
        """Load greenfield state from file if it exists."""
        project_root = os.path.dirname(
            os.path.dirname(os.path.abspath(__file__))
        )
        state_path = os.path.join(project_root, "agents", adw_id, cls.STATE_FILENAME)
        
        if not os.path.exists(state_path):
            return None
        
        try:
            with open(state_path, "r") as f:
                data = json.load(f)
            
            state = cls(data["adw_id"], logger=logger)
            state.spec_files = data.get("spec_files", [])
            state.modules = {
                mid: ModuleDefinition.from_dict(m)
                for mid, m in data.get("modules", {}).items()
            }
            state.module_states = {
                mid: ModuleState.from_dict(s)
                for mid, s in data.get("module_states", {}).items()
            }
            state.execution_order = data.get("execution_order", [])
            state.user_personas = data.get("user_personas", [])
            state.current_module = data.get("current_module")
            state.modules_completed = data.get("modules_completed", 0)
            state.modules_total = data.get("modules_total", 0)
            state.decomposition_plan_path = data.get("decomposition_plan_path")
            state.created_at = data.get("created_at")
            state.updated_at = data.get("updated_at")
            
            if logger:
                logger.info(f"Loaded greenfield state from {state_path}")
            
            return state
        except Exception as e:
            if logger:
                logger.error(f"Failed to load greenfield state: {e}")
            return None
    
    def generate_tracking_markdown(self) -> str:
        """Generate the tracking markdown file content."""
        lines = [
            "# Module Implementation Tracking",
            "",
            f"**ADW ID:** `{self.adw_id}`",
            f"**Created:** {self.created_at or 'N/A'}",
            f"**Last Updated:** {self.updated_at or 'N/A'}",
            f"**Progress:** {self.modules_completed}/{self.modules_total} modules completed",
            "",
            "## Specification Files",
            "",
        ]
        
        for spec_file in self.spec_files:
            lines.append(f"- `{spec_file}`")
        
        lines.extend([
            "",
            "## Module Status",
            "",
            "| Module | Priority | Status | Issue | Complexity | Dependencies |",
            "|--------|----------|--------|-------|------------|--------------|",
        ])
        
        for module_id in self.execution_order:
            module = self.modules.get(module_id)
            state = self.module_states.get(module_id)
            
            if not module or not state:
                continue
            
            status_icon = {
                ModuleStatus.PENDING: "⏳",
                ModuleStatus.IN_PROGRESS: "🔄",
                ModuleStatus.COMPLETED: "✅",
                ModuleStatus.FAILED: "❌",
                ModuleStatus.SKIPPED: "⏭️",
            }.get(state.status, "❓")
            
            issue_link = f"#{state.issue_number}" if state.issue_number else "-"
            deps = ", ".join(module.dependencies) if module.dependencies else "-"
            
            lines.append(
                f"| **{module.name}** | {module.priority.value} | {status_icon} {state.status.value} | "
                f"{issue_link} | {module.estimated_complexity} | {deps} |"
            )
        
        lines.extend([
            "",
            "## Module Details",
            "",
        ])
        
        for module_id in self.execution_order:
            module = self.modules.get(module_id)
            state = self.module_states.get(module_id)
            
            if not module:
                continue
            
            lines.extend([
                f"### {module.name} (`{module.id}`)",
                "",
                f"**Description:** {module.description}",
                "",
            ])
            
            if module.user_stories:
                lines.append("**User Stories:**")
                for story in module.user_stories[:5]:  # Limit to 5
                    lines.append(f"- {story}")
                if len(module.user_stories) > 5:
                    lines.append(f"- ... and {len(module.user_stories) - 5} more")
                lines.append("")
            
            if module.acceptance_criteria:
                lines.append("**Acceptance Criteria:**")
                for criteria in module.acceptance_criteria[:5]:
                    lines.append(f"- {criteria}")
                if len(module.acceptance_criteria) > 5:
                    lines.append(f"- ... and {len(module.acceptance_criteria) - 5} more")
                lines.append("")
            
            if state:
                lines.append("**Implementation Status:**")
                lines.append(f"- Status: {state.status.value}")
                if state.issue_number:
                    lines.append(f"- Issue: #{state.issue_number}")
                if state.child_adw_id:
                    lines.append(f"- ADW ID: `{state.child_adw_id}`")
                if state.started_at:
                    lines.append(f"- Started: {state.started_at}")
                if state.completed_at:
                    lines.append(f"- Completed: {state.completed_at}")
                if state.error_message:
                    lines.append(f"- Error: {state.error_message}")
                lines.append("")
            
            lines.append("---")
            lines.append("")
        
        return "\n".join(lines)
    
    def save_tracking_file(self, working_dir: str) -> str:
        """Save the tracking markdown file and return its path."""
        tracking_path = self.get_tracking_path(working_dir)
        os.makedirs(os.path.dirname(tracking_path), exist_ok=True)
        
        content = self.generate_tracking_markdown()
        with open(tracking_path, "w") as f:
            f.write(content)
        
        self.logger.info(f"Saved tracking file to {tracking_path}")
        return tracking_path


def _handle_termination(signum=None, frame=None):
    """Handle termination signals gracefully, saving state before exit."""
    global _cleanup_done
    if _cleanup_done:
        return
    _cleanup_done = True
    # Save greenfield state so progress isn't lost on interruption
    if _active_gf_state is not None:
        try:
            _active_gf_state.save()
        except Exception:
            pass  # Best-effort; don't mask the original signal
    # Kill entire process group so child subprocesses are terminated too
    try:
        os.killpg(os.getpgid(0), signal.SIGTERM)
    except OSError:
        pass
    if signum is not None:
        sys.exit(1)


# Register signal handlers
signal.signal(signal.SIGTERM, _handle_termination)
signal.signal(signal.SIGINT, _handle_termination)


def load_spec_files(spec_pattern: str, working_dir: str, logger: logging.Logger) -> Tuple[List[str], str]:
    """Load specification files matching the pattern.
    
    Returns:
        Tuple of (list of file paths, concatenated content)
    """
    # Handle comma-separated file list
    if "," in spec_pattern:
        patterns = [p.strip() for p in spec_pattern.split(",")]
    else:
        patterns = [spec_pattern]
    
    all_files = []
    for pattern in patterns:
        if os.path.isabs(pattern):
            matches = glob_module.glob(pattern)
        else:
            matches = glob_module.glob(os.path.join(working_dir, pattern))
        all_files.extend(matches)
    
    # Deduplicate while preserving order
    seen = set()
    unique_files = []
    for f in all_files:
        if f not in seen:
            seen.add(f)
            unique_files.append(f)
    
    if not unique_files:
        raise ValueError(f"No spec files found matching pattern: {spec_pattern}")
    
    logger.info(f"Found {len(unique_files)} spec file(s)")
    
    # Load and concatenate content
    combined_content = []
    for filepath in unique_files:
        logger.info(f"Loading spec file: {filepath}")
        with open(filepath, "r") as f:
            content = f.read()
        
        # Add file header for context
        rel_path = os.path.relpath(filepath, working_dir)
        combined_content.append(f"# FILE: {rel_path}\n\n{content}")
    
    return unique_files, "\n\n---\n\n".join(combined_content)


def auto_assimilate_design(
    handoff_path: str,
    parent_adw_id: str,
    working_dir: str,
    logger: logging.Logger,
) -> Tuple[bool, Optional[str]]:
    """Run /assimilate_design as phase 0 and auto-merge the result to main.

    Used when --design was provided but `ai_docs/frontend/context/design_system.md`
    is missing. Spawns adw_assimilate_design_iso.py with --no-pr (no tracking issue,
    no PR cycle), then merges the resulting branch into main and pushes so that
    subsequent module worktrees see the rewritten ai_docs/ files.

    Args:
        handoff_path: Absolute path to the design handoff directory.
        parent_adw_id: Greenfield's ADW ID. Child gets `{parent}-assimilate`.
        working_dir: Project root.
        logger: Logger instance.

    Returns:
        Tuple of (success, error_message).
    """
    child_adw_id = f"{parent_adw_id}-assimilate"
    logger.info(f"Phase 0: auto-assimilating design handoff (child ADW: {child_adw_id})")
    print(f"\n--- Phase 0: Assimilating design handoff ---")
    print(f"Child ADW ID: {child_adw_id}")

    script_dir = os.path.dirname(os.path.abspath(__file__))
    cmd = [
        "uv", "run",
        os.path.join(script_dir, "adw_assimilate_design_iso.py"),
        handoff_path,
        child_adw_id,
        "--no-pr",  # No tracking issue, no PR — greenfield merges to main directly.
    ]
    logger.info(f"Running: {' '.join(cmd)}")

    try:
        # Inherit stdout/stderr so user sees assimilation progress live.
        result = subprocess.run(cmd, cwd=working_dir, timeout=1800)
    except subprocess.TimeoutExpired:
        return False, "Assimilation subprocess timed out after 30 minutes"

    if result.returncode != 0:
        return False, f"Assimilation subprocess exited with code {result.returncode}"

    # Load the child's state to discover the branch name that was committed.
    child_state = ADWState.load(child_adw_id, logger)
    if not child_state:
        return False, f"Could not load child ADW state for {child_adw_id}"

    branch_name = child_state.get("branch_name")
    if not branch_name:
        return False, "Child ADW state has no branch_name; cannot merge"

    logger.info(f"Assimilation produced branch: {branch_name}")

    logger.info("Merging assimilation branch to main")
    print(f"Merging {branch_name} to main...")
    merged, merge_error = manual_merge_to_main(branch_name, logger, adw_id=child_adw_id)
    if not merged:
        return False, f"Failed to merge assimilation branch to main: {merge_error}"

    expected_doc = os.path.join(working_dir, "ai_docs/frontend/context/design_system.md")
    if not os.path.isfile(expected_doc):
        return False, (
            f"Assimilation merged but expected output is missing: {expected_doc}. "
            "The /assimilate_design skill may have written to a different path."
        )

    logger.info("Phase 0 complete: design handoff assimilated and merged to main")
    print(f"✅ Design handoff assimilated and merged to main")
    return True, None


def decompose_specifications(
    spec_content: str,
    adw_id: str,
    logger: logging.Logger,
    working_dir: str,
) -> Tuple[bool, List[ModuleDefinition], List[str], List[Dict[str, Any]]]:
    """Use AI to decompose specifications into functional modules.

    Returns:
        Tuple of (success, list of modules, execution order, user personas)
    """
    logger.info("Decomposing specifications into functional modules")

    decomposition_path = os.path.join(working_dir, "specs", "greenfields", adw_id, "decomposition.json")

    # Write spec content to file to avoid exceeding OS ARG_MAX limits
    spec_content_dir = os.path.join(working_dir, "specs", "greenfields", adw_id)
    os.makedirs(spec_content_dir, exist_ok=True)
    spec_content_file = os.path.join(spec_content_dir, "spec_content.md")
    with open(spec_content_file, "w") as f:
        f.write(spec_content)
    logger.info(f"Wrote spec content to {spec_content_file}")

    request = AgentTemplateRequest(
        agent_name=AGENT_DECOMPOSER,
        slash_command="/decompose_specs",
        args=[spec_content_file, decomposition_path],
        adw_id=adw_id,
        working_dir=working_dir,
    )
    
    response = execute_template(request)
    
    if not response.success:
        logger.error(f"Specification decomposition failed: {response.output}")
        return False, [], [], []

    # Read decomposition from the output file the agent wrote
    if not os.path.exists(decomposition_path):
        logger.error(f"Agent did not write decomposition file: {decomposition_path}")
        logger.error(f"Response was: {response.output[:500]}")
        return False, [], [], []

    try:
        with open(decomposition_path, "r") as f:
            data = json.load(f)
    except Exception as e:
        logger.error(f"Failed to parse decomposition file {decomposition_path}: {e}")
        return False, [], [], []

    try:
        modules = []
        for m in data.get("modules", []):
            module = ModuleDefinition(
                id=m["id"],
                name=m["name"],
                description=m["description"],
                priority=ModulePriority(m.get("priority", "medium")),
                dependencies=m.get("dependencies", []),
                target_audience=m.get("target_audience", "end_user"),
                user_stories=m.get("user_stories", []),
                acceptance_criteria=m.get("acceptance_criteria", []),
                estimated_complexity=m.get("estimated_complexity", "medium"),
                spec_references=m.get("spec_references", []),
                design_references=m.get("design_references", []),
                design_screens=m.get("design_screens", []),
            )
            modules.append(module)

        execution_order = data.get("execution_order", [m.id for m in modules])
        user_personas = data.get("user_personas", [])

        if user_personas:
            logger.info(f"Identified {len(user_personas)} user personas: {', '.join(p.get('name', p.get('id', '?')) for p in user_personas)}")
        else:
            logger.info("No custom user personas identified (default member role sufficient)")

        logger.info(f"Decomposed into {len(modules)} modules")
        return True, modules, execution_order, user_personas

    except Exception as e:
        logger.error(f"Failed to build modules from decomposition data: {e}")
        return False, [], [], []


def create_module_issue(
    module: ModuleDefinition,
    parent_adw_id: str,
    repo_path: str,
    logger: logging.Logger,
    working_dir: str,
    user_personas: Optional[List[Dict[str, Any]]] = None,
) -> Tuple[bool, Optional[str]]:
    """Create a GitHub issue for a module.

    Returns:
        Tuple of (success, issue_number)
    """
    logger.info(f"Creating issue for module: {module.name}")

    # Build issue body
    audience_labels = {
        "end_user": "End User (main sidebar)",
        "admin": "Admin (admin hub /admin)",
        "platform_admin": "Platform Admin (/platform-admin)",
        "backend_only": "Backend Only (no UI)",
    }
    audience_display = audience_labels.get(module.target_audience, module.target_audience)

    body_parts = [
        f"## Module: {module.name}",
        "",
        f"**Parent ADW:** `{parent_adw_id}`",
        f"**Priority:** {module.priority.value}",
        f"**Estimated Complexity:** {module.estimated_complexity}",
        f"**Target Audience:** {audience_display}",
        "",
        "## Description",
        "",
        module.description,
        "",
    ]

    # Include user personas context if available
    if user_personas:
        body_parts.extend([
            "## User Personas",
            "",
            "The following user personas were identified for this project. "
            "Use these when creating roles, permissions, user types, onboarding steps, "
            "and when deciding navigation placement.",
            "",
        ])
        for persona in user_personas:
            pid = persona.get("id", "unknown")
            pname = persona.get("name", pid)
            pdesc = persona.get("description", "")
            prole = persona.get("suggested_role", "member")
            pzone = persona.get("navigation_zone", "end_user")
            ponboard = persona.get("requires_onboarding", False)
            preview = persona.get("requires_manual_review", False)
            pfields = persona.get("onboarding_fields", [])
            pperms = persona.get("permissions", [])
            pnotes = persona.get("notes", "")

            body_parts.append(f"### {pname} (`{pid}`)")
            body_parts.append(f"- **Description:** {pdesc}")
            body_parts.append(f"- **Suggested Role:** `{prole}`")
            body_parts.append(f"- **Navigation Zone:** {pzone}")
            body_parts.append(f"- **Requires Onboarding:** {'Yes' if ponboard else 'No'}")
            if ponboard:
                body_parts.append(f"- **Requires Manual Review:** {'Yes' if preview else 'No'}")
                if pfields:
                    body_parts.append(f"- **Onboarding Fields:** {', '.join(pfields)}")
            if pperms:
                body_parts.append(f"- **Permissions:** `{'`, `'.join(pperms)}`")
            if pnotes:
                body_parts.append(f"- **Notes:** {pnotes}")
            body_parts.append("")
    
    if module.dependencies:
        body_parts.extend([
            "## Dependencies",
            "",
            *[f"- {dep}" for dep in module.dependencies],
            "",
        ])
    
    if module.user_stories:
        body_parts.extend([
            "## User Stories",
            "",
            *[f"- {story}" for story in module.user_stories],
            "",
        ])
    
    if module.acceptance_criteria:
        body_parts.extend([
            "## Acceptance Criteria",
            "",
            *[f"- [ ] {criteria}" for criteria in module.acceptance_criteria],
            "",
        ])
    
    if module.spec_references:
        body_parts.extend([
            "## Specification References",
            "",
            *[f"- {ref}" for ref in module.spec_references],
            "",
        ])

    # Design handoff integration: surface design references and inline screen specs.
    # No-op when the module has no design refs (i.e. backend-only modules, or when
    # the greenfield run was invoked without a design handoff).
    if module.design_references:
        body_parts.extend([
            "## Design References",
            "",
            "This module must match the visual design defined in the handoff. "
            "Before implementing any component, read `ai_docs/frontend/baseline_context.md` "
            "(Brand Design System section) and `ai_docs/frontend/context/design_system.md`. "
            "Then read each linked prototype file below.",
            "",
        ])
        for ref in module.design_references:
            screen_name = ref.get("screen_name", ref.get("screen_id", "screen"))
            surface = ref.get("surface", "")
            theme = ref.get("theme", "")
            readme_section = ref.get("readme_section", "")
            prototype_file = ref.get("prototype_file", "")
            prototype_component = ref.get("prototype_component", "")

            body_parts.append(f"### {screen_name}")
            if surface or theme:
                meta = " · ".join(filter(None, [surface, f"theme: {theme}" if theme else ""]))
                body_parts.append(f"- {meta}")
            if readme_section:
                body_parts.append(f"- **Spec section:** {readme_section}")
            if prototype_file:
                comp = f" — component `{prototype_component}`" if prototype_component else ""
                body_parts.append(f"- **Prototype:** `{prototype_file}`{comp}")
            body_parts.append("")

    if module.design_screens:
        body_parts.extend([
            "## Design Screen Specs (verbatim from handoff)",
            "",
            "The following are the exact screen specifications from the design handoff. "
            "Reproduce these layouts pixel-faithfully using the design tokens and shape-language "
            "utilities from `ai_docs/frontend/context/design_system.md`.",
            "",
        ])
        for screen_spec in module.design_screens:
            body_parts.append(screen_spec)
            body_parts.append("")
            body_parts.append("---")
            body_parts.append("")

    body = "\n".join(body_parts)

    # Truncate body if it exceeds GitHub's limit (~65535 chars, use 60000 for safety)
    MAX_BODY_LEN = 60000
    if len(body) > MAX_BODY_LEN:
        logger.warning(f"Issue body for {module.name} is {len(body)} chars, truncating to {MAX_BODY_LEN}")
        body = body[:MAX_BODY_LEN] + "\n\n... (truncated)"

    title = f"[Greenfield] {module.name}"

    # Create issue via gh CLI
    cmd = [
        "gh", "issue", "create",
        "-R", repo_path,
        "--title", title,
        "--body", body,
    ]

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        cwd=working_dir,
        timeout=60,
    )

    if result.returncode != 0:
        logger.error(f"Failed to create issue: {result.stderr}")
        return False, None
    
    # Extract issue number from URL
    issue_url = result.stdout.strip()
    issue_number_match = re.search(r"/issues/(\d+)", issue_url)
    
    if not issue_number_match:
        logger.error(f"Could not extract issue number from: {issue_url}")
        return False, None
    
    issue_number = issue_number_match.group(1)
    logger.info(f"Created issue #{issue_number} for module {module.name}")
    
    return True, issue_number


def _is_child_state_resumable(child_adw_id: str, working_dir: str) -> bool:
    """Return True when the child SDLC's saved state is intact enough to
    resume from where it left off rather than replaying the entire pipeline.

    The orchestrator's resume loop and ``run_sdlc_for_module`` both consult
    this. When True, we keep ``issue_number`` and ``child_adw_id`` on the
    parent ModuleState (so no new GitHub issue is created) and invoke
    ``adw_multi_phase_sdlc_iso.py`` directly with ``--resume`` (so the child
    skips classification, planning, and completed phases).

    The check covers the verify-gate-failure case in particular: that path
    deliberately leaves the worktree + state files at canonical paths
    (see the comment near ``mark_module_failed`` for the verify gate). Single-
    phase SDLC runs return False here because they have no
    ``multi_phase_state.json`` — they'll continue to use the router as before.
    """
    state_file = os.path.join(working_dir, "agents", child_adw_id, "adw_state.json")
    if not os.path.isfile(state_file):
        return False

    try:
        with open(state_file) as f:
            state_data = json.load(f)
    except Exception:
        return False

    required_fields = ("issue_number", "branch_name", "worktree_path", "plan_file")
    if not all(state_data.get(k) for k in required_fields):
        return False

    if not os.path.isdir(state_data["worktree_path"]):
        return False

    mp_state_file = os.path.join(
        working_dir, "agents", child_adw_id, "multi_phase_state.json"
    )
    if not os.path.isfile(mp_state_file):
        return False

    try:
        with open(mp_state_file) as f:
            mp_state_data = json.load(f)
    except Exception:
        return False

    return bool(mp_state_data.get("multi_phase_plan"))


def _restore_preserved_state_for_resume(
    child_adw_id: str,
    logger: logging.Logger,
) -> bool:
    """Restore `.last-failure-<ts>` state files to their canonical names if
    the child worktree still exists.

    Why "if worktree exists": when default cleanup ran, both the worktree
    AND the renamed state files persist but the WORKTREE is gone — the child
    branch was destroyed too, so any "phase completed at commit X" entries
    in the preserved state point at unreachable commits. Restoring the state
    in that scenario would mislead the SDLC into skipping phases whose code
    no longer exists.

    With ``--preserve-on-failure``, cleanup is skipped entirely so no rename
    happens; this function is a no-op (nothing to restore).

    Returns True if any state file was restored.
    """
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    agent_dir = os.path.join(project_root, "agents", child_adw_id)
    if not os.path.isdir(agent_dir):
        return False

    # Check worktree existence FIRST — if the worktree is gone, any preserved
    # state is unsafe to restore.
    worktree_path: Optional[str] = None
    try:
        child_state = ADWState.load(child_adw_id, logger)
        if child_state:
            worktree_path = child_state.get("worktree_path")
    except Exception:
        # ADWState may also have been renamed; check for a .last-failure copy too.
        pass

    # If we couldn't get worktree_path from a live state file, try the
    # most recent .last-failure copy of adw_state.json.
    if not worktree_path:
        try:
            adw_state_backups = sorted(
                f for f in os.listdir(agent_dir)
                if f.startswith("adw_state.json.last-failure-")
            )
            if adw_state_backups:
                with open(os.path.join(agent_dir, adw_state_backups[-1]), "r") as f:
                    backup = json.load(f)
                worktree_path = backup.get("worktree_path") if isinstance(backup, dict) else None
        except Exception as e:
            logger.debug(f"Could not read adw_state backup for {child_adw_id}: {e}")

    if not worktree_path or not os.path.isdir(worktree_path):
        logger.debug(
            f"Skipping state restore for {child_adw_id}: worktree not present "
            f"(worktree_path={worktree_path})"
        )
        return False

    # Worktree exists. Restore the most recent .last-failure-* copy of each
    # canonical state file. Sort by filename so the newest timestamp wins.
    restored_any = False
    for canonical in ("adw_state.json", "multi_phase_state.json"):
        canonical_path = os.path.join(agent_dir, canonical)
        if os.path.exists(canonical_path):
            # Live state already in place; don't clobber it.
            continue
        prefix = f"{canonical}.last-failure-"
        try:
            backups = sorted(
                f for f in os.listdir(agent_dir) if f.startswith(prefix)
            )
        except OSError:
            continue
        if not backups:
            continue
        latest = backups[-1]
        try:
            os.rename(os.path.join(agent_dir, latest), canonical_path)
            logger.info(f"Restored {canonical} from {latest} for {child_adw_id}")
            restored_any = True
        except OSError as e:
            logger.warning(f"Failed to restore {latest}: {e}")

    return restored_any


def _cleanup_failed_module(
    child_adw_id: str,
    working_dir: str,
    logger: logging.Logger,
    *,
    preserve_state_for_diagnosis: bool = True,
) -> None:
    """Clean up worktree, branch, DB, and Redis for a failed module.

    Logs (agents/{child_adw_id}/) are preserved for debugging.
    Only the worktree (source code checkout), isolated database,
    Redis data, and the git branch are removed so --resume starts fresh.

    ``preserve_state_for_diagnosis``: when True (default), the stale state
    files are renamed with a `.last-failure-<ts>` suffix rather than deleted.
    This gives operators visibility into which phase failed (the failed
    multi_phase_state.json contains per-phase status + failure_reason) without
    causing the child SDLC to re-use stale state on resume — the renamed file
    is no longer at the path the child loads from.
    """
    # Load child state to get branch name
    branch_name = None
    try:
        child_state = ADWState.load(child_adw_id, logger)
        if child_state:
            branch_name = child_state.get("branch_name")
    except Exception:
        pass

    # Remove worktree (also drops DB, flushes Redis, releases ports)
    try:
        remove_worktree(child_adw_id, logger)
        print(f"🧹 Cleaned up worktree for {child_adw_id}")
    except Exception as e:
        logger.warning(f"Failed to cleanup worktree for {child_adw_id}: {e}")

    # Delete the local branch so --resume can recreate it
    if branch_name:
        try:
            subprocess.run(
                ["git", "branch", "-D", branch_name],
                capture_output=True, text=True, cwd=working_dir, timeout=30,
            )
            logger.info(f"Deleted local branch {branch_name}")
        except Exception as e:
            logger.debug(f"Branch delete for {branch_name}: {e}")

    # Either delete the stale state files or rename them to a suffixed
    # filename so future operators can diagnose what failed.
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    agent_dir = os.path.join(project_root, "agents", child_adw_id)
    stale_files = ["adw_state.json", "adw_state.json.lock", "multi_phase_state.json"]
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    for fname in stale_files:
        fpath = os.path.join(agent_dir, fname)
        if not os.path.exists(fpath):
            continue
        if preserve_state_for_diagnosis and not fname.endswith(".lock"):
            new_path = f"{fpath}.last-failure-{ts}"
            try:
                os.rename(fpath, new_path)
                logger.info(f"Preserved stale state for diagnosis: {os.path.basename(new_path)}")
            except Exception as e:
                logger.warning(f"Failed to preserve {fpath} (will delete): {e}")
                try:
                    os.remove(fpath)
                except Exception:
                    pass
        else:
            try:
                os.remove(fpath)
                logger.info(f"Removed stale state file: {fname}")
            except Exception as e:
                logger.warning(f"Failed to remove {fpath}: {e}")


def run_sdlc_for_module(
    module: ModuleDefinition,
    issue_number: str,
    child_adw_id: str,
    working_dir: str,
    logger: logging.Logger,
    skip_smoke: bool = False,
) -> str:
    """Run the SDLC router workflow for a module.

    Args:
        child_adw_id: Pre-computed child ADW ID (from caller).

    Returns:
        "success" if SDLC succeeded,
        "failed" for regular failures,
        "usage_limit" if a usage limit or server error caused the failure
            (signals the orchestrator to stop the entire run).
    """
    script_dir = os.path.dirname(os.path.abspath(__file__))

    # If the child SDLC's prior run left behind a usable multi-phase state
    # (verify-gate-failure or post-phase failure), skip the router and invoke
    # the multi-phase SDLC directly with --resume. The router would otherwise
    # re-classify the (now possibly new) issue and re-plan from scratch,
    # generating fresh phase names that don't match the saved phase records.
    resumable = _is_child_state_resumable(child_adw_id, working_dir)

    if resumable:
        logger.info(
            f"Resumable child state detected for module {module.id} "
            f"(ADW: {child_adw_id}) — skipping router, invoking multi-phase "
            f"SDLC directly with --resume"
        )
        cmd = [
            "uv", "run",
            os.path.join(script_dir, "adw_multi_phase_sdlc_iso.py"),
            issue_number,
            child_adw_id,
            "--resume",
        ]
    else:
        logger.info(f"Running SDLC router for module {module.id} (ADW: {child_adw_id})")
        cmd = [
            "uv", "run",
            os.path.join(script_dir, "adw_sdlc_router_iso.py"),
            issue_number,
            child_adw_id,
        ]

    if skip_smoke:
        cmd.append("--skip-smoke")

    logger.info(f"Running: {' '.join(cmd)}")

    # Timeout accounts for normal execution (~2h) plus potential agent-level
    # sleep-retry for usage limits (up to 3h).
    sdlc_timeout = 7200 + _MAX_WAIT_RETRIES * _WAIT_INTERVAL_SECONDS

    try:
        result = subprocess.run(
            cmd, cwd=working_dir, timeout=sdlc_timeout,
            capture_output=True, text=True,
        )
    except subprocess.TimeoutExpired as e:
        output_snippet = ""
        if e.stdout:
            output_snippet = f"\nLast stdout: {e.stdout[-500:]}"
        if e.stderr:
            output_snippet += f"\nLast stderr: {e.stderr[-500:]}"
        logger.error(f"Module {module.id} timed out after {sdlc_timeout // 3600}h{output_snippet}")
        return "failed"

    if result.returncode == 0:
        logger.info(f"Module {module.id} completed successfully")
        return "success"

    # Module failed — determine if it was a usage limit / server error.
    # Check subprocess stdout/stderr first.
    stdout_tail = result.stdout[-2000:] if result.stdout else ""
    stderr_tail = result.stderr[-2000:] if result.stderr else ""
    wait_error = _detect_wait_error(stdout_tail, stderr_tail)

    if not wait_error:
        # Fallback: check the child's multi_phase_state.json for usage limit
        # in phase failure_reason (the error text lives in JSONL, not stderr).
        wait_error = _detect_wait_error_in_child_state(child_adw_id, logger)

    stderr_snippet = stderr_tail[-1000:] if stderr_tail else "(no stderr)"
    stdout_snippet = stdout_tail[-1000:] if stdout_tail else "(no stdout)"
    logger.error(f"Module {module.id} failed with return code {result.returncode}: {stderr_snippet}")
    logger.error(f"Module {module.id} stdout tail: {stdout_snippet}")

    if wait_error:
        return "usage_limit"
    return "failed"


def merge_module_to_main(
    issue_number: str,
    child_adw_id: str,
    working_dir: str,
    logger: logging.Logger,
) -> bool:
    """Merge a module's branch to main via the ship workflow.

    Calls adw_ship_iso.py which handles fetch, checkout main, merge, and push.

    Returns:
        True if merge succeeded, False otherwise.
    """
    script_dir = os.path.dirname(os.path.abspath(__file__))

    cmd = [
        "uv",
        "run",
        os.path.join(script_dir, "adw_ship_iso.py"),
        issue_number,
        child_adw_id,
    ]

    logger.info(f"Merging module to main: {' '.join(cmd)}")

    try:
        result = subprocess.run(
            cmd, cwd=working_dir, timeout=600,
            capture_output=True, text=True,
        )  # 10 minute timeout for merge
    except subprocess.TimeoutExpired:
        logger.error(f"Merge timed out for module {child_adw_id} after 10 minutes")
        return False

    if result.returncode == 0:
        logger.info(f"Successfully merged module {child_adw_id} to main")
        return True
    else:
        stderr_snippet = result.stderr[-1000:] if result.stderr else "(no stderr)"
        stdout_snippet = result.stdout[-500:] if result.stdout else "(no stdout)"
        logger.error(
            f"Failed to merge module {child_adw_id} to main (exit code {result.returncode})\n"
            f"  stderr: {stderr_snippet}\n  stdout: {stdout_snippet}"
        )
        return False


def extract_module_review_issues(
    child_adw_id: str,
    worktree_path: str,
    logger: logging.Logger,
) -> Optional[Dict[str, Any]]:
    """Extract review issues JSON from a child module's worktree.

    Globs for *_review_issues.json in the worktree's app_docs/ directory.

    Args:
        child_adw_id: The child module's ADW ID
        worktree_path: Path to the child worktree (still on disk after merge)
        logger: Logger instance

    Returns:
        Parsed JSON dict or None if not found
    """
    pattern = os.path.join(worktree_path, "app_docs", "*_review_issues.json")
    matches = glob_module.glob(pattern)

    if not matches:
        logger.debug(f"No review issues JSON found in {worktree_path}/app_docs/")
        return None

    # Use the first match (there should be exactly one per module)
    json_path = matches[0]
    try:
        with open(json_path, "r") as f:
            data = json.load(f)
        logger.info(f"Extracted review issues from {os.path.basename(json_path)} for {child_adw_id}")
        return data
    except Exception as e:
        logger.warning(f"Failed to read review issues JSON {json_path}: {e}")
        return None


def recover_review_issues_from_main(
    gf_state: "GreenfieldState",
    working_dir: str,
    logger: logging.Logger,
) -> Dict[str, Dict[str, Any]]:
    """Recover review issues for previously completed modules from main branch.

    For --resume runs where prior modules' worktrees have been cleaned up.
    Uses 'git show main:app_docs/...' to read JSON without checking out.

    Args:
        gf_state: Greenfield state with module info
        working_dir: Repository working directory
        logger: Logger instance

    Returns:
        Dict mapping module_id to review issues data
    """
    recovered: Dict[str, Dict[str, Any]] = {}

    for module_id, mod_state in gf_state.module_states.items():
        if mod_state.status != ModuleStatus.COMPLETED or not mod_state.merged_to_main:
            continue

        # List review issues JSON files on main via git ls-tree
        child_adw_id = mod_state.child_adw_id
        if not child_adw_id:
            continue

        try:
            # Find matching files on main
            result = subprocess.run(
                ["git", "ls-tree", "--name-only", "main", "app_docs/"],
                capture_output=True, text=True, cwd=working_dir, timeout=10,
            )
            if result.returncode != 0:
                continue

            # Look for this module's review issues JSON
            for filename in result.stdout.strip().split("\n"):
                if not filename.endswith("_review_issues.json"):
                    continue
                if child_adw_id not in filename:
                    continue

                # Read file content from main
                show_result = subprocess.run(
                    ["git", "show", f"main:{filename}"],
                    capture_output=True, text=True, cwd=working_dir, timeout=10,
                )
                if show_result.returncode == 0:
                    data = json.loads(show_result.stdout)
                    recovered[module_id] = data
                    logger.info(f"Recovered review issues for module {module_id} from main")
                break
        except Exception as e:
            logger.debug(f"Could not recover review issues for module {module_id}: {e}")

    logger.info(f"Recovered review issues for {len(recovered)} previously completed modules")
    return recovered


def build_consolidated_review_tracker(
    adw_id: str,
    gf_state: "GreenfieldState",
    all_module_issues: Dict[str, Dict[str, Any]],
) -> str:
    """Build a consolidated markdown review tracker from all module issues.

    Args:
        adw_id: Greenfield ADW ID
        gf_state: Greenfield state with module definitions
        all_module_issues: Dict mapping module_id to review issues JSON data

    Returns:
        Markdown content for the consolidated tracker
    """
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    # Aggregate counts
    total_issues = 0
    total_blockers = 0
    total_tech_debt = 0
    total_skippable = 0
    modules_with_issues = 0

    for module_id, data in all_module_issues.items():
        counts = data.get("counts", {})
        module_total = counts.get("total", 0)
        total_issues += module_total
        total_blockers += counts.get("blockers", 0)
        total_tech_debt += counts.get("tech_debt", 0)
        total_skippable += counts.get("skippable", 0)
        if module_total > 0:
            modules_with_issues += 1

    lines = [
        f"# Consolidated Review Issues — {adw_id}",
        f"",
        f"Generated: {now}",
        f"Modules reviewed: {len(all_module_issues)}/{gf_state.modules_total}",
        f"",
        f"## Summary",
        f"",
        f"| Metric | Count |",
        f"|--------|-------|",
        f"| Total issues | {total_issues} |",
        f"| Blockers | {total_blockers} |",
        f"| Tech debt | {total_tech_debt} |",
        f"| Skippable | {total_skippable} |",
        f"| Modules with issues | {modules_with_issues} |",
        f"",
    ]

    # Collect issues by severity across all modules
    all_blockers: List[Tuple[str, Dict[str, Any]]] = []
    all_tech_debts: List[Tuple[str, Dict[str, Any]]] = []
    all_skippables: List[Tuple[str, Dict[str, Any]]] = []

    for module_id, data in all_module_issues.items():
        module = gf_state.modules.get(module_id)
        module_name = module.name if module else module_id
        for issue in data.get("issues", []):
            severity = issue.get("severity", "")
            entry = (module_name, issue)
            if severity == "blocker":
                all_blockers.append(entry)
            elif severity == "tech_debt":
                all_tech_debts.append(entry)
            elif severity == "skippable":
                all_skippables.append(entry)

    if all_blockers:
        lines.append("## Blockers")
        lines.append("")
        for module_name, issue in all_blockers:
            lines.append(f"- **[{module_name}]** {issue.get('description', '')}")
            lines.append(f"  - Resolution: {issue.get('resolution', '')}")
            screenshot = issue.get("screenshot_url")
            if screenshot and str(screenshot).startswith("http"):
                lines.append(f"  - ![Screenshot]({screenshot})")
        lines.append("")

    if all_tech_debts:
        lines.append("## Tech Debt")
        lines.append("")
        for module_name, issue in all_tech_debts:
            lines.append(f"- **[{module_name}]** {issue.get('description', '')}")
            lines.append(f"  - Resolution: {issue.get('resolution', '')}")
            screenshot = issue.get("screenshot_url")
            if screenshot and str(screenshot).startswith("http"):
                lines.append(f"  - ![Screenshot]({screenshot})")
        lines.append("")

    if all_skippables:
        lines.append("## Skippable")
        lines.append("")
        for module_name, issue in all_skippables:
            lines.append(f"- **[{module_name}]** {issue.get('description', '')}")
            lines.append(f"  - Resolution: {issue.get('resolution', '')}")
        lines.append("")

    # Per-module review summaries
    lines.append("## Per-Module Review Summaries")
    lines.append("")
    for module_id, data in all_module_issues.items():
        module = gf_state.modules.get(module_id)
        module_name = module.name if module else module_id
        counts = data.get("counts", {})
        summary = data.get("review_summary", "No summary available.")
        lines.append(f"### {module_name}")
        lines.append(f"")
        lines.append(f"Issues: {counts.get('total', 0)} "
                      f"(blockers: {counts.get('blockers', 0)}, "
                      f"tech_debt: {counts.get('tech_debt', 0)}, "
                      f"skippable: {counts.get('skippable', 0)})")
        lines.append(f"")
        lines.append(f"{summary}")
        lines.append(f"")

    return "\n".join(lines)


def commit_review_tracker_to_main(
    adw_id: str,
    tracker_content: str,
    working_dir: str,
    logger: logging.Logger,
) -> bool:
    """Commit the consolidated review tracker to main branch.

    Follows the same safe git pattern as manual_merge_to_main() in adw_ship_iso.py:
    stash → checkout main → pull → write file → commit → push → restore branch → unstash.

    Args:
        adw_id: Greenfield ADW ID
        tracker_content: Markdown content for REVIEW_ISSUES.md
        working_dir: Repository working directory
        logger: Logger instance

    Returns:
        True if successfully committed and pushed
    """
    tracker_dir = os.path.join("specs", "greenfields", adw_id)
    tracker_rel_path = os.path.join(tracker_dir, "REVIEW_ISSUES.md")
    tracker_abs_path = os.path.join(working_dir, tracker_rel_path)

    stashed = False
    original_branch = None

    try:
        # Save current branch
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True, text=True, cwd=working_dir,
        )
        original_branch = result.stdout.strip()

        # Stash uncommitted changes
        stash_result = subprocess.run(
            ["git", "stash", "--include-untracked"],
            capture_output=True, text=True, cwd=working_dir,
        )
        stashed = stash_result.returncode == 0 and "No local changes" not in stash_result.stdout

        # Checkout main
        result = subprocess.run(
            ["git", "checkout", "main"],
            capture_output=True, text=True, cwd=working_dir,
        )
        if result.returncode != 0:
            logger.error(f"Failed to checkout main for tracker commit: {result.stderr}")
            if stashed:
                subprocess.run(["git", "stash", "pop"], capture_output=True, text=True, cwd=working_dir)
            return False

        # Pull latest
        subprocess.run(
            ["git", "pull", "origin", "main"],
            capture_output=True, text=True, cwd=working_dir,
        )

        # Write tracker file
        os.makedirs(os.path.join(working_dir, tracker_dir), exist_ok=True)
        with open(tracker_abs_path, "w") as f:
            f.write(tracker_content)

        # Stage and commit
        subprocess.run(
            ["git", "add", tracker_rel_path],
            capture_output=True, text=True, cwd=working_dir,
        )

        result = subprocess.run(
            ["git", "commit", "-m", f"docs: add consolidated review issues tracker for {adw_id}"],
            capture_output=True, text=True, cwd=working_dir,
        )
        if result.returncode != 0:
            logger.warning(f"Tracker commit failed (may be no changes): {result.stderr}")
            # Restore even if commit fails
        else:
            # Push
            push_result = subprocess.run(
                ["git", "push", "origin", "main"],
                capture_output=True, text=True, cwd=working_dir, timeout=60,
            )
            if push_result.returncode != 0:
                logger.error(f"Failed to push tracker to main: {push_result.stderr}")
            else:
                logger.info(f"Committed and pushed review tracker to main: {tracker_rel_path}")

        # Restore original branch
        if original_branch and original_branch != "main":
            subprocess.run(
                ["git", "checkout", original_branch],
                capture_output=True, text=True, cwd=working_dir,
            )
        if stashed:
            subprocess.run(["git", "stash", "pop"], capture_output=True, text=True, cwd=working_dir)

        return True

    except Exception as e:
        logger.error(f"Error committing review tracker: {e}")
        # Best-effort restore
        try:
            if original_branch and original_branch != "main":
                subprocess.run(
                    ["git", "checkout", original_branch],
                    capture_output=True, text=True, cwd=working_dir,
                )
            if stashed:
                subprocess.run(["git", "stash", "pop"], capture_output=True, text=True, cwd=working_dir)
        except Exception:
            pass
        return False


def generate_domain_docs(
    adw_id: str,
    decomposition_path: str,
    working_dir: str,
    logger: logging.Logger,
) -> bool:
    """Generate per-domain context docs in ai_docs/domain/ via /document_domains (fan-out).

    Runs the command on main (one subagent per decomposed module/domain), then commits
    and pushes the resulting domain docs, index, and conditional_context registration.

    Advisory only — a completed greenfield build must never fail because domain docs
    could not be generated. Returns True on success, False on any failure.
    """
    # Ensure we're on main with latest code (verification already does this, but be safe).
    subprocess.run(
        ["git", "checkout", "main"], capture_output=True, text=True, cwd=working_dir
    )
    subprocess.run(
        ["git", "pull", "origin", "main"], capture_output=True, text=True, cwd=working_dir
    )

    request = AgentTemplateRequest(
        agent_name=AGENT_DOMAIN_DOCUMENTER,
        slash_command="/document_domains",
        args=[decomposition_path],
        adw_id=adw_id,
        working_dir=working_dir,
    )
    response = execute_template(request)
    if not response.success:
        logger.warning(f"Domain doc generation failed (advisory): {response.output}")
        return False

    logger.info(f"Domain doc generation output: {response.output.strip()[:500]}")

    # Commit and push the generated docs + registration changes.
    commit_paths = ["ai_docs/domain", ".claude/commands/conditional_context.md"]
    subprocess.run(
        ["git", "add"] + commit_paths, capture_output=True, text=True, cwd=working_dir
    )
    commit_result = subprocess.run(
        ["git", "commit", "-m", f"docs: generate domain context docs for {adw_id}"],
        capture_output=True, text=True, cwd=working_dir,
    )
    if commit_result.returncode != 0:
        logger.info(
            f"No domain doc changes to commit: {commit_result.stderr or commit_result.stdout}"
        )
        return True

    push_result = subprocess.run(
        ["git", "push", "origin", "main"],
        capture_output=True, text=True, cwd=working_dir, timeout=60,
    )
    if push_result.returncode != 0:
        logger.error(f"Failed to push domain docs to main: {push_result.stderr}")
        return False

    logger.info("Committed and pushed domain docs to main")
    return True


POLISH_MODULE_ID = "design-polish"


def _ensure_polish_module_deps(
    modules: List[ModuleDefinition],
    execution_order: List[str],
    logger: logging.Logger,
) -> bool:
    """Safety net: after `/decompose_specs` runs, verify that if a polish
    module exists, its dependencies cover every UI-bearing module, and that
    it sits at the end of execution_order.

    The skill is supposed to emit the polish module correctly when a design
    handoff is detected, but LLM-driven decomposition can drift. This
    function is a deterministic post-step that:

    1. Finds the polish module by id (``design-polish``).
    2. Identifies every UI-bearing module (``target_audience`` ∈
       ``{end_user, admin, platform_admin}``) other than the polish module
       itself.
    3. Appends any missing UI module ids to the polish module's
       ``dependencies`` list (in place; preserves any extras the decomposer
       added intentionally).
    4. Moves the polish module to the END of ``execution_order`` if it's
       not already there.

    Logs a warning when it has to fix anything, so operators see drift over
    time. Returns True if the polish module was found and validated; False
    if no polish module is present (which is the expected no-handoff case).
    """
    polish = next((m for m in modules if m.id == POLISH_MODULE_ID), None)
    if polish is None:
        # No handoff, no polish module — that's fine. Nothing to enforce.
        return False

    # Every UI module is a candidate dep for polish.
    ui_module_ids = [
        m.id for m in modules
        if m.target_audience in ("end_user", "admin", "platform_admin")
        and m.id != POLISH_MODULE_ID
    ]

    current_deps = set(polish.dependencies)
    missing_deps = [mid for mid in ui_module_ids if mid not in current_deps]
    if missing_deps:
        polish.dependencies.extend(missing_deps)
        logger.warning(
            f"Polish module '{POLISH_MODULE_ID}' was missing dependencies on "
            f"{len(missing_deps)} UI module(s): {', '.join(missing_deps)}. "
            f"Appended automatically to enforce cross-cutting ordering."
        )

    # Polish must execute last. Move it to the end if it isn't already.
    if POLISH_MODULE_ID in execution_order:
        if execution_order[-1] != POLISH_MODULE_ID:
            execution_order.remove(POLISH_MODULE_ID)
            execution_order.append(POLISH_MODULE_ID)
            logger.warning(
                f"Polish module '{POLISH_MODULE_ID}' was not last in "
                "execution_order; moved to the end."
            )
    else:
        execution_order.append(POLISH_MODULE_ID)
        logger.warning(
            f"Polish module '{POLISH_MODULE_ID}' was missing from "
            "execution_order; appended to the end."
        )

    return True


def _load_full_decomposition(
    adw_id: str, working_dir: str, logger: logging.Logger,
) -> Optional[Dict[str, Any]]:
    """Read the parent decomposition.json. None on failure."""
    src_path = os.path.join(working_dir, "specs", "greenfields", adw_id, "decomposition.json")
    if not os.path.exists(src_path):
        logger.error(f"Decomposition not found: {src_path}")
        return None
    try:
        with open(src_path, "r") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Failed to read decomposition: {e}")
        return None


def _build_single_module_decomposition(
    adw_id: str,
    module_id: str,
    parent_working_dir: str,
    logger: logging.Logger,
    output_root: Optional[str] = None,
) -> Optional[str]:
    """Write a decomposition slice containing only the requested module.

    Returns the path to the slice, or None if the source decomposition is
    missing or doesn't contain the module.

    ``parent_working_dir`` is where the source decomposition.json lives (the
    parent repo). ``output_root`` is where the slice is written; defaults to
    ``parent_working_dir`` but callers can target a child worktree so that
    a worktree-scoped agent can read the slice under its working-dir lock.

    The slice preserves the parent decomposition's top-level metadata (project
    summary, etc.) but contains a single module in the modules array, so the
    /verify_greenfield agent only inspects that module's acceptance criteria.
    """
    full = _load_full_decomposition(adw_id, parent_working_dir, logger)
    if full is None:
        return None

    modules = full.get("modules", []) or []
    found = next((m for m in modules if m.get("id") == module_id), None)
    if not found:
        logger.error(f"Module {module_id} not found in decomposition")
        return None

    slice_data = dict(full)
    slice_data["modules"] = [found]
    # Trim execution_order to just this module; downstream verifiers shouldn't
    # complain about siblings that weren't part of this slice.
    slice_data["execution_order"] = [module_id]

    out_root = output_root or parent_working_dir
    slice_path = os.path.join(
        out_root, "specs", "greenfields", adw_id,
        f"decomposition_module_{module_id}.json",
    )
    try:
        os.makedirs(os.path.dirname(slice_path), exist_ok=True)
        with open(slice_path, "w") as f:
            json.dump(slice_data, f, indent=2)
    except Exception as e:
        logger.error(f"Failed to write decomposition slice: {e}")
        return None

    return slice_path


def verify_module_before_merge(
    adw_id: str,
    module: ModuleDefinition,
    child_adw_id: str,
    working_dir: str,
    logger: logging.Logger,
    cost_tracker: Optional[CostTracker] = None,
) -> Tuple[bool, Optional[Dict[str, Any]]]:
    """Run /verify_greenfield on a single module's worktree before merging.

    The verifier must see the module's actual implementation — which lives on
    the child branch inside the child's worktree, not on the parent's
    checkout. This function:

    1. Loads ``child_adw_id``'s ADWState to get its ``worktree_path``.
    2. Writes a single-module decomposition slice INSIDE that worktree (so the
       agent's working-dir lock lets it Read the slice).
    3. Invokes /verify_greenfield with ``working_dir=worktree_path`` so the
       agent's Glob/Grep operations target the module's code.
    4. The agent writes its report inside the worktree; we copy that report
       back to the parent's ``specs/greenfields/<adw_id>/`` for preservation
       (the worktree is destroyed after a successful merge).

    Returns ``(passed, report)`` where ``passed`` is True only if the
    per-module verdict is ``pass``. ``partial`` and ``fail`` are treated as
    blocking — partial code shouldn't land on main without operator review.

    Falls back to running in the parent working_dir if the child worktree
    can't be located (logs a warning so the operator knows the gate is degraded).
    """
    # Resolve the child worktree path so the agent inspects the module's code.
    target_working_dir = working_dir
    worktree_path: Optional[str] = None
    try:
        child_state = ADWState.load(child_adw_id, logger)
        if child_state:
            worktree_path = child_state.get("worktree_path")
    except Exception as e:
        logger.warning(f"Could not load child state for pre-merge verify: {e}")

    if worktree_path and os.path.isdir(worktree_path):
        target_working_dir = worktree_path
        logger.info(f"Pre-merge verifier will run in child worktree: {worktree_path}")
    else:
        logger.warning(
            f"Child worktree not found for {child_adw_id} "
            f"(worktree_path={worktree_path}); falling back to parent working_dir. "
            "Verification accuracy will be degraded."
        )

    # Slice goes INSIDE the agent's working_dir so the working-dir lock allows
    # the agent to Read it. For the fallback path (parent working_dir), the
    # slice lives next to decomposition.json as before.
    slice_path = _build_single_module_decomposition(
        adw_id, module.id, working_dir, logger, output_root=target_working_dir,
    )
    if not slice_path:
        return False, None

    # The report is written by the agent inside its working_dir. We then
    # copy it back to the parent's specs/ tree so it survives worktree teardown.
    agent_report_path = os.path.join(
        target_working_dir, "specs", "greenfields", adw_id,
        f"verification_module_{module.id}.json",
    )

    agent_name = f"{AGENT_VERIFIER}_module_{module.id}"
    request = AgentTemplateRequest(
        agent_name=agent_name,
        slash_command="/verify_greenfield",
        args=[slice_path, agent_report_path],
        adw_id=adw_id,
        working_dir=target_working_dir,
    )

    logger.info(f"Running pre-merge verification for module {module.id}")
    response = execute_template(request)
    if cost_tracker is not None:
        cost_tracker.record_from_template_request(
            adw_id, agent_name, bucket=module.id, logger=logger,
        )

    if not response.success:
        logger.warning(f"Pre-merge verifier agent failed for {module.id}: {response.output[:300]}")
        return False, None

    if not os.path.exists(agent_report_path):
        logger.warning(f"Pre-merge verifier did not write report: {agent_report_path}")
        return False, None

    try:
        with open(agent_report_path, "r") as f:
            report = json.load(f)
    except Exception as e:
        logger.warning(f"Pre-merge verification report parse failed: {e}")
        return False, None

    # Persist a copy in the parent's specs tree (worktree may be deleted soon).
    parent_report_path = os.path.join(
        working_dir, "specs", "greenfields", adw_id,
        f"verification_module_{module.id}.json",
    )
    if parent_report_path != agent_report_path:
        try:
            os.makedirs(os.path.dirname(parent_report_path), exist_ok=True)
            with open(agent_report_path, "r") as src, open(parent_report_path, "w") as dst:
                dst.write(src.read())
        except Exception as e:
            logger.warning(f"Failed to copy module verification report to parent: {e}")

    # The slice has exactly one module; trust the per-module verdict.
    module_reports = report.get("modules", []) or []
    if not module_reports:
        # Fall back to overall verdict if the agent didn't fill the modules array.
        verdict = report.get("overall_verdict", "fail")
    else:
        verdict = module_reports[0].get("verdict", "fail")

    passed = (verdict == "pass")
    logger.info(
        f"Pre-merge verification for {module.id}: verdict={verdict} (passed={passed})"
    )
    return passed, report


# Agent name used for the rescue hop after a partial pre-merge verdict.
AGENT_RESCUE_VERIFIER = "rescue_verification"


def _module_verdict_stats(
    report: Optional[Dict[str, Any]], module_id: str
) -> Tuple[str, int, int]:
    """Return (verdict, criteria_met, criteria_total) for a module in a report.

    Falls back to overall-verdict and zero counts if the per-module slice is
    missing, so callers can still make a sensible threshold decision.
    """
    if not report:
        return "fail", 0, 0
    for mod in report.get("modules", []) or []:
        if mod.get("id") == module_id:
            return (
                mod.get("verdict", "fail"),
                int(mod.get("criteria_met", 0) or 0),
                int(mod.get("criteria_total", 0) or 0),
            )
    return report.get("overall_verdict", "fail"), 0, 0


def attempt_module_rescue(
    adw_id: str,
    module: ModuleDefinition,
    child_adw_id: str,
    working_dir: str,
    logger: logging.Logger,
    initial_report: Optional[Dict[str, Any]],
    min_criteria_pct: int,
    cost_tracker: Optional[CostTracker] = None,
) -> Tuple[bool, Optional[Dict[str, Any]], str]:
    """Try to upgrade a partial pre-merge verdict into a pass by spawning the
    /rescue_verification agent against the same worktree, committing its fixes,
    pushing the branch, then re-running the verifier once.

    Skipped (returns immediately with ``"skipped_low_criteria"``) when the
    initial verdict is not ``partial`` OR the ratio of criteria met is below
    ``min_criteria_pct`` (a planning-bust is escalated to the operator instead
    of patched). Capped at one attempt per module per ADW; the caller is
    responsible for tracking ``rescue_attempts`` on ModuleState so a --resume
    cannot re-enter the rescue path twice.

    Returns ``(passed, final_report, outcome)`` where ``outcome`` is one of:
      - ``upgraded_to_pass``    rescue ran, re-verify now returns ``pass``
      - ``still_partial``       rescue ran, re-verify still ``partial``/``fail``
      - ``errored``             rescue agent failed to run or did not commit
      - ``skipped_low_criteria`` not enough met-criteria to justify a patch
    """
    verdict, criteria_met, criteria_total = _module_verdict_stats(
        initial_report, module.id
    )

    # Threshold gate. A planning-bust (0 met or very low %) should escalate to
    # the operator rather than burn a rescue budget on it.
    if verdict != "partial":
        logger.info(
            f"Rescue not attempted for {module.id}: verdict={verdict} "
            "(only 'partial' is rescuable)"
        )
        return False, initial_report, "skipped_low_criteria"

    if criteria_total <= 0:
        logger.info(
            f"Rescue not attempted for {module.id}: criteria_total=0 in report"
        )
        return False, initial_report, "skipped_low_criteria"

    pct = (criteria_met * 100) // criteria_total
    if pct < min_criteria_pct:
        logger.info(
            f"Rescue not attempted for {module.id}: "
            f"{criteria_met}/{criteria_total} criteria met ({pct}% < {min_criteria_pct}%)"
        )
        return False, initial_report, "skipped_low_criteria"

    # Locate the child worktree — rescue must run in the same worktree the
    # verifier already inspected.
    worktree_path: Optional[str] = None
    try:
        child_state = ADWState.load(child_adw_id, logger)
        if child_state:
            worktree_path = child_state.get("worktree_path")
    except Exception as e:
        logger.warning(f"Could not load child state for rescue: {e}")

    if not worktree_path or not os.path.isdir(worktree_path):
        logger.warning(
            f"Rescue aborted for {module.id}: child worktree not available "
            f"(worktree_path={worktree_path})"
        )
        return False, initial_report, "errored"

    # The verification report should already exist inside the worktree (the
    # verifier writes it there before copying back to the parent). Re-derive
    # the path so the agent can Read it under its working-dir lock.
    worktree_report_path = os.path.join(
        worktree_path, "specs", "greenfields", adw_id,
        f"verification_module_{module.id}.json",
    )
    parent_report_path = os.path.join(
        working_dir, "specs", "greenfields", adw_id,
        f"verification_module_{module.id}.json",
    )

    # If the worktree copy was cleaned up but the parent still has one, mirror
    # it back so the agent's working-dir lock allows Read().
    if not os.path.exists(worktree_report_path) and os.path.exists(parent_report_path):
        try:
            os.makedirs(os.path.dirname(worktree_report_path), exist_ok=True)
            with open(parent_report_path, "r") as src, open(worktree_report_path, "w") as dst:
                dst.write(src.read())
        except Exception as e:
            logger.warning(f"Failed to mirror verification report into worktree: {e}")
            return False, initial_report, "errored"

    if not os.path.exists(worktree_report_path):
        logger.warning(
            f"Rescue aborted for {module.id}: verification report missing at "
            f"{worktree_report_path}"
        )
        return False, initial_report, "errored"

    # Snapshot HEAD so we can detect whether the agent actually committed.
    head_before: Optional[str] = None
    try:
        head_before = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=worktree_path, capture_output=True, text=True, check=True,
        ).stdout.strip()
    except Exception as e:
        logger.warning(f"Could not capture HEAD before rescue: {e}")

    logger.info(
        f"Attempting auto-rescue for {module.id} "
        f"({criteria_met}/{criteria_total} criteria met, verdict=partial)"
    )
    print(
        f"🛟  Auto-rescue: attempting to patch {module.name} "
        f"({criteria_met}/{criteria_total} criteria met)"
    )

    agent_name = f"{AGENT_RESCUE_VERIFIER}_module_{module.id}"
    request = AgentTemplateRequest(
        agent_name=agent_name,
        slash_command="/rescue_verification",
        args=[adw_id, module.id, worktree_report_path],
        adw_id=adw_id,
        working_dir=worktree_path,
    )

    response = execute_template(request)
    if cost_tracker is not None:
        cost_tracker.record_from_template_request(
            adw_id, agent_name, bucket=module.id, logger=logger,
        )

    if not response.success:
        logger.warning(
            f"Rescue agent failed for {module.id}: {response.output[:300]}"
        )
        return False, initial_report, "errored"

    # Verify the agent actually produced commits. Agents have historically
    # forgotten the "commit each fix" instruction — we observed a real rescue
    # that did 90 turns of valid work but never ran `git commit`, then
    # returned a prose summary instead of the required JSON report. To
    # salvage that case, fall back to auto-committing any uncommitted
    # working-tree changes the agent left behind before declaring the
    # rescue a no-op.
    head_after: Optional[str] = None
    try:
        head_after = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=worktree_path, capture_output=True, text=True, check=True,
        ).stdout.strip()
    except Exception as e:
        logger.warning(f"Could not capture HEAD after rescue: {e}")

    if head_before and head_after and head_before == head_after:
        # No commits — but did the agent actually change anything?
        dirty = False
        try:
            porcelain = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=worktree_path, capture_output=True, text=True, check=True,
            ).stdout
            dirty = bool(porcelain.strip())
        except Exception as e:
            logger.warning(f"Could not check working tree state after rescue: {e}")

        if not dirty:
            logger.warning(
                f"Rescue produced no commits and no working-tree changes for "
                f"{module.id} (HEAD unchanged at {head_before[:8]}); skipping re-verify"
            )
            return False, initial_report, "still_partial"

        # Salvage the agent's uncommitted work. Commit it on the agent's
        # behalf with a generic message so the re-verify sees the changes.
        logger.info(
            f"Rescue did not commit but left working-tree changes for "
            f"{module.id}; auto-committing on the agent's behalf"
        )
        try:
            # Stage everything — including untracked files — so any new
            # scripts/locale stubs the agent created are picked up.
            subprocess.run(
                ["git", "add", "-A"],
                cwd=worktree_path, capture_output=True, text=True, check=True,
            )
            commit_msg = (
                f"fix({module.id}): auto-rescue commit for uncommitted agent changes\n"
                "\n"
                "The /rescue_verification agent produced working-tree changes but did\n"
                "not run `git commit`. Salvaging the work so the re-verifier sees it.\n"
                "If any of these changes look wrong, revert this commit and re-run\n"
                "with --no-auto-rescue.\n"
            )
            subprocess.run(
                ["git", "commit", "-m", commit_msg],
                cwd=worktree_path, capture_output=True, text=True, check=True,
            )
            head_after = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=worktree_path, capture_output=True, text=True, check=True,
            ).stdout.strip()
            logger.info(
                f"Auto-committed rescue work for {module.id} at {head_after[:8]}"
            )
        except subprocess.CalledProcessError as e:
            logger.warning(
                f"Auto-commit of rescue work failed for {module.id}: "
                f"stdout={e.stdout!r}, stderr={e.stderr!r}"
            )
            return False, initial_report, "errored"

    # Push so the re-verifier sees committed code on origin and so the
    # operator can inspect the rescue commits if it still fails. Best-effort.
    try:
        subprocess.run(
            ["git", "push", "--set-upstream", "origin", "HEAD"],
            cwd=worktree_path, capture_output=True, text=True, check=False,
        )
    except Exception as e:
        logger.warning(f"Rescue push failed (continuing to re-verify): {e}")

    # Re-run the verifier against the patched branch.
    logger.info(f"Re-verifying module {module.id} after rescue")
    passed, new_report = verify_module_before_merge(
        adw_id, module, child_adw_id, working_dir, logger,
        cost_tracker=cost_tracker,
    )

    if passed:
        new_verdict, new_met, new_total = _module_verdict_stats(new_report, module.id)
        logger.info(
            f"Rescue UPGRADED {module.id} to pass "
            f"({new_met}/{new_total} criteria met)"
        )
        return True, new_report, "upgraded_to_pass"

    new_verdict, new_met, new_total = _module_verdict_stats(new_report, module.id)
    logger.warning(
        f"Rescue did not flip verdict for {module.id}: "
        f"new_verdict={new_verdict}, {new_met}/{new_total} criteria met"
    )
    return False, new_report, "still_partial"


def verify_final_implementation(
    adw_id: str,
    working_dir: str,
    logger: logging.Logger,
) -> Tuple[bool, Optional[Dict[str, Any]]]:
    """Run final verification of the integrated implementation against decomposition requirements.

    Reads the decomposition JSON and calls the /verify_greenfield agent to inspect
    the codebase, producing a structured pass/fail report.

    Returns:
        Tuple of (success, report_dict). success=False means the agent failed to run,
        not that verification found issues.
    """
    decomposition_path = os.path.join(working_dir, "specs", "greenfields", adw_id, "decomposition.json")

    if not os.path.exists(decomposition_path):
        logger.error(f"Decomposition file not found: {decomposition_path}")
        return False, None

    report_path = os.path.join(working_dir, "specs", "greenfields", adw_id, "verification_report.json")

    logger.info("Running final verification against decomposition requirements")

    # Pass file path instead of content to avoid exceeding OS ARG_MAX limits
    request = AgentTemplateRequest(
        agent_name=AGENT_VERIFIER,
        slash_command="/verify_greenfield",
        args=[decomposition_path, report_path],
        adw_id=adw_id,
        working_dir=working_dir,
    )

    response = execute_template(request)

    if not response.success:
        logger.error(f"Verification agent failed: {response.output}")
        return False, None

    if not os.path.exists(report_path):
        logger.error(f"Verification agent did not write report: {report_path}")
        return False, None

    try:
        with open(report_path, "r") as f:
            report = json.load(f)
        logger.info(f"Verification report written to {report_path}")
        return True, report
    except Exception as e:
        logger.error(f"Failed to parse verification report: {e}")
        return False, None


def print_verification_report(report: Dict[str, Any]) -> None:
    """Print a human-readable summary of the verification report."""
    overall = report.get("overall_verdict", "unknown")
    summary = report.get("summary", "")

    verdict_icon = {"pass": "PASS", "partial": "PARTIAL", "fail": "FAIL"}.get(overall, "UNKNOWN")
    print(f"\n--- Final Verification: {verdict_icon} ---")
    if summary:
        print(f"  {summary}")

    modules = report.get("modules", [])
    if modules:
        print(f"\n  Module Results ({len(modules)} modules):")
        for mod in modules:
            mod_verdict = mod.get("verdict", "unknown")
            mod_icon = {"pass": "PASS", "partial": "PARTIAL", "fail": "FAIL"}.get(mod_verdict, "?")
            criteria_met = mod.get("criteria_met", 0)
            criteria_total = mod.get("criteria_total", 0)
            print(f"    [{mod_icon}] {mod.get('name', mod.get('id', '?'))}: {criteria_met}/{criteria_total} criteria met")

    cross_issues = report.get("cross_module_issues", [])
    if cross_issues:
        print(f"\n  Cross-Module Issues ({len(cross_issues)}):")
        for issue in cross_issues:
            modules_involved = ", ".join(issue.get("modules", []))
            print(f"    - [{issue.get('severity', '?')}] {modules_involved}: {issue.get('issue', '')}")

    gaps = report.get("gaps", [])
    if gaps:
        print(f"\n  Gaps ({len(gaps)}):")
        for gap in gaps:
            print(f"    - {gap}")


def write_known_limitations_summary(
    adw_id: str,
    working_dir: str,
    gf_state: "GreenfieldState",
    logger: logging.Logger,
) -> Optional[str]:
    """Aggregate every verifier-flagged unmet criterion across all modules
    into a single operator-facing registry at ``specs/KNOWN_LIMITATIONS.md``.

    Reads each ``specs/greenfields/<adw_id>/verification_module_*.json`` that
    exists, extracts criteria where ``met: false``, and emits a markdown
    summary grouped by module. Cross-references the parent greenfield state
    so each module's auto-rescue outcome is surfaced (``still_partial`` /
    ``skipped_low_criteria`` / ``upgraded_to_pass`` / ``errored``) — that
    lets the operator distinguish "rescue tried and gave up because the
    gap is structural" from "rescue refused because criteria-met was too
    low" from "module was never even rescued."

    Called at end-of-run, including the blocked-by-dependencies exit path
    that previously dropped the operator into a terminal without a summary.
    Idempotent — overwrites the file each call so a partial run that later
    resumes gets an updated registry.

    Returns the absolute path of the written file, or ``None`` when there
    are no verification reports yet (early-failure / fresh start).
    """
    reports_dir = os.path.join(working_dir, "specs", "greenfields", adw_id)
    if not os.path.isdir(reports_dir):
        return None

    pattern = os.path.join(reports_dir, "verification_module_*.json")
    report_paths = sorted(glob_module.glob(pattern))
    if not report_paths:
        return None

    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    header = [
        "# Known Limitations",
        "",
        f"_Auto-generated by the greenfield orchestrator (ADW: `{adw_id}`)._",
        f"_Last updated: {now_iso}._",
        "",
        "Every acceptance criterion the verifier marked as not-met across the",
        "project's modules. For each gap the operator should decide whether to:",
        "",
        "- Address in a follow-up patch (typical for partial fixes)",
        "- Accept as a documented architectural limitation",
        "- Re-open as a separate spec for larger refactors",
        "",
        "Auto-rescue outcomes give context on what the workflow already tried:",
        "",
        "- `upgraded_to_pass` — rescue closed all gaps; module should not appear here",
        "- `still_partial` — rescue ran but couldn't close at least one gap (often a structural deviation from spec)",
        "- `skipped_low_criteria` — criteria-met % was below the threshold; rescue refused (likely planning bust)",
        "- `errored` — rescue agent crashed; manual review recommended",
        "- `(none)` — module passed verifier without rescue, OR rescue never ran",
        "",
        "---",
        "",
    ]

    body: list[str] = []
    modules_with_gaps = 0

    for report_path in report_paths:
        try:
            with open(report_path) as f:
                report = json.load(f)
        except Exception as e:
            logger.debug(f"KNOWN_LIMITATIONS: skip unparseable {report_path}: {e}")
            continue

        mods = report.get("modules", []) or []
        if not mods:
            continue
        mod = mods[0]

        module_id = mod.get("id", "")
        if not module_id:
            continue

        failing = [
            cd for cd in mod.get("criteria_details", []) or []
            if not cd.get("met")
        ]
        if not failing:
            continue

        modules_with_gaps += 1
        module_def = gf_state.modules.get(module_id)
        module_state = gf_state.module_states.get(module_id)

        name = mod.get("name") or (module_def.name if module_def else module_id)
        status = module_state.status.value if module_state else "unknown"
        merged = module_state.merged_to_main if module_state else False
        rescue_attempts = module_state.rescue_attempts if module_state else 0
        rescue_outcome = (module_state.rescue_outcome if module_state else None) or "(none)"
        criteria_met = mod.get("criteria_met", 0)
        criteria_total = mod.get("criteria_total", 0)
        verdict = mod.get("verdict", "unknown")

        body.append(f"## {name} (`{module_id}`)")
        body.append("")
        body.append(
            f"- **Module status:** `{status}`"
            f"{' (merged to main)' if merged else ''}"
        )
        body.append(
            f"- **Verifier verdict:** `{verdict}` "
            f"({criteria_met}/{criteria_total} criteria met)"
        )
        body.append(
            f"- **Auto-rescue:** `{rescue_outcome}` "
            f"(attempts: {rescue_attempts})"
        )
        body.append("")

        for cd in failing:
            crit = (cd.get("criterion") or "").strip()
            evid = (cd.get("evidence") or "").strip()
            body.append(f"### Unmet: {crit[:160]}")
            body.append("")
            if evid:
                body.append("**Evidence:**")
                body.append("")
                # Render evidence as blockquote; truncate to keep file readable.
                evid_short = evid[:1200]
                for line in evid_short.splitlines() or [evid_short]:
                    body.append(f"> {line}")
                if len(evid) > 1200:
                    body.append("> _(evidence truncated)_")
                body.append("")

        body.append("---")
        body.append("")

    if modules_with_gaps == 0:
        body = [
            "_No unmet acceptance criteria across any module._ 🎉",
        ]

    out_path = os.path.join(working_dir, "specs", "KNOWN_LIMITATIONS.md")
    try:
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        with open(out_path, "w") as f:
            f.write("\n".join(header + body).rstrip() + "\n")
        logger.info(
            f"Wrote KNOWN_LIMITATIONS.md ({modules_with_gaps} module(s) with gaps) "
            f"to {out_path}"
        )
        return out_path
    except Exception as e:
        logger.warning(f"Failed to write KNOWN_LIMITATIONS.md: {e}")
        return None


def main():
    """Main entry point."""
    load_dotenv()
    
    # Check for flags
    resume_mode = "--resume" in sys.argv
    skip_smoke = "--skip-smoke" in sys.argv
    skip_verify = "--skip-verify" in sys.argv
    skip_e2e = "--skip-e2e" in sys.argv
    dry_run = "--dry-run" in sys.argv
    # When set, failed modules keep their worktree + state intact so the next
    # --resume can pick up at the failed phase instead of re-running the
    # entire child SDLC. Off by default to preserve disk/port hygiene.
    preserve_on_failure = "--preserve-on-failure" in sys.argv
    # Auto-rescue loop: on a "partial" pre-merge verdict, spawn one
    # /rescue_verification pass to fix met:false criteria, push, and re-verify
    # before falling through to the failure branch. On by default; cap is 1
    # attempt per module per ADW. Disable with --no-auto-rescue.
    auto_rescue = "--no-auto-rescue" not in sys.argv
    # Threshold below which a partial verdict is treated as a planning bust
    # rather than a patchable gap (escalates to operator instead of patch
    # agent). Default 40 means: at least 40% of criteria already met.
    rescue_min_criteria_pct = 25
    if "--rescue-min-criteria-pct" in sys.argv:
        idx = sys.argv.index("--rescue-min-criteria-pct")
        if idx + 1 >= len(sys.argv):
            print("Error: --rescue-min-criteria-pct requires an integer value (0-100)")
            sys.exit(1)
        try:
            rescue_min_criteria_pct = int(sys.argv[idx + 1])
            if not (0 <= rescue_min_criteria_pct <= 100):
                raise ValueError
        except ValueError:
            print("Error: --rescue-min-criteria-pct must be an integer between 0 and 100")
            sys.exit(1)
        del sys.argv[idx:idx + 2]

    # Extract --design <path> (value flag, must be parsed before removing flags).
    design_handoff_path: Optional[str] = None
    if "--design" in sys.argv:
        design_idx = sys.argv.index("--design")
        if design_idx + 1 >= len(sys.argv):
            print("Error: --design requires a path argument (e.g. --design specs/design_handoff_<project>)")
            sys.exit(1)
        design_handoff_path = sys.argv[design_idx + 1]
        # Remove both the flag and its value.
        del sys.argv[design_idx:design_idx + 2]

    # Remove boolean flags from argv
    flags_to_remove = [
        "--resume", "--skip-smoke", "--skip-verify", "--skip-e2e",
        "--dry-run", "--preserve-on-failure", "--no-auto-rescue",
    ]
    for flag in flags_to_remove:
        while flag in sys.argv:
            sys.argv.remove(flag)

    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    spec_pattern = sys.argv[1]
    adw_id = sys.argv[2] if len(sys.argv) > 2 else None
    
    # Generate ADW ID if not provided
    if not adw_id:
        adw_id = make_adw_id()
    
    print(f"Using ADW ID: {adw_id}")

    # Set up logger
    logger = setup_logger(adw_id, "adw_greenfield_iso")
    logger.info(f"Starting Greenfield Orchestrator - ADW ID: {adw_id}")

    # Cost telemetry — shared across decomposition, per-module verification,
    # final verification, and E2E. Child SDLC subprocesses write into their
    # own child_adw_id agents/ trees; only direct-from-orchestrator calls
    # land here.
    greenfield_cost_tracker = CostTracker()

    logger.info(f"Spec pattern: {spec_pattern}")
    logger.info(f"Resume mode: {resume_mode}, Skip smoke: {skip_smoke}, Skip verify: {skip_verify}, Skip E2E: {skip_e2e}, Dry run: {dry_run}")
    logger.info(f"Auto-rescue: {auto_rescue} (min criteria pct: {rescue_min_criteria_pct})")
    
    # Validate environment
    check_env_vars(logger)

    # Validate gh CLI is authenticated (needed for creating module issues)
    if check_gh_auth():
        logger.error("GitHub CLI (gh) is not authenticated. Run 'gh auth login' first.")
        print("\nError: GitHub CLI (gh) is not authenticated.")
        print("Run 'gh auth login' before running greenfield workflow.")
        sys.exit(1)

    # Get working directory (main repo for now)
    project_root = os.path.dirname(
        os.path.dirname(os.path.abspath(__file__))
    )

    # Get repo information
    try:
        github_repo_url = get_repo_url(cwd=project_root)
        repo_path = extract_repo_path(github_repo_url)
    except ValueError as e:
        logger.error(f"Error getting repository URL: {e}")
        sys.exit(1)
    
    # Use main repo, not worktree - the child ADWs will create their own worktrees
    working_dir = project_root

    # Validate design handoff if --design was provided. The handoff must already have
    # been assimilated via adw_assimilate_design_iso.py; this orchestrator does not
    # rewrite agent context itself, it just opts each module into design-aware decomposition.
    if design_handoff_path:
        if not os.path.isabs(design_handoff_path):
            design_handoff_path = os.path.join(working_dir, design_handoff_path)

        if not os.path.isdir(design_handoff_path):
            logger.error(f"--design path is not a directory: {design_handoff_path}")
            print(f"\nError: --design path is not a directory: {design_handoff_path}")
            sys.exit(1)

        handoff_readme = os.path.join(design_handoff_path, "README.md")
        if not os.path.isfile(handoff_readme):
            logger.error(f"Design handoff is missing README.md at {handoff_readme}")
            print(f"\nError: design handoff at {design_handoff_path} has no README.md")
            sys.exit(1)

        design_system_doc = os.path.join(working_dir, "ai_docs/frontend/context/design_system.md")

        # Phase 0: if the handoff hasn't been assimilated yet, run assimilation
        # automatically and merge its branch to main before continuing. This keeps
        # the user's flow to a single command. Re-runs that already have an
        # assimilated handoff skip this phase entirely.
        if not os.path.isfile(design_system_doc):
            assimilated, assim_error = auto_assimilate_design(
                design_handoff_path, adw_id, working_dir, logger
            )
            if not assimilated:
                logger.error(f"Phase 0 (auto-assimilation) failed: {assim_error}")
                print(f"\nError: design assimilation failed: {assim_error}")
                print(
                    "To debug, run assimilation manually:\n"
                    f"  uv run adws/adw_assimilate_design_iso.py "
                    f"{os.path.relpath(design_handoff_path, working_dir)}"
                )
                sys.exit(1)
        else:
            logger.info(f"Design handoff already assimilated ({design_system_doc} exists) — skipping phase 0")
            print(f"\nDesign handoff already assimilated — skipping phase 0")

        # Inject the handoff README into the spec pattern so /decompose_specs sees it
        # and can extract per-module design_references / design_screens.
        handoff_rel = os.path.relpath(handoff_readme, working_dir)
        if handoff_rel not in spec_pattern:
            spec_pattern = f"{spec_pattern},{handoff_rel}"
        logger.info(f"Design handoff active: {design_handoff_path}")
        logger.info(f"Effective spec pattern: {spec_pattern}")
        print(f"Design handoff active: {os.path.relpath(design_handoff_path, working_dir)}")
    else:
        logger.info("No design handoff provided — running greenfield without design-aware phases")

    # Load or create greenfield state
    gf_state = GreenfieldState.load(adw_id, logger)
    
    if resume_mode and not gf_state:
        logger.warning(f"--resume specified but no state found for ADW ID: {adw_id}")
        print(f"\nWarning: --resume specified but no state found for ADW ID: {adw_id}")
        print("Starting fresh instead. To resume, provide the original ADW ID as the second argument.")

    if resume_mode and gf_state:
        # Reset failed, skipped, and in_progress modules back to pending so they can be retried
        reset_failed = 0
        reset_skipped = 0
        reset_in_progress = 0
        restored_modules = 0
        for mid, state in gf_state.module_states.items():
            if state.status not in (ModuleStatus.FAILED, ModuleStatus.SKIPPED, ModuleStatus.IN_PROGRESS):
                continue

            # If --preserve-on-failure was used on the prior run, the child's
            # state files were left intact and we can pick up mid-phase. If
            # rename-on-cleanup happened instead, the renamed copies are
            # restored only when the worktree still exists. Otherwise this is
            # a no-op and the child SDLC will start fresh.
            child_adw_id_for_module = f"{adw_id}-{mid}"
            this_module_restored = _restore_preserved_state_for_resume(
                child_adw_id_for_module, logger,
            )
            if this_module_restored:
                restored_modules += 1

            # The pre-merge verify-gate failure path deliberately skips
            # _cleanup_failed_module, leaving the worktree + state at
            # canonical paths. Detect that case and do a LIGHT reset that
            # preserves the existing GitHub issue + child_adw_id so the
            # multi-phase SDLC can resume from saved phase state instead of
            # creating a new issue and re-planning all 6-8 phases.
            child_resumable = _is_child_state_resumable(
                child_adw_id_for_module, working_dir,
            )

            if state.status == ModuleStatus.FAILED:
                reset_failed += 1
            elif state.status == ModuleStatus.SKIPPED:
                reset_skipped += 1
            else:  # IN_PROGRESS
                reset_in_progress += 1

            state.status = ModuleStatus.PENDING
            state.error_message = None
            state.retry_count = 0

            if child_resumable:
                # KEEP issue_number, child_adw_id, started_at, commit_sha so
                # run_sdlc_for_module can spot the resumable state and invoke
                # adw_multi_phase_sdlc_iso.py directly with --resume.
                logger.info(
                    f"Module {mid} has resumable child state — preserving "
                    f"issue #{state.issue_number} and child_adw_id "
                    f"{state.child_adw_id} for mid-phase resume"
                )
            else:
                state.issue_number = None
                state.started_at = None
                state.completed_at = None
                state.commit_sha = None
                # Keep child_adw_id ONLY when we restored state — the child SDLC's
                # saved state references that ID. Otherwise clear it so a fresh
                # ID is generated (which is still deterministic for the same
                # module, but this guards against stale references).
                if this_module_restored:
                    state.child_adw_id = child_adw_id_for_module
                else:
                    state.child_adw_id = None

        reset_count = reset_failed + reset_skipped + reset_in_progress
        if reset_count:
            gf_state.save()
            logger.info(f"Reset {reset_count} module(s) to pending for retry "
                       f"({reset_failed} failed, {reset_skipped} skipped, {reset_in_progress} in_progress)")
        if restored_modules:
            logger.info(
                f"Restored preserved state for {restored_modules} module(s) — "
                f"child SDLCs will resume mid-phase rather than replaying"
            )
            print(f"📦 Restored preserved state for {restored_modules} module(s) — granular resume enabled")

        logger.info(f"Resuming from previous state: {gf_state.modules_completed}/{gf_state.modules_total} modules completed")
        print(f"\n=== RESUMING GREENFIELD IMPLEMENTATION ===")
        print(f"Progress: {gf_state.modules_completed}/{gf_state.modules_total} modules")
        if reset_failed:
            print(f"Retrying: {reset_failed} previously failed module(s)")
        if reset_skipped:
            print(f"Retrying: {reset_skipped} previously skipped module(s)")
        if reset_in_progress:
            print(f"Retrying: {reset_in_progress} previously interrupted module(s)")
    else:
        # Fresh start
        gf_state = GreenfieldState(adw_id, logger=logger)
        
        # Load spec files
        try:
            spec_files, spec_content = load_spec_files(spec_pattern, working_dir, logger)
            gf_state.spec_files = [os.path.relpath(f, working_dir) for f in spec_files]
        except ValueError as e:
            logger.error(str(e))
            sys.exit(1)
        
        print(f"\n=== GREENFIELD IMPLEMENTATION ===")
        print(f"Loaded {len(spec_files)} spec file(s)")
        
        # Decompose specifications
        print("\n--- Decomposing Specifications ---")
        success, modules, execution_order, user_personas = decompose_specifications(
            spec_content, adw_id, logger, working_dir
        )
        greenfield_cost_tracker.record_from_template_request(
            adw_id, AGENT_DECOMPOSER, bucket="decomposition", logger=logger,
        )

        if not success or not modules:
            logger.error("Failed to decompose specifications")
            sys.exit(1)

        # Safety net: if a design-polish module was emitted (handoff detected),
        # enforce that its deps cover every UI module and that it runs LAST.
        # No-op when there's no polish module.
        _ensure_polish_module_deps(modules, execution_order, logger)

        # Initialize state
        gf_state.initialize_modules(modules, execution_order)
        gf_state.user_personas = user_personas

        # Validate module consistency (execution_order, dependencies, cycles)
        consistency_warnings = gf_state.validate_module_consistency()
        if consistency_warnings:
            print(f"\nModule consistency warnings:")
            for warning in consistency_warnings:
                print(f"  - {warning}")
                logger.warning(f"Module consistency: {warning}")

        gf_state.save()

        # Generate and save tracking file
        tracking_path = gf_state.save_tracking_file(working_dir)
        print(f"\nTracking file: {tracking_path}")
        print(f"Total modules: {len(modules)}")
        print(f"Execution order: {', '.join(gf_state.execution_order)}")

        if dry_run:
            print("\n=== DRY RUN - Showing decomposition ===")
            for module in modules:
                print(f"\n  {module.id}: {module.name}")
                print(f"    Priority: {module.priority.value}")
                print(f"    Complexity: {module.estimated_complexity}")
                print(f"    Dependencies: {', '.join(module.dependencies) or 'none'}")
                print(f"    User stories: {len(module.user_stories)}")
                print(f"    Acceptance criteria: {len(module.acceptance_criteria)}")
            print("\nDry run complete. Run without --dry-run to execute.")
            sys.exit(0)
    
    # Register state for signal handler to save on interruption
    global _active_gf_state
    _active_gf_state = gf_state

    # Accumulator for review issues across all modules
    all_module_review_issues: Dict[str, Dict[str, Any]] = {}

    # For --resume, recover review issues from previously completed modules on main
    if resume_mode:
        all_module_review_issues = recover_review_issues_from_main(gf_state, working_dir, logger)

    # Execute modules
    print("\n--- Executing Modules ---")
    
    while True:
        # Get next module to implement
        next_module_id = gf_state.get_next_module()
        
        if not next_module_id:
            # Check if all done or blocked
            pending = [
                mid for mid, state in gf_state.module_states.items()
                if state.status == ModuleStatus.PENDING
            ]
            
            if pending:
                logger.error(f"Cannot proceed: {len(pending)} modules blocked by unmet dependencies")
                print(f"\n❌ Blocked: {len(pending)} modules have unmet dependencies")
                for mid in pending:
                    module = gf_state.modules.get(mid)
                    if module:
                        dep_details = []
                        for dep_id in module.dependencies:
                            dep_state = gf_state.module_states.get(dep_id)
                            if dep_state is None:
                                dep_details.append(f"{dep_id} (NOT FOUND)")
                            elif dep_state.status != ModuleStatus.COMPLETED:
                                dep_details.append(f"{dep_id} ({dep_state.status.value})")
                        if dep_details:
                            print(f"  - {module.name}: blocked by {', '.join(dep_details)}")
                        else:
                            print(f"  - {module.name}: depends on {', '.join(module.dependencies)}")
                # Write the known-limitations registry before exiting so the
                # operator can see which acceptance criteria across already-run
                # modules are intentionally / accidentally unmet.
                limits_path = write_known_limitations_summary(
                    adw_id, working_dir, gf_state, logger
                )
                if limits_path:
                    print(
                        f"\nKnown limitations across run-so-far: "
                        f"{os.path.relpath(limits_path, working_dir)}"
                    )
                sys.exit(1)
            else:
                # All done!
                break
        
        module = gf_state.modules.get(next_module_id)
        if not module:
            logger.error(f"Module not found: {next_module_id}")
            continue
        
        # Show position in execution_order (not completed count) for accurate progress
        try:
            module_position = gf_state.execution_order.index(next_module_id) + 1
        except ValueError:
            module_position = gf_state.modules_completed + 1
        print(f"\n--- Module: {module.name} ({module_position}/{gf_state.modules_total}) ---")

        # Reuse existing issue if this module was previously attempted
        existing_state = gf_state.module_states.get(next_module_id)
        if existing_state and existing_state.issue_number:
            issue_number = existing_state.issue_number
            logger.info(f"Reusing existing issue #{issue_number} for module {module.name}")
        else:
            # Create GitHub issue for this module
            success, issue_number = create_module_issue(
                module, adw_id, repo_path, logger, working_dir,
                user_personas=gf_state.user_personas,
            )

            if not success or not issue_number:
                # Don't use mark_module_failed() here — issue creation failures are
                # infrastructure errors, not module implementation failures.  Burning
                # retry_count would cause the module to be SKIPPED before SDLC even runs.
                mod_state = gf_state.module_states.get(next_module_id)
                if mod_state:
                    mod_state.status = ModuleStatus.FAILED
                    mod_state.error_message = "Failed to create GitHub issue"
                gf_state.save()
                gf_state.save_tracking_file(working_dir)
                continue
        
        # Generate child ADW ID
        child_adw_id = f"{adw_id}-{module.id}"
        
        # Mark as started
        gf_state.mark_module_started(next_module_id, issue_number, child_adw_id)
        gf_state.save()
        gf_state.save_tracking_file(working_dir)
        
        # Run SDLC router (child_adw_id computed above, passed in to avoid duplication)
        sdlc_result = run_sdlc_for_module(
            module, issue_number, child_adw_id, working_dir, logger, skip_smoke
        )

        if sdlc_result == "success":
            # Pre-merge verification gate. Run /verify_greenfield against a
            # single-module decomposition slice; only merge if it returns pass.
            # partial/fail keeps the branch around for inspection and avoids
            # polluting main with broken module code.
            if skip_verify:
                gate_passed = True
                module_report: Optional[Dict[str, Any]] = None
                logger.info(f"Skipping pre-merge verification (--skip-verify)")
            else:
                print(f"🔍 Verifying module {module.name} before merge...")
                gate_passed, module_report = verify_module_before_merge(
                    adw_id, module, child_adw_id, working_dir, logger,
                    cost_tracker=greenfield_cost_tracker,
                )

            # Auto-rescue hop. On a "partial" verdict where enough criteria
            # are already met to suggest a planning gap rather than a planning
            # bust, spawn ONE /rescue_verification pass to patch the
            # met:false criteria, push, and re-verify. Capped at one real
            # invocation per module per ADW via ModuleState.rescue_attempts.
            #
            # Subtlety: attempt_module_rescue can return
            # outcome="skipped_low_criteria" WITHOUT invoking the rescue
            # agent — when criteria_met / criteria_total < min_criteria_pct,
            # or when the verdict isn't "partial". Those non-firings must
            # NOT count toward rescue_attempts; otherwise a future --resume
            # (e.g. with a lower threshold, or where verifier improved) will
            # see rescue_attempts > 0 and silently skip the rescue path.
            # We claim the slot before the call to prevent infinite retries
            # on a crash, then refund it if the agent didn't actually fire.
            mod_state_for_rescue = gf_state.module_states.get(next_module_id)
            already_rescued = (
                mod_state_for_rescue is not None
                and mod_state_for_rescue.rescue_attempts > 0
            )
            if (
                not gate_passed
                and auto_rescue
                and not skip_verify
                and not already_rescued
            ):
                if mod_state_for_rescue is not None:
                    mod_state_for_rescue.rescue_attempts += 1
                    gf_state.save()
                rescued, rescued_report, outcome = attempt_module_rescue(
                    adw_id, module, child_adw_id, working_dir, logger,
                    initial_report=module_report,
                    min_criteria_pct=rescue_min_criteria_pct,
                    cost_tracker=greenfield_cost_tracker,
                )
                if mod_state_for_rescue is not None:
                    mod_state_for_rescue.rescue_outcome = outcome
                    # Refund the attempt slot if the rescue function returned
                    # without invoking the agent (verdict wasn't partial, or
                    # criteria_met was below the threshold). The agent burned
                    # no time/tokens, so this shouldn't gate a future retry.
                    if outcome == "skipped_low_criteria":
                        mod_state_for_rescue.rescue_attempts = max(
                            0, mod_state_for_rescue.rescue_attempts - 1
                        )
                    gf_state.save()
                if rescued:
                    print(
                        f"🛟  Auto-rescue UPGRADED {module.name} to pass — "
                        "continuing to merge"
                    )
                    gate_passed = True
                    module_report = rescued_report
                elif outcome == "skipped_low_criteria":
                    logger.info(
                        f"Auto-rescue skipped for {module.id}: too few "
                        "criteria met to justify a patch attempt"
                    )
                else:
                    print(
                        f"🛟  Auto-rescue did not flip {module.name}: outcome={outcome}"
                    )

            if not gate_passed:
                fail_reason = "Pre-merge verification did not return pass — branch not merged"
                if mod_state_for_rescue is not None and mod_state_for_rescue.rescue_outcome:
                    fail_reason += f" (rescue: {mod_state_for_rescue.rescue_outcome})"
                gf_state.mark_module_failed(next_module_id, fail_reason)
                print(f"❌ Module {module.name} blocked at pre-merge verification gate")
                logger.warning(
                    f"Module {module.id} pre-merge verification failed; "
                    f"preserving worktree for inspection"
                )
                # Don't run _cleanup_failed_module here — leave the worktree so
                # the operator can inspect/fix without re-running the full SDLC.
                gf_state.save()
                gf_state.save_tracking_file(working_dir)
                continue

            # Merge module branch to main so dependent modules get the code
            print(f"🔀 Merging module {module.name} to main...")
            merge_success = merge_module_to_main(
                issue_number, child_adw_id, working_dir, logger
            )

            if merge_success:
                gf_state.mark_module_completed(next_module_id)
                gf_state.mark_module_merged(next_module_id)
                print(f"✅ Module {module.name} completed and merged to main")

                # Load child state once — used for PR close and review extraction
                child_state = None
                worktree_path = None
                try:
                    child_state = ADWState.load(child_adw_id, logger)
                    if child_state:
                        worktree_path = child_state.get("worktree_path")
                except Exception:
                    pass

                # Extract review issues from worktree before cleanup
                if worktree_path and os.path.isdir(worktree_path):
                    review_data = extract_module_review_issues(child_adw_id, worktree_path, logger)
                    if review_data:
                        all_module_review_issues[next_module_id] = review_data

                # Close any open PR for this module's branch
                branch_name = f"{child_adw_id}"
                if child_state:
                    branch_name = child_state.get("branch_name", branch_name)
                try:
                    subprocess.run(
                        ["gh", "pr", "close", branch_name, "-R", repo_path, "--delete-branch"],
                        capture_output=True, text=True, cwd=working_dir, timeout=30,
                    )
                except Exception as e:
                    logger.debug(f"PR close attempt for {branch_name}: {e}")

                # Cleanup child worktree to free ports for subsequent modules
                try:
                    remove_worktree(child_adw_id, logger)
                    logger.info(f"Cleaned up worktree for {child_adw_id}")
                except Exception as e:
                    logger.warning(f"Failed to cleanup worktree for {child_adw_id}: {e}")
            else:
                gf_state.mark_module_failed(
                    next_module_id, "SDLC succeeded but merge to main failed"
                )
                print(f"❌ Module {module.name} SDLC passed but merge failed")
                logger.warning(f"Module {module.id} merge failed, continuing with other modules")
                if not preserve_on_failure:
                    _cleanup_failed_module(child_adw_id, working_dir, logger)
        elif sdlc_result == "usage_limit":
            gf_state.mark_module_failed(next_module_id, "Usage limit or server error")
            print(f"❌ Module {module.name} failed due to usage limit / server error")
            if not preserve_on_failure:
                _cleanup_failed_module(child_adw_id, working_dir, logger)
            # Stop the entire run — subsequent modules will fail too
            print("\n🛑 Stopping greenfield run: usage limit / server error detected.")
            print("All subsequent modules would fail. Use --resume when capacity is available.")
            gf_state.save()
            gf_state.save_tracking_file(working_dir)
            sys.exit(1)
        else:
            gf_state.mark_module_failed(next_module_id, "SDLC workflow failed")
            print(f"❌ Module {module.name} failed")
            logger.warning(f"Module {module.id} failed, continuing with other modules")
            if not preserve_on_failure:
                _cleanup_failed_module(child_adw_id, working_dir, logger)
            else:
                logger.info(
                    f"--preserve-on-failure: leaving worktree and state for {child_adw_id} intact"
                )
        
        # Save state after each module
        gf_state.save()
        gf_state.save_tracking_file(working_dir)
    
    # Aggregate every verifier-flagged unmet criterion into a single
    # operator-facing registry before printing the final summary, so
    # operators have a canonical place to look up known gaps without
    # grepping across 20 verification_module_*.json files.
    limits_path = write_known_limitations_summary(
        adw_id, working_dir, gf_state, logger
    )

    # Final summary
    print("\n=== GREENFIELD IMPLEMENTATION COMPLETE ===")
    print(f"ADW ID: {adw_id}")
    print(f"Modules completed: {gf_state.modules_completed}/{gf_state.modules_total}")
    if limits_path:
        print(
            f"Known limitations: "
            f"{os.path.relpath(limits_path, working_dir)}"
        )
    
    failed_modules = [
        mid for mid, state in gf_state.module_states.items()
        if state.status == ModuleStatus.FAILED
    ]
    incomplete_modules = [
        mid for mid, state in gf_state.module_states.items()
        if state.status in (ModuleStatus.IN_PROGRESS, ModuleStatus.PENDING)
    ]

    if failed_modules or incomplete_modules:
        if failed_modules:
            print(f"Failed modules: {len(failed_modules)}")
            for mid in failed_modules:
                module = gf_state.modules.get(mid)
                state = gf_state.module_states.get(mid)
                if module and state:
                    print(f"  - {module.name}: {state.error_message}")
        if incomplete_modules:
            print(f"Incomplete modules: {len(incomplete_modules)}")
            for mid in incomplete_modules:
                module = gf_state.modules.get(mid)
                state = gf_state.module_states.get(mid)
                if module and state:
                    print(f"  - {module.name}: {state.status.value}")

        # Build and save tracker locally for partial runs (don't push to main)
        if all_module_review_issues:
            tracker_content = build_consolidated_review_tracker(adw_id, gf_state, all_module_review_issues)
            tracker_dir = os.path.join(working_dir, "specs", "greenfields", adw_id)
            os.makedirs(tracker_dir, exist_ok=True)
            tracker_path = os.path.join(tracker_dir, "REVIEW_ISSUES.md")
            try:
                with open(tracker_path, "w") as f:
                    f.write(tracker_content)
                print(f"\n📋 Partial review tracker saved locally: {tracker_path}")
            except Exception as e:
                logger.warning(f"Failed to save partial review tracker: {e}")

        print("\nUse --resume to retry failed/incomplete modules.")
        sys.exit(1)
    else:
        print("All modules completed successfully!")

        # Update final tracking file
        gf_state.save_tracking_file(working_dir)

        # Build and commit consolidated review tracker to main
        if all_module_review_issues:
            print("\n--- Building Consolidated Review Tracker ---")
            tracker_content = build_consolidated_review_tracker(adw_id, gf_state, all_module_review_issues)
            commit_review_tracker_to_main(adw_id, tracker_content, working_dir, logger)
            print(f"📋 Review tracker committed to specs/greenfields/{adw_id}/REVIEW_ISSUES.md")
        else:
            print("\nNo review issues found across modules — skipping tracker.")

        # Final verification step
        if skip_verify:
            print("\nSkipping final verification (--skip-verify)")
        else:
            # Ensure we're on main with latest code before verifying
            logger.info("Checking out main branch for verification...")
            checkout_result = subprocess.run(
                ["git", "checkout", "main"],
                capture_output=True, text=True, cwd=working_dir,
            )
            if checkout_result.returncode != 0:
                logger.error(f"Failed to checkout main for verification: {checkout_result.stderr}")
                print(f"\nWarning: Could not checkout main ({checkout_result.stderr.strip()}). Verification may use stale code.")
            else:
                pull_result = subprocess.run(
                    ["git", "pull", "origin", "main"],
                    capture_output=True, text=True, cwd=working_dir,
                )
                if pull_result.returncode != 0:
                    logger.warning(f"Failed to pull latest main: {pull_result.stderr}")
                    print(f"\nWarning: Could not pull latest main ({pull_result.stderr.strip()}). Verification may use stale code.")

            print("\n--- Running Final Verification ---")
            verify_success, report = verify_final_implementation(
                adw_id, working_dir, logger,
            )
            greenfield_cost_tracker.record_from_template_request(
                adw_id, AGENT_VERIFIER, bucket="final_verification", logger=logger,
            )
            if verify_success and report:
                print_verification_report(report)
            else:
                print("\nWarning: Final verification could not be completed (agent error). This is advisory only.")
                logger.warning("Final verification failed to produce a report")

        # E2E Validation step (advisory only — never blocks)
        if skip_e2e:
            print("\nSkipping E2E validation (--skip-e2e)")
        else:
            decomposition_path = os.path.join(
                working_dir, "specs", "greenfields", adw_id, "decomposition.json"
            )
            if os.path.exists(decomposition_path):
                print("\n--- Running E2E Validation ---")
                try:
                    from adw_e2e_validation_iso import run_e2e_validation, print_e2e_validation_summary
                    e2e_result = run_e2e_validation(
                        decomposition_path=decomposition_path,
                        adw_id=adw_id,
                        working_dir=working_dir,
                        logger=logger,
                        cost_tracker=greenfield_cost_tracker,
                    )
                    print_e2e_validation_summary(e2e_result)
                except Exception as e:
                    logger.warning(f"E2E validation encountered an error (advisory): {e}")
                    print(f"\nWarning: E2E validation could not be completed: {e}")
                    print("This is advisory only and does not block the greenfield.")
            else:
                print("\nSkipping E2E validation (no decomposition.json found)")

        # Domain documentation step (advisory only — never blocks).
        # Generate/update per-domain context docs in ai_docs/domain/ so future
        # ADWs that touch a built domain can load its business + full-stack map.
        domain_decomposition_path = os.path.join(
            working_dir, "specs", "greenfields", adw_id, "decomposition.json"
        )
        if os.path.exists(domain_decomposition_path):
            print("\n--- Generating Domain Documentation ---")
            try:
                generate_domain_docs(
                    adw_id=adw_id,
                    decomposition_path=domain_decomposition_path,
                    working_dir=working_dir,
                    logger=logger,
                )
                greenfield_cost_tracker.record_from_template_request(
                    adw_id, AGENT_DOMAIN_DOCUMENTER, bucket="domain_docs", logger=logger,
                )
            except Exception as e:
                logger.warning(f"Domain doc generation encountered an error (advisory): {e}")
                print(f"\nWarning: Domain doc generation could not be completed: {e}")
                print("This is advisory only and does not block the greenfield.")
        else:
            print("\nSkipping domain documentation (no decomposition.json found)")

        # Persist greenfield-level cost telemetry and print summary.
        greenfield_cost_summary_path = os.path.join(
            working_dir, "specs", "greenfields", adw_id, "greenfield_cost_summary.json",
        )
        try:
            greenfield_cost_tracker.write_summary(greenfield_cost_summary_path, adw_id)
            logger.info(f"Greenfield cost summary written to {greenfield_cost_summary_path}")
        except Exception as e:
            logger.warning(f"Failed to write greenfield cost summary: {e}")
        greenfield_cost_tracker.print_summary(header=f"Greenfield Cost Summary ({adw_id})")

        sys.exit(0)


if __name__ == "__main__":
    main()
