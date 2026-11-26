"""Test operations for ADW workflows.

Provides shared test execution utilities for running scoped tests,
full test suites, and validation commands across ADW workflows.
"""

import subprocess
import os
import logging
import re
from typing import Tuple, List, Optional
from dataclasses import dataclass

from adw_modules.agent import execute_template
from adw_modules.data_types import AgentTemplateRequest
from adw_modules.github import make_issue_comment
from adw_modules.workflow_ops import format_issue_message


@dataclass
class TestSuiteResult:
    """Result from running a test suite."""
    name: str
    passed: bool
    output: str
    error: Optional[str] = None


@dataclass
class ValidationResult:
    """Result from running the full validation suite."""
    all_passed: bool
    backend_tests: TestSuiteResult
    frontend_build: TestSuiteResult
    backend_lint: Optional[TestSuiteResult] = None
    frontend_types: Optional[TestSuiteResult] = None

    def summary(self) -> str:
        """Generate a summary string of all results."""
        results = []
        results.append(f"Backend tests: {'PASS' if self.backend_tests.passed else 'FAIL'}")
        results.append(f"Frontend build: {'PASS' if self.frontend_build.passed else 'FAIL'}")
        if self.backend_lint:
            results.append(f"Backend lint: {'PASS' if self.backend_lint.passed else 'FAIL'}")
        if self.frontend_types:
            results.append(f"Frontend types: {'PASS' if self.frontend_types.passed else 'FAIL'}")
        return "\n".join(results)


# Patterns indicating no tests were found (not a failure)
NO_TESTS_PATTERNS = [
    "No test files found",
    "no tests ran",
    "collected 0 items",
    "no tests collected",
]


def run_scoped_tests(
    test_scope: str,
    working_dir: str,
    logger: logging.Logger,
    timeout: int = 300,
) -> Tuple[bool, str]:
    """Run tests scoped to a specific directory/pattern.

    Automatically detects backend vs frontend tests based on path patterns
    and runs the appropriate test command.

    Args:
        test_scope: Test file/directory pattern (e.g., "tests/test_api.py" or "src/components/")
        working_dir: Root working directory (worktree path)
        logger: Logger instance
        timeout: Test timeout in seconds (default 5 minutes)

    Returns:
        Tuple of (success, output_message)
    """
    logger.info(f"Running scoped tests: `{test_scope}`")

    # BUG-010 fix: Sanitize test scope to prevent path traversal
    if os.path.isabs(test_scope) or ".." in test_scope:
        logger.error(f"Invalid test scope (must be relative, no ..): {test_scope}")
        return False, f"Invalid test scope (must be relative, no ..): {test_scope}"

    # Determine test type based on scope
    if "backend" in test_scope or test_scope.startswith("tests/"):
        # Backend tests with pytest using venv directly
        test_cwd = os.path.join(working_dir, "app", "backend")
        # Normalize test_scope - strip app/backend/ prefix if present since we're already in that dir
        normalized_scope = test_scope
        if test_scope.startswith("app/backend/"):
            normalized_scope = test_scope[len("app/backend/"):]
        cmd = [".venv/bin/pytest", normalized_scope, "-v", "--tb=short"]
    elif "frontend" in test_scope or test_scope.startswith("src/"):
        # Frontend tests with npm/vitest
        test_cwd = os.path.join(working_dir, "app", "frontend")
        # Normalize test_scope - strip app/frontend/ prefix if present
        normalized_scope = test_scope
        if test_scope.startswith("app/frontend/"):
            normalized_scope = test_scope[len("app/frontend/"):]
        cmd = ["npx", "vitest", "run", normalized_scope, "--passWithNoTests"]
    else:
        # Default to backend
        test_cwd = os.path.join(working_dir, "app", "backend")
        normalized_scope = test_scope
        cmd = [".venv/bin/pytest", normalized_scope, "-v", "--tb=short"]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=test_cwd,
            timeout=timeout,
            stdin=subprocess.DEVNULL,
        )

        output = result.stdout + result.stderr
        success = result.returncode == 0

        # Treat "no test files found" as success (nothing to test in scope)
        if not success and any(pattern in output for pattern in NO_TESTS_PATTERNS):
            logger.info("No test files found in scope - treating as passed")
            return True, output

        if not success:
            logger.warning(f"Scoped tests failed: {output[:500]}")
        else:
            logger.info("Scoped tests passed")

        return success, output

    except subprocess.TimeoutExpired:
        logger.error(f"Scoped tests timed out after {timeout} seconds")
        return False, f"Tests timed out after {timeout // 60} minutes"
    except FileNotFoundError as e:
        logger.error(f"Test command not found: {e}")
        return False, f"Test command not found: {e}"
    except Exception as e:
        logger.error(f"Error running scoped tests: {e}")
        return False, str(e)


def run_backend_tests(
    working_dir: str,
    logger: logging.Logger,
    timeout: int = 600,
    use_make: bool = False,
) -> TestSuiteResult:
    """Run the backend test suite.

    Args:
        working_dir: Root working directory (worktree path)
        logger: Logger instance
        timeout: Test timeout in seconds (default 10 minutes)
        use_make: If True, use `make test`, otherwise use pytest directly (default)

    Returns:
        TestSuiteResult with pass/fail status and output
    """
    logger.info("Running backend tests")
    backend_cwd = os.path.join(working_dir, "app", "backend")

    if use_make:
        cmd = ["make", "test"]
    else:
        cmd = [".venv/bin/pytest", "tests/", "-v", "--tb=short", "-n", "8"]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=backend_cwd,
            timeout=timeout,
            stdin=subprocess.DEVNULL,
        )

        output = result.stdout + result.stderr
        passed = result.returncode == 0

        if passed:
            logger.info("Backend tests passed")
        else:
            logger.warning("Backend tests failed")

        return TestSuiteResult(
            name="backend_tests",
            passed=passed,
            output=output,
        )

    except subprocess.TimeoutExpired:
        logger.error(f"Backend tests timed out after {timeout} seconds")
        return TestSuiteResult(
            name="backend_tests",
            passed=False,
            output="",
            error=f"Tests timed out after {timeout // 60} minutes",
        )
    except Exception as e:
        logger.error(f"Error running backend tests: {e}")
        return TestSuiteResult(
            name="backend_tests",
            passed=False,
            output="",
            error=str(e),
        )


def run_backend_lint(
    working_dir: str,
    logger: logging.Logger,
    timeout: int = 120,
) -> TestSuiteResult:
    """Run backend linting (ruff).

    Args:
        working_dir: Root working directory (worktree path)
        logger: Logger instance
        timeout: Lint timeout in seconds (default 2 minutes)

    Returns:
        TestSuiteResult with pass/fail status and output
    """
    logger.info("Running backend lint")
    backend_cwd = os.path.join(working_dir, "app", "backend")

    try:
        result = subprocess.run(
            [".venv/bin/ruff", "check", "."],
            capture_output=True,
            text=True,
            cwd=backend_cwd,
            timeout=timeout,
            stdin=subprocess.DEVNULL,
        )

        output = result.stdout + result.stderr
        passed = result.returncode == 0

        if passed:
            logger.info("Backend lint passed")
        else:
            logger.warning("Backend lint failed")

        return TestSuiteResult(
            name="backend_lint",
            passed=passed,
            output=output,
        )

    except subprocess.TimeoutExpired:
        logger.error(f"Backend lint timed out after {timeout} seconds")
        return TestSuiteResult(
            name="backend_lint",
            passed=False,
            output="",
            error=f"Lint timed out after {timeout} seconds",
        )
    except Exception as e:
        logger.error(f"Error running backend lint: {e}")
        return TestSuiteResult(
            name="backend_lint",
            passed=False,
            output="",
            error=str(e),
        )


def run_frontend_build(
    working_dir: str,
    logger: logging.Logger,
    timeout: int = 300,
) -> TestSuiteResult:
    """Run frontend build (includes type checking).

    Args:
        working_dir: Root working directory (worktree path)
        logger: Logger instance
        timeout: Build timeout in seconds (default 5 minutes)

    Returns:
        TestSuiteResult with pass/fail status and output
    """
    logger.info("Running frontend build")
    frontend_cwd = os.path.join(working_dir, "app", "frontend")

    try:
        result = subprocess.run(
            ["npm", "run", "build"],
            capture_output=True,
            text=True,
            cwd=frontend_cwd,
            timeout=timeout,
            stdin=subprocess.DEVNULL,
        )

        output = result.stdout + result.stderr
        passed = result.returncode == 0

        if passed:
            logger.info("Frontend build passed")
        else:
            logger.warning("Frontend build failed")

        return TestSuiteResult(
            name="frontend_build",
            passed=passed,
            output=output,
        )

    except subprocess.TimeoutExpired:
        logger.error(f"Frontend build timed out after {timeout} seconds")
        return TestSuiteResult(
            name="frontend_build",
            passed=False,
            output="",
            error=f"Build timed out after {timeout // 60} minutes",
        )
    except Exception as e:
        logger.error(f"Error running frontend build: {e}")
        return TestSuiteResult(
            name="frontend_build",
            passed=False,
            output="",
            error=str(e),
        )


def run_frontend_typecheck(
    working_dir: str,
    logger: logging.Logger,
    timeout: int = 180,
) -> TestSuiteResult:
    """Run frontend TypeScript type checking.

    Args:
        working_dir: Root working directory (worktree path)
        logger: Logger instance
        timeout: Type check timeout in seconds (default 3 minutes)

    Returns:
        TestSuiteResult with pass/fail status and output
    """
    logger.info("Running frontend type check")
    frontend_cwd = os.path.join(working_dir, "app", "frontend")

    try:
        result = subprocess.run(
            ["npx", "tsc", "--noEmit"],
            capture_output=True,
            text=True,
            cwd=frontend_cwd,
            timeout=timeout,
            stdin=subprocess.DEVNULL,
        )

        output = result.stdout + result.stderr
        passed = result.returncode == 0

        if passed:
            logger.info("Frontend type check passed")
        else:
            logger.warning("Frontend type check failed")

        return TestSuiteResult(
            name="frontend_types",
            passed=passed,
            output=output,
        )

    except subprocess.TimeoutExpired:
        logger.error(f"Frontend type check timed out after {timeout} seconds")
        return TestSuiteResult(
            name="frontend_types",
            passed=False,
            output="",
            error=f"Type check timed out after {timeout} seconds",
        )
    except Exception as e:
        logger.error(f"Error running frontend type check: {e}")
        return TestSuiteResult(
            name="frontend_types",
            passed=False,
            output="",
            error=str(e),
        )


def run_validation_suite(
    working_dir: str,
    logger: logging.Logger,
    include_lint: bool = False,
    include_typecheck: bool = False,
) -> ValidationResult:
    """Run the full validation suite for integration testing.

    This runs backend tests and frontend build as the minimum validation.
    Optionally includes linting and type checking.

    Args:
        working_dir: Root working directory (worktree path)
        logger: Logger instance
        include_lint: If True, also run backend linting
        include_typecheck: If True, also run frontend type checking

    Returns:
        ValidationResult with all test results
    """
    logger.info("Running full validation suite")

    # Run backend tests
    backend_result = run_backend_tests(working_dir, logger)

    # Run frontend build (includes type checking in build)
    frontend_result = run_frontend_build(working_dir, logger)

    # Optional: backend lint
    lint_result = None
    if include_lint:
        lint_result = run_backend_lint(working_dir, logger)

    # Optional: explicit frontend type check
    types_result = None
    if include_typecheck:
        types_result = run_frontend_typecheck(working_dir, logger)

    # Determine overall success
    all_passed = backend_result.passed and frontend_result.passed
    if lint_result:
        all_passed = all_passed and lint_result.passed
    if types_result:
        all_passed = all_passed and types_result.passed

    result = ValidationResult(
        all_passed=all_passed,
        backend_tests=backend_result,
        frontend_build=frontend_result,
        backend_lint=lint_result,
        frontend_types=types_result,
    )

    logger.info(f"Validation suite complete: {'PASS' if all_passed else 'FAIL'}")
    logger.info(result.summary())

    return result


def run_full_test_suite(
    working_dir: str,
    logger: logging.Logger,
) -> Tuple[bool, str]:
    """Run the full test suite for integration validation.

    This is a simplified wrapper around run_validation_suite() that returns
    the same tuple format used by the legacy implementation.

    Args:
        working_dir: Root working directory (worktree path)
        logger: Logger instance

    Returns:
        Tuple of (all_passed, summary_string)
    """
    result = run_validation_suite(working_dir, logger)
    return result.all_passed, result.summary()


def run_frontend_lint(
    working_dir: str,
    logger: logging.Logger,
    timeout: int = 120,
) -> TestSuiteResult:
    """Run frontend linting (ESLint).

    Args:
        working_dir: Root working directory (worktree path)
        logger: Logger instance
        timeout: Lint timeout in seconds (default 2 minutes)

    Returns:
        TestSuiteResult with pass/fail status and output
    """
    logger.info("Running frontend lint")
    frontend_cwd = os.path.join(working_dir, "app", "frontend")

    try:
        result = subprocess.run(
            ["npm", "run", "lint"],
            capture_output=True,
            text=True,
            cwd=frontend_cwd,
            timeout=timeout,
            stdin=subprocess.DEVNULL,
        )

        output = result.stdout + result.stderr
        passed = result.returncode == 0

        if passed:
            logger.info("Frontend lint passed")
        else:
            logger.warning("Frontend lint failed")

        return TestSuiteResult(
            name="frontend_lint",
            passed=passed,
            output=output,
        )

    except subprocess.TimeoutExpired:
        logger.error(f"Frontend lint timed out after {timeout} seconds")
        return TestSuiteResult(
            name="frontend_lint",
            passed=False,
            output="",
            error=f"Lint timed out after {timeout} seconds",
        )
    except Exception as e:
        logger.error(f"Error running frontend lint: {e}")
        return TestSuiteResult(
            name="frontend_lint",
            passed=False,
            output="",
            error=str(e),
        )


@dataclass
class BuildError:
    """Individual build/type error from compilation."""
    file_path: str
    line: int
    column: int
    error_code: str
    message: str
    raw_error: str

    def to_resolution_payload(self) -> str:
        """Format error for resolution agent."""
        return (
            f"File: {self.file_path}\n"
            f"Location: Line {self.line}, Column {self.column}\n"
            f"Error Code: {self.error_code}\n"
            f"Message: {self.message}\n"
            f"Raw: {self.raw_error}"
        )


@dataclass
class BuildValidationResult:
    """Result from running build validation."""
    passed: bool
    errors: List[BuildError]
    raw_output: str

    def summary(self) -> str:
        """Generate summary of build errors."""
        if self.passed:
            return "Build validation passed"
        return f"Build validation failed with {len(self.errors)} error(s)"


def parse_build_errors(output: str) -> List[BuildError]:
    """Parse TypeScript/build errors from compiler output.

    Parses errors in the format:
    src/file.tsx(10,5): error TS2741: Message here

    Args:
        output: Raw build output containing error messages

    Returns:
        List of BuildError objects
    """
    import re

    errors = []
    # Pattern matches: file(line,col): error TSxxxx: message
    # Also matches: file:line:col - error TSxxxx: message (alternate format)
    pattern = r'([^\s(]+)\((\d+),(\d+)\):\s*error\s+(TS\d+):\s*(.+?)(?=\n[^\s]|\Z)'
    alt_pattern = r'([^\s:]+):(\d+):(\d+)\s*-\s*error\s+(TS\d+):\s*(.+?)(?=\n[^\s]|\Z)'

    for match in re.finditer(pattern, output, re.MULTILINE | re.DOTALL):
        file_path, line, column, error_code, message = match.groups()
        errors.append(BuildError(
            file_path=file_path.strip(),
            line=int(line),
            column=int(column),
            error_code=error_code,
            message=message.strip(),
            raw_error=match.group(0).strip(),
        ))

    # Try alternate pattern if no matches
    if not errors:
        for match in re.finditer(alt_pattern, output, re.MULTILINE | re.DOTALL):
            file_path, line, column, error_code, message = match.groups()
            errors.append(BuildError(
                file_path=file_path.strip(),
                line=int(line),
                column=int(column),
                error_code=error_code,
                message=message.strip(),
                raw_error=match.group(0).strip(),
            ))

    return errors


def run_build_validation(
    working_dir: str,
    logger: logging.Logger,
    timeout: int = 300,
) -> BuildValidationResult:
    """Run build validation and return structured errors.

    Runs the frontend build (which includes TypeScript compilation)
    and parses any errors into structured BuildError objects.

    Args:
        working_dir: Root working directory (worktree path)
        logger: Logger instance
        timeout: Build timeout in seconds (default 5 minutes)

    Returns:
        BuildValidationResult with pass/fail status and parsed errors
    """
    logger.info("Running build validation")

    # Run frontend build
    build_result = run_frontend_build(working_dir, logger, timeout)

    if build_result.passed:
        return BuildValidationResult(
            passed=True,
            errors=[],
            raw_output=build_result.output,
        )

    # Parse errors from build output
    errors = parse_build_errors(build_result.output)

    # Deduplicate errors by file+line+error_code
    seen = set()
    unique_errors = []
    for error in errors:
        key = (error.file_path, error.line, error.error_code)
        if key not in seen:
            seen.add(key)
            unique_errors.append(error)

    logger.warning(f"Build validation failed with {len(unique_errors)} unique error(s)")

    return BuildValidationResult(
        passed=False,
        errors=unique_errors,
        raw_output=build_result.output,
    )


# Pattern to match failed pytest tests
# Matches: FAILED tests/unit_tests/test_foo.py::test_bar - AssertionError
FAILED_TEST_PATTERN = re.compile(r'FAILED\s+([\w/.\_-]+::\w+)')


@dataclass
class FailedTest:
    """A failed test from pytest output."""
    test_path: str  # Full path like tests/unit_tests/test_foo.py::test_bar

    @property
    def file_path(self) -> str:
        """Extract file path from test path."""
        return self.test_path.split("::")[0]

    @property
    def test_name(self) -> str:
        """Extract test function name from test path."""
        parts = self.test_path.split("::")
        return parts[-1] if len(parts) > 1 else self.test_path


def parse_failed_tests(pytest_output: str) -> List[FailedTest]:
    """Parse pytest output to extract failed test names.

    Args:
        pytest_output: Raw pytest output containing test results

    Returns:
        List of FailedTest objects
    """
    matches = FAILED_TEST_PATTERN.findall(pytest_output)
    return [FailedTest(test_path=match) for match in matches]


def run_full_test_suite_with_resolution(
    issue_number: str,
    adw_id: str,
    working_dir: str,
    logger: logging.Logger,
    max_attempts: int = 3,
    step: Optional[Tuple[str, Optional[str]]] = None,
) -> Tuple[bool, str]:
    """Run full test suite with automatic failure resolution.

    Runs the test suite and if failures occur, attempts to resolve them
    using the /resolve_failed_test agent. Retries up to max_attempts times.

    Args:
        issue_number: GitHub issue number for comments
        adw_id: ADW workflow ID
        working_dir: Root working directory (worktree path)
        logger: Logger instance
        max_attempts: Maximum resolution attempts (default 3)
        step: (key, parent) of the step to record each attempt under (adw_modules.steps), or None

    Returns:
        Tuple of (all_passed, summary_string)
    """
    from adw_modules import steps
    attempt = 0
    last_result: Optional[ValidationResult] = None

    while attempt < max_attempts:
        attempt += 1
        logger.info(f"\n=== Full Test Suite Attempt {attempt}/{max_attempts} ===")
        if step and attempt > 1:
            steps.record(adw_id, step[0], "running", note=f"Attempt {attempt}", parent=step[1])

        # Run the validation suite
        result = run_validation_suite(working_dir, logger)
        last_result = result
        if step and not result.all_passed:
            steps.record(adw_id, step[0], "failed", note=result.summary(), parent=step[1])

        # If all passed, we're done
        if result.all_passed:
            logger.info("All tests passed")
            return True, result.summary()

        # If this is the last attempt, stop
        if attempt == max_attempts:
            logger.warning(f"Reached maximum attempts ({max_attempts}), stopping")
            break

        # Check if backend tests failed (we can only resolve test failures)
        if not result.backend_tests.passed:
            # Parse failed tests from backend output
            failed_tests = parse_failed_tests(result.backend_tests.output)

            if not failed_tests:
                logger.warning("Backend tests failed but could not parse failed test names")
                # Can't resolve what we can't identify
                break

            logger.info(f"Found {len(failed_tests)} failed test(s), attempting resolution")

            make_issue_comment(
                issue_number,
                format_issue_message(
                    adw_id,
                    "test_resolver",
                    f"🔧 Found {len(failed_tests)} failed test(s). Attempting resolution (attempt {attempt}/{max_attempts})...",
                ),
            )

            # Attempt to resolve each failed test
            resolved_count = 0
            for idx, failed_test in enumerate(failed_tests):
                logger.info(f"Resolving failed test {idx + 1}/{len(failed_tests)}: {failed_test.test_path}")

                try:
                    request = AgentTemplateRequest(
                        agent_name=f"test_resolver_integration_{attempt}_{idx}",
                        slash_command="/resolve_failed_test",
                        args=[failed_test.test_path],
                        adw_id=adw_id,
                        model="sonnet",
                        working_dir=working_dir,
                    )
                    response = execute_template(request)

                    if response.success:
                        resolved_count += 1
                        logger.info(f"Resolved: {failed_test.test_path}")
                    else:
                        logger.warning(f"Failed to resolve: {failed_test.test_path}")
                except Exception as e:
                    logger.error(f"Error resolving {failed_test.test_path}: {e}")

            if resolved_count > 0:
                make_issue_comment(
                    issue_number,
                    format_issue_message(
                        adw_id,
                        "test_resolver",
                        f"✅ Resolved {resolved_count}/{len(failed_tests)} test(s). Retrying test suite...",
                    ),
                )
                logger.info(f"Resolved {resolved_count}/{len(failed_tests)} tests, retrying")
            else:
                # No tests were resolved, no point retrying
                logger.warning("No tests were resolved, stopping retry attempts")
                break
        else:
            # Backend passed but frontend failed - we can't auto-resolve frontend build errors here
            # (that's handled by run_build_with_resolution in the workflow)
            logger.warning("Backend tests passed but frontend build failed - cannot auto-resolve")
            break

    # Return final result
    if last_result:
        return last_result.all_passed, last_result.summary()
    else:
        return False, "No test results available"
