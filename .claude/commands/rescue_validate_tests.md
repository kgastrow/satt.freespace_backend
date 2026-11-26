# Validate Tests

Run all tests for the rescued project and report results.

## Arguments
- `$1` - ADW ID

## Instructions

### 1. Run Backend Tests

```bash
cd app/backend && make test-fast
```

Capture:
- Total tests run
- Passed count
- Failed count
- Error details for failures

### 2. Run Frontend Tests

```bash
cd app/frontend && npm run test -- --reporter=json
```

Capture:
- Total tests run
- Passed count
- Failed count
- Error details for failures

### 3. Run Linting

Backend:
```bash
cd app/backend && make lint
```

Frontend:
```bash
cd app/frontend && npm run lint
```

### 4. Run Type Checking

Backend:
```bash
cd app/backend && mypy src/
```

Frontend:
```bash
cd app/frontend && npm run build:only
```

### 5. Analyze Results

Categorize failures:
- **Critical**: Tests for core functionality
- **Important**: Tests for rescued features
- **Minor**: Edge cases, cosmetic issues

### 6. Generate Report

## Output

Create `rescue/test_results.json`:

```json
{
  "timestamp": "2024-01-15T10:30:00Z",
  "backend": {
    "tests_run": 45,
    "passed": 42,
    "failed": 3,
    "skipped": 0,
    "duration_seconds": 12.5,
    "failures": [
      {
        "test": "test_post.py::TestPostCRUD::test_create_post",
        "error": "AssertionError: Expected 201, got 500",
        "category": "critical",
        "file": "app/backend/tests/test_post.py",
        "line": 45
      }
    ],
    "lint_passed": true,
    "lint_errors": [],
    "type_check_passed": true,
    "type_errors": []
  },
  "frontend": {
    "tests_run": 28,
    "passed": 26,
    "failed": 2,
    "skipped": 0,
    "duration_seconds": 8.3,
    "failures": [
      {
        "test": "PostList.test.tsx::renders list of posts",
        "error": "Expected element not found",
        "category": "important",
        "file": "src/components/features/PostList.test.tsx",
        "line": 32
      }
    ],
    "lint_passed": true,
    "lint_errors": [],
    "build_passed": true,
    "build_errors": []
  },
  "summary": {
    "total_tests": 73,
    "total_passed": 68,
    "total_failed": 5,
    "pass_rate": 93.15,
    "critical_failures": 1,
    "important_failures": 2,
    "minor_failures": 2,
    "all_lint_passed": true,
    "all_types_passed": true
  }
}
```

Report summary to stdout:

```
=== TEST VALIDATION RESULTS ===

Backend: 42/45 passed (93%)
  - 3 failures (1 critical)

Frontend: 26/28 passed (93%)
  - 2 failures (1 important)

Overall: 68/73 passed (93.15%)

Critical Failures:
  1. test_post.py::test_create_post - API returns 500

Linting: PASS
Type Checking: PASS

Recommendation: Fix critical failures before proceeding
```

## Validation

- Test results file exists
- All test suites were executed
- Failure details include file and line
- Categories assigned to failures
- Pass rate calculated correctly

$ARGUMENTS
