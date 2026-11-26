# Request/Response Logging Middleware

**ADW ID:** 20260114231610-27a17f80
**Date:** 2026-01-15
**Specification:** specs/multi-phase/issue-139-adw-20260114231610-27a17f80-multi-phase.md

## Overview

Captures all API requests with timing, status codes, and sanitized payloads. Stores logs in rotating files and optionally in the database for admin search functionality. Super admin endpoints provide advanced filtering with configurable retention policies.

## Implementation

### Files

| File | Purpose |
|------|---------|
| `app/backend/src/middleware/request_response_logging.py` | Core middleware with request/response interception, timing, and payload sanitization |
| `app/backend/src/models/request_log.py` | RequestLog model with organization/user associations, soft delete support |
| `app/backend/src/crud/request_log.py` | CRUD operations with advanced filtering and pagination |
| `app/backend/src/services/request_log_writer.py` | Asynchronous database writer service |
| `app/backend/src/api/request_log.py` | Super admin API endpoints for log search and manual cleanup |
| `app/backend/src/serialisers/request_log.py` | Pydantic response models |
| `app/backend/src/workers/request_log_cleanup.py` | ARQ background task for daily log cleanup |
| `app/backend/src/core/config.py` | Configuration settings (modified) |
| `app/backend/main.py` | Middleware registration after MetricsMiddleware (modified) |
| `app/backend/alembic/versions/14c0aff2510a_add_requestlog_model.py` | Database migration |
| `app/backend/tests/unit_tests/test_request_logging.py` | Comprehensive test suite |

### Key Features

- **Middleware Integration**: Intercepts all requests, measures duration, extracts user/organization context from JWT tokens, sanitizes sensitive data
- **Multi-Tenant Support**: Nullable `organization_id` and `user_id` fields handle authenticated and unauthenticated requests with composite indexes for efficient queries
- **Payload Sanitization**: Automatically masks passwords, tokens, API keys, and other sensitive fields
- **Dual Storage**: Always logs to rotating files (100MB per file, 10 backups); optional database storage for admin search
- **Non-Blocking**: FastAPI BackgroundTasks for database writes; ARQ scheduled tasks for daily cleanup

## Configuration

Environment variables:
- `REQUEST_LOGGING_ENABLED=true` - Enable/disable request logging
- `REQUEST_LOGGING_FILE=request_response.log` - Log file path
- `REQUEST_LOGGING_EXCLUDED_PATHS=/health,/metrics,/docs,/redoc,/openapi.json` - Paths to exclude
- `REQUEST_LOGGING_MAX_BODY_SIZE=10240` - Max body size to capture (bytes)
- `REQUEST_LOGGING_DB_ENABLED=true` - Enable database storage

Or via `app.config.yaml`:

```yaml
request_logging:
  enabled: true
  filename: request_response.log
  excluded_paths: /health,/metrics,/docs,/redoc,/openapi.json
  max_body_size: 10240
  db_enabled: true
```

Retention configured via SystemConfig:
- Key: `request_logs.retention_days`
- Default: `30` days
- Configure via: `PUT /api/v1/admin/config/request_logs.retention_days`

## API Endpoints

### List Logs (Super Admin Only)

```
GET /api/v1/admin/request-logs?method=POST&status_code_min=400&limit=50
```

Filters:
- `method` - HTTP method (GET, POST, PUT, DELETE, etc.)
- `path` - Path pattern using SQL LIKE (e.g., `/api/v1/users%`)
- `status_code_min`/`status_code_max` - Status code range
- `date_from`/`date_to` - ISO datetime range
- `organization_id` - Filter by tenant UUID
- `user_id` - Filter by user UUID
- `limit` - Results per page (1-100, default 50)
- `offset` - Pagination offset

### Get Log Details

```
GET /api/v1/admin/request-logs/{request_log_id}
```

### Manual Cleanup

```
POST /api/v1/admin/request-logs/cleanup
```

Returns count of deleted logs.

### Set Retention

```
PUT /api/v1/admin/config/request_logs.retention_days
Content-Type: application/json

{
  "value": "60"
}
```

## Testing

```bash
cd app/backend
make test
```

Test coverage includes:
- Middleware request/response capture
- Payload sanitization
- RequestLog model and CRUD operations
- Multi-tenant isolation
- Database writer service
- API endpoint authorization and filtering
- Log retention and cleanup
- JWT token extraction

## Security & Performance

**Security:**
- Automatic sanitization of passwords, tokens, API keys, and sensitive fields
- Super admin access required for all request log endpoints
- Multi-tenant isolation with organization context preservation

**Performance:**
- Non-blocking database writes via FastAPI BackgroundTasks
- Health checks, metrics, and documentation endpoints excluded by default
- Request/response bodies truncated to 10KB (configurable)
- Composite database indexes on `organization_id`, `status_code`, `user_id`, and `created_time`
- File logging uses rotating handlers (100MB per file, 10 backups)

**Limitations:**
- Bodies larger than `REQUEST_LOGGING_MAX_BODY_SIZE` are truncated
- Database writes fail gracefully if unavailable
- Soft deletes only (requires explicit cleanup job for storage reclamation)
