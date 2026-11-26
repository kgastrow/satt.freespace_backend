#!/usr/bin/env -S uv run
# /// script
# dependencies = ["python-dotenv", "pydantic"]
# ///

"""
ADW E2E Validation - Comprehensive end-to-end testing for greenfield projects

Generates and executes Playwright E2E tests per-module, grouped by target
audience (end_user, admin, platform_admin). Each module gets its own test
file, generated in parallel for speed.

Usage:
  uv run adw_e2e_validation_iso.py <decomposition_json> <adw_id> [--working-dir <path>] [--max-attempts N] [--max-parallel N]

Features:
- Groups modules by target_audience from decomposition JSON
- Generates one test file per module (parallel, default 4 workers)
- Retry loop with fix attempts (default 5) per module
- Retries test generation up to 3 times if agent fails
- Commits all generated test artifacts to main
- Documents unresolved defects in E2E_DEFECTS.md
- Advisory only — always exits 0

Exit codes:
- 0: Always (advisory mode)
"""

import sys
import os
import json
import logging
import subprocess
import time
import concurrent.futures
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from dotenv import load_dotenv
from adw_modules.agent import execute_template
from adw_modules.data_types import AgentTemplateRequest
from adw_modules.utils import setup_logger, parse_json, check_env_vars
from adw_modules.e2e_quality_gate import (
    QualityGateResult,
    format_failure_for_resolver,
    run_quality_gate,
)
from adw_modules.cost_tracker import CostTracker

# Agent name constants
AGENT_E2E_WRITER = "greenfield_e2e_writer"
AGENT_E2E_RUNNER = "greenfield_e2e_runner"
AGENT_E2E_RESOLVER = "greenfield_e2e_resolver"
AGENT_APP_PREPARER = "e2e_app_preparer"

# Retry settings
MAX_E2E_ATTEMPTS = 5
MAX_GENERATION_ATTEMPTS = 3

# Per-module cost budget — past this, stop spending on retries for that module.
# Tuned conservatively; expect to revise after observing real runs.
DEFAULT_PER_MODULE_USD_CAP = 5.00

# Sentinel value passed in the 7th positional slot when no prior gate
# feedback is available. A literal dash survives agent.py's empty-arg
# stripping (str.strip is a no-op on `-`) and is exceedingly unlikely to
# appear in real feedback text. The skill docs treat this as "no feedback".
NO_GATE_FEEDBACK_SENTINEL = "-"

# Target audiences that have UI (skip backend_only)
TARGET_AUDIENCES_WITH_UI = ["end_user", "admin", "platform_admin"]

# Audience display labels
AUDIENCE_LABELS = {
    "end_user": "End User (main sidebar)",
    "admin": "Admin (admin hub /admin)",
    "platform_admin": "Platform Admin (/platform-admin)",
}


def load_decomposition(decomposition_path: str) -> Dict[str, Any]:
    """Load and parse the decomposition JSON file.

    Returns:
        Parsed decomposition dict with 'modules', 'execution_order', etc.

    Raises:
        FileNotFoundError, json.JSONDecodeError
    """
    with open(decomposition_path, "r") as f:
        return json.load(f)


def group_modules_by_audience(
    decomposition: Dict[str, Any],
) -> Dict[str, List[Dict[str, Any]]]:
    """Group modules by target_audience, filtering out backend_only.

    Returns:
        Dict mapping audience string -> list of module dicts.
        Only includes audiences that have at least one module.
    """
    groups: Dict[str, List[Dict[str, Any]]] = {}

    for module in decomposition.get("modules", []):
        audience = module.get("target_audience", "end_user")
        if audience == "backend_only":
            continue
        if audience not in groups:
            groups[audience] = []
        groups[audience].append(module)

    return groups


def get_e2e_output_paths(
    adw_id: str,
    audience: str,
    working_dir: str,
) -> Tuple[str, str]:
    """Compute output paths for generated test files.

    Returns:
        (spec_path, test_path) where:
          spec_path = .claude/commands/e2e/test_greenfield_{adw_id}_{audience}.md
          test_path = app/frontend/tests/e2e/greenfield-{audience}.spec.ts
    """
    # Sanitize adw_id for filenames (replace non-alphanumeric with underscore)
    safe_id = adw_id.replace("-", "_").replace("/", "_")

    spec_path = os.path.join(
        working_dir,
        ".claude", "commands", "e2e",
        f"test_greenfield_{safe_id}_{audience}.md",
    )
    # TypeScript Playwright test in the frontend test dir, numbered 30+ to avoid
    # collisions with template tests (01-23).
    audience_num = {"end_user": "31", "admin": "30", "platform_admin": "32"}.get(
        audience, "33"
    )
    test_path = os.path.join(
        working_dir,
        "app", "frontend", "tests", "e2e",
        f"{audience_num}-greenfield-{audience.replace('_', '-')}.spec.ts",
    )
    return spec_path, test_path


def get_e2e_module_output_paths(
    adw_id: str,
    audience: str,
    module_id: str,
    module_index: int,
    working_dir: str,
) -> Tuple[str, str]:
    """Compute output paths for a per-module generated test file.

    Returns:
        (spec_path, test_path) where:
          spec_path = .claude/commands/e2e/test_greenfield_{adw_id}_{audience}_{module_id}.md
          test_path = app/frontend/tests/e2e/{num}-greenfield-{audience}-{module_id}.spec.ts
    """
    safe_id = adw_id.replace("-", "_").replace("/", "_")
    safe_module = module_id.replace("_", "-")

    spec_path = os.path.join(
        working_dir,
        ".claude", "commands", "e2e",
        f"test_greenfield_{safe_id}_{audience}_{module_id}.md",
    )

    audience_base = {"end_user": 31, "admin": 30, "platform_admin": 32}.get(audience, 33)
    test_num = f"{audience_base}-{module_index:02d}"

    test_path = os.path.join(
        working_dir,
        "app", "frontend", "tests", "e2e",
        f"{test_num}-greenfield-{audience.replace('_', '-')}-{safe_module}.spec.ts",
    )
    return spec_path, test_path


def generate_e2e_test(
    decomposition_path: str,
    audience: str,
    spec_output_path: str,
    test_output_path: str,
    adw_id: str,
    working_dir: str,
    logger: logging.Logger,
    module_id: str = "",
    cost_tracker: Optional[CostTracker] = None,
) -> Tuple[bool, Optional[QualityGateResult]]:
    """Spawn Claude agent to generate comprehensive E2E test.

    When module_id is provided, generates a test for that single module.
    Otherwise generates for all modules matching the audience (legacy mode).

    Creates a Playwright .spec.ts test file (required) and optionally a .md
    spec documentation file. The .md file is advisory — its absence does not
    block test execution.

    Each attempt runs the quality gate (tsc/playwright-list/selectors/idempotency)
    after the agent writes the file. A gate failure feeds back into the next
    generation attempt as additional context, so the agent has a chance to fix
    its own output before the retry loop gives up.

    Returns:
        ``(success, last_gate_result)``. ``success`` is True only when both
        the agent produced a file AND the quality gate passed. ``last_gate_result``
        is the most recent QualityGateResult (may be None if the agent never
        produced a parseable file).
    """
    label = f"{audience}/{module_id}" if module_id else audience

    # Ensure output directories exist
    os.makedirs(os.path.dirname(spec_output_path), exist_ok=True)
    os.makedirs(os.path.dirname(test_output_path), exist_ok=True)

    bucket = module_id or audience
    last_gate: Optional[QualityGateResult] = None
    prior_gate_feedback: Optional[str] = None

    for attempt in range(1, MAX_GENERATION_ATTEMPTS + 1):
        logger.info(
            f"Generating E2E test for {label} "
            f"(attempt {attempt}/{MAX_GENERATION_ATTEMPTS})"
        )

        agent_suffix = f"{audience}_{module_id}_{attempt}" if module_id else f"{audience}_{attempt}"
        agent_name = f"{AGENT_E2E_WRITER}_{agent_suffix}"

        # Always pass exactly 7 args. The 7th slot is the prior gate feedback
        # diagnostic on retry, or NO_GATE_FEEDBACK_SENTINEL ("-") on the first
        # attempt. A sentinel is used instead of an empty string because
        # adw_modules/agent.py strips empty/whitespace args during sanitization,
        # which would silently reduce the arg count back to 6.
        args = [
            decomposition_path, audience, spec_output_path, test_output_path,
            adw_id, module_id,
            prior_gate_feedback if prior_gate_feedback else NO_GATE_FEEDBACK_SENTINEL,
        ]

        request = AgentTemplateRequest(
            agent_name=agent_name,
            slash_command="/write_greenfield_e2e",
            args=args,
            adw_id=adw_id,
            working_dir=working_dir,
        )

        response = execute_template(request)
        if cost_tracker is not None:
            cost_tracker.record_from_template_request(
                adw_id, agent_name, bucket=bucket, logger=logger,
            )

        if not response.success:
            logger.warning(
                f"E2E test generation agent failed for {label} "
                f"(attempt {attempt}): {response.output[:500]}"
            )
            if attempt < MAX_GENERATION_ATTEMPTS:
                continue
            logger.error(f"E2E test generation exhausted all {MAX_GENERATION_ATTEMPTS} attempts for {label}")
            return False, last_gate

        # The .spec.ts test file is the only hard requirement
        if not os.path.exists(test_output_path):
            logger.warning(
                f"Agent did not write test file: {test_output_path} "
                f"(attempt {attempt}/{MAX_GENERATION_ATTEMPTS})"
            )
            if attempt < MAX_GENERATION_ATTEMPTS:
                continue
            logger.error(f"Test file not produced after {MAX_GENERATION_ATTEMPTS} attempts for {label}")
            return False, last_gate

        # Quality gate — pre-execution validation
        logger.info(f"Running quality gate for {label}")
        last_gate = run_quality_gate(test_output_path, working_dir, logger)

        if last_gate.passed:
            # .md spec file is advisory — warn but don't block
            if not os.path.exists(spec_output_path):
                logger.warning(f"Agent did not write spec file (advisory): {spec_output_path}")
            logger.info(f"Generated E2E test for {label} (attempt {attempt}): {last_gate.summary()}")
            logger.info(f"  Test: {test_output_path}")
            if os.path.exists(spec_output_path):
                logger.info(f"  Spec: {spec_output_path}")
            return True, last_gate

        # Gate failed — capture diagnostics for the next attempt, then retry.
        logger.warning(
            f"Quality gate failed for {label} (attempt {attempt}): {last_gate.summary()}"
        )
        prior_gate_feedback = format_failure_for_resolver(last_gate)

        if attempt < MAX_GENERATION_ATTEMPTS:
            continue
        logger.error(
            f"Quality gate did not pass after {MAX_GENERATION_ATTEMPTS} generation attempts for {label}"
        )
        return False, last_gate

    return False, last_gate


def _read_ports(working_dir: str) -> Tuple[int, int]:
    """Read FRONTEND_PORT and BACKEND_PORT from .ports.env."""
    frontend_port, backend_port = 5173, 8000
    ports_file = os.path.join(working_dir, ".ports.env")
    if os.path.exists(ports_file):
        with open(ports_file) as f:
            for line in f:
                if line.startswith("FRONTEND_PORT="):
                    frontend_port = int(line.split("=", 1)[1].strip())
                elif line.startswith("BACKEND_PORT="):
                    backend_port = int(line.split("=", 1)[1].strip())
    return frontend_port, backend_port


def _setup_test_auth(
    adw_id: str,
    working_dir: str,
    logger: logging.Logger,
) -> Optional[Dict[str, str]]:
    """Run seed_smoke_test.py and return auth tokens."""
    script = os.path.join(working_dir, "app", "backend", "scripts", "seed_smoke_test.py")
    try:
        venv_python = os.path.join(working_dir, "app", "backend", ".venv", "bin", "python")
        python_cmd = venv_python if os.path.exists(venv_python) else "python"
        proc = subprocess.run(
            [python_cmd, script, "--adw-id", adw_id],
            capture_output=True, text=True, cwd=os.path.join(working_dir, "app", "backend"),
            timeout=30,
        )
        if proc.returncode != 0:
            logger.error(f"Auth seed failed: {proc.stderr[:300]}")
            return None
        # Extract JSON from output (skip log lines)
        for line in proc.stdout.strip().split("\n"):
            line = line.strip()
            if line.startswith("{"):
                return json.loads(line)
        # Try parsing entire output
        return json.loads(proc.stdout)
    except Exception as e:
        logger.error(f"Auth setup error: {e}")
        return None


def _teardown_test_auth(
    adw_id: str,
    working_dir: str,
    logger: logging.Logger,
) -> None:
    """Run teardown_smoke_test.py to clean up test data."""
    script = os.path.join(working_dir, "app", "backend", "scripts", "teardown_smoke_test.py")
    if not os.path.exists(script):
        return
    try:
        subprocess.run(
            ["python", script, "--adw-id", adw_id],
            capture_output=True, text=True,
            cwd=os.path.join(working_dir, "app", "backend"),
            timeout=30,
        )
    except Exception as e:
        logger.warning(f"Auth teardown error: {e}")


def execute_e2e_test(
    test_path: str,
    adw_id: str,
    audience: str,
    working_dir: str,
    logger: logging.Logger,
) -> Tuple[bool, Optional[str]]:
    """Execute the generated TypeScript Playwright test file.

    Runs the .spec.ts file via ``npx playwright test``.  The existing
    Playwright infrastructure handles auth via global-setup.ts and
    storageState — no separate seed/teardown step is needed here
    because the ``setup`` project runs automatically as a dependency.

    Returns:
        (passed, error_message) — passed=True if all tests passed.
    """
    logger.info(f"Executing E2E Playwright test for {audience}: {test_path}")

    # Resolve test filename relative to the frontend test dir
    test_filename = os.path.basename(test_path)
    frontend_dir = os.path.join(working_dir, "app", "frontend")

    # Fallback: if playwright.config.ts isn't in frontend_dir (e.g. working_dir
    # points to adws/ rather than the repo root), resolve to the repo root.
    if not os.path.exists(os.path.join(frontend_dir, "playwright.config.ts")):
        repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        alt_frontend_dir = os.path.join(repo_root, "app", "frontend")
        if os.path.exists(os.path.join(alt_frontend_dir, "playwright.config.ts")):
            logger.info(
                f"Playwright config not found in {frontend_dir}, "
                f"falling back to {alt_frontend_dir}"
            )
            frontend_dir = alt_frontend_dir

    # Determine ports: if a .ports.env exists (ADW worktree), use those ports
    # explicitly. Otherwise let the Playwright config derive ports from
    # ADW_CODEBASE_INDEX (which is inherited from the environment).
    env = os.environ.copy()
    env["E2E_ADW_ID"] = adw_id

    ports_file = os.path.join(working_dir, ".ports.env")
    if os.path.exists(ports_file):
        frontend_port, backend_port = _read_ports(working_dir)
        env["E2E_API_URL"] = f"http://localhost:{backend_port}"
        env["E2E_BACKEND_PORT"] = str(backend_port)
        env["E2E_FRONTEND_PORT"] = str(frontend_port)

    cmd = [
        "npx", "playwright", "test",
        test_filename,
        "--project=setup",
        "--project=chromium",
        "--reporter=list",
    ]

    try:
        proc = subprocess.run(
            cmd,
            capture_output=True, text=True,
            cwd=frontend_dir,
            env=env,
            timeout=300,
        )
    except subprocess.TimeoutExpired:
        return False, "Playwright test timed out after 300 seconds"
    except Exception as e:
        return False, f"Playwright execution error: {e}"

    output = proc.stdout + "\n" + proc.stderr
    logger.info(f"Playwright exit code: {proc.returncode}")

    if proc.returncode == 0:
        return True, None

    # Extract failure info
    lines = output.strip().split("\n")
    error_lines = [
        l for l in lines
        if "failed" in l.lower() or "error" in l.lower() or "✘" in l
    ]
    error_msg = "\n".join(error_lines[-5:]) if error_lines else output[-500:]
    return False, error_msg


def _snapshot_test_file(test_path: str, attempt: int, logger: logging.Logger) -> Optional[str]:
    """Copy a test file aside so a resolver edit can be diffed/reverted.

    Returns the snapshot path, or None if the source file did not exist.
    """
    if not os.path.exists(test_path):
        return None
    snapshot_path = f"{test_path}.pre-resolve-{attempt}"
    try:
        with open(test_path, "rb") as src, open(snapshot_path, "wb") as dst:
            dst.write(src.read())
        logger.info(f"Snapshotted pre-resolve copy: {os.path.basename(snapshot_path)}")
        return snapshot_path
    except (IOError, OSError) as e:
        logger.warning(f"Failed to snapshot {test_path}: {e}")
        return None


def _revert_to_snapshot(test_path: str, snapshot_path: str, logger: logging.Logger) -> bool:
    """Restore a snapshotted test file. Keeps the snapshot for audit."""
    if not os.path.exists(snapshot_path):
        return False
    try:
        with open(snapshot_path, "rb") as src, open(test_path, "wb") as dst:
            dst.write(src.read())
        logger.info(f"Reverted {os.path.basename(test_path)} to snapshot")
        return True
    except (IOError, OSError) as e:
        logger.warning(f"Failed to revert from snapshot: {e}")
        return False


def _normalize_for_diff(text: str) -> str:
    """Collapse whitespace so byte-exact differences in formatting don't
    register as 'progress'. We strip trailing whitespace per line, drop
    empty lines, and collapse runs of internal whitespace to a single space.

    This is permissive on purpose — a resolver that only reformatted the file
    has made zero semantic progress, and burning a retry attempt on it (plus
    re-running the gate) wastes both time and budget.
    """
    out_lines: List[str] = []
    for raw in text.splitlines():
        stripped = raw.strip()
        if not stripped:
            continue
        # Collapse runs of whitespace inside the line
        out_lines.append(" ".join(stripped.split()))
    return "\n".join(out_lines)


def _files_differ(a: str, b: str) -> bool:
    """True if two files have semantically different contents.

    Whitespace-only differences (reformatting, blank line shuffles, indent
    changes) are treated as 'same'. Either file missing is treated as differing.
    """
    try:
        if not (os.path.exists(a) and os.path.exists(b)):
            return True
        # Fast path: identical bytes are obviously identical.
        if os.path.getsize(a) == os.path.getsize(b):
            with open(a, "rb") as fa, open(b, "rb") as fb:
                if fa.read() == fb.read():
                    return False
        # Slow path: normalize whitespace and compare.
        with open(a, "r", errors="replace") as fa, open(b, "r", errors="replace") as fb:
            return _normalize_for_diff(fa.read()) != _normalize_for_diff(fb.read())
    except (IOError, OSError):
        return True


def resolve_e2e_failure(
    spec_path: str,
    error_message: str,
    adw_id: str,
    audience: str,
    attempt: int,
    working_dir: str,
    logger: logging.Logger,
    cost_tracker: Optional[CostTracker] = None,
    cost_bucket: str = "",
) -> Tuple[bool, Optional[QualityGateResult]]:
    """Spawn Claude agent to fix a failing E2E test, with snapshot + revert safety.

    Before invoking the resolver, snapshot the current test file. After the
    agent returns:

    1. Run the quality gate against the resulting file.
    2. If the gate fails, REVERT to the snapshot — the agent has just made
       things worse, and we'd rather rerun the original failure than build on
       broken edits.
    3. If the file is unchanged from the snapshot, return False so the caller
       stops retrying (no-progress signal).

    Returns:
        ``(made_progress, gate_result_after_edit)``. ``made_progress`` is True
        only if the resolver produced a different, gate-passing file.
    """
    logger.info(f"Attempting to resolve E2E failure for {audience} (attempt {attempt})")

    snapshot_path = _snapshot_test_file(spec_path, attempt, logger)

    # Build failure JSON payload for the resolve command
    failure_payload = json.dumps({
        "test_name": f"Greenfield E2E: {audience}",
        "test_path": spec_path,
        "error": error_message,
        "screenshots": [],
    })

    agent_name = f"{AGENT_E2E_RESOLVER}_{audience}_{attempt}"

    request = AgentTemplateRequest(
        agent_name=agent_name,
        slash_command="/resolve_failed_e2e_test",
        args=[failure_payload],
        adw_id=adw_id,
        working_dir=working_dir,
    )

    response = execute_template(request)
    if cost_tracker is not None:
        cost_tracker.record_from_template_request(
            adw_id, agent_name, bucket=cost_bucket or audience, logger=logger,
        )

    if not response.success:
        logger.warning(f"Resolve agent failed for {audience}: {response.output[:300]}")
        return False, None

    # Determine if the resolver actually changed anything. Identical content
    # means "no progress" — stop retrying.
    if snapshot_path and not _files_differ(spec_path, snapshot_path):
        logger.info(f"Resolver made no changes to {os.path.basename(spec_path)} — stopping retries")
        return False, None

    # The resolver edited the file. Run the quality gate; if it now fails,
    # revert. Otherwise accept the edit and let the caller re-execute.
    gate = run_quality_gate(spec_path, working_dir, logger)
    if not gate.passed:
        logger.warning(
            f"Resolver output failed quality gate for {audience}: {gate.summary()}; reverting"
        )
        if snapshot_path:
            _revert_to_snapshot(spec_path, snapshot_path, logger)
        return False, gate

    logger.info(f"Resolve agent completed for {audience} (gate passed)")
    return True, gate


def commit_e2e_artifacts(
    files: List[str],
    adw_id: str,
    commit_message: str,
    working_dir: str,
    logger: logging.Logger,
) -> bool:
    """Commit generated test files to main.

    Uses the same stash-checkout-commit-push-restore pattern as
    commit_review_tracker_to_main() in adw_greenfield_iso.py.

    Args:
        files: Absolute paths to files to commit
        adw_id: ADW identifier
        commit_message: Git commit message
        working_dir: Repository root

    Returns:
        True if successfully committed and pushed.
    """
    if not files:
        return True

    # Convert to relative paths
    rel_paths = []
    for f in files:
        if os.path.exists(f):
            rel_paths.append(os.path.relpath(f, working_dir))
        else:
            logger.warning(f"File not found, skipping: {f}")

    if not rel_paths:
        logger.warning("No files to commit")
        return True

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
            logger.error(f"Failed to checkout main: {result.stderr}")
            if stashed:
                subprocess.run(["git", "stash", "pop"], capture_output=True, text=True, cwd=working_dir)
            return False

        # Pull latest
        subprocess.run(
            ["git", "pull", "origin", "main"],
            capture_output=True, text=True, cwd=working_dir,
        )

        # Stage specific files
        for rel_path in rel_paths:
            subprocess.run(
                ["git", "add", rel_path],
                capture_output=True, text=True, cwd=working_dir,
            )

        # Commit
        result = subprocess.run(
            ["git", "commit", "-m", commit_message],
            capture_output=True, text=True, cwd=working_dir,
        )
        if result.returncode != 0:
            logger.warning(f"Commit failed (may be no changes): {result.stderr}")
        else:
            # Push
            push_result = subprocess.run(
                ["git", "push", "origin", "main"],
                capture_output=True, text=True, cwd=working_dir, timeout=60,
            )
            if push_result.returncode != 0:
                logger.error(f"Failed to push to main: {push_result.stderr}")
            else:
                logger.info(f"Committed and pushed {len(rel_paths)} E2E artifact(s) to main")

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
        logger.error(f"Error committing E2E artifacts: {e}")
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


def build_defect_report(
    module_results: List[Dict[str, Any]],
    adw_id: str,
    working_dir: str,
    logger: logging.Logger,
) -> Optional[str]:
    """Build a markdown defect report from failed E2E results.

    Args:
        module_results: List of per-module result dicts with keys: module_id,
            module_name, target_audience, passed, total_attempts, defects,
            test_spec_path, test_file_path, error
        adw_id: ADW identifier
        working_dir: Repository root

    Returns:
        Path to the defect report file, or None if no defects.
    """
    failed = [r for r in module_results if not r.get("passed") and r.get("defects")]
    if not failed:
        return None

    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    lines = [
        f"# E2E Validation Defects — {adw_id}",
        "",
        f"Generated: {timestamp}",
        "Status: Advisory (does not block greenfield)",
        "",
        "## Summary",
        "",
        "| Module | Audience | Status | Attempts | Defects |",
        "|--------|----------|--------|----------|---------|",
    ]

    for r in module_results:
        module_name = r.get("module_name", r.get("module_id", "?"))
        audience = r.get("target_audience", "?")
        label = AUDIENCE_LABELS.get(audience, audience)
        if r.get("error") and not r.get("defects"):
            status = "SKIPPED"
        elif r.get("passed"):
            status = "PASSED"
        else:
            status = "FAILED"
        attempts = r.get("total_attempts", 0)
        defect_count = len(r.get("defects", []))
        lines.append(f"| {module_name} | {label} | {status} | {attempts}/{MAX_E2E_ATTEMPTS} | {defect_count} |")

    lines.append("")

    # Detail section for failures
    for r in failed:
        module_name = r.get("module_name", r.get("module_id", "?"))
        audience = r.get("target_audience", "?")
        label = AUDIENCE_LABELS.get(audience, audience)
        lines.extend([
            f"## {module_name} ({label})",
            "",
        ])

        spec = r.get("test_spec_path")
        test = r.get("test_file_path")
        if spec:
            lines.append(f"- **Test spec:** `{os.path.relpath(spec, working_dir)}`")
        if test:
            lines.append(f"- **Test file:** `{os.path.relpath(test, working_dir)}`")
        lines.append("")

        for i, defect in enumerate(r.get("defects", []), 1):
            lines.extend([
                f"### Defect {i}",
                "",
                defect,
                "",
            ])

    lines.extend([
        "## Next Steps",
        "",
        "1. Review the generated test files for accuracy",
        "2. Run tests locally: `npx playwright test <test-filename>.spec.ts --headed`",
        "3. Fix identified defects manually",
        "4. Consider adding `data-testid` attributes to improve test reliability",
        "",
    ])

    # Write report
    report_dir = os.path.join(working_dir, "specs", "greenfields", adw_id)
    os.makedirs(report_dir, exist_ok=True)
    report_path = os.path.join(report_dir, "E2E_DEFECTS.md")

    with open(report_path, "w") as f:
        f.write("\n".join(lines))

    logger.info(f"Defect report written to {report_path}")
    return report_path


def run_e2e_validation(
    decomposition_path: str,
    adw_id: str,
    working_dir: str,
    logger: logging.Logger,
    max_attempts: int = MAX_E2E_ATTEMPTS,
    max_parallel_generation: int = 4,
    cost_tracker: Optional[CostTracker] = None,
    per_module_usd_cap: float = DEFAULT_PER_MODULE_USD_CAP,
) -> Dict[str, Any]:
    """Main orchestration: run E2E validation for all audiences.

    This is the function called from adw_greenfield_iso.py.

    Flow:
    1. Load decomposition, group modules by audience
    2. Check Chrome availability (skip if unavailable)
    3. Prepare app (start frontend + backend)
    4. For each audience:
       a. Generate E2E tests in PARALLEL (one per module) with quality gate
       b. Execute each module's test with its own retry/resolve loop
          (snapshot/revert on resolver failure, per-module USD cap)
    5. Commit all generated test files to main
    6. Build defect report if any failures
    7. Return structured result

    If a CostTracker is supplied, every agent invocation is recorded against
    the module_id bucket. A module that exceeds ``per_module_usd_cap`` halts
    its retry loop early — failures are still tracked, but we stop spending.

    Returns:
        Dict with keys: adw_id, audiences (per-audience summaries),
        module_results (flat list), total_passed, total_failed, total_skipped,
        cost (grand-total summary if tracker supplied)
    """
    if cost_tracker is None:
        cost_tracker = CostTracker()
        owns_tracker = True
    else:
        owns_tracker = False

    result: Dict[str, Any] = {
        "adw_id": adw_id,
        "audiences": [],
        "module_results": [],
        "total_passed": 0,
        "total_failed": 0,
        "total_skipped": 0,
    }

    # 1. Load decomposition and group by audience
    try:
        decomposition = load_decomposition(decomposition_path)
    except Exception as e:
        logger.error(f"Failed to load decomposition: {e}")
        return result

    audience_groups = group_modules_by_audience(decomposition)

    if not audience_groups:
        logger.info("No UI modules found — skipping E2E validation")
        return result

    audiences_found = ", ".join(
        f"{a} ({len(mods)} modules)" for a, mods in audience_groups.items()
    )
    logger.info(f"UI audiences found: {audiences_found}")

    # 2. Check Chrome availability
    try:
        sys.path.insert(0, os.path.join(working_dir, "adws"))
        from adw_modules.utils import is_chrome_available
        available, reason = is_chrome_available()
        if not available:
            logger.warning(f"Chrome not available: {reason}. Skipping E2E validation.")
            print(f"  Chrome not available ({reason}). Skipping E2E validation.")
            return result
    except ImportError:
        logger.warning("Could not check Chrome availability, proceeding anyway")

    # 3. Prepare app (start frontend + backend)
    logger.info("Preparing application for E2E testing...")
    prepare_request = AgentTemplateRequest(
        agent_name=AGENT_APP_PREPARER,
        slash_command="/prepare_app",
        args=[],
        adw_id=adw_id,
        working_dir=working_dir,
    )
    prepare_response = execute_template(prepare_request)
    cost_tracker.record_from_template_request(
        adw_id, AGENT_APP_PREPARER, bucket="prepare_app", logger=logger,
    )
    if not prepare_response.success:
        logger.warning(f"App preparation may have failed: {prepare_response.output[:300]}")
        print("  Warning: App preparation may have failed. E2E tests may not work correctly.")

    generated_files: List[str] = []

    # 4. For each audience — generate per-module in parallel, then execute sequentially
    for audience in TARGET_AUDIENCES_WITH_UI:
        if audience not in audience_groups:
            continue

        modules = audience_groups[audience]
        label = AUDIENCE_LABELS.get(audience, audience)

        print(f"\n  === E2E Validation: {label} ({len(modules)} modules) ===")
        logger.info(f"E2E validation for {audience}: {len(modules)} modules")

        # 4a. PARALLEL GENERATION — one agent per module
        # Maps module_id -> (spec_path, test_path, success, gate_summary)
        generation_results: Dict[str, Tuple[str, str, bool, str]] = {}

        print(f"  Generating tests ({max_parallel_generation} parallel)...")
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_parallel_generation) as executor:
            future_to_module: Dict[concurrent.futures.Future, Tuple[Dict, int, str, str, str]] = {}

            for idx, module in enumerate(modules):
                module_id = module.get("id", f"module-{idx}")
                spec_path, test_path = get_e2e_module_output_paths(
                    adw_id, audience, module_id, idx, working_dir,
                )
                future = executor.submit(
                    generate_e2e_test,
                    decomposition_path, audience, spec_path, test_path,
                    adw_id, working_dir, logger, module_id, cost_tracker,
                )
                future_to_module[future] = (module, idx, module_id, spec_path, test_path)

            for future in concurrent.futures.as_completed(future_to_module):
                module, idx, module_id, spec_path, test_path = future_to_module[future]
                module_name = module.get("name", module_id)
                try:
                    gen_success, gate = future.result()
                    gate_summary = gate.summary() if gate else "no gate result"
                    generation_results[module_id] = (spec_path, test_path, gen_success, gate_summary)
                    status = "generated" if gen_success else "FAILED"
                    print(f"    [{status}] {module_name} — {gate_summary}")
                except Exception as e:
                    logger.exception(f"Generation error for {module_id}")
                    generation_results[module_id] = (spec_path, test_path, False, f"exception: {e}")
                    print(f"    [ERROR] {module_name}: {e}")

        # 4b. SEQUENTIAL EXECUTION — retry/resolve per module
        audience_module_results: List[Dict[str, Any]] = []

        for idx, module in enumerate(modules):
            module_id = module.get("id", f"module-{idx}")
            module_name = module.get("name", module_id)
            spec_path, test_path, gen_success, gate_summary = generation_results.get(
                module_id, ("", "", False, "no result")
            )

            module_result: Dict[str, Any] = {
                "module_id": module_id,
                "module_name": module_name,
                "target_audience": audience,
                "test_spec_path": None,
                "test_file_path": None,
                "total_attempts": 0,
                "passed": False,
                "defects": [],
                "error": None,
                "generation_gate": gate_summary,
            }

            if not gen_success:
                module_result["error"] = (
                    f"Test generation failed for {module_name}: {gate_summary}"
                )
                result["total_skipped"] += 1
                audience_module_results.append(module_result)
                result["module_results"].append(module_result)
                print(f"    {module_name}: SKIPPED ({gate_summary})")
                continue

            module_result["test_file_path"] = test_path
            generated_files.append(test_path)
            if os.path.exists(spec_path):
                module_result["test_spec_path"] = spec_path
                generated_files.append(spec_path)

            # Retry loop per module — bounded by attempts AND per-module $ cap
            for attempt in range(1, max_attempts + 1):
                if cost_tracker.bucket_exceeds(module_id, max_usd=per_module_usd_cap):
                    bucket = cost_tracker.bucket_total(module_id)
                    spent = bucket.cost_usd if bucket else 0.0
                    module_result["defects"].append(
                        f"Per-module USD cap ${per_module_usd_cap:.2f} reached "
                        f"(spent ${spent:.2f}); halting retries for {module_name}"
                    )
                    print(f"      Cap reached (${spent:.2f}/${per_module_usd_cap:.2f}) — halting")
                    logger.warning(
                        f"Per-module cap reached for {module_id}: ${spent:.2f} >= ${per_module_usd_cap:.2f}"
                    )
                    break

                module_result["total_attempts"] = attempt
                print(f"    {module_name}: attempt {attempt}/{max_attempts}...", end=" ", flush=True)
                logger.info(f"E2E attempt {attempt}/{max_attempts} for {audience}/{module_id}")

                passed, error_msg = execute_e2e_test(
                    test_path, adw_id, audience, working_dir, logger,
                )

                if passed:
                    module_result["passed"] = True
                    print("PASSED")
                    logger.info(f"E2E PASSED for {audience}/{module_id} on attempt {attempt}")
                    break

                print("FAILED")
                logger.warning(f"E2E failed for {audience}/{module_id} (attempt {attempt}): {error_msg}")

                if attempt == max_attempts:
                    module_result["defects"].append(
                        f"E2E test failed after {max_attempts} attempts for {module_name}. "
                        f"Last error: {error_msg}"
                    )
                    print(f"      Exhausted all {max_attempts} attempts")
                    break

                # Attempt resolution (snapshots + reverts internally; gate-checks the edit)
                print(f"      Resolving...", end=" ", flush=True)
                resolved, _ = resolve_e2e_failure(
                    test_path, error_msg or "Unknown error",
                    adw_id, audience, attempt, working_dir, logger,
                    cost_tracker=cost_tracker, cost_bucket=module_id,
                )

                if not resolved:
                    module_result["defects"].append(
                        f"Could not resolve E2E failure for {module_name} (attempt {attempt}). "
                        f"Error: {error_msg}"
                    )
                    print("no progress — stopping retries")
                    logger.warning(f"Resolution made no progress for {audience}/{module_id}, stopping retries")
                    break

                print("resolved — retrying")

            if module_result["passed"]:
                result["total_passed"] += 1
            elif not module_result.get("error"):
                result["total_failed"] += 1

            audience_module_results.append(module_result)
            result["module_results"].append(module_result)

        # Per-audience summary
        result["audiences"].append({
            "target_audience": audience,
            "modules": audience_module_results,
            "passed": sum(1 for m in audience_module_results if m["passed"]),
            "failed": sum(1 for m in audience_module_results if not m["passed"] and not m.get("error")),
            "skipped": sum(1 for m in audience_module_results if m.get("error")),
        })

    # 5. Commit all generated test files to main
    if generated_files:
        print(f"\n  Committing {len(generated_files)} E2E test artifact(s) to main...")
        commit_e2e_artifacts(
            generated_files, adw_id,
            f"test: add greenfield E2E tests for {adw_id}",
            working_dir, logger,
        )

    # 6. Build defect report if any failures
    failed_modules = [m for m in result["module_results"] if not m.get("passed") and m.get("defects")]
    if failed_modules:
        defect_path = build_defect_report(
            result["module_results"], adw_id, working_dir, logger,
        )
        if defect_path:
            commit_e2e_artifacts(
                [defect_path], adw_id,
                f"docs: add E2E defect report for {adw_id}",
                working_dir, logger,
            )

    # 7. Persist cost summary. Even when we don't own the tracker (parent did),
    # writing an E2E-scoped summary is useful for diagnosis.
    cost_summary_path = os.path.join(
        working_dir, "specs", "greenfields", adw_id, "e2e_cost_summary.json",
    )
    try:
        cost_tracker.write_summary(cost_summary_path, adw_id)
        result["cost_summary_path"] = cost_summary_path
        result["cost"] = cost_tracker.grand_total().to_dict()
    except Exception as e:
        logger.warning(f"Failed to write cost summary: {e}")

    if owns_tracker:
        cost_tracker.print_summary(header=f"E2E Cost Summary ({adw_id})")

    return result


def print_e2e_validation_summary(result: Dict[str, Any]) -> None:
    """Print human-readable summary of E2E validation results."""
    module_results = result.get("module_results", [])
    if not module_results:
        print("\n  No E2E tests were generated (no UI modules found).")
        return

    total_passed = result.get("total_passed", 0)
    total_failed = result.get("total_failed", 0)
    total_skipped = result.get("total_skipped", 0)

    print(f"\n--- E2E Validation Summary ---")
    print(f"  Passed: {total_passed}  Failed: {total_failed}  Skipped: {total_skipped}")

    for audience_data in result.get("audiences", []):
        audience = audience_data.get("target_audience", "?")
        label = AUDIENCE_LABELS.get(audience, audience)
        a_passed = audience_data.get("passed", 0)
        a_failed = audience_data.get("failed", 0)
        a_skipped = audience_data.get("skipped", 0)
        print(f"\n  {label}: {a_passed} passed, {a_failed} failed, {a_skipped} skipped")

        for m in audience_data.get("modules", []):
            module_name = m.get("module_name", m.get("module_id", "?"))
            if m.get("error") and not m.get("defects"):
                status = "SKIP"
            elif m.get("passed"):
                status = "PASS"
            else:
                status = "FAIL"

            attempts = m.get("total_attempts", 0)
            defect_count = len(m.get("defects", []))
            print(f"    [{status}] {module_name}: {attempts} attempt(s), {defect_count} defect(s)")

            if m.get("test_file_path"):
                print(f"           Test: {m['test_file_path']}")

            for defect in m.get("defects", []):
                msg = defect[:200] + "..." if len(defect) > 200 else defect
                print(f"           Defect: {msg}")

    if total_failed > 0:
        print(f"\n  Advisory: {total_failed} module(s) have unresolved E2E defects.")
        print(f"  See specs/greenfields/{result.get('adw_id', '?')}/E2E_DEFECTS.md for details.")


def main():
    """CLI entry point for standalone execution."""
    load_dotenv()

    # Parse arguments
    max_attempts = MAX_E2E_ATTEMPTS
    max_parallel = 4
    # Default to repo root (parent of adws/), not cwd — Playwright config,
    # node_modules, and fixtures live under app/frontend/ in the repo root.
    working_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    # Extract flags
    args = sys.argv[1:]
    filtered_args = []
    i = 0
    while i < len(args):
        if args[i] == "--working-dir" and i + 1 < len(args):
            working_dir = args[i + 1]
            i += 2
        elif args[i] == "--max-attempts" and i + 1 < len(args):
            max_attempts = int(args[i + 1])
            i += 2
        elif args[i] == "--max-parallel" and i + 1 < len(args):
            max_parallel = int(args[i + 1])
            i += 2
        elif args[i] == "--help":
            print(__doc__)
            sys.exit(0)
        else:
            filtered_args.append(args[i])
            i += 1

    if len(filtered_args) < 2:
        print(__doc__)
        sys.exit(0)

    decomposition_path = filtered_args[0]
    adw_id = filtered_args[1]

    # Setup
    logger = setup_logger(adw_id, "adw_e2e_validation_iso")
    logger.info(f"Starting E2E Validation — ADW: {adw_id}")
    logger.info(f"Decomposition: {decomposition_path}")
    logger.info(f"Working dir: {working_dir}")
    logger.info(f"Max attempts: {max_attempts}, Max parallel: {max_parallel}")

    check_env_vars(logger)

    print(f"E2E Validation — ADW: {adw_id}")
    print(f"Max attempts per module: {max_attempts}, Parallel generation: {max_parallel}")

    # Run validation
    result = run_e2e_validation(
        decomposition_path=decomposition_path,
        adw_id=adw_id,
        working_dir=working_dir,
        logger=logger,
        max_attempts=max_attempts,
        max_parallel_generation=max_parallel,
    )

    print_e2e_validation_summary(result)

    # Write result JSON for callers
    result_path = os.path.join(
        working_dir, "specs", "greenfields", adw_id, "e2e_validation_result.json"
    )
    os.makedirs(os.path.dirname(result_path), exist_ok=True)
    with open(result_path, "w") as f:
        json.dump(result, f, indent=2)
    logger.info(f"Result written to {result_path}")

    # Advisory — always exit 0
    sys.exit(0)


if __name__ == "__main__":
    main()
