# Classify Backend

Classify backend components and determine rescue approach.

## Arguments
- `$1` - ADW ID

## Input Files
- `discovery/structure_report.json`
- `discovery/feature_map.json`
- `discovery/schema_analysis.json`

## Context Files to Read
- `ai_docs/backend/context/models.md`
- `ai_docs/backend/context/crud.md`
- `ai_docs/backend/context/api.md`
- `ai_docs/backend/context/multitenancy.md`

## Instructions

Analyze the source backend and classify each domain for rescue.

### 1. Domain Identification

Group endpoints and models into logical domains:
- User management (auth, profiles, sessions)
- Content/data domains (posts, products, etc.)
- Settings/configuration
- Integrations (external APIs)

### 2. Classification per Domain

For each domain, determine:

**Rescue Verdict:**
- `REPLACE` - Source backend is broken/incomplete, build from scratch
- `ADAPT` - Source has useful logic, adapt to template patterns
- `SKIP` - Not needed for MVP or handled by template

**Complexity Assessment:**
- Simple CRUD (standard patterns)
- Complex queries (aggregations, reports)
- Real-time (WebSocket, SSE)
- External integrations (third-party APIs)
- Background jobs (queues, scheduled tasks)

### 3. Multi-tenancy Analysis

For each domain/table, determine:
- Needs `organization_id` filtering? (most do)
- Is organization-agnostic? (system tables)
- Has existing tenant isolation? (can adapt)

### 4. API Mapping

Map source endpoints to template patterns:

```
Source: GET /api/users/:id
Target: GET /api/v1/users/{user_id}

Source: POST /api/posts
Target: POST /api/v1/posts (with org_id from auth context)
```

## Output

Create `triage/backend_classification.json`:

```json
{
  "domains": [
    {
      "name": "users",
      "description": "User management including auth and profiles",
      "verdict": "REPLACE",
      "verdict_reason": "Source uses JWT without refresh, template has better auth",
      "source_models": ["User", "Session"],
      "target_models": ["User", "Session"],
      "complexity": "simple_crud",
      "needs_multitenancy": true,
      "estimated_hours": 4,
      "endpoints": [
        {
          "source": "GET /api/users/:id",
          "target": "GET /api/v1/users/{user_id}",
          "notes": "Add org_id filter"
        },
        {
          "source": "PUT /api/users/:id",
          "target": "PUT /api/v1/users/{user_id}",
          "notes": "Standard CRUD"
        }
      ]
    },
    {
      "name": "posts",
      "description": "Blog posts and content management",
      "verdict": "ADAPT",
      "verdict_reason": "Has useful rich text handling logic",
      "source_models": ["Post", "Category", "Tag"],
      "target_models": ["Post", "Category", "Tag", "PostTag"],
      "complexity": "complex_queries",
      "needs_multitenancy": true,
      "estimated_hours": 8,
      "endpoints": [
        {
          "source": "GET /api/posts",
          "target": "GET /api/v1/posts",
          "notes": "Pagination + filtering"
        }
      ]
    }
  ],
  "integrations": [
    {
      "name": "Stripe",
      "type": "payment",
      "verdict": "SKIP",
      "reason": "Not in MVP scope"
    },
    {
      "name": "SendGrid",
      "type": "email",
      "verdict": "REPLACE",
      "reason": "Template has email service"
    }
  ],
  "summary": {
    "total_domains": 4,
    "replace_count": 2,
    "adapt_count": 1,
    "skip_count": 1,
    "total_estimated_hours": 20,
    "multitenancy_required": ["users", "posts", "settings"],
    "external_integrations": 2
  }
}
```

## Validation

- File exists and is valid JSON
- All domains from feature_map are classified
- Each domain has verdict and reason
- Estimated hours are provided

$ARGUMENTS
