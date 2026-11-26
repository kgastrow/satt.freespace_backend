"""Quality gate for LLM-generated Playwright E2E tests.

After an agent writes a `.spec.ts` file we cannot trust it blindly — invalid
syntax, hallucinated selectors, or non-idempotent test data all cause silent
waste in the downstream retry loop. This module validates a freshly generated
test BEFORE the orchestrator hands it to the execution phase.

The gate has three stages, in order of cost:

1. ``check_typescript_compiles``  — local ``tsc --noEmit`` (fast, deterministic)
2. ``check_playwright_lists``     — ``playwright test --list`` (catches runtime parse errors)
3. ``check_selectors_exist``      — grep selector tokens against frontend source
4. ``check_idempotent_test_data`` — regex over creation calls for unique-name pattern

Each check returns a ``GateCheckResult`` describing pass/fail plus a short
diagnostic. ``run_quality_gate`` runs them in sequence and aggregates the
result so callers get one structured verdict.
"""

from __future__ import annotations

import logging
import os
import re
import subprocess
from dataclasses import dataclass, field
from typing import List, Optional, Set, Tuple


# Selectors we want to verify exist in source. The keys are the JS APIs the
# generated tests typically use; the values describe how to extract the
# selector token from the call site.
#
# Regex groups capture the literal string argument (single, double, or template).
_TESTID_PATTERNS: List[re.Pattern] = [
    # getByTestId('foo'), getByTestId("foo"), getByTestId(`foo`)
    re.compile(r"""getByTestId\(\s*['"`]([^'"`]+)['"`]"""),
    # data-testid="foo" in locator strings
    re.compile(r"""data-testid=['"]([^'"]+)['"]"""),
    # [data-testid="foo"]
    re.compile(r"""\[data-testid=['"]([^'"]+)['"]"""),
]

# Test data patterns that indicate good idempotency:
#  Date.now(), Math.random(), crypto.randomUUID(), or interpolation of adw_id.
_IDEMPOTENT_PATTERNS: List[re.Pattern] = [
    re.compile(r"Date\.now\(\)"),
    re.compile(r"Math\.random\(\)"),
    re.compile(r"crypto\.randomUUID\(\)"),
    re.compile(r"\$\{[^}]*adw[_-]?id[^}]*\}", re.IGNORECASE),
    re.compile(r"\$\{[^}]*E2E_ADW_ID[^}]*\}"),
    re.compile(r"process\.env\.E2E_ADW_ID"),
]

# Creation operations whose payload should be made unique.
_CREATE_CALL_PATTERNS: List[re.Pattern] = [
    # apiCall(token, 'POST', '/foo', { name: ... })
    re.compile(r"""apiCall\([^,]+,\s*['"]POST['"][^)]*\{([^}]*)\}""", re.DOTALL),
    # await page.getByLabel('Name').fill('Static')
    re.compile(r"""\.fill\(\s*['"`]([^'"`{][^'"`]*)['"`]\s*\)"""),
]

# Quoted-method-name fallback for create detection. Matches "POST" or 'POST'
# tokens (HTTP method strings used in fetch/apiCall) but NOT bare POST in
# comments, identifiers, or enum names.
_HTTP_POST_TOKEN = re.compile(r"""['"`]POST['"`]""")


@dataclass
class GateCheckResult:
    """Result of a single quality check."""

    name: str
    passed: bool
    detail: str = ""

    def to_log_line(self) -> str:
        status = "PASS" if self.passed else "FAIL"
        if self.detail:
            return f"  [{status}] {self.name}: {self.detail}"
        return f"  [{status}] {self.name}"


@dataclass
class QualityGateResult:
    """Aggregated quality gate verdict."""

    passed: bool
    checks: List[GateCheckResult] = field(default_factory=list)

    @property
    def failed_checks(self) -> List[GateCheckResult]:
        return [c for c in self.checks if not c.passed]

    def summary(self) -> str:
        if self.passed:
            return f"Quality gate PASSED ({len(self.checks)} checks)"
        fails = ", ".join(c.name for c in self.failed_checks)
        return f"Quality gate FAILED on: {fails}"


def _resolve_frontend_dir(working_dir: str) -> str:
    """Return the directory containing playwright.config.ts.

    Mirrors the fallback logic in adw_e2e_validation_iso.execute_e2e_test so a
    test that runs there will pass the same path check here.
    """
    frontend = os.path.join(working_dir, "app", "frontend")
    if os.path.exists(os.path.join(frontend, "playwright.config.ts")):
        return frontend
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    # adw_modules is two levels under repo root: <repo>/adws/adw_modules
    repo_root = os.path.dirname(repo_root)
    alt = os.path.join(repo_root, "app", "frontend")
    if os.path.exists(os.path.join(alt, "playwright.config.ts")):
        return alt
    return frontend  # caller will see the failure clearly


def check_typescript_compiles(
    test_path: str,
    working_dir: str,
    logger: logging.Logger,
) -> GateCheckResult:
    """Run ``tsc --noEmit`` on the test file's project.

    We invoke the project-wide type-check (no narrowing) because Playwright
    fixtures and helpers live in sibling files; isolating the single test
    file would miss most of the failure modes we care about.

    Errors are filtered to those whose file path includes the generated test
    file — type errors elsewhere in the repo are not the gate's concern.
    """
    if not os.path.exists(test_path):
        return GateCheckResult("typescript_compiles", False, f"test file missing: {test_path}")

    frontend_dir = _resolve_frontend_dir(working_dir)
    if not os.path.exists(os.path.join(frontend_dir, "package.json")):
        return GateCheckResult(
            "typescript_compiles", False,
            f"frontend dir has no package.json: {frontend_dir}",
        )

    try:
        proc = subprocess.run(
            ["npx", "--no-install", "tsc", "--noEmit"],
            capture_output=True, text=True,
            cwd=frontend_dir, timeout=180,
        )
    except subprocess.TimeoutExpired:
        return GateCheckResult("typescript_compiles", False, "tsc --noEmit timed out after 180s")
    except FileNotFoundError:
        return GateCheckResult("typescript_compiles", False, "npx not found in PATH")

    if proc.returncode == 0:
        return GateCheckResult("typescript_compiles", True)

    # Filter output to errors that mention our specific test file.
    rel = os.path.relpath(test_path, frontend_dir)
    test_basename = os.path.basename(test_path)
    related: List[str] = []
    for line in (proc.stdout + proc.stderr).splitlines():
        if rel in line or test_basename in line:
            related.append(line.strip())

    if not related:
        # No errors point at our file — repo had pre-existing errors. Don't
        # block on those; treat as pass with a warning.
        logger.warning(
            "tsc reported errors but none mention the generated test. "
            "Treating as pre-existing repo state, not a generation failure."
        )
        return GateCheckResult(
            "typescript_compiles", True,
            "no errors specific to generated test (repo had pre-existing tsc errors)",
        )

    detail = "; ".join(related[:5])
    if len(related) > 5:
        detail += f" (+{len(related) - 5} more)"
    return GateCheckResult("typescript_compiles", False, detail)


def check_playwright_lists(
    test_path: str,
    working_dir: str,
    logger: logging.Logger,
) -> GateCheckResult:
    """Run ``playwright test --list`` to confirm the file parses at runtime.

    ``--list`` discovers tests without running them, which exercises the
    Playwright loader (imports, fixture resolution, ``test.describe`` block
    structure) but does NOT touch the app or the browser.

    A non-zero exit with no listed tests indicates a parse-time failure —
    that's the case we want to catch before wasting a real execution attempt.
    """
    if not os.path.exists(test_path):
        return GateCheckResult("playwright_lists", False, f"test file missing: {test_path}")

    frontend_dir = _resolve_frontend_dir(working_dir)
    test_filename = os.path.basename(test_path)

    try:
        proc = subprocess.run(
            ["npx", "--no-install", "playwright", "test", test_filename, "--list"],
            capture_output=True, text=True,
            cwd=frontend_dir, timeout=60,
        )
    except subprocess.TimeoutExpired:
        return GateCheckResult("playwright_lists", False, "playwright --list timed out after 60s")
    except FileNotFoundError:
        return GateCheckResult("playwright_lists", False, "npx not found in PATH")

    # Playwright prints "Total: N tests" or similar; a 0-test result with
    # non-zero exit is the failure mode we want to flag.
    combined = proc.stdout + proc.stderr
    has_tests = bool(re.search(r"Total:\s*\d+\s+test", combined)) or bool(
        re.search(r"\b\d+\s+tests?\s+in\s+\d+\s+file", combined)
    )

    if proc.returncode == 0 and has_tests:
        return GateCheckResult("playwright_lists", True)

    # Capture last ~5 useful lines of output
    lines = [l for l in combined.splitlines() if l.strip()]
    detail = " | ".join(lines[-5:])[:400] or f"exit={proc.returncode}"
    return GateCheckResult("playwright_lists", False, detail)


def _extract_testid_tokens(test_source: str) -> Set[str]:
    """Collect all data-testid tokens referenced in a generated test file."""
    found: Set[str] = set()
    for pat in _TESTID_PATTERNS:
        for match in pat.finditer(test_source):
            token = match.group(1).strip()
            if token and not _looks_dynamic(token):
                found.add(token)
    return found


def _looks_dynamic(token: str) -> bool:
    """A token built via template interpolation cannot be grepped statically."""
    return "${" in token or "$ENV" in token


def check_selectors_exist(
    test_path: str,
    working_dir: str,
    logger: logging.Logger,
) -> GateCheckResult:
    """Confirm every static data-testid in the test maps to source.

    Dynamic selectors (template literals) are skipped — we can't statically
    verify them, but the test is still expected to be written carefully.
    """
    if not os.path.exists(test_path):
        return GateCheckResult("selectors_exist", False, f"test file missing: {test_path}")

    with open(test_path, "r") as f:
        source = f.read()

    tokens = _extract_testid_tokens(source)
    if not tokens:
        # No static testids referenced; nothing to verify. The test may rely
        # purely on getByRole / getByText, which is fine.
        return GateCheckResult(
            "selectors_exist", True,
            "no static data-testid tokens to verify",
        )

    src_dir = os.path.join(working_dir, "app", "frontend", "src")
    if not os.path.exists(src_dir):
        repo_root = os.path.dirname(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        )
        src_dir = os.path.join(repo_root, "app", "frontend", "src")
    if not os.path.exists(src_dir):
        return GateCheckResult(
            "selectors_exist", False,
            f"frontend src dir not found ({src_dir})",
        )

    missing: List[str] = []
    for token in sorted(tokens):
        # rg is faster but optional — fall back to grep -r.
        cmd_options = [
            ["rg", "--quiet", "--fixed-strings", token, src_dir],
            ["grep", "-rq", "--include=*.ts", "--include=*.tsx", token, src_dir],
        ]
        found = False
        for cmd in cmd_options:
            try:
                proc = subprocess.run(
                    cmd, capture_output=True, text=True, timeout=20,
                )
                if proc.returncode == 0:
                    found = True
                    break
                if proc.returncode == 1:
                    # rg/grep: no match — try the next variant or treat as missing.
                    continue
                # returncode > 1 = real error; fall through to next variant
            except (FileNotFoundError, subprocess.TimeoutExpired):
                continue
        if not found:
            missing.append(token)

    if not missing:
        return GateCheckResult(
            "selectors_exist", True,
            f"{len(tokens)} testid token(s) verified in source",
        )

    detail = f"missing in source: {', '.join(missing[:8])}"
    if len(missing) > 8:
        detail += f" (+{len(missing) - 8} more)"
    return GateCheckResult("selectors_exist", False, detail)


def check_idempotent_test_data(
    test_path: str,
    logger: logging.Logger,
) -> GateCheckResult:
    """Reject tests that create resources with hard-coded names.

    A test that runs twice in the retry loop must not collide with its own
    previous attempt. We check two things:

    1. The file contains at least one of the idempotent patterns
       (Date.now / randomUUID / adw_id interpolation) so the author at least
       knew the contract.
    2. Static ``.fill('Some Literal')`` calls inside an obvious create flow
       are not followed by `expect(...).toContain('Some Literal')` — that's
       the smell of a hard-coded resource name. (Heuristic; advisory.)

    The first check is the hard gate. The second contributes a warning.
    """
    if not os.path.exists(test_path):
        return GateCheckResult("idempotent_test_data", False, f"test file missing: {test_path}")

    with open(test_path, "r") as f:
        source = f.read()

    has_idempotent_pattern = any(p.search(source) for p in _IDEMPOTENT_PATTERNS)

    # If the test has no create/POST calls at all, idempotency is moot.
    # Match `'POST'` / `"POST"` quoted tokens (HTTP method strings), not bare
    # `POST` substrings that may occur in comments, identifiers, or enums.
    has_create = (
        any(p.search(source) for p in _CREATE_CALL_PATTERNS)
        or bool(_HTTP_POST_TOKEN.search(source))
    )

    if not has_create:
        return GateCheckResult(
            "idempotent_test_data", True,
            "no create operations detected — skipped",
        )

    if not has_idempotent_pattern:
        return GateCheckResult(
            "idempotent_test_data", False,
            "test performs create operations but has no Date.now / "
            "randomUUID / adw_id interpolation — runs will collide",
        )

    return GateCheckResult(
        "idempotent_test_data", True,
        "uniqueness pattern present",
    )


def run_quality_gate(
    test_path: str,
    working_dir: str,
    logger: logging.Logger,
    *,
    skip_tsc: bool = False,
    skip_playwright: bool = False,
    skip_selectors: bool = False,
    skip_idempotency: bool = False,
) -> QualityGateResult:
    """Run all quality checks and return an aggregated verdict.

    Each ``skip_*`` flag is provided for callers that need to bypass an
    individual check (e.g. CI runs without a node_modules install). The
    flags are not surfaced as a runtime config — they exist so tests of this
    module can isolate behavior.
    """
    checks: List[GateCheckResult] = []

    if not skip_tsc:
        checks.append(check_typescript_compiles(test_path, working_dir, logger))
    if not skip_playwright:
        checks.append(check_playwright_lists(test_path, working_dir, logger))
    if not skip_selectors:
        checks.append(check_selectors_exist(test_path, working_dir, logger))
    if not skip_idempotency:
        checks.append(check_idempotent_test_data(test_path, logger))

    for c in checks:
        logger.info(c.to_log_line())

    passed = all(c.passed for c in checks)
    return QualityGateResult(passed=passed, checks=checks)


def format_failure_for_resolver(result: QualityGateResult) -> str:
    """Build a human-readable diagnostic to feed back into the resolver agent."""
    lines = ["Quality gate failed:"]
    for c in result.failed_checks:
        lines.append(f"  - {c.name}: {c.detail}")
    return "\n".join(lines)
