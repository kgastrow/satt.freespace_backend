# Write Tests from Spec

Create all test files specified in a plan's Testing Strategy section. This command ensures that tests are written before they are run.

## Variables

spec_file: $1

## Instructions

### 1. Load Context

- Read `.claude/commands/conditional_context.md` and load relevant context for testing
- Read `ai_docs/backend/context/multitenancy.md` if the spec involves tenant-scoped data

### 2. Parse the Spec

- Read the spec file provided in `spec_file`
- Extract the `Testing Strategy` section (includes Unit Tests, Integration Tests, Edge Cases, Multi-tenancy Isolation Tests)
- Also check for test requirements in `Step by Step Tasks` sections (e.g., "Create test file...")
- Identify all test files that should be created

### 3. Analyze Implementation

- Run `git diff origin/main --name-only` to see what files were implemented
- Read the new/modified implementation files to understand what needs to be tested
- Map implementation files to required test files:
  - Models in `src/models/` → Tests in `tests/unit_tests/` or `tests/crud_tests/`
  - CRUD in `src/crud/` → Tests in `tests/crud_tests/` or `tests/unit_tests/`
  - Services in `src/services/` → Tests in `tests/unit_tests/` or `tests/services_tests/`
  - API endpoints in `src/api/` → Tests in `tests/api_tests/`

### 4. Check Existing Tests

- For each required test file, check if it already exists
- If it exists, verify it covers the requirements from the Testing Strategy
- Track which tests need to be created vs updated

### 5. Create Test Files

For each missing test file, create comprehensive tests following these patterns:

#### Backend Test Patterns

**CRUD Tests** (`app/backend/tests/crud_tests/` or `tests/unit_tests/`):
```python
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.crud.{module} import {crud_functions}
from src.models.{model} import {Model}
from tests.conftest import test_organization, test_user  # Use existing fixtures


class Test{Operation}{Model}:
    """Test {operation} operations for {Model}."""

    @pytest.mark.asyncio
    async def test_{operation}_success(self, db_session: AsyncSession, test_organization):
        """Test successful {operation}."""
        # Arrange
        # Act
        # Assert

    @pytest.mark.asyncio
    async def test_{operation}_not_found(self, db_session: AsyncSession, test_organization):
        """Test {operation} with non-existent record."""
        # Test error handling

    @pytest.mark.asyncio
    async def test_multi_tenancy_isolation(self, db_session: AsyncSession):
        """Test that organization A cannot access organization B's data."""
        # Create data for org A
        # Try to access from org B context
        # Assert isolation
```

**API Tests** (`app/backend/tests/api_tests/`):
```python
import pytest
from httpx import AsyncClient

from tests.conftest import test_client, authenticated_client  # Use existing fixtures


class Test{Endpoint}Endpoint:
    """Test {endpoint} API endpoint."""

    @pytest.mark.asyncio
    async def test_{endpoint}_success(self, authenticated_client: AsyncClient):
        """Test successful {endpoint} request."""
        response = await authenticated_client.{method}("{path}")
        assert response.status_code == {expected_status}

    @pytest.mark.asyncio
    async def test_{endpoint}_unauthorized(self, test_client: AsyncClient):
        """Test {endpoint} without authentication."""
        response = await test_client.{method}("{path}")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_{endpoint}_validation_error(self, authenticated_client: AsyncClient):
        """Test {endpoint} with invalid input."""
        # Test validation
```

**Service Tests** (`app/backend/tests/unit_tests/` or `tests/services_tests/`):
```python
import pytest
from unittest.mock import AsyncMock, patch

from src.services.{module} import {service_functions}


class Test{Service}Service:
    """Test {Service} service functions."""

    @pytest.mark.asyncio
    async def test_{function}_success(self):
        """Test successful {function} execution."""
        # Mock external dependencies
        # Call function
        # Assert results

    @pytest.mark.asyncio
    async def test_{function}_error_handling(self):
        """Test {function} error handling."""
        # Mock error conditions
        # Assert proper error handling
```

#### Test Content Guidelines

- Use `pytest.mark.asyncio` for all async tests
- Use existing fixtures from `tests/conftest.py` (read it first)
- Mock external APIs using `respx` for HTTP or `unittest.mock` for other dependencies
- Include docstrings explaining what each test validates
- Test both success and failure cases
- For tenant-scoped features, ALWAYS include multi-tenancy isolation tests
- Follow existing test patterns in the codebase (read similar test files first)

### 6. Verify Test Files

After creating tests:
- Run `cd app/backend && uv run python -m py_compile tests/**/*.py` to verify syntax
- Run `cd app/backend && uv run ruff check tests/` to check linting

### 7. Multi-Tenancy Checklist

If the spec involves tenant-scoped models (with `organization_id`), ensure tests include:
- [ ] Test that CRUD operations filter by `organization_id`
- [ ] Test that Organization A cannot access Organization B's data
- [ ] Test that API endpoints enforce tenant isolation
- [ ] Test soft delete behavior (`deleted_time`) is respected

## Report

Return a JSON object with the following structure:

```json
{
  "tests_created": [
    {
      "file_path": "app/backend/tests/api_tests/test_example.py",
      "line_count": 150,
      "test_classes": ["TestExampleEndpoint"],
      "test_count": 8
    }
  ],
  "tests_updated": [
    {
      "file_path": "app/backend/tests/unit_tests/test_existing.py",
      "tests_added": 3
    }
  ],
  "tests_skipped": [
    {
      "file_path": "app/backend/tests/api_tests/test_auth.py",
      "reason": "Already exists with full coverage"
    }
  ],
  "validation": {
    "syntax_check": "passed",
    "lint_check": "passed"
  },
  "summary": "Created 3 test files with 24 tests covering CRUD, API, and service layers"
}
```
