"""Claude Code agent module for executing prompts programmatically."""

import subprocess
import signal
import sys
import os
import json
import re
import logging
import time
from typing import Optional, List, Dict, Any, Tuple, Final
from dotenv import load_dotenv
from .data_types import (
    AgentPromptRequest,
    AgentPromptResponse,
    AgentTemplateRequest,
    ClaudeCodeResultMessage,
    SlashCommand,
    ModelSet,
    RetryCode,
)

# Load environment variables
load_dotenv()

# Get Claude Code CLI path from environment
CLAUDE_PATH = os.getenv("CLAUDE_CODE_PATH", "claude")

# Usage limit / server error detection patterns
_USAGE_LIMIT_PATTERNS = [
    "hit your limit",
    "you've hit your limit",
    "extra-usage",
    "usage limit",
]

_SERVER_ERROR_PATTERNS = [
    "internal server error",
    "500 internal",
    "overloaded_error",
    "overloaded error",
    "529",  # Overloaded status code
    "api error: 500",
    "anthropic api error",
    "server_error",
]

# Max times to sleep-retry for usage limit / server errors before giving up
_MAX_WAIT_RETRIES = 12  # 12 x 15 min = 3 hours max wait
_WAIT_INTERVAL_SECONDS = 15 * 60  # 15 minutes


def _classify_transient_error(text: str) -> Optional[RetryCode]:
    """Check if error text indicates a usage limit or server error.

    Returns RetryCode.USAGE_LIMIT, RetryCode.SERVER_ERROR, or None.
    """
    text_lower = text.lower()
    for pattern in _USAGE_LIMIT_PATTERNS:
        if pattern in text_lower:
            return RetryCode.USAGE_LIMIT
    for pattern in _SERVER_ERROR_PATTERNS:
        if pattern in text_lower:
            return RetryCode.SERVER_ERROR
    return None


# Explicit model IDs for the "opus" alias, pinned per tier.
# Keeping "opus" in the map below means "use this tier's opus version".
OPUS_4_6: Final[str] = "claude-opus-4-6"
OPUS_4_7: Final[str] = "claude-opus-4-7"

_OPUS_BY_MODEL_SET: Final[Dict[ModelSet, str]] = {
    "base": OPUS_4_6,
    "heavy": OPUS_4_6,
    "superheavy": OPUS_4_7,
}

# Model selection mapping for slash commands.
# Each command maps to {model_set: alias}. Aliases:
#   - "sonnet": passed through as the CLI alias (resolves to latest sonnet)
#   - "opus": pinned to a specific version via _OPUS_BY_MODEL_SET at resolution time
# Entries only need "base" and "heavy"; "superheavy" falls back to "heavy" and only
# changes which opus version is used (4.7 instead of 4.6).
SLASH_COMMAND_MODEL_MAP: Final[Dict[SlashCommand, Dict[ModelSet, str]]] = {
    "/classify_issue": {"base": "sonnet", "heavy": "opus"},
    "/classify_adw": {"base": "sonnet", "heavy": "sonnet"},
    "/classify_sdlc_complexity": {"base": "sonnet", "heavy": "sonnet"},
    "/generate_branch_name": {"base": "sonnet", "heavy": "sonnet"},
    "/implement": {"base": "opus", "heavy": "opus"},
    "/test": {"base": "opus", "heavy": "sonnet"},
    "/write_tests": {"base": "opus", "heavy": "opus"},
    "/resolve_failed_test": {"base": "sonnet", "heavy": "opus"},
    "/test_e2e": {"base": "opus", "heavy": "opus"},
    "/resolve_failed_e2e_test": {"base": "opus", "heavy": "opus"},
    "/smoke_test": {"base": "opus", "heavy": "opus"},
    "/review": {"base": OPUS_4_7, "heavy": OPUS_4_7},
    "/document": {"base": "opus", "heavy": "opus"},
    "/commit": {"base": "sonnet", "heavy": "sonnet"},
    "/pull_request": {"base": "sonnet", "heavy": "sonnet"},
    "/chore": {"base": "opus", "heavy": "opus"},
    "/bug": {"base": "opus", "heavy": "opus"},
    "/feature": {"base": "opus", "heavy": "opus"},
    "/patch": {"base": "opus", "heavy": "opus"},
    "/install_worktree": {"base": "sonnet", "heavy": "sonnet"},
    # "/track_agentic_kpis": {"base": "sonnet", "heavy": "sonnet"},  # Disabled - causes merge conflicts
    # Multi-phase workflow commands - planning always uses opus for thoroughness
    "/plan_multi_phase": {"base": "opus", "heavy": "opus"},
    "/implement_phase": {"base": "opus", "heavy": "opus"},
    "/review_phase": {"base": OPUS_4_7, "heavy": OPUS_4_7},
    # Context management commands
    "/refine_context": {"base": "opus", "heavy": "opus"},
    # Implementation consistency commands
    "/review_consistency": {"base": "opus", "heavy": "opus"},
    # Greenfield orchestration commands - decomposition and verification use opus for thorough analysis
    "/decompose_specs": {"base": "opus", "heavy": "opus"},
    "/verify_greenfield": {"base": "opus", "heavy": "opus"},
    "/rescue_verification": {"base": "opus", "heavy": "opus"},
    "/write_greenfield_e2e": {"base": "opus", "heavy": "opus"},
    # Design handoff commands - opus for analytical rewriting and visual judgment
    "/assimilate_design": {"base": "opus", "heavy": "opus"},
    "/validate_design_match": {"base": "opus", "heavy": "opus"},
    # Generic E2E generation commands
    "/discover_e2e_targets": {"base": "opus", "heavy": "opus"},
    "/write_e2e_test": {"base": "opus", "heavy": "opus"},
    # Rescue workflow commands - Discovery (mostly Sonnet, Opus for synthesis)
    "/rescue_scan_structure": {"base": "opus", "heavy": "sonnet"},
    "/rescue_map_features": {"base": "opus", "heavy": "sonnet"},
    "/rescue_extract_schema": {"base": "opus", "heavy": "sonnet"},
    "/rescue_catalog_ui": {"base": "opus", "heavy": "opus"},
    "/rescue_document_discovery": {"base": "opus", "heavy": "opus"},
    # Rescue workflow commands - Triage (Opus for planning decisions)
    "/rescue_score_components": {"base": "opus", "heavy": "sonnet"},
    "/rescue_classify_backend": {"base": "opus", "heavy": "opus"},
    "/rescue_plan_ui": {"base": "opus", "heavy": "opus"},
    "/rescue_generate_tasks": {"base": "opus", "heavy": "opus"},
    "/rescue_evaluate_feasibility": {"base": "opus", "heavy": "opus"},
    # Rescue workflow commands - Execution (Sonnet for implementation, Opus for complex)
    "/rescue_execute_model": {"base": "opus", "heavy": "opus"},
    "/rescue_execute_crud": {"base": "opus", "heavy": "opus"},
    "/rescue_execute_api": {"base": "opus", "heavy": "opus"},
    "/rescue_execute_component": {"base": "opus", "heavy": "opus"},
    "/rescue_execute_wire": {"base": "opus", "heavy": "opus"},
    "/rescue_execute_test": {"base": "opus", "heavy": "opus"},
    "/rescue_replan": {"base": "opus", "heavy": "opus"},
    # Rescue workflow commands - Validation (Opus for judgment)
    "/rescue_validate_tests": {"base": "opus", "heavy": "opus"},
    "/rescue_validate_visual": {"base": "opus", "heavy": "opus"},
    "/rescue_validate_features": {"base": "opus", "heavy": "opus"},
    # Rescue workflow commands - Control
    "/rescue_status": {"base": "sonnet", "heavy": "sonnet"},
    "/rescue_skip_task": {"base": "sonnet", "heavy": "sonnet"},
    "/rescue_checkpoint": {"base": "opus", "heavy": "opus"},
}

# Commands that should skip context preamble (utility/classification commands)
SKIP_CONTEXT_PREAMBLE_COMMANDS: Final[set] = {
    "/classify_issue",
    "/classify_adw",
    "/classify_sdlc_complexity",
    "/generate_branch_name",
    "/commit",
    "/pull_request",
    "/install_worktree",
    # "/track_agentic_kpis",  # Disabled - causes merge conflicts
    "/prepare_app",
    "/start",
    "/setup_test_auth",
    "/teardown_test_auth",
    "/prime",  # Prime loads its own context
    "/decompose_specs",  # Receives full spec content, no additional context needed
    # Rescue utility commands (status/control don't need full context)
    "/rescue_status",
    "/rescue_skip_task",
}

# Mandatory context preamble injected before implementation/planning commands
_CONTEXT_PREAMBLE_TEMPLATE: Final[str] = """
## Mandatory Context Loading (AUTO-INJECTED)
{working_dir_notice}
Before starting your task, you MUST:

1. **Read `CLAUDE.md`** - Project conventions, critical rules, and guidelines
2. **Read `.claude/commands/conditional_context.md`** - Use this lookup table to determine which `ai_docs/` files apply to your specific task
3. **Load applicable context** - Based on conditional_context.md, read the relevant `ai_docs/` files BEFORE writing any code

**ASSERT**: After loading context, confirm: "Context loaded from: [list files]"

---

"""


def get_context_preamble(working_dir: str | None = None) -> str:
    """Get the context preamble, optionally with explicit working directory.

    When working_dir is provided (e.g., for worktree isolation), adds a notice
    instructing the agent to use only paths within that directory.
    """
    if working_dir:
        working_dir_notice = f"""
**WORKING DIRECTORY: `{working_dir}`**
ALL file operations (Read, Write, Edit, Glob, Grep, Bash) MUST use paths within this directory.
Do NOT use paths outside this directory. Do NOT cd to other directories.
"""
    else:
        working_dir_notice = ""

    return _CONTEXT_PREAMBLE_TEMPLATE.format(working_dir_notice=working_dir_notice)


# Backward compatibility alias for code that uses the constant directly
CONTEXT_PREAMBLE: Final[str] = get_context_preamble()


def get_model_for_slash_command(
    request: AgentTemplateRequest, default: str = "sonnet"
) -> str:
    """Get the appropriate model for a template request based on ADW state and slash command.

    Resolution:
      1. Look up the alias from SLASH_COMMAND_MODEL_MAP using the active model_set.
         For "superheavy", fall back to the "heavy" entry, then "base".
      2. If the alias is "opus", translate to the explicit model ID for that tier
         (base/heavy → claude-opus-4-6, superheavy → claude-opus-4-7).
      3. Other aliases (e.g. "sonnet") are passed through unchanged.

    Returns:
        Model name to use (CLI alias like "sonnet" or explicit ID like "claude-opus-4-7").
    """
    # Import here to avoid circular imports
    from .state import ADWState

    # Load state to get model_set
    # Note: ADWState.load() uses file locking internally to prevent race conditions
    model_set: ModelSet = "base"  # Default model set
    state = ADWState.load(request.adw_id)
    if state:
        model_set = state.get("model_set", "base")
    else:
        # Log when state doesn't exist - this is expected for first command in a workflow
        logging.getLogger(__name__).debug(
            f"No ADW state found for {request.adw_id}, using default model_set 'base'"
        )

    # Get the model configuration for the command
    command_config = SLASH_COMMAND_MODEL_MAP.get(request.slash_command)

    if command_config:
        if model_set == "superheavy":
            # Most commands won't define an explicit "superheavy" entry; fall back to
            # the "heavy" config (which already escalates utility→opus where intended).
            alias = command_config.get(
                "superheavy",
                command_config.get("heavy", command_config.get("base", default)),
            )
        else:
            alias = command_config.get(model_set, command_config.get("base", default))
    else:
        alias = default

    # Pin the "opus" alias to a specific version based on tier.
    if alias == "opus":
        return _OPUS_BY_MODEL_SET.get(model_set, OPUS_4_6)
    return alias


def truncate_output(
    output: str, max_length: int = 500, suffix: str = "... (truncated)"
) -> str:
    """Truncate output to a reasonable length for display.

    Special handling for JSONL data - if the output appears to be JSONL,
    try to extract just the meaningful part.

    Args:
        output: The output string to truncate
        max_length: Maximum length before truncation (default: 500)
        suffix: Suffix to add when truncated (default: "... (truncated)")

    Returns:
        Truncated string if needed, original if shorter than max_length
    """
    # Check if this looks like JSONL data
    if output.startswith('{"type":') and '\n{"type":' in output:
        # This is likely JSONL output - try to extract the last meaningful message
        lines = output.strip().split("\n")
        for line in reversed(lines):
            try:
                data = json.loads(line)
                # Look for result message
                if data.get("type") == "result":
                    result = data.get("result", "")
                    if result:
                        return truncate_output(result, max_length, suffix)
                # Look for assistant message
                elif data.get("type") == "assistant" and data.get("message"):
                    content = data["message"].get("content", [])
                    if isinstance(content, list) and content:
                        text = content[0].get("text", "")
                        if text:
                            return truncate_output(text, max_length, suffix)
            except (json.JSONDecodeError, KeyError, TypeError, IndexError):
                pass
        # If we couldn't extract anything meaningful, just show that it's JSONL
        return f"[JSONL output with {len(lines)} messages]{suffix}"

    # Regular truncation logic
    if len(output) <= max_length:
        return output

    # Try to find a good break point (newline or space)
    truncate_at = max_length - len(suffix)

    # Look for newline near the truncation point
    newline_pos = output.rfind("\n", truncate_at - 50, truncate_at)
    if newline_pos > 0:
        return output[:newline_pos] + suffix

    # Look for space near the truncation point
    space_pos = output.rfind(" ", truncate_at - 20, truncate_at)
    if space_pos > 0:
        return output[:space_pos] + suffix

    # Just truncate at the limit
    return output[:truncate_at] + suffix


def check_claude_installed() -> Optional[str]:
    """Check if Claude Code CLI is installed. Return error message if not."""
    try:
        result = subprocess.run(
            [CLAUDE_PATH, "--version"], capture_output=True, text=True
        )
        if result.returncode != 0:
            return (
                f"Error: Claude Code CLI is not installed. Expected at: {CLAUDE_PATH}"
            )
    except FileNotFoundError:
        return f"Error: Claude Code CLI is not installed. Expected at: {CLAUDE_PATH}"
    return None


def parse_jsonl_output(
    output_file: str,
) -> Tuple[List[Dict[str, Any]], Optional[Dict[str, Any]]]:
    """Parse JSONL output file and return all messages and the result message.

    Returns:
        Tuple of (all_messages, result_message) where result_message is None if not found.
        Logs warnings for parse errors instead of silently swallowing them.
    """
    logger = logging.getLogger(__name__)
    try:
        with open(output_file, "r") as f:
            messages = []
            for line_num, line in enumerate(f, 1):
                if not line.strip():
                    continue
                try:
                    messages.append(json.loads(line))
                except json.JSONDecodeError as e:
                    logger.warning(f"Failed to parse line {line_num} in {output_file}: {e}")
                    # Continue parsing remaining lines

            # Find the result message (should be the last one)
            result_message = None
            for message in reversed(messages):
                if message.get("type") == "result":
                    result_message = message
                    break

            return messages, result_message
    except FileNotFoundError:
        logger.warning(f"Output file not found: {output_file}")
        return [], None
    except IOError as e:
        logger.warning(f"Failed to read output file {output_file}: {e}")
        return [], None
    except Exception as e:
        logger.warning(f"Unexpected error parsing {output_file}: {e}")
        return [], None


def record_rate_limits(messages: List[Dict[str, Any]]) -> None:
    """The latest rate_limit_event of a finished claude run goes to the machine-wide ~/.adw/usage.json (Ore's
    machine view). Best effort."""
    for message in reversed(messages):
        if message.get("type") == "rate_limit_event" and isinstance(message.get("rate_limit_info"), dict):
            try:
                from . import resources
                resources.record_rate_limit(message["rate_limit_info"])
            except Exception:  # noqa: BLE001
                pass
            return


def convert_jsonl_to_json(jsonl_file: str) -> str:
    """Convert JSONL file to JSON array file.

    Creates a .json file with the same name as the .jsonl file,
    containing all messages as a JSON array.

    Returns:
        Path to the created JSON file
    """
    # Create JSON filename by replacing .jsonl with .json
    json_file = jsonl_file.replace(".jsonl", ".json")

    # Parse the JSONL file
    messages, _ = parse_jsonl_output(jsonl_file)

    # Write as JSON array
    with open(json_file, "w") as f:
        json.dump(messages, f, indent=2)

    return json_file


def get_claude_env() -> Dict[str, str]:
    """Get only the required environment variables for Claude Code execution.

    This is a wrapper around get_safe_subprocess_env() from utils.py for
    backward compatibility. New code should use get_safe_subprocess_env() directly.

    Returns a dictionary containing only the necessary environment variables
    based on .env.sample configuration.
    """
    # Import here to avoid circular imports
    from .utils import get_safe_subprocess_env

    # Use the shared function
    return get_safe_subprocess_env()


def save_prompt(prompt: str, adw_id: str, agent_name: str = "ops") -> None:
    """Save a prompt to the appropriate logging directory."""
    # Extract slash command from prompt
    match = re.match(r"^(/\w+)", prompt)
    if not match:
        return

    slash_command = match.group(1)
    # Remove leading slash for filename
    command_name = slash_command[1:]

    # Path traversal protection: validate adw_id and agent_name don't contain dangerous characters
    # Only allow alphanumeric, dash, underscore for adw_id and agent_name
    if not re.match(r'^[\w-]+$', adw_id):
        logging.getLogger(__name__).warning(f"Invalid adw_id format (potential path traversal): {adw_id}")
        return
    if not re.match(r'^[\w-]+$', agent_name):
        logging.getLogger(__name__).warning(f"Invalid agent_name format (potential path traversal): {agent_name}")
        return

    # Create directory structure at project root (parent of adws)
    # __file__ is in adws/adw_modules/, so we need to go up 3 levels to get to project root
    project_root = os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    )
    prompt_dir = os.path.join(project_root, "agents", adw_id, agent_name, "prompts")

    # Additional safety: ensure the final path is within the expected directory
    agents_dir = os.path.join(project_root, "agents")
    real_prompt_dir = os.path.realpath(prompt_dir)
    real_agents_dir = os.path.realpath(agents_dir)
    if not real_prompt_dir.startswith(real_agents_dir + os.sep):
        logging.getLogger(__name__).warning(f"Path traversal attempt detected: {prompt_dir}")
        return

    os.makedirs(prompt_dir, exist_ok=True)

    # Save prompt to file
    prompt_file = os.path.join(prompt_dir, f"{command_name}.txt")
    with open(prompt_file, "w") as f:
        f.write(prompt)


def prompt_claude_code_with_retry(
    request: AgentPromptRequest,
    max_retries: int = 3,
    retry_delays: List[int] = None,
    max_total_timeout: int = 3600,  # 1 hour cumulative timeout
) -> AgentPromptResponse:
    """Execute Claude Code with retry logic for certain error types.

    Args:
        request: The prompt request configuration
        max_retries: Maximum number of retry attempts (default: 3)
        retry_delays: List of delays in seconds between retries (default: [1, 3, 5])
        max_total_timeout: Maximum total time across all retries in seconds (default: 3600)

    Returns:
        AgentPromptResponse with output and retry code

    BUG-081 fix: Dynamic subprocess timeout based on remaining cumulative time.
    """
    if retry_delays is None:
        retry_delays = [1, 3, 5]

    # Ensure we have enough delays for max_retries
    while len(retry_delays) < max_retries:
        retry_delays.append(retry_delays[-1] + 2)  # Add incrementing delays

    last_response = None
    start_time = time.time()

    for attempt in range(max_retries + 1):  # +1 for initial attempt
        # Check cumulative timeout before each attempt
        elapsed = time.time() - start_time
        remaining_time = max_total_timeout - elapsed

        if remaining_time <= 60:  # Less than 1 minute remaining
            logging.getLogger(__name__).warning(
                f"Cumulative timeout reached ({elapsed:.0f}s >= {max_total_timeout}s) after {attempt} attempts"
            )
            if last_response:
                return last_response
            return AgentPromptResponse(
                output=f"Error: Cumulative timeout reached after {elapsed:.0f}s",
                success=False,
                session_id=None,
                retry_code=RetryCode.TIMEOUT_ERROR,
            )

        if attempt > 0:
            # This is a retry
            delay = retry_delays[attempt - 1]
            # BUG-081 fix: Don't sleep if it would exceed remaining time
            if delay >= remaining_time - 60:
                logging.getLogger(__name__).warning(
                    f"Skipping retry delay ({delay}s) as it exceeds remaining time ({remaining_time:.0f}s)"
                )
            else:
                time.sleep(delay)

        # BUG-083 fix: Recalculate remaining time AFTER any delay to avoid stale value
        elapsed_after_delay = time.time() - start_time
        remaining_time_now = max_total_timeout - elapsed_after_delay

        # BUG-086 fix: Ensure timeout is positive (minimum 60 seconds)
        subprocess_timeout = max(60, min(1800, int(remaining_time_now - 30)))

        # BUG-081 fix: Pass remaining time to prompt_claude_code for dynamic timeout
        response = prompt_claude_code(request, subprocess_timeout=subprocess_timeout)
        last_response = response

        # Check if we should retry based on the retry code
        if response.success or response.retry_code == RetryCode.NONE:
            # Success or non-retryable error
            return response

        # Check if this is a retryable error
        # Note: USAGE_LIMIT and SERVER_ERROR are handled internally by
        # prompt_claude_code() via sleep-retry, so they won't appear here.
        if response.retry_code in [
            RetryCode.CLAUDE_CODE_ERROR,
            RetryCode.TIMEOUT_ERROR,
            RetryCode.EXECUTION_ERROR,
            RetryCode.ERROR_DURING_EXECUTION,
            RetryCode.AGENT_SOFT_ERROR,
        ]:
            if attempt < max_retries:
                logging.getLogger(__name__).info(
                    f"Retrying (attempt {attempt + 1}/{max_retries}) after {response.retry_code.value}"
                )
                continue
            else:
                return response

    # Should not reach here, but return last response just in case
    return last_response


def prompt_claude_code(
    request: AgentPromptRequest,
    subprocess_timeout: int = 1800,  # BUG-081 fix: Accept dynamic timeout
) -> AgentPromptResponse:
    """Execute Claude Code with the given prompt configuration.

    Wraps _prompt_claude_code_once() with sleep-retry logic for usage limits
    and API 500/overloaded errors. Sleeps in 15-minute increments and retries
    so that callers never see USAGE_LIMIT or SERVER_ERROR retry codes and
    don't need to handle wait logic themselves.

    Args:
        request: The prompt request configuration
        subprocess_timeout: Timeout for the subprocess in seconds (default: 1800 = 30 min)
    """
    response = _prompt_claude_code_once(request, subprocess_timeout)

    if response.retry_code not in (RetryCode.USAGE_LIMIT, RetryCode.SERVER_ERROR):
        return response

    # Enter sleep-retry loop for usage limit / server errors
    label = "Usage limit" if response.retry_code == RetryCode.USAGE_LIMIT else "Server error (500)"
    for wait_attempt in range(_MAX_WAIT_RETRIES):
        print(
            f"⏳ {label} reached. Sleeping 15 minutes before retry "
            f"({wait_attempt + 1}/{_MAX_WAIT_RETRIES})..."
        )
        logging.getLogger(__name__).warning(
            f"{label} hit: {response.output[:200]}. "
            f"Sleeping {_WAIT_INTERVAL_SECONDS}s (attempt {wait_attempt + 1}/{_MAX_WAIT_RETRIES})"
        )
        time.sleep(_WAIT_INTERVAL_SECONDS)

        response = _prompt_claude_code_once(request, subprocess_timeout)

        if response.retry_code not in (RetryCode.USAGE_LIMIT, RetryCode.SERVER_ERROR):
            return response

        # Update label in case error type changed (usage → server or vice versa)
        label = "Usage limit" if response.retry_code == RetryCode.USAGE_LIMIT else "Server error (500)"

    # Exhausted all wait retries
    print(f"❌ {label} persisted after {_MAX_WAIT_RETRIES} waits ({_MAX_WAIT_RETRIES * 15} minutes). Giving up.")
    return response


def _prompt_claude_code_once(
    request: AgentPromptRequest,
    subprocess_timeout: int = 1800,
) -> AgentPromptResponse:
    """Execute a single Claude Code invocation (no wait-retry).

    BUG-081 fix: Accepts dynamic timeout to fit within cumulative timeout window.
    BUG-082 fix: Cleans up partial output files on timeout.
    BUG-086 fix: Validates subprocess_timeout is positive.
    """
    # BUG-086 fix: Validate subprocess_timeout is positive
    if subprocess_timeout <= 0:
        logging.getLogger(__name__).warning(
            f"Invalid subprocess_timeout ({subprocess_timeout}), using minimum 60 seconds"
        )
        subprocess_timeout = 60

    # Check if Claude Code CLI is installed
    error_msg = check_claude_installed()
    if error_msg:
        return AgentPromptResponse(
            output=error_msg,
            success=False,
            session_id=None,
            retry_code=RetryCode.NONE,  # Installation error is not retryable
        )

    # Save prompt before execution
    save_prompt(request.prompt, request.adw_id, request.agent_name)

    # Create output directory if needed
    output_dir = os.path.dirname(request.output_file)
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)

    # Build command - always use stream-json format and verbose
    cmd = [CLAUDE_PATH, "-p", request.prompt]
    cmd.extend(["--model", request.model])
    cmd.extend(["--output-format", "stream-json"])
    cmd.append("--verbose")
    
    # Check for MCP config in working directory
    if request.working_dir:
        mcp_config_path = os.path.join(request.working_dir, ".mcp.json")
        if os.path.exists(mcp_config_path):
            cmd.extend(["--mcp-config", mcp_config_path])

    # Add dangerous skip permissions flag if enabled
    if request.dangerously_skip_permissions:
        cmd.append("--dangerously-skip-permissions")

    # Set up environment with only required variables
    env = get_claude_env()

    # Validate working directory if provided
    if request.working_dir:
        if not os.path.isabs(request.working_dir):
            return AgentPromptResponse(
                output=f"Error: working_dir must be an absolute path: {request.working_dir}",
                success=False,
                session_id=None,
                retry_code=RetryCode.NONE,
            )
        if not os.path.isdir(request.working_dir):
            return AgentPromptResponse(
                output=f"Error: working_dir does not exist or is not a directory: {request.working_dir}",
                success=False,
                session_id=None,
                retry_code=RetryCode.NONE,
            )

    try:
        # Open output file for streaming
        # Review fix #3: Use Popen with start_new_session=True so that on timeout
        # we can kill the entire process group (Claude Code spawns child processes
        # for API calls and tool executions that would otherwise become orphans)
        with open(request.output_file, "w") as output_f:
            proc = subprocess.Popen(
                cmd,
                stdout=output_f,
                stderr=subprocess.PIPE,
                text=True,
                env=env,
                cwd=request.working_dir,
                start_new_session=True,  # Creates new process group
            )
            try:
                _, stderr_output = proc.communicate(timeout=subprocess_timeout)
            except subprocess.TimeoutExpired:
                # Kill entire process group to clean up Claude Code's children
                try:
                    os.killpg(proc.pid, signal.SIGTERM)
                    proc.wait(timeout=5)
                except (ProcessLookupError, subprocess.TimeoutExpired):
                    try:
                        os.killpg(proc.pid, signal.SIGKILL)
                        proc.wait(timeout=5)
                    except (ProcessLookupError, subprocess.TimeoutExpired):
                        pass
                raise subprocess.TimeoutExpired(cmd, subprocess_timeout)

            # Build a result-like object for compatibility with existing code
            result = type('Result', (), {
                'returncode': proc.returncode,
                'stderr': stderr_output or '',
            })()

        if result.returncode == 0:

            # Parse the JSONL file
            messages, result_message = parse_jsonl_output(request.output_file)
            record_rate_limits(messages)

            # Convert JSONL to JSON array file
            json_file = convert_jsonl_to_json(request.output_file)

            if result_message:
                # Extract session_id from result message
                session_id = result_message.get("session_id")

                # Check if there was an error in the result
                is_error = result_message.get("is_error", False)
                subtype = result_message.get("subtype", "")

                # Handle error_during_execution case where there's no result field
                if subtype == "error_during_execution":
                    error_msg = "Error during execution: Agent encountered an error and did not return a result"
                    transient = _classify_transient_error(error_msg)
                    return AgentPromptResponse(
                        output=error_msg,
                        success=False,
                        session_id=session_id,
                        retry_code=transient if transient else RetryCode.ERROR_DURING_EXECUTION,
                    )

                result_text = result_message.get("result", "")

                # For error cases, truncate the output to prevent JSONL blobs
                if is_error and len(result_text) > 1000:
                    result_text = truncate_output(result_text, max_length=800)

                # Check if soft error is actually a usage/server limit
                if is_error:
                    transient = _classify_transient_error(result_text)
                    retry_code = transient if transient else RetryCode.AGENT_SOFT_ERROR
                else:
                    retry_code = RetryCode.NONE

                return AgentPromptResponse(
                    output=result_text,
                    success=not is_error,
                    session_id=session_id,
                    retry_code=retry_code,
                )
            else:
                # No result message found, try to extract meaningful error
                error_msg = "No result message found in Claude Code output"

                # Try to get the last few lines of output for context
                try:
                    with open(request.output_file, "r") as f:
                        lines = f.readlines()
                        if lines:
                            # Get last 5 lines or less
                            last_lines = lines[-5:] if len(lines) > 5 else lines
                            # Try to parse each as JSON to find any error messages
                            for line in reversed(last_lines):
                                try:
                                    data = json.loads(line.strip())
                                    if data.get("type") == "assistant" and data.get(
                                        "message"
                                    ):
                                        # Extract text from assistant message
                                        content = data["message"].get("content", [])
                                        if isinstance(content, list) and content:
                                            text = content[0].get("text", "")
                                            if text:
                                                error_msg = f"Claude Code output: {text[:500]}"  # Truncate
                                                break
                                except (json.JSONDecodeError, KeyError, TypeError, IndexError):
                                    pass
                except (IOError, OSError):
                    pass

                return AgentPromptResponse(
                    output=truncate_output(error_msg, max_length=800),
                    success=False,
                    session_id=None,
                    retry_code=RetryCode.NONE,
                )
        else:
            # Error occurred - stderr is captured, stdout went to file
            stderr_msg = result.stderr.strip() if result.stderr else ""

            # Try to read the output file to check for errors in stdout
            stdout_msg = ""
            error_from_jsonl = None
            try:
                if os.path.exists(request.output_file):
                    # Parse JSONL to find error message
                    messages, result_message = parse_jsonl_output(request.output_file)
                    record_rate_limits(messages)

                    if result_message and result_message.get("is_error"):
                        # Found error in result message
                        error_from_jsonl = result_message.get("result", "Unknown error")
                    elif messages:
                        # Look for error in last few messages
                        for msg in reversed(messages[-5:]):
                            if msg.get("type") == "assistant" and msg.get(
                                "message", {}
                            ).get("content"):
                                content = msg["message"]["content"]
                                if isinstance(content, list) and content:
                                    text = content[0].get("text", "")
                                    if text and (
                                        "error" in text.lower()
                                        or "failed" in text.lower()
                                    ):
                                        error_from_jsonl = text[:500]  # Truncate
                                        break

                    # If no structured error found, get last line only
                    if not error_from_jsonl:
                        with open(request.output_file, "r") as f:
                            lines = f.readlines()
                            if lines:
                                # Just get the last line instead of entire file
                                stdout_msg = lines[-1].strip()[
                                    :200
                                ]  # Truncate to 200 chars
            except (IOError, OSError, json.JSONDecodeError, KeyError, TypeError, IndexError):
                pass

            if error_from_jsonl:
                error_msg = f"Claude Code error: {error_from_jsonl}"
            elif stdout_msg and not stderr_msg:
                error_msg = f"Claude Code error: {stdout_msg}"
            elif stderr_msg and not stdout_msg:
                error_msg = f"Claude Code error: {stderr_msg}"
            elif stdout_msg and stderr_msg:
                error_msg = f"Claude Code error: {stderr_msg}\nStdout: {stdout_msg}"
            else:
                error_msg = f"Claude Code error: Command failed with exit code {result.returncode}"

            # Classify error: usage limit and server errors get special retry codes
            transient_code = _classify_transient_error(error_msg)
            retry_code = transient_code if transient_code else RetryCode.CLAUDE_CODE_ERROR

            # Always truncate error messages to prevent huge outputs
            return AgentPromptResponse(
                output=truncate_output(error_msg, max_length=800),
                success=False,
                session_id=None,
                retry_code=retry_code,
            )

    except subprocess.TimeoutExpired:
        # BUG-082 fix: Clean up partial output file on timeout to prevent parse errors on retry
        if os.path.exists(request.output_file):
            try:
                # Mark the file as incomplete rather than deleting
                # This preserves any useful output for debugging
                with open(request.output_file, "a") as f:
                    f.write('\n{"type":"timeout","message":"Process timed out"}\n')
            except Exception:
                pass
        error_msg = f"Error: Claude Code command timed out after {subprocess_timeout // 60} minutes"
        return AgentPromptResponse(
            output=error_msg,
            success=False,
            session_id=None,
            retry_code=RetryCode.TIMEOUT_ERROR,
        )
    except Exception as e:
        error_msg = f"Error executing Claude Code: {e}"
        return AgentPromptResponse(
            output=error_msg,
            success=False,
            session_id=None,
            retry_code=RetryCode.EXECUTION_ERROR,
        )


def execute_template(request: AgentTemplateRequest) -> AgentPromptResponse:
    """Execute a Claude Code template with slash command and arguments.

    This function automatically selects the appropriate model based on:
    1. The slash command being executed
    2. The model_set stored in the ADW state (base, heavy, or superheavy)

    Additionally, for implementation/planning commands, a context preamble is
    automatically injected to ensure agents load relevant context files before
    starting work.

    Example:
        request = AgentTemplateRequest(
            agent_name="planner",
            slash_command="/implement",
            args=["plan.md"],
            adw_id="20260107143052-a1b2c3d4"
        )
        # base/heavy + "opus" mapping -> "claude-opus-4-6"
        # superheavy + "opus" mapping -> "claude-opus-4-7"
        # Utility commands mapped to "sonnet" stay as the "sonnet" alias.
        response = execute_template(request)
    """
    # Validate request parameters
    if not request.adw_id or not request.adw_id.strip():
        return AgentPromptResponse(
            output="Error: adw_id is required and cannot be empty",
            success=False,
            session_id=None,
            retry_code=RetryCode.NONE,
        )
    if not request.slash_command or not request.slash_command.strip():
        return AgentPromptResponse(
            output="Error: slash_command is required and cannot be empty",
            success=False,
            session_id=None,
            retry_code=RetryCode.NONE,
        )
    if not request.agent_name or not request.agent_name.strip():
        return AgentPromptResponse(
            output="Error: agent_name is required and cannot be empty",
            success=False,
            session_id=None,
            retry_code=RetryCode.NONE,
        )

    # Get the appropriate model for this request
    mapped_model = get_model_for_slash_command(request)
    request = request.model_copy(update={"model": mapped_model})

    # Construct prompt from slash command and args
    # Validate args don't contain problematic characters that could cause prompt issues
    sanitized_args = []
    for idx, arg in enumerate(request.args):
        if arg is None:
            logging.getLogger(__name__).debug(f"Skipping None arg at index {idx}")
            continue
        # Convert to string and strip
        arg_str = str(arg).strip()
        # Skip empty strings to avoid malformed prompts
        if not arg_str:
            logging.getLogger(__name__).debug(f"Skipping empty arg at index {idx}")
            continue
        sanitized_args.append(arg_str)

    # BUG-084 fix: Don't add trailing space when args is empty
    if sanitized_args:
        prompt = f"{request.slash_command} {' '.join(sanitized_args)}"
    else:
        prompt = request.slash_command

    # Inject context preamble for commands that benefit from it
    # Use working_dir-aware preamble to enforce worktree isolation
    if request.slash_command not in SKIP_CONTEXT_PREAMBLE_COMMANDS:
        prompt = get_context_preamble(request.working_dir) + prompt

    # Create output directory with adw_id at project root
    # __file__ is in adws/adw_modules/, so we need to go up 3 levels to get to project root
    project_root = os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    )
    output_dir = os.path.join(
        project_root, "agents", request.adw_id, request.agent_name
    )
    os.makedirs(output_dir, exist_ok=True)

    # Build output file path
    output_file = os.path.join(output_dir, "raw_output.jsonl")

    # Create prompt request with specific parameters
    prompt_request = AgentPromptRequest(
        prompt=prompt,
        adw_id=request.adw_id,
        agent_name=request.agent_name,
        model=request.model,
        dangerously_skip_permissions=True,
        output_file=output_file,
        working_dir=request.working_dir,  # Pass through working_dir
    )

    # Execute with retry logic and return response (prompt_claude_code now handles all parsing)
    return prompt_claude_code_with_retry(prompt_request)
