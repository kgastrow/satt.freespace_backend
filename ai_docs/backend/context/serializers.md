# Serializers Pattern and Conventions

Pydantic models for request/response validation in `app/backend/src/serialisers/`.

## Core Patterns

All serializers use:
- `ConfigDict(extra='forbid')` on requests
- Naming: `{Operation}{Entity}Request/Response`
- Separate Request/Response models

## Field Types

| Type | Example |
|------|---------|
| Email | `email: EmailStr = Field(..., max_length=255)` |
| Phone | `phone: Optional[PhoneNumber] = None` (E.164 format, from `pydantic_extra_types.phone_numbers`) |
| String | `name: str = Field(..., min_length=1, max_length=100)` |
| UUID | `user_id: UUID` |
| List | `tags: list[str] = Field(default_factory=list)` |

## Request/Response Patterns

**Create Request**:
```python
class CreateRoleRequest(BaseModel):
    name: str = Field(..., max_length=100)
    description: Optional[str] = Field(None, max_length=1000)
    model_config = ConfigDict(extra="forbid")
```

**Update Request** - all fields optional:
```python
class UpdateRoleRequest(BaseModel):
    name: Optional[str] = Field(None, max_length=100)
    model_config = ConfigDict(extra="forbid")
```

**Response** - use `from_attributes=True` only when converting directly from ORM:
```python
class GetOrganizationDetailsResponse(BaseModel):
    id: str
    name: str
    model_config = ConfigDict(from_attributes=True)
```

**List Response** - offset pagination (standard):
```python
class ListRolesResponse(BaseModel):
    items: list[GetRoleResponse]  # Always use 'items'
    total: int
    limit: int
    offset: int
```

**List Response** - cursor pagination (for large datasets >100k rows):
```python
class UserCursorListResponse(BaseModel):
    items: list[UserListItemResponse]
    total: int
    limit: int
    next_cursor: str | None = None
    has_more: bool = False
```

**Message Response** - inherit from `MessageResponse` or include both fields:
```python
from src.serialisers.common import MessageResponse

class DeleteRoleResponse(BaseModel):
    message: str
    message_code: str = Field(..., description="Translation code for i18n")
    role_id: str
```

## Password Validation

Reuse `validate_password_complexity` from `src.serialisers.user`:

```python
from src.serialisers.user import validate_password_complexity

@field_validator('password')
@classmethod
def validate_password(cls, v: Optional[str]) -> Optional[str]:
    if v is not None:
        return validate_password_complexity(v)
    return v
```

Requirements: 8-128 chars, lowercase, uppercase, digit, special char.

## Critical Rules

### Multi-Tenancy Security
- **NEVER** include `organization_id` in request serializers
- Extract from JWT via `current_user.organization_id`
- Set internally in CRUD layer

### Type Safety

| Correct | Wrong |
|---------|-------|
| `email: EmailStr = Field(...)` | `email: EmailStr = Field(None)` |
| `name: Optional[str] = Field(None)` | `name: str = Field(None)` |

### Never Include in Create/Update Requests
`id`, `organization_id`, `created_time`, `updated_time`, `deleted_time`

## Best Practices

- Always use `ConfigDict(extra='forbid')` on requests
- Import serializers from `src.serialisers/`, never define inline in API files
- Add field constraints (min/max length, patterns)
- Handle optional DB fields: `user.created_time.isoformat() if user.created_time else ""`
