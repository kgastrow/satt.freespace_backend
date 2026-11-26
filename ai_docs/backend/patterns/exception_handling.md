# Exception Handling Patterns

Best practices for exception handling in the backend. Broad `except Exception` catches hide bugs and make debugging difficult.

## The Problem: Broad Exception Catches

Many files currently use patterns like:

```python
# ANTI-PATTERN - hides bugs
try:
    result = do_something()
except Exception:
    pass  # Silently swallows ALL errors

# ANTI-PATTERN - loses error context
try:
    result = do_something()
except Exception as e:
    logger.warning(f"Error: {e}")
    return None  # Caller never knows what failed
```

These patterns:
- Hide programming errors (AttributeError, TypeError, KeyError)
- Make debugging impossible (no stack trace)
- Mask configuration issues (ImportError, ConnectionError)
- Prevent proper error propagation to callers

## Correct Patterns

### 1. API Endpoint Exception Handling

API endpoints should follow the 3-tier exception pattern established in `src/api/`:

```python
import traceback
from fastapi import APIRouter, HTTPException, Request, status
from src.core.exceptions import create_http_exception
from src.logger.logger import Logger

@router.post("")
async def create_resource(
    request: CreateResourceRequest,
    http_request: Request,
    current_user: Annotated[CurrentUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_session)]
):
    try:
        result = await create_resource_crud(session, request.model_dump())
        return ResourceResponse(id=str(result.id))

    # Tier 1: Business logic errors -> 400
    except ValueError as e:
        raise create_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
            detail_code="validation.error",
        )

    # Tier 2: Re-raise HTTP exceptions as-is
    except HTTPException:
        raise

    # Tier 3: Unexpected errors -> 500 with full logging
    except Exception as e:
        error_tb = traceback.format_exc()
        Logger.error(f"Unexpected error in create_resource: {e}\n{error_tb}")
        http_request.state.error_traceback = error_tb  # For request logging middleware
        raise create_http_exception(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
            detail_code="common.internal_error",
        )
```

**Why `http_request.state.error_traceback`?** The request logging middleware captures this for failed requests, enabling debugging from logs.

### 2. Service Layer Exception Handling

Services should catch specific exceptions and either handle or re-raise:

```python
from redis.exceptions import RedisError, ConnectionError as RedisConnectionError
from sqlalchemy.exc import SQLAlchemyError

async def get_cached_data(key: str) -> Optional[dict]:
    """Get data from cache, returns None on cache miss or error."""
    try:
        data = await redis_client.get(key)
        if data:
            return json.loads(data)
        return None

    # Catch specific Redis errors
    except RedisConnectionError as e:
        logger.warning(f"Redis connection error, cache unavailable: {e}")
        return None

    except RedisError as e:
        logger.warning(f"Redis error getting {key}: {e}")
        record_cache_error("get", key)
        return None

    # Catch JSON decode errors separately
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in cache for {key}: {e}")
        return None

    # Let other exceptions propagate - they indicate bugs
```

### 3. Background Job Exception Handling

Background jobs should log errors with context but may continue processing other items:

```python
async def process_batch(items: list[Item]) -> BatchResult:
    """Process items, continuing on individual failures."""
    results = []
    errors = []

    for item in items:
        try:
            result = await process_single_item(item)
            results.append(result)

        # Expected failure modes for individual items
        except ValidationError as e:
            logger.warning(f"Validation failed for item {item.id}: {e}")
            errors.append({"item_id": str(item.id), "error": str(e)})

        except ExternalServiceError as e:
            logger.error(f"External service failed for item {item.id}: {e}")
            errors.append({"item_id": str(item.id), "error": "service_unavailable"})

        # Programming errors should fail the entire batch
        except (TypeError, AttributeError, KeyError) as e:
            logger.exception(f"Bug in process_single_item for item {item.id}")
            raise  # Re-raise to fail the job

    return BatchResult(processed=results, errors=errors)
```

### 4. Utility Function Exception Handling

Low-level utilities should be specific about what they catch:

```python
def parse_config_value(value: str, expected_type: type) -> Any:
    """Parse a config value to the expected type."""
    try:
        if expected_type == int:
            return int(value)
        elif expected_type == float:
            return float(value)
        elif expected_type == bool:
            return value.lower() in ("true", "1", "yes")
        else:
            return value
    except (ValueError, AttributeError) as e:
        raise ConfigurationError(f"Cannot parse '{value}' as {expected_type.__name__}: {e}")
```

## When Broad Catches Are Acceptable

Broad `except Exception` is acceptable ONLY at:

### 1. Top-Level Request Handlers (Middleware)

```python
class ErrorHandlingMiddleware(BaseHTTPMiddleware):
    """Global error handler - catches everything as last resort."""

    async def dispatch(self, request: Request, call_next):
        try:
            return await call_next(request)
        except Exception as e:
            # This is the last line of defense
            logger.exception(f"Unhandled exception in request: {request.url.path}")
            return JSONResponse(
                status_code=500,
                content={"detail": "Internal server error"}
            )
```

### 2. Graceful Degradation for Optional Features

```python
async def get_optional_metrics() -> dict:
    """Get metrics if available, empty dict otherwise."""
    try:
        # Optional external service - ok to fail silently
        return await metrics_service.collect()
    except Exception:
        # Metrics are optional, don't fail the request
        logger.debug("Metrics collection failed, returning empty")
        return {}
```

### 3. Cleanup Operations in Finally Blocks

```python
async def process_with_cleanup():
    resource = await acquire_resource()
    try:
        return await do_work(resource)
    finally:
        try:
            await resource.cleanup()
        except Exception:
            # Cleanup failure shouldn't mask the original error
            logger.warning("Resource cleanup failed")
```

## Common Exceptions to Catch Specifically

### Database Exceptions

| Exception | When to Catch | Response |
|-----------|---------------|----------|
| `IntegrityError` | Unique constraint violation | 409 Conflict |
| `NoResultFound` | Query returned no results | 404 Not Found |
| `SQLAlchemyError` | Connection issues | Log + retry or 503 |

### Redis Exceptions

| Exception | When to Catch | Response |
|-----------|---------------|----------|
| `ConnectionError` | Redis unavailable | Graceful degradation |
| `TimeoutError` | Redis slow | Log warning, proceed without cache |
| `RedisError` | Other Redis issues | Log, fallback to no-cache |

### Validation Exceptions

| Exception | When to Catch | Response |
|-----------|---------------|----------|
| `ValueError` | Business rule violation | 400 Bad Request |
| `ValidationError` (Pydantic) | Schema validation | 422 Unprocessable Entity |
| `PermissionError` | Authorization failure | 403 Forbidden |

### External Service Exceptions

| Exception | When to Catch | Response |
|-----------|---------------|----------|
| `httpx.HTTPStatusError` | API returned error | Map to appropriate status |
| `httpx.ConnectError` | Service unreachable | 503 or retry |
| `httpx.TimeoutException` | Service slow | 504 Gateway Timeout |

### Cryptography Exceptions

| Exception | When to Catch | Response |
|-----------|---------------|----------|
| `InvalidToken` (Fernet) | Decryption failed | Log error, raise ValueError |
| `InvalidSignature` | JWT tampering | 401 Unauthorized |

## Testing Exception Handling

When writing tests, verify exception handling:

```python
async def test_handles_database_error_gracefully():
    """Verify endpoint returns 500 on database errors, not 200."""
    # Mock the CRUD to raise a database error
    with patch("src.crud.resource.get_resource") as mock_get:
        mock_get.side_effect = SQLAlchemyError("Connection lost")

        response = await client.get("/api/v1/resources/123")

        assert response.status_code == 500
        assert response.json()["detail_code"] == "common.internal_error"

async def test_specific_exception_returns_correct_status():
    """Verify ValueError becomes 400, not 500."""
    with patch("src.crud.resource.create_resource") as mock_create:
        mock_create.side_effect = ValueError("Name already exists")

        response = await client.post("/api/v1/resources", json={"name": "test"})

        assert response.status_code == 400
        assert "already exists" in response.json()["detail"]
```

## Summary

| Layer | Pattern | Broad Catch OK? |
|-------|---------|-----------------|
| API endpoints | 3-tier (ValueError, HTTPException, Exception) | Yes, with full logging |
| CRUD functions | Let exceptions propagate | No |
| Services | Catch specific, re-raise unknown | Only for graceful degradation |
| Background jobs | Catch expected failures | For individual items only |
| Middleware | Global error handler | Yes, as last resort |
| Utilities | Catch specific, wrap in domain exception | No |
