# Execute Test Task

Generate tests for a rescued domain/feature.

## Arguments
- `$1` - ADW ID
- `$2` - Domain name or feature name
- `$3` - Test type (unit/integration/e2e)

## Context Files to Read
- `ai_docs/backend/context/testing.md` (for backend tests)
- `ai_docs/frontend/context/testing.md` (for frontend tests)

## Instructions

### 1. Identify Test Targets

Based on domain `$2`, identify what to test:
- Backend: Model, CRUD, API endpoints
- Frontend: Components, hooks, API integration

### 2. Backend Unit Tests

Create `app/backend/tests/test_{domain}.py`:

```python
import pytest
import uuid
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.{domain} import {DomainName}
from src.crud.{domain} import {domain}_crud
from src.schemas.{domain} import {DomainName}Create, {DomainName}Update


class Test{DomainName}CRUD:
    """Tests for {DomainName} CRUD operations."""

    @pytest.fixture
    def sample_data(self) -> {DomainName}Create:
        return {DomainName}Create(
            # ... sample field values
        )

    @pytest.mark.asyncio
    async def test_create_{domain}(
        self,
        session: AsyncSession,
        test_organization,
        sample_data,
    ):
        """Test creating a {domain}."""
        result = await {domain}_crud.create(
            session=session,
            organization_id=test_organization.id,
            data=sample_data,
        )

        assert result.id is not None
        assert result.organization_id == test_organization.id
        # ... assert other fields

    @pytest.mark.asyncio
    async def test_get_{domain}(
        self,
        session: AsyncSession,
        test_organization,
        sample_data,
    ):
        """Test getting a {domain} by ID."""
        created = await {domain}_crud.create(
            session=session,
            organization_id=test_organization.id,
            data=sample_data,
        )

        result = await {domain}_crud.get(
            session=session,
            organization_id=test_organization.id,
            id=created.id,
        )

        assert result is not None
        assert result.id == created.id

    @pytest.mark.asyncio
    async def test_get_{domain}_wrong_org(
        self,
        session: AsyncSession,
        test_organization,
        other_organization,
        sample_data,
    ):
        """Test tenant isolation - cannot access other org's data."""
        created = await {domain}_crud.create(
            session=session,
            organization_id=test_organization.id,
            data=sample_data,
        )

        # Try to access from different org
        result = await {domain}_crud.get(
            session=session,
            organization_id=other_organization.id,
            id=created.id,
        )

        assert result is None  # Should not be accessible

    @pytest.mark.asyncio
    async def test_soft_delete_{domain}(
        self,
        session: AsyncSession,
        test_organization,
        sample_data,
    ):
        """Test soft delete sets deleted_time."""
        created = await {domain}_crud.create(
            session=session,
            organization_id=test_organization.id,
            data=sample_data,
        )

        success = await {domain}_crud.delete(
            session=session,
            organization_id=test_organization.id,
            id=created.id,
        )

        assert success is True

        # Verify soft deleted
        await session.refresh(created)
        assert created.deleted_time is not None

        # Verify not returned by get
        result = await {domain}_crud.get(
            session=session,
            organization_id=test_organization.id,
            id=created.id,
        )
        assert result is None
```

### 3. Backend API Tests

Create API endpoint tests:

```python
import pytest
from httpx import AsyncClient


class Test{DomainName}API:
    """Tests for {DomainName} API endpoints."""

    @pytest.mark.asyncio
    async def test_create_{domain}_endpoint(
        self,
        client: AsyncClient,
        auth_headers,
    ):
        """Test POST /{domain}s endpoint."""
        response = await client.post(
            "/api/v1/{domain}s",
            json={...},
            headers=auth_headers,
        )

        assert response.status_code == 201
        data = response.json()
        assert "id" in data

    @pytest.mark.asyncio
    async def test_list_{domain}s_endpoint(
        self,
        client: AsyncClient,
        auth_headers,
    ):
        """Test GET /{domain}s endpoint."""
        response = await client.get(
            "/api/v1/{domain}s",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert "total" in data

    @pytest.mark.asyncio
    async def test_unauthorized_access(
        self,
        client: AsyncClient,
    ):
        """Test endpoints require authentication."""
        response = await client.get("/api/v1/{domain}s")

        assert response.status_code == 401
```

### 4. Frontend Component Tests

Create `app/frontend/src/components/features/{DomainName}.test.tsx`:

```typescript
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { {DomainName}List } from './{DomainName}List';
import { TestWrapper } from '@/test/TestWrapper';

describe('{DomainName}List', () => {
  it('renders loading state', () => {
    render(
      <TestWrapper>
        <{DomainName}List />
      </TestWrapper>
    );

    expect(screen.getByRole('progressbar')).toBeInTheDocument();
  });

  it('renders list of {domain}s', async () => {
    render(
      <TestWrapper>
        <{DomainName}List />
      </TestWrapper>
    );

    await waitFor(() => {
      expect(screen.getByText('Sample {DomainName}')).toBeInTheDocument();
    });
  });

  it('handles empty state', async () => {
    // Mock empty response
    render(
      <TestWrapper>
        <{DomainName}List />
      </TestWrapper>
    );

    await waitFor(() => {
      expect(screen.getByText(/no {domain}s found/i)).toBeInTheDocument();
    });
  });
});
```

### 5. Tenant Isolation Tests (MANDATORY)

Every CRUD operation must have a tenant isolation test:

```python
@pytest.mark.asyncio
async def test_{operation}_tenant_isolation(
    self,
    session: AsyncSession,
    test_organization,
    other_organization,
):
    """Test that {operation} respects tenant boundaries."""
    # Create in org A
    # Try to access/modify from org B
    # Assert failure/no access
```

## Output

Report:
1. Test files created
2. Test count by type
3. Coverage areas

Example:
```
Created tests:
- app/backend/tests/test_post.py (8 tests)
- app/frontend/src/components/features/PostList.test.tsx (4 tests)

Test Coverage:
- CRUD: create, get, get_multi, update, delete
- API: all endpoints + auth
- Tenant isolation: 5 tests
- Frontend: loading, list, empty, error states

Run with:
  Backend: cd app/backend && make test-fast
  Frontend: cd app/frontend && npm run test
```

## Validation

- Test files exist
- All CRUD operations have tests
- Tenant isolation tests included
- Tests pass when run

$ARGUMENTS
