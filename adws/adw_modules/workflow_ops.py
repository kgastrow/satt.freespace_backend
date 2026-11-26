"""Shared AI Developer Workflow (ADW) operations."""

import fcntl
import glob
import json
import logging
import os
import subprocess
import re
from typing import Tuple, Optional, List
from adw_modules.data_types import (
    AgentTemplateRequest,
    GitHubIssue,
    AgentPromptResponse,
    IssueClassSlashCommand,
    ADWExtractionResult,
    RetryCode,
)
from adw_modules.agent import execute_template
from adw_modules.github import get_repo_url, extract_repo_path, ADW_BOT_IDENTIFIER
from adw_modules.state import ADWState
from adw_modules.utils import parse_json

# Module logger
logger = logging.getLogger(__name__)

# Default timeout for git operations
GIT_TIMEOUT = 60  # seconds


# Agent name constants
AGENT_PLANNER = "sdlc_planner"
AGENT_IMPLEMENTOR = "sdlc_implementor"
AGENT_CLASSIFIER = "issue_classifier"
AGENT_BRANCH_GENERATOR = "branch_generator"
AGENT_PR_CREATOR = "pr_creator"
AGENT_COMPLEXITY_CLASSIFIER = "complexity_classifier"

# Available ADW workflows for runtime validation
AVAILABLE_ADW_WORKFLOWS = [
    # Isolated workflows (all workflows are now iso-based)
    "adw_plan_iso",
    "adw_patch_iso",
    "adw_build_iso",
    "adw_test_iso",
    "adw_review_iso",
    "adw_document_iso",
    "adw_ship_iso",
    "adw_sdlc_ZTE_iso",  # Zero Touch Execution workflow
    "adw_plan_build_iso",
    "adw_plan_build_test_iso",
    "adw_plan_build_test_review_iso",
    "adw_plan_build_document_iso",
    "adw_plan_build_review_iso",
    "adw_sdlc_iso",
    # Router workflow that auto-selects single or multi-phase
    "adw_sdlc_router_iso",
    # Multi-phase workflow for large features
    "adw_multi_phase_sdlc_iso",
    # Implementation consistency review
    "adw_implementation_consistency_iso",
    # Greenfield orchestration for full project implementation from specs
    "adw_greenfield_iso",
    # Vibe Code Rescue workflow
    "adw_rescue_project_iso",
]


def format_issue_message(
    adw_id: str, agent_name: str, message: str, session_id: Optional[str] = None
) -> str:
    """Format a message for issue comments with ADW tracking and bot identifier."""
    # Always include ADW_BOT_IDENTIFIER to prevent webhook loops
    if session_id:
        return f"{ADW_BOT_IDENTIFIER} {adw_id}_{agent_name}_{session_id}: {message}"
    return f"{ADW_BOT_IDENTIFIER} {adw_id}_{agent_name}: {message}"


def extract_adw_info(text: str, temp_adw_id: str) -> ADWExtractionResult:
    """Extract ADW workflow, ID, and model_set from text using classify_adw agent.
    Returns ADWExtractionResult with workflow_command, adw_id, and model_set."""

    # Use classify_adw to extract structured info
    request = AgentTemplateRequest(
        agent_name="adw_classifier",
        slash_command="/classify_adw",
        args=[text],
        adw_id=temp_adw_id,
    )

    try:
        response = execute_template(request)  # No logger available in this function

        if not response.success:
            logger.warning(f"Failed to classify ADW: {response.output}")
            return ADWExtractionResult()  # Empty result

        # Parse JSON response using utility that handles markdown
        try:
            data = parse_json(response.output, dict)
            adw_command = data.get("adw_slash_command", "").replace(
                "/", ""
            )  # Remove slash
            adw_id = data.get("adw_id")
            model_set = data.get("model_set", "base")  # Default to "base"

            # Validate command
            if adw_command and adw_command in AVAILABLE_ADW_WORKFLOWS:
                return ADWExtractionResult(
                    workflow_command=adw_command,
                    adw_id=adw_id,
                    model_set=model_set
                )

            return ADWExtractionResult()  # Empty result

        except ValueError as e:
            logger.warning(f"Failed to parse classify_adw response: {e}")
            return ADWExtractionResult()  # Empty result

    except Exception as e:
        logger.error(f"Error calling classify_adw: {e}")
        return ADWExtractionResult()  # Empty result


def _extract_classification(
    output: str, logger: logging.Logger
) -> Tuple[Optional[IssueClassSlashCommand], Optional[str]]:
    """Extract classification command from LLM output.
    Returns (command, error_message) tuple."""
    output = output.strip()

    # Look for slash commands first (most specific)
    classification_match = re.search(r"(/chore|/bug|/feature)", output)

    if classification_match:
        return classification_match.group(1), None  # type: ignore

    # Check for standalone "0" (no command)
    if re.fullmatch(r"\s*0\s*", output):
        return None, f"No command selected: {output}"

    # Fallback: look for bare keywords (feature/bug/chore) without the slash
    # This handles cases where the LLM produces verbose output containing
    # the classification word but not as a slash command
    fallback_match = re.search(r"\b(feature|bug|chore)\b", output, re.IGNORECASE)
    if fallback_match:
        issue_command = f"/{fallback_match.group(1).lower()}"
        logger.warning(
            f"LLM produced verbose output. Extracted classification via fallback: {issue_command}"
        )
        return issue_command, None  # type: ignore

    if output == "0":
        return None, f"No command selected: {output}"

    return None, f"Invalid command selected: {output}"


def classify_issue(
    issue: GitHubIssue, adw_id: str, logger: logging.Logger
) -> Tuple[Optional[IssueClassSlashCommand], Optional[str]]:
    """Classify GitHub issue and return appropriate slash command.
    Returns (command, error_message) tuple. Retries once on failure."""

    # Use the classify_issue slash command template with minimal payload
    # Only include the essential fields: number, title, body
    minimal_issue_json = issue.model_dump_json(
        by_alias=True, include={"number", "title", "body"}
    )

    max_attempts = 2
    last_error = None

    for attempt in range(1, max_attempts + 1):
        request = AgentTemplateRequest(
            agent_name=AGENT_CLASSIFIER,
            slash_command="/classify_issue",
            args=[minimal_issue_json],
            adw_id=adw_id,
        )

        logger.debug(f"Classifying issue (attempt {attempt}/{max_attempts}): {issue.title}")

        response = execute_template(request)

        logger.debug(
            f"Classification response (attempt {attempt}): {response.model_dump_json(indent=2, by_alias=True)}"
        )

        if not response.success:
            last_error = response.output
            if attempt < max_attempts:
                logger.warning(f"Classification attempt {attempt} failed, retrying: {last_error}")
                continue
            return None, last_error

        command, error = _extract_classification(response.output, logger)
        if command:
            return command, None

        last_error = error
        if attempt < max_attempts:
            logger.warning(f"Classification attempt {attempt} could not extract command, retrying: {error}")
            continue

    return None, last_error


def classify_sdlc_complexity(
    issue: GitHubIssue, adw_id: str, logger: logging.Logger
) -> Tuple[Optional[str], Optional[str]]:
    """Classify issue complexity for SDLC routing.

    Analyzes a feature issue to determine if it should use single-phase
    or multi-phase SDLC workflow based on scope and complexity.

    Returns (complexity, error_message) tuple.
    complexity is 'single-phase' or 'multi-phase'
    """
    # Use minimal payload like classify_issue does
    minimal_issue_json = issue.model_dump_json(
        by_alias=True, include={"number", "title", "body"}
    )

    request = AgentTemplateRequest(
        agent_name=AGENT_COMPLEXITY_CLASSIFIER,
        slash_command="/classify_sdlc_complexity",
        args=[minimal_issue_json],
        adw_id=adw_id,
    )

    logger.debug(f"Classifying complexity for issue: {issue.title}")

    response = execute_template(request)

    logger.debug(
        f"Complexity classification response: {response.model_dump_json(indent=2, by_alias=True)}"
    )

    if not response.success:
        return None, response.output

    # Parse JSON response
    try:
        data = parse_json(response.output, dict)
        complexity = data.get("complexity", "single-phase")

        # Validate complexity value
        if complexity not in ["single-phase", "multi-phase"]:
            logger.warning(f"Invalid complexity value '{complexity}', defaulting to single-phase")
            complexity = "single-phase"

        reasoning = data.get("reasoning", "")
        logger.info(f"Complexity: {complexity} - {reasoning}")

        return complexity, None

    except (ValueError, json.JSONDecodeError) as e:
        logger.warning(f"Failed to parse complexity response: {e}")
        return None, f"Failed to parse complexity response: {e}"


def build_plan(
    issue: GitHubIssue,
    command: str,
    adw_id: str,
    logger: logging.Logger,
    working_dir: Optional[str] = None,
) -> AgentPromptResponse:
    """Build implementation plan for the issue using the specified command."""
    # Use minimal payload like classify_issue does
    minimal_issue_json = issue.model_dump_json(
        by_alias=True, include={"number", "title", "body"}
    )

    issue_plan_template_request = AgentTemplateRequest(
        agent_name=AGENT_PLANNER,
        slash_command=command,
        args=[str(issue.number), adw_id, minimal_issue_json],
        adw_id=adw_id,
        working_dir=working_dir,
    )

    logger.debug(
        f"issue_plan_template_request: {issue_plan_template_request.model_dump_json(indent=2, by_alias=True)}"
    )

    issue_plan_response = execute_template(issue_plan_template_request)

    logger.debug(
        f"issue_plan_response: {issue_plan_response.model_dump_json(indent=2, by_alias=True)}"
    )

    return issue_plan_response


def implement_plan(
    plan_file: str,
    adw_id: str,
    logger: logging.Logger,
    agent_name: Optional[str] = None,
    working_dir: Optional[str] = None,
) -> AgentPromptResponse:
    """Implement the plan using the /implement command."""
    # Use provided agent_name or default to AGENT_IMPLEMENTOR
    implementor_name = agent_name or AGENT_IMPLEMENTOR

    implement_template_request = AgentTemplateRequest(
        agent_name=implementor_name,
        slash_command="/implement",
        args=[plan_file],
        adw_id=adw_id,
        working_dir=working_dir,
    )

    logger.debug(
        f"implement_template_request: {implement_template_request.model_dump_json(indent=2, by_alias=True)}"
    )

    implement_response = execute_template(implement_template_request)

    logger.debug(
        f"implement_response: {implement_response.model_dump_json(indent=2, by_alias=True)}"
    )

    return implement_response


def generate_branch_name(
    issue: GitHubIssue,
    issue_class: IssueClassSlashCommand,
    adw_id: str,
    logger: logging.Logger,
) -> Tuple[Optional[str], Optional[str]]:
    """Generate a git branch name for the issue.
    Returns (branch_name, error_message) tuple."""
    # Remove the leading slash from issue_class for the branch name
    issue_type = issue_class.replace("/", "")

    # Use minimal payload like classify_issue does
    minimal_issue_json = issue.model_dump_json(
        by_alias=True, include={"number", "title", "body"}
    )

    request = AgentTemplateRequest(
        agent_name=AGENT_BRANCH_GENERATOR,
        slash_command="/generate_branch_name",
        args=[issue_type, adw_id, minimal_issue_json],
        adw_id=adw_id,
    )

    response = execute_template(request)

    if not response.success:
        return None, response.output

    branch_name = response.output.strip()

    # Validate branch name format and use regex fallback if needed
    # Expected format: <issue_class>-issue-<number>-adw-<adw_id>-<name>
    # ADW ID format: YYYYMMDDHHMMSS-<12-char-uuid> (e.g., 20260107143052-a1b2c3d4e5f6)
    branch_name_pattern = r"((?:chore|bug|feat|feature)-issue-\d+-adw-\d{14}-[a-f0-9]{12}-[a-z0-9-]+)"

    # Check if the output matches the expected format
    if not re.match(f"^{branch_name_pattern}$", branch_name):
        # Try to extract branch name using regex
        match = re.search(branch_name_pattern, branch_name)
        if match:
            extracted_name = match.group(1)
            logger.warning(
                f"LLM produced extra output. Extracted branch name using regex: {extracted_name}"
            )
            branch_name = extracted_name
        else:
            # Both direct output and regex search failed
            return None, f"Invalid branch name format: {response.output}"

    logger.info(f"Generated branch name: {branch_name}")
    return branch_name, None


def create_commit(
    agent_name: str,
    issue: GitHubIssue,
    issue_class: IssueClassSlashCommand,
    adw_id: str,
    logger: logging.Logger,
    working_dir: str,
) -> Tuple[Optional[str], Optional[str]]:
    """Create a git commit with a properly formatted message.
    Returns (commit_message, error_message) tuple."""
    # Remove the leading slash from issue_class
    issue_type = issue_class.replace("/", "")

    # Create unique committer agent name by suffixing '_committer'
    unique_agent_name = f"{agent_name}_committer"

    # Use minimal payload like classify_issue does
    minimal_issue_json = issue.model_dump_json(
        by_alias=True, include={"number", "title", "body"}
    )

    request = AgentTemplateRequest(
        agent_name=unique_agent_name,
        slash_command="/commit",
        args=[agent_name, issue_type, minimal_issue_json],
        adw_id=adw_id,
        working_dir=working_dir,
    )

    response = execute_template(request)

    if not response.success:
        return None, response.output

    commit_message = response.output.strip()
    logger.info(f"Created commit message: {commit_message}")
    return commit_message, None


def create_pull_request(
    branch_name: str,
    issue: Optional[GitHubIssue],
    state: ADWState,
    logger: logging.Logger,
    working_dir: str,
) -> Tuple[Optional[str], Optional[str]]:
    """Create a pull request for the implemented changes.
    Returns (pr_url, error_message) tuple."""

    # Get plan file from state (may be None for test runs)
    plan_file = state.get("plan_file") or "No plan file (test run)"
    adw_id = state.get("adw_id")

    # BUG-056 fix: Validate ADW ID is present
    if not adw_id:
        return None, "ADW ID not found in state"

    # BUG-057 fix: Validate working_dir exists if provided
    if working_dir and not os.path.exists(working_dir):
        logger.warning(f"Working directory does not exist: {working_dir}")

    # Get smoke test screenshot URLs from state (if smoke tests were run)
    smoke_test_screenshot_urls = state.get("smoke_test_screenshot_urls", [])
    smoke_test_passed = state.get("smoke_test_passed", 0)
    smoke_test_failed = state.get("smoke_test_failed", 0)

    # BUG-058 fix: Handle JSON serialization errors safely
    try:
        smoke_test_data = json.dumps({
            "passed": smoke_test_passed,
            "failed": smoke_test_failed,
            "screenshot_urls": smoke_test_screenshot_urls,
        })
    except (TypeError, ValueError) as e:
        logger.warning(f"Failed to serialize smoke test data: {e}")
        smoke_test_data = json.dumps({
            "passed": smoke_test_passed,
            "failed": smoke_test_failed,
            "screenshot_urls": [],
        })

    # If we don't have issue data, try to construct minimal data
    if not issue:
        issue_data = state.get("issue", {})
        issue_json = json.dumps(issue_data) if issue_data else "{}"
    elif isinstance(issue, dict):
        # Try to reconstruct as GitHubIssue model which handles datetime serialization
        from adw_modules.data_types import GitHubIssue

        try:
            issue_model = GitHubIssue(**issue)
            # Use minimal payload like classify_issue does
            issue_json = issue_model.model_dump_json(
                by_alias=True, include={"number", "title", "body"}
            )
        except (TypeError, ValueError) as e:
            # BUG-059 fix: Log exception and use fallback
            logger.warning(f"Failed to reconstruct GitHubIssue from dict: {e}, using fallback")
            try:
                issue_json = json.dumps(issue, default=str)
            except Exception as e2:
                logger.error(f"Fallback JSON serialization also failed: {e2}")
                issue_json = json.dumps({"error": "Could not serialize issue"})
    else:
        # Use minimal payload like classify_issue does
        issue_json = issue.model_dump_json(
            by_alias=True, include={"number", "title", "body"}
        )

    request = AgentTemplateRequest(
        agent_name=AGENT_PR_CREATOR,
        slash_command="/pull_request",
        args=[branch_name, issue_json, plan_file, adw_id, smoke_test_data],
        adw_id=adw_id,
        working_dir=working_dir,
    )

    response = execute_template(request)

    if not response.success:
        return None, response.output

    pr_url = response.output.strip()
    logger.info(f"Created pull request: {pr_url}")
    return pr_url, None


def ensure_plan_exists(state: ADWState, issue_number: str) -> str:
    """Find or error if no plan exists for issue.
    Used by isolated build workflows in standalone mode."""
    # Check if plan file is in state
    if state.get("plan_file"):
        return state.get("plan_file")

    # Check current branch
    from adw_modules.git_ops import get_current_branch

    branch = get_current_branch()

    # Look for plan in branch name
    if f"-{issue_number}-" in branch:
        # Look for plan file
        plans = glob.glob(f"specs/*{issue_number}*.md")
        if plans:
            return plans[0]

    # No plan found
    raise ValueError(
        f"No plan found for issue {issue_number}. Run adw_plan_iso.py first."
    )


def _get_adw_lock_path(adw_id: str) -> str:
    """Get the lock file path for an ADW ID."""
    project_root = os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    )
    locks_dir = os.path.join(project_root, "agents", ".locks")
    os.makedirs(locks_dir, exist_ok=True)
    return os.path.join(locks_dir, f"adw_{adw_id}.lock")


def ensure_adw_id(
    issue_number: str,
    adw_id: Optional[str] = None,
    logger: Optional[logging.Logger] = None,
) -> str:
    """Get ADW ID or create a new one and initialize state.

    Uses file locking to prevent race conditions when multiple processes
    try to create state for the same ADW ID concurrently.

    Args:
        issue_number: The issue number to find/create ADW ID for
        adw_id: Optional existing ADW ID to use
        logger: Optional logger instance

    Returns:
        The ADW ID (existing or newly created)
    """
    log = logger if logger else logging.getLogger(__name__)

    # If ADW ID provided, use it with locking
    if adw_id:
        lock_path = _get_adw_lock_path(adw_id)
        lock_file = None
        try:
            lock_file = open(lock_path, "a")
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)

            # Re-check state after acquiring lock (might have been created by another process)
            state = ADWState.load(adw_id, logger)
            if state:
                log.info(f"Found existing ADW state for ID: {adw_id}")
                return adw_id

            # ADW ID provided but no state exists, create state
            state = ADWState(adw_id)
            state.update(adw_id=adw_id, issue_number=issue_number)
            state.save("ensure_adw_id")
            log.info(f"Created new ADW state for provided ID: {adw_id}")
            return adw_id
        except OSError as e:
            log.error(f"Failed to acquire lock for ADW ID {adw_id}: {e}")
            raise RuntimeError(f"Failed to acquire lock for ADW state: {e}") from e
        except (ValueError, TypeError, json.JSONDecodeError) as e:
            # BUG-084 fix: Catch state.save() serialization errors
            log.error(f"Failed to save ADW state for {adw_id}: {e}")
            raise RuntimeError(f"Failed to save ADW state: {e}") from e
        finally:
            if lock_file:
                try:
                    fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
                    lock_file.close()
                except Exception:
                    pass

    # No ADW ID provided, create new one with state
    from adw_modules.utils import make_adw_id

    new_adw_id = make_adw_id()

    lock_path = _get_adw_lock_path(new_adw_id)
    lock_file = None
    try:
        lock_file = open(lock_path, "a")
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)

        state = ADWState(new_adw_id)
        state.update(adw_id=new_adw_id, issue_number=issue_number)
        state.save("ensure_adw_id")
        log.info(f"Created new ADW ID and state: {new_adw_id}")
        return new_adw_id
    except OSError as e:
        log.error(f"Failed to acquire lock for new ADW ID {new_adw_id}: {e}")
        raise RuntimeError(f"Failed to acquire lock for ADW state: {e}") from e
    except (ValueError, TypeError, json.JSONDecodeError) as e:
        # BUG-084 fix: Catch state.save() serialization errors
        log.error(f"Failed to save ADW state for new ID {new_adw_id}: {e}")
        raise RuntimeError(f"Failed to save ADW state: {e}") from e
    finally:
        if lock_file:
            try:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
                lock_file.close()
            except Exception:
                pass


def find_existing_branch_for_issue(
    issue_number: str, adw_id: Optional[str] = None, cwd: Optional[str] = None
) -> Optional[str]:
    """Find an existing branch for the given issue number.
    Returns branch name if found, None otherwise."""
    # List all branches
    try:
        result = subprocess.run(
            ["git", "branch", "-a"], capture_output=True, text=True, cwd=cwd,
            timeout=GIT_TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        logger.warning("git branch -a timed out")
        return None

    if result.returncode != 0:
        return None

    branches = result.stdout.strip().split("\n")

    # Look for branch with standardized pattern: *-issue-{issue_number}-adw-{adw_id}-*
    for branch in branches:
        branch = branch.strip().replace("* ", "").replace("remotes/origin/", "")
        # Check for the standardized pattern
        if f"-issue-{issue_number}-" in branch:
            if adw_id and f"-adw-{adw_id}-" in branch:
                return branch
            elif not adw_id:
                # Return first match if no adw_id specified
                return branch

    return None


def find_plan_for_issue(
    issue_number: str, adw_id: Optional[str] = None
) -> Optional[str]:
    """Find plan file for the given issue number and optional adw_id.
    Returns path to plan file if found, None otherwise."""
    import os

    # Get project root
    project_root = os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    )
    agents_dir = os.path.join(project_root, "agents")

    if not os.path.exists(agents_dir):
        return None

    # If adw_id is provided, check specific directory first
    if adw_id:
        plan_path = os.path.join(agents_dir, adw_id, AGENT_PLANNER, "plan.md")
        if os.path.exists(plan_path):
            return plan_path

    # Otherwise, search all agent directories
    for agent_id in os.listdir(agents_dir):
        agent_path = os.path.join(agents_dir, agent_id)
        if os.path.isdir(agent_path):
            plan_path = os.path.join(agent_path, AGENT_PLANNER, "plan.md")
            if os.path.exists(plan_path):
                # Check if this plan is for our issue by reading branch info or checking commits
                # For now, return the first plan found (can be improved)
                return plan_path

    return None


def create_or_find_branch(
    issue_number: str,
    issue: GitHubIssue,
    state: ADWState,
    logger: logging.Logger,
    cwd: Optional[str] = None,
) -> Tuple[str, Optional[str]]:
    """Create or find a branch for the given issue.

    1. First checks state for existing branch name
    2. Then looks for existing branches matching the issue
    3. If none found, classifies the issue and creates a new branch

    Returns (branch_name, error_message) tuple.
    """
    # 1. Check state for branch name
    branch_name = state.get("branch_name") or state.get("branch", {}).get("name")
    if branch_name:
        logger.info(f"Found branch in state: {branch_name}")
        # Check if we need to checkout
        from adw_modules.git_ops import get_current_branch

        current = get_current_branch(cwd=cwd)
        if current != branch_name:
            try:
                result = subprocess.run(
                    ["git", "checkout", branch_name],
                    capture_output=True,
                    text=True,
                    cwd=cwd,
                    timeout=GIT_TIMEOUT,
                )
            except subprocess.TimeoutExpired:
                return "", "git checkout timed out"
            if result.returncode != 0:
                # Branch might not exist locally, try to create from remote
                try:
                    result = subprocess.run(
                        ["git", "checkout", "-b", branch_name, f"origin/{branch_name}"],
                        capture_output=True,
                        text=True,
                        cwd=cwd,
                        timeout=GIT_TIMEOUT,
                    )
                except subprocess.TimeoutExpired:
                    return "", "git checkout -b from remote timed out"
                if result.returncode != 0:
                    return "", f"Failed to checkout branch: {result.stderr}"
        return branch_name, None

    # 2. Look for existing branch
    adw_id = state.get("adw_id")
    existing_branch = find_existing_branch_for_issue(issue_number, adw_id, cwd=cwd)
    if existing_branch:
        logger.info(f"Found existing branch: {existing_branch}")
        # Checkout the branch
        try:
            result = subprocess.run(
                ["git", "checkout", existing_branch],
                capture_output=True,
                text=True,
                cwd=cwd,
                timeout=GIT_TIMEOUT,
            )
        except subprocess.TimeoutExpired:
            return "", "git checkout timed out"
        if result.returncode != 0:
            return "", f"Failed to checkout branch: {result.stderr}"
        state.update(branch_name=existing_branch)
        state.save("create_or_find_branch")
        return existing_branch, None

    # 3. Create new branch - classify issue first
    logger.info("No existing branch found, creating new one")

    # Classify the issue
    issue_command, error = classify_issue(issue, adw_id, logger)
    if error:
        return "", f"Failed to classify issue: {error}"

    state.update(issue_class=issue_command)
    state.save("create_or_find_branch")

    # Generate branch name
    branch_name, error = generate_branch_name(issue, issue_command, adw_id, logger)
    if error:
        return "", f"Failed to generate branch name: {error}"

    # Create the branch
    from adw_modules.git_ops import create_branch

    success, error = create_branch(branch_name, cwd=cwd)
    if not success:
        return "", f"Failed to create branch: {error}"

    state.update(branch_name=branch_name)
    state.save("create_or_find_branch")
    logger.info(f"Created and checked out new branch: {branch_name}")

    return branch_name, None


def find_spec_file(state: ADWState, logger: logging.Logger) -> Optional[str]:
    """Find the spec file from state or by examining git diff.

    For isolated workflows, automatically uses worktree_path from state.
    """
    # Get worktree path if in isolated workflow
    worktree_path = state.get("worktree_path")

    # Check if spec file is already in state (from plan phase)
    spec_file = state.get("plan_file")
    if spec_file:
        # If worktree_path exists and spec_file is relative, make it absolute
        if worktree_path and not os.path.isabs(spec_file):
            spec_file = os.path.join(worktree_path, spec_file)

        if os.path.exists(spec_file):
            logger.info(f"Using spec file from state: {spec_file}")
            return spec_file

    # Otherwise, try to find it from git diff
    logger.info("Looking for spec file in git diff")
    try:
        result = subprocess.run(
            ["git", "diff", "origin/main", "--name-only"],
            capture_output=True,
            text=True,
            cwd=worktree_path,
            timeout=GIT_TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        logger.warning("git diff timed out while looking for spec file")
        result = None

    if result and result.returncode == 0:
        files = result.stdout.strip().split("\n")
        spec_files = [f for f in files if f.startswith("specs/") and f.endswith(".md")]

        if spec_files:
            # Use the first spec file found
            spec_file = spec_files[0]
            if worktree_path:
                spec_file = os.path.join(worktree_path, spec_file)
            logger.info(f"Found spec file: {spec_file}")
            return spec_file

    # If still not found, try to derive from branch name
    branch_name = state.get("branch_name")
    if branch_name:
        # Extract issue number from branch name
        import re

        match = re.search(r"issue-(\d+)", branch_name)
        if match:
            issue_num = match.group(1)
            adw_id = state.get("adw_id")

            # Look for spec files matching the pattern
            import glob

            # Use worktree_path if provided, otherwise current directory
            search_dir = worktree_path if worktree_path else os.getcwd()
            pattern = os.path.join(
                search_dir, f"specs/issue-{issue_num}-adw-{adw_id}*.md"
            )
            spec_files = glob.glob(pattern)

            if spec_files:
                spec_file = spec_files[0]
                logger.info(f"Found spec file by pattern: {spec_file}")
                return spec_file

    logger.warning("No spec file found")
    return None


def create_and_implement_patch(
    adw_id: str,
    review_change_request: str,
    logger: logging.Logger,
    agent_name_planner: str,
    agent_name_implementor: str,
    spec_path: Optional[str] = None,
    issue_screenshots: Optional[str] = None,
    working_dir: Optional[str] = None,
) -> Tuple[Optional[str], AgentPromptResponse]:
    """Create a patch plan and implement it.
    Returns (patch_file_path, implement_response) tuple."""

    # BUG-060 fix: Validate ADW ID is present
    if not adw_id:
        return None, AgentPromptResponse(
            output="ADW ID is required for patch creation",
            success=False,
            session_id=None,
            retry_code=RetryCode.NONE,
        )

    # BUG-061 fix: Validate working_dir exists if provided - FAIL if missing
    if working_dir and not os.path.exists(working_dir):
        error_msg = f"Working directory does not exist: {working_dir}"
        logger.error(error_msg)
        return None, AgentPromptResponse(
            output=error_msg,
            success=False,
            session_id=None,
            retry_code=RetryCode.NONE,
        )

    # Create patch plan using /patch command
    # BUG-062 fix: Remove agent_name_planner from args to avoid double parameter
    # The agent_name is already specified in AgentTemplateRequest
    args = [adw_id, review_change_request]

    # Add optional arguments in the correct order
    if spec_path:
        args.append(spec_path)
    else:
        args.append("")  # Empty string for optional spec_path

    if issue_screenshots:
        args.append(issue_screenshots)

    request = AgentTemplateRequest(
        agent_name=agent_name_planner,
        slash_command="/patch",
        args=args,
        adw_id=adw_id,
        working_dir=working_dir,
    )

    logger.debug(
        f"Patch plan request: {request.model_dump_json(indent=2, by_alias=True)}"
    )

    response = execute_template(request)

    logger.debug(
        f"Patch plan response: {response.model_dump_json(indent=2, by_alias=True)}"
    )

    if not response.success:
        logger.error(f"Error creating patch plan: {response.output}")
        # Return None and the original failed response to preserve session_id and retry_code
        return None, response

    # Extract the patch plan file path from the response
    patch_file_path = response.output.strip()

    # BUG-065 fix: Validate output is not empty
    if not patch_file_path:
        logger.error("Patch plan response output is empty")
        return None, AgentPromptResponse(
            output="Patch plan response output is empty",
            success=False,
            session_id=response.session_id,  # Preserve session_id from original response
            retry_code=RetryCode.NONE,
        )

    # BUG-063 fix: Use proper path validation instead of fragile string matching
    # Make patch path absolute if needed
    if not os.path.isabs(patch_file_path) and working_dir:
        patch_file_path = os.path.join(working_dir, patch_file_path)

    # BUG-064/BUG-089 fix: Validate path to prevent path traversal
    # When working_dir is provided, validate path is within it
    # When working_dir is None, validate path is within project directory
    if working_dir:
        resolved_path = os.path.realpath(patch_file_path)
        resolved_working_dir = os.path.realpath(working_dir)
        if not resolved_path.startswith(resolved_working_dir + os.sep) and resolved_path != resolved_working_dir:
            logger.error(f"Path traversal detected: {patch_file_path} is outside {working_dir}")
            return None, AgentPromptResponse(
                output=f"Path traversal detected: path is outside working directory",
                success=False,
                session_id=response.session_id,
                retry_code=RetryCode.NONE,
            )
    else:
        # BUG-089 fix: When no working_dir, validate path is within project root
        project_root = os.path.dirname(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        )
        resolved_path = os.path.realpath(patch_file_path)
        resolved_project_root = os.path.realpath(project_root)
        if not resolved_path.startswith(resolved_project_root + os.sep) and resolved_path != resolved_project_root:
            logger.error(f"Path traversal detected: {patch_file_path} is outside project root")
            return None, AgentPromptResponse(
                output=f"Path traversal detected: path is outside project root",
                success=False,
                session_id=response.session_id,
                retry_code=RetryCode.NONE,
            )

    # Validate the file exists and has correct extension
    if not patch_file_path.endswith(".md"):
        logger.error(f"Invalid patch plan path (wrong extension): {patch_file_path}")
        return None, AgentPromptResponse(
            output=f"Invalid patch plan path (expected .md file): {patch_file_path}",
            success=False,
            session_id=response.session_id,
            retry_code=RetryCode.NONE,
        )

    if not os.path.exists(patch_file_path):
        logger.error(f"Patch file does not exist: {patch_file_path}")
        return None, AgentPromptResponse(
            output=f"Patch file not found: {patch_file_path}",
            success=False,
            session_id=response.session_id,
            retry_code=RetryCode.NONE,
        )

    logger.info(f"Created patch plan: {patch_file_path}")

    # Now implement the patch plan using the provided implementor agent name
    implement_response = implement_plan(
        patch_file_path, adw_id, logger, agent_name_implementor, working_dir=working_dir
    )

    return patch_file_path, implement_response


def get_workflow_from_state(adw_id: str) -> Optional[str]:
    """Get the last workflow type from an ADW state file.

    Args:
        adw_id: The ADW ID to look up

    Returns:
        Workflow type (e.g., "adw_multi_phase_sdlc_iso") or None if not found
    """
    state = ADWState.load(adw_id)
    if not state:
        return None

    # Get the last workflow from all_adws list
    all_adws = state.get("all_adws", [])
    if all_adws:
        return all_adws[-1]

    return None


def find_latest_adw_for_issue(issue_number: str) -> Tuple[Optional[str], Optional[str]]:
    """Find the most recent ADW ID and workflow type for a given issue.

    Scans the agents/ directory for state files matching the issue number,
    sorted by timestamp (most recent first).

    Args:
        issue_number: The GitHub issue number to find ADW for

    Returns:
        Tuple of (adw_id, workflow_type) or (None, None) if not found
    """
    # Get project root and agents directory
    project_root = os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    )
    agents_dir = os.path.join(project_root, "agents")

    if not os.path.exists(agents_dir):
        return None, None

    # Collect all ADW IDs with matching issue numbers
    matching_adws = []

    for adw_id in os.listdir(agents_dir):
        agent_path = os.path.join(agents_dir, adw_id)
        if not os.path.isdir(agent_path):
            continue

        state_file = os.path.join(agent_path, "adw_state.json")
        lock_file_path = state_file + ".lock"
        if not os.path.exists(state_file):
            continue

        # BUG-085 fix: Use try-finally pattern outside the with block
        # to ensure lock is always released even if exception occurs
        lock_file = None
        try:
            lock_file = open(lock_file_path, "a")
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_SH)  # Shared lock for reading

            with open(state_file, "r") as f:
                state_data = json.load(f)

            # Check if this state matches our issue number
            if str(state_data.get("issue_number")) == str(issue_number):
                matching_adws.append((adw_id, state_data))

        except json.JSONDecodeError as e:
            # BUG-090 fix: Log corrupted state files for debugging
            logger.debug(f"Skipping corrupted state file {state_file}: {e}")
            continue
        except (IOError, OSError) as e:
            # BUG-090 fix: Log I/O errors for debugging
            logger.debug(f"Failed to read state file {state_file}: {e}")
            continue
        finally:
            # BUG-085 fix: Always release lock in finally block
            if lock_file:
                try:
                    fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
                    lock_file.close()
                except Exception:
                    pass

    if not matching_adws:
        return None, None

    # Sort by ADW ID timestamp (first 14 chars: YYYYMMDDHHMMSS) - most recent first
    matching_adws.sort(key=lambda x: x[0], reverse=True)

    # Get the most recent ADW
    adw_id, state_data = matching_adws[0]

    # Get the last workflow type from all_adws
    all_adws = state_data.get("all_adws", [])
    workflow = all_adws[-1] if all_adws else None

    return adw_id, workflow


# Context validation patterns for automated compliance checking
CONTEXT_VALIDATION_PATTERNS = {
    "multitenancy": {
        "file_patterns": ["app/backend/src/crud/"],
        "check_pattern": r"organization_id",
        "violation_pattern": r"\.filter\([^)]*\)(?!.*organization_id)",
        "description": "CRUD operations must filter by organization_id",
        "severity": "blocker",
        "context_file": "ai_docs/backend/context/multitenancy.md",
    },
    "i18n": {
        "file_patterns": ["app/frontend/src/"],
        "file_extensions": [".tsx", ".jsx"],
        "check_pattern": r'(?:^|[^a-zA-Z])t\s*\(',
        "violation_pattern": r'>[^<]*[A-Z][a-z]+[^<]*<',  # Hardcoded text in JSX
        "description": "Frontend strings must use t() for i18n",
        "severity": "blocker",
        "context_file": "ai_docs/frontend/context/i18n.md",
    },
    "soft_delete": {
        "file_patterns": ["app/backend/src/crud/", "app/backend/src/api/"],
        "check_pattern": r"deleted_time",
        "violation_pattern": r"\.delete\s*\(",
        "description": "Use soft deletes (deleted_time) instead of hard deletes",
        "severity": "blocker",
        "context_file": "ai_docs/backend/context/crud.md",
    },
    "async_io": {
        "file_patterns": ["app/backend/src/"],
        "file_extensions": [".py"],
        "check_pattern": r"async\s+def",
        "violation_pattern": r"(?<!async\s)def\s+\w+.*session.*:",
        "description": "Database operations must be async",
        "severity": "tech_debt",
        "context_file": "ai_docs/backend/context/crud.md",
    },
}


def validate_context_compliance(
    changed_files: list,
    worktree_path: str,
    logger: logging.Logger,
) -> list:
    """Check if implementation follows documented patterns based on changed files.

    Analyzes the changed files against known patterns from conditional_context.md
    to identify potential violations that should have been caught by reading context.

    Args:
        changed_files: List of file paths that were changed
        worktree_path: Root path of the worktree
        logger: Logger instance

    Returns:
        List of violation dicts with keys: pattern_name, file, description, severity, context_file
    """
    violations = []

    for pattern_name, pattern_config in CONTEXT_VALIDATION_PATTERNS.items():
        file_patterns = pattern_config["file_patterns"]
        file_extensions = pattern_config.get("file_extensions", [])
        violation_regex = pattern_config.get("violation_pattern")

        # Find changed files that match this pattern's scope
        matching_files = []
        for changed_file in changed_files:
            # Check if file matches any of the path patterns
            matches_path = any(p in changed_file for p in file_patterns)
            if not matches_path:
                continue

            # Check extension if specified
            if file_extensions:
                matches_ext = any(changed_file.endswith(ext) for ext in file_extensions)
                if not matches_ext:
                    continue

            matching_files.append(changed_file)

        if not matching_files:
            continue

        logger.debug(f"Checking {pattern_name} pattern against {len(matching_files)} files")

        # Check each matching file for violations
        for file_path in matching_files:
            full_path = os.path.join(worktree_path, file_path)
            if not os.path.exists(full_path):
                continue

            try:
                with open(full_path, "r") as f:
                    content = f.read()

                # For i18n pattern, skip files that already use useTranslation
                # This avoids false positives from JS expressions like {Math.round()}
                if pattern_name == "i18n":
                    if "useTranslation" in content and re.search(r'\bt\s*\(', content):
                        logger.debug(f"Skipping i18n check for {file_path} - already uses useTranslation")
                        continue

                # Look for violations using regex
                if violation_regex:
                    violation_matches = re.findall(violation_regex, content, re.MULTILINE)
                    if violation_matches:
                        violations.append({
                            "pattern_name": pattern_name,
                            "file": file_path,
                            "description": pattern_config["description"],
                            "severity": pattern_config["severity"],
                            "context_file": pattern_config["context_file"],
                            "matches": len(violation_matches),
                        })
                        logger.warning(
                            f"Pattern violation [{pattern_name}] in {file_path}: "
                            f"{pattern_config['description']}"
                        )
            except Exception as e:
                logger.debug(f"Error checking {file_path}: {e}")
                continue

    return violations


def get_changed_files(worktree_path: str, logger: logging.Logger) -> list:
    """Get list of changed files compared to origin/main.

    Args:
        worktree_path: Path to the worktree
        logger: Logger instance

    Returns:
        List of changed file paths relative to worktree root
    """
    try:
        result = subprocess.run(
            ["git", "diff", "origin/main", "--name-only"],
            capture_output=True,
            text=True,
            cwd=worktree_path,
            timeout=GIT_TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        logger.warning("git diff timed out while getting changed files")
        return []

    if result.returncode != 0:
        logger.warning(f"Failed to get changed files: {result.stderr}")
        return []

    files = [f.strip() for f in result.stdout.strip().split("\n") if f.strip()]
    logger.debug(f"Found {len(files)} changed files")
    return files


def run_context_validation(
    worktree_path: str,
    logger: logging.Logger,
) -> tuple:
    """Run full context validation on a worktree.

    Combines getting changed files and validating them against patterns.

    Args:
        worktree_path: Path to the worktree
        logger: Logger instance

    Returns:
        Tuple of (violations_list, changed_files_count)
    """
    changed_files = get_changed_files(worktree_path, logger)
    if not changed_files:
        logger.info("No changed files to validate")
        return [], 0

    violations = validate_context_compliance(changed_files, worktree_path, logger)
    logger.info(f"Context validation found {len(violations)} potential violation(s)")

    return violations, len(changed_files)


# Agent name for context violation resolution
AGENT_CONTEXT_RESOLVER = "context_resolver"


def resolve_context_violations(
    violations: list,
    adw_id: str,
    logger: logging.Logger,
    worktree_path: str,
) -> AgentPromptResponse:
    """Resolve context pattern violations by creating and implementing a patch.

    Creates a focused patch plan with all violations and their context references,
    then calls the implementing agent to fix them.

    Args:
        violations: List of violation dicts from validate_context_compliance
        adw_id: ADW workflow ID
        logger: Logger instance
        worktree_path: Path to the worktree

    Returns:
        AgentPromptResponse indicating success/failure of the resolution
    """
    if not violations:
        return AgentPromptResponse(success=True, output="No violations to resolve")

    logger.info(f"Resolving {len(violations)} context violations")

    # Build a comprehensive patch description with all violations
    violation_descriptions = []
    context_files_to_read = set()

    for v in violations:
        violation_descriptions.append(
            f"- **{v['pattern_name']}** in `{v['file']}`: {v['description']}"
        )
        context_files_to_read.add(v["context_file"])

    # Create patch args with clear instructions
    patch_args = [
        "Fix context pattern violations identified by automated validation.",
        "Violations to fix:\n" + "\n".join(violation_descriptions),
        "Context files to reference:\n" + "\n".join(f"- {cf}" for cf in sorted(context_files_to_read)),
        "Instructions: Read each context file for the correct patterns, then fix each violation in the specified files.",
    ]

    # Create patch plan
    request = AgentTemplateRequest(
        agent_name=AGENT_CONTEXT_RESOLVER,
        slash_command="/patch",
        args=patch_args,
        adw_id=adw_id,
        working_dir=worktree_path,
    )

    logger.debug(f"Creating context violation patch plan: {request.model_dump_json(indent=2, by_alias=True)}")
    plan_response = execute_template(request)

    if not plan_response.success:
        logger.error(f"Failed to create context violation patch plan: {plan_response.output}")
        return plan_response

    # Extract plan file path from response
    plan_file = plan_response.output.strip()
    logger.info(f"Created context violation patch plan: {plan_file}")

    # Implement the patch
    impl_response = implement_plan(
        plan_file=plan_file,
        adw_id=adw_id,
        logger=logger,
        agent_name=AGENT_CONTEXT_RESOLVER,
        working_dir=worktree_path,
    )

    if not impl_response.success:
        logger.error(f"Failed to implement context violation fixes: {impl_response.output}")
    else:
        logger.info("Successfully implemented context violation fixes")

    return impl_response
