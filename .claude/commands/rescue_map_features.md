# Map Features

Analyze and map all features in the source project.

## Arguments
- `$1` - ADW ID
- `$2` - Path to source project

## Instructions

Analyze the source project at `$2` to identify all user-facing features.

### 1. Feature Detection

For each feature, identify:

**Routes/Pages:**
- Frontend routes (React Router, Next.js pages, etc.)
- Associated URL patterns

**API Endpoints:**
- Backend endpoints that support this feature
- HTTP methods (GET, POST, PUT, DELETE)
- Request/response patterns

**Components:**
- UI components involved in rendering this feature
- Shared vs feature-specific components

**Data Models:**
- Database tables/collections involved
- Relationships between models

### 2. Feature Completeness Assessment

For each feature, evaluate:
- Is the frontend complete (UI renders properly)?
- Is the backend complete (API returns real data)?
- Are there hardcoded/mock data?
- Are there TODO comments indicating incomplete work?

### 3. Feature Categorization

Categorize each feature:
- **CRUD**: Basic create/read/update/delete operations
- **AUTH**: Authentication and authorization
- **DISPLAY**: Read-only data display
- **INTERACTIVE**: Complex user interactions
- **INTEGRATION**: Third-party service integrations

## Output

Create `discovery/feature_map.json`:

```json
{
  "features": [
    {
      "name": "User Authentication",
      "description": "Login, logout, password reset functionality",
      "category": "AUTH",
      "routes": ["/login", "/logout", "/reset-password"],
      "endpoints": [
        {"method": "POST", "path": "/api/auth/login"},
        {"method": "POST", "path": "/api/auth/logout"},
        {"method": "POST", "path": "/api/auth/reset-password"}
      ],
      "components": ["LoginForm", "ResetPasswordForm"],
      "models": ["User", "Session"],
      "is_complete": true,
      "completeness_notes": "Fully functional"
    },
    {
      "name": "User Profile",
      "description": "View and edit user profile",
      "category": "CRUD",
      "routes": ["/profile", "/profile/edit"],
      "endpoints": [
        {"method": "GET", "path": "/api/users/me"},
        {"method": "PUT", "path": "/api/users/me"}
      ],
      "components": ["ProfileView", "ProfileEditForm", "AvatarUpload"],
      "models": ["User"],
      "is_complete": false,
      "completeness_notes": "Avatar upload returns mock response"
    }
  ],
  "summary": {
    "total_features": 8,
    "complete_features": 5,
    "incomplete_features": 3,
    "categories": {
      "AUTH": 1,
      "CRUD": 4,
      "DISPLAY": 2,
      "INTERACTIVE": 1
    }
  }
}
```

## Validation

- File `discovery/feature_map.json` exists and is valid JSON
- Each feature has required fields: `name`, `description`, `category`, `is_complete`
- Summary counts match the features array

$ARGUMENTS
