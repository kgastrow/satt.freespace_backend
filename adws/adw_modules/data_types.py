"""Data types for GitHub API responses and Claude Code agent."""

from datetime import datetime
from typing import Optional, List, Literal
from pydantic import BaseModel, Field
from enum import Enum


# Retry codes for Claude Code execution errors
class RetryCode(str, Enum):
    """Codes indicating different types of errors that may be retryable."""

    CLAUDE_CODE_ERROR = "claude_code_error"  # General Claude Code CLI error
    TIMEOUT_ERROR = "timeout_error"  # Command timed out
    EXECUTION_ERROR = "execution_error"  # Error during execution
    ERROR_DURING_EXECUTION = "error_during_execution"  # Agent encountered an error
    AGENT_SOFT_ERROR = "agent_soft_error"  # Agent reported is_error=True but exit code 0 (retryable)
    USAGE_LIMIT = "usage_limit"  # Claude Code usage limit reached (wait and retry)
    SERVER_ERROR = "server_error"  # API 500/overloaded error (wait and retry)
    NONE = "none"  # No retry needed


# Supported slash commands for issue classification
# These should align with your custom slash commands in .claude/commands that you want to run
IssueClassSlashCommand = Literal["/chore", "/bug", "/feature"]

# Model set types for ADW workflows
# - "base": default; sonnet for utility commands, claude-opus-4-6 where opus is selected
# - "heavy": pins the "opus" alias to claude-opus-4-6 (explicit version)
# - "superheavy": pins the "opus" alias to claude-opus-4-7 (latest, most expensive)
ModelSet = Literal["base", "heavy", "superheavy"]

# ADW workflow types (all isolated now)
ADWWorkflow = Literal[
    "adw_plan_iso",  # Planning only
    "adw_patch_iso",  # Direct patch from issue
    "adw_build_iso",  # Building only (dependent workflow)
    "adw_test_iso",  # Testing only (dependent workflow)
    "adw_smoke_iso",  # Smoke testing only (dependent workflow)
    "adw_review_iso",  # Review only (dependent workflow)
    "adw_document_iso",  # Documentation only (dependent workflow)
    "adw_ship_iso",  # Ship/deployment workflow
    "adw_sdlc_ZTE_iso",  # Zero Touch Execution - full SDLC with auto-merge
    "adw_plan_build_iso",  # Plan + Build
    "adw_plan_build_test_iso",  # Plan + Build + Test
    "adw_plan_build_test_review_iso",  # Plan + Build + Test + Review
    "adw_plan_build_document_iso",  # Plan + Build + Document
    "adw_plan_build_review_iso",  # Plan + Build + Review
    "adw_sdlc_iso",  # Complete SDLC: Plan + Build + Test + Review + Document
    "adw_multi_phase_sdlc_iso",  # Multi-phase SDLC for large features
    "adw_implementation_consistency_iso",  # Parallel code consistency review
    "adw_rescue_project_iso",  # Vibe Code Rescue workflow
]

# All slash commands used in the ADW system
# Includes issue classification commands and ADW-specific commands
SlashCommand = Literal[
    # Issue classification commands
    "/chore",
    "/bug",
    "/feature",
    # ADW workflow commands
    "/classify_issue",
    "/classify_adw",
    "/classify_sdlc_complexity",
    "/generate_branch_name",
    "/commit",
    "/pull_request",
    "/implement",
    "/test",
    "/write_tests",
    "/resolve_failed_test",
    "/test_e2e",
    "/resolve_failed_e2e_test",
    "/resolve_build_error",
    "/resolve_merge_conflict",
    "/smoke_test",
    "/resolve_failed_smoke_test",
    "/review",
    "/patch",
    "/document",
    # "/track_agentic_kpis",  # Disabled - causes merge conflicts
    # Greenfield workflow commands
    "/decompose_specs",
    "/verify_greenfield",
    "/rescue_verification",
    "/write_greenfield_e2e",
    # Design handoff commands
    "/assimilate_design",
    "/validate_design_match",
    # Generic E2E generation commands
    "/discover_e2e_targets",
    "/write_e2e_test",
    # Multi-phase workflow commands
    "/plan_multi_phase",
    "/implement_phase",
    "/review_phase",
    # Installation/setup commands
    "/install_worktree",
    "/prepare_app",
    "/prime",
    # Context management commands
    "/refine_context",
    # Implementation consistency commands
    "/review_consistency",
    # Rescue workflow commands - Discovery
    "/rescue_scan_structure",
    "/rescue_map_features",
    "/rescue_extract_schema",
    "/rescue_catalog_ui",
    "/rescue_document_discovery",
    # Rescue workflow commands - Triage
    "/rescue_score_components",
    "/rescue_classify_backend",
    "/rescue_plan_ui",
    "/rescue_generate_tasks",
    "/rescue_evaluate_feasibility",
    # Rescue workflow commands - Execution
    "/rescue_execute_model",
    "/rescue_execute_crud",
    "/rescue_execute_api",
    "/rescue_execute_component",
    "/rescue_execute_wire",
    "/rescue_execute_test",
    "/rescue_replan",
    # Rescue workflow commands - Validation
    "/rescue_validate_tests",
    "/rescue_validate_visual",
    "/rescue_validate_features",
    # Rescue workflow commands - Control
    "/rescue_status",
    "/rescue_skip_task",
    "/rescue_checkpoint",
]


class GitHubUser(BaseModel):
    """GitHub user model."""

    id: Optional[str] = None  # Not always returned by GitHub API
    login: str
    name: Optional[str] = None
    is_bot: bool = Field(default=False, alias="is_bot")


class GitHubLabel(BaseModel):
    """GitHub label model."""

    id: str
    name: str
    color: str
    description: Optional[str] = None


class GitHubMilestone(BaseModel):
    """GitHub milestone model."""

    id: str
    number: int
    title: str
    description: Optional[str] = None
    state: str


class GitHubComment(BaseModel):
    """GitHub comment model."""

    id: str
    author: GitHubUser
    body: str
    created_at: datetime = Field(alias="createdAt")
    updated_at: Optional[datetime] = Field(
        None, alias="updatedAt"
    )  # Not always returned


class GitHubIssueListItem(BaseModel):
    """GitHub issue model for list responses (simplified)."""

    number: int
    title: str
    body: str
    labels: List[GitHubLabel] = []
    created_at: datetime = Field(alias="createdAt")
    updated_at: datetime = Field(alias="updatedAt")

    class Config:
        populate_by_name = True


class GitHubIssue(BaseModel):
    """GitHub issue model."""

    number: int
    title: str
    body: str
    state: str
    author: GitHubUser
    assignees: List[GitHubUser] = []
    labels: List[GitHubLabel] = []
    milestone: Optional[GitHubMilestone] = None
    comments: List[GitHubComment] = []
    created_at: datetime = Field(alias="createdAt")
    updated_at: datetime = Field(alias="updatedAt")
    closed_at: Optional[datetime] = Field(None, alias="closedAt")
    url: str

    class Config:
        populate_by_name = True


class AgentPromptRequest(BaseModel):
    """Claude Code agent prompt configuration."""

    prompt: str
    adw_id: str
    agent_name: str = "ops"
    # Accepts CLI aliases ("sonnet", "opus") or explicit model IDs ("claude-opus-4-6", "claude-opus-4-7").
    model: str = "sonnet"
    dangerously_skip_permissions: bool = False
    output_file: str
    working_dir: Optional[str] = None


class AgentPromptResponse(BaseModel):
    """Claude Code agent response."""

    output: str
    success: bool
    session_id: Optional[str] = None
    retry_code: RetryCode = RetryCode.NONE


class AgentTemplateRequest(BaseModel):
    """Claude Code agent template execution request."""

    agent_name: str
    slash_command: SlashCommand
    args: List[str]
    adw_id: str
    # Accepts CLI aliases ("sonnet", "opus") or explicit model IDs ("claude-opus-4-6", "claude-opus-4-7").
    model: str = "sonnet"
    working_dir: Optional[str] = None


class ClaudeCodeResultMessage(BaseModel):
    """Claude Code JSONL result message (last line)."""

    type: str
    subtype: str
    is_error: bool
    duration_ms: int
    duration_api_ms: int
    num_turns: int
    result: str
    session_id: str
    total_cost_usd: float


class TestResult(BaseModel):
    """Individual test result from test suite execution."""

    test_name: str
    passed: bool
    execution_command: str
    test_purpose: str
    error: Optional[str] = None


class BuildError(BaseModel):
    """Individual build/type error from compilation."""

    file_path: str
    line: int
    column: int
    error_code: str
    message: str
    raw_error: str  # Full error line for context

    def to_resolution_payload(self) -> str:
        """Format error for resolution agent."""
        return (
            f"File: {self.file_path}\n"
            f"Location: Line {self.line}, Column {self.column}\n"
            f"Error Code: {self.error_code}\n"
            f"Message: {self.message}\n"
            f"Raw: {self.raw_error}"
        )


class E2ETestResult(BaseModel):
    """Individual E2E test result from browser automation."""

    test_name: str
    status: Literal["passed", "failed"]
    test_path: str  # Path to the test file for re-execution
    screenshots: List[str] = []
    error: Optional[str] = None

    @property
    def passed(self) -> bool:
        """Check if test passed."""
        return self.status == "passed"


class SmokeTestResult(BaseModel):
    """Individual smoke test result from contextual browser testing."""

    test_name: str
    status: Literal["passed", "failed", "skipped"]
    test_description: str
    screenshots: List[str] = []
    screenshot_urls: List[str] = []  # Public URLs after R2 upload
    error: Optional[str] = None


class ADWStateData(BaseModel):
    """Minimal persistent state for ADW workflow.

    Stored in agents/{adw_id}/adw_state.json
    Contains only essential identifiers to connect workflow steps.
    """

    adw_id: str
    issue_number: Optional[str] = None
    branch_name: Optional[str] = None
    plan_file: Optional[str] = None
    issue_class: Optional[IssueClassSlashCommand] = None
    worktree_path: Optional[str] = None
    backend_port: Optional[int] = None
    frontend_port: Optional[int] = None
    database_name: Optional[str] = None  # Isolated database name (e.g., appdb_ccfd0008)
    model_set: Optional[ModelSet] = "base"  # Default to "base" model set
    all_adws: List[str] = Field(default_factory=list)
    # Smoke test results for PR creation
    smoke_test_passed: Optional[int] = None
    smoke_test_failed: Optional[int] = None
    smoke_test_skipped: Optional[int] = None
    smoke_test_screenshot_urls: List[str] = Field(default_factory=list)
    # Resume support: tracks where workflow stopped
    workflow_stage: Optional[str] = None  # e.g., "planning", "implementing", "smoke_testing", "committing", "completed"
    # Process tracking for stop functionality
    workflow_pid: Optional[int] = None  # PID of the main workflow process
    workflow_pgid: Optional[int] = None  # Process group ID for killing all child processes
    # Context tracking for auditing and debugging
    context_files_loaded: List[str] = Field(default_factory=list)  # ai_docs files read by agents
    context_validation_passed: Optional[bool] = None  # Whether context validation passed in review
    context_violations_count: Optional[int] = None  # Number of violations found during review
    # Orchestrated SDLC (adw_orchestrated_sdlc_iso.py): the orchestrator's Claude Code session, for --resume
    orchestrator_session_id: Optional[str] = None
    # Started by the Ore trigger: its run folder, so `adw_report.py check` joins the batch's full check
    ore_run_dir: Optional[str] = None


class ReviewIssue(BaseModel):
    """Individual review issue found during spec verification."""

    review_issue_number: int
    screenshot_path: Optional[str] = None  # Local file path to screenshot (e.g., "agents/ADW-123/reviewer/review_img/error.png")
    screenshot_url: Optional[str] = (
        None  # Public URL after upload (e.g., "https://domain.com/adw/ADW-123/review/error.png")
    )
    issue_description: str
    issue_resolution: str
    issue_severity: Literal["skippable", "tech_debt", "blocker"]


class ReviewResult(BaseModel):
    """Result from reviewing implementation against specification."""

    success: bool
    review_summary: (
        str  # 2-4 sentences describing what was built and whether it matches the spec
    )
    review_issues: List[ReviewIssue] = []
    screenshots: List[str] = (
        []
    )  # Local file paths (e.g., ["agents/ADW-123/reviewer/review_img/ui.png"])
    screenshot_urls: List[str] = (
        []
    )  # Public URLs after upload, indexed-aligned with screenshots


class DocumentationResult(BaseModel):
    """Result from documentation generation workflow."""

    success: bool
    documentation_created: bool
    documentation_path: Optional[str] = None
    error_message: Optional[str] = None


class ADWExtractionResult(BaseModel):
    """Result from extracting ADW information from text."""

    workflow_command: Optional[str] = None  # e.g., "adw_plan_iso" (without slash)
    adw_id: Optional[str] = None  # ADW ID (format: YYYYMMDDHHMMSS-<8-char-uuid>)
    model_set: Optional[ModelSet] = "base"  # Model set to use, defaults to "base"

    @property
    def has_workflow(self) -> bool:
        """Check if a workflow command was extracted."""
        return self.workflow_command is not None


# =============================================================================
# Implementation Consistency Types (for adw_implementation_consistency_iso.py)
# =============================================================================


class PatternViolation(BaseModel):
    """A pattern violation found during consistency review."""

    file: str
    line: int = 0
    pattern: str
    description: str
    severity: Literal["critical", "high", "medium", "low", "info"]
    fix_suggestion: str


class Antipattern(BaseModel):
    """An antipattern detected in the codebase."""

    type: Literal[
        "hard_delete",
        "missing_tenant_isolation",
        "sync_in_async",
        "wrong_layer",
        "naming",
        "typing",
        "hardcoded",
    ]
    file: str
    line: int
    description: str
    severity: Literal["critical", "high", "medium", "low"]
    fix_suggestion: str


class DeadCode(BaseModel):
    """Dead code detected in the codebase."""

    file: str
    line: int
    type: Literal["unused_import", "unused_function", "commented_code", "obsolete"]
    description: str
    confidence: Literal["high", "medium", "low"]


class DuplicateCode(BaseModel):
    """Duplicate code detected across files."""

    files: List[str]
    lines: List[int]
    description: str
    abstraction_suggestion: str


class DocumentationDrift(BaseModel):
    """Documentation that has drifted from implementation."""

    doc_location: str
    issue: Literal["outdated", "incorrect", "missing"]
    description: str
    fix_suggestion: str


class ConsistencyRecommendation(BaseModel):
    """A recommendation from the consistency review."""

    priority: Literal["high", "medium", "low"]
    category: Literal["refactor", "security", "performance", "documentation", "testing"]
    description: str
    affected_files: List[str] = []


class ConsistencyReviewResult(BaseModel):
    """Result from a single area consistency review."""

    context_file: str
    review_area: str
    files_analyzed: int
    compliance_score: int  # 0-100
    summary: str
    pattern_violations: List[PatternViolation] = []
    antipatterns: List[Antipattern] = []
    dead_code: List[DeadCode] = []
    duplicate_code: List[DuplicateCode] = []
    documentation_drift: List[DocumentationDrift] = []
    recommendations: List[ConsistencyRecommendation] = []


class ConsistencyReportSummary(BaseModel):
    """Aggregated summary of all consistency reviews."""

    total_files_analyzed: int
    overall_compliance_score: int  # Weighted average
    areas_reviewed: int
    critical_issues: int
    high_issues: int
    medium_issues: int
    low_issues: int
    total_dead_code: int
    total_duplicates: int
    doc_drift_count: int


# =============================================================================
# Smoke Test Direct Execution Types (for smoke_test_runner.py)
# =============================================================================


class SmokeTestStep(BaseModel):
    """A single step in a smoke test.

    Supported actions:
    - navigate: Go to URL (url field, can be relative)
    - click: Click element (selector)
    - fill/type: Enter text (selector, text)
    - press: Press keyboard key (key, optional selector)
    - waitForSelector: Wait for element (selector)
    - waitForUrl: Wait for URL pattern (url)
    - screenshot: Take screenshot (name)
    - assertVisible: Assert element is visible (selector)
    - assertHidden: Assert element is hidden (selector)
    - assertText: Assert element contains text (selector, text)
    - wait: Simple delay (timeout in ms)
    - hover: Hover over element (selector)
    - selectOption: Select dropdown option (selector, text=value)
    """
    action: str
    selector: Optional[str] = None
    url: Optional[str] = None
    name: Optional[str] = None  # For screenshots
    text: Optional[str] = None  # For fill/type/assertText actions
    timeout: int = 5000  # ms
    key: Optional[str] = None  # For keyboard actions


class SmokeTestDefinition(BaseModel):
    """Definition of a single smoke test to be executed."""
    name: str
    description: str
    steps: List[SmokeTestStep]


class SmokeTestAuthConfig(BaseModel):
    """Authentication configuration for smoke tests."""
    access_token: str
    refresh_token: str


class SmokeTestSuite(BaseModel):
    """Complete smoke test suite definition.

    This is the input format for smoke_test_runner.py.
    Claude generates this once, then it can be executed multiple times
    without regenerating tests (Solution A: cache generated tests).
    """
    application_url: str
    auth: Optional[SmokeTestAuthConfig] = None
    tests: List[SmokeTestDefinition]
