# Validate Features

Verify feature parity between source and rescued project.

## Arguments
- `$1` - ADW ID

## Input Files
- `discovery/feature_map.json`
- `triage/task_graph.json`

## Instructions

### 1. Load Feature Map

Read the features detected during discovery.

### 2. Check Each Feature

For each feature in the map:

**Verify Backend:**
- API endpoints exist and respond
- CRUD operations work correctly
- Data persists properly

**Verify Frontend:**
- Pages/routes accessible
- Components render correctly
- Forms submit successfully
- Data displays as expected

**Verify Integration:**
- Frontend calls correct API endpoints
- Data flows end-to-end
- Error handling works

### 3. Feature Status Categories

**COMPLETE:**
- All functionality working
- Tests pass
- No known issues

**PARTIAL:**
- Core functionality works
- Some edge cases missing
- Minor issues exist

**MISSING:**
- Feature not implemented
- Was in scope but skipped
- Needs future work

**IMPROVED:**
- Feature works better than source
- Using template patterns
- Added missing functionality

### 4. Functional Testing

For each feature, perform quick functional test:

```
Example: User Profile Feature

1. Navigate to /profile
   - Expected: Profile page loads
   - Result: PASS

2. Click Edit button
   - Expected: Edit form appears
   - Result: PASS

3. Change name field
   - Expected: Input accepts text
   - Result: PASS

4. Click Save
   - Expected: Profile updates, success message
   - Result: PASS

5. Refresh page
   - Expected: Changes persisted
   - Result: PASS

Feature Status: COMPLETE
```

## Output

Create `rescue/feature_parity.json`:

```json
{
  "timestamp": "2024-01-15T10:30:00Z",
  "features": [
    {
      "name": "User Authentication",
      "source_status": "complete",
      "rescued_status": "complete",
      "parity": "matched",
      "tests_performed": [
        {"action": "Login with valid credentials", "result": "pass"},
        {"action": "Login with invalid credentials", "result": "pass"},
        {"action": "Logout", "result": "pass"},
        {"action": "Session persistence", "result": "pass"}
      ],
      "notes": "Using template auth system"
    },
    {
      "name": "User Profile",
      "source_status": "complete",
      "rescued_status": "complete",
      "parity": "improved",
      "tests_performed": [
        {"action": "View profile", "result": "pass"},
        {"action": "Edit profile", "result": "pass"},
        {"action": "Upload avatar", "result": "pass"}
      ],
      "notes": "Added avatar cropping (template feature)"
    },
    {
      "name": "Post Management",
      "source_status": "complete",
      "rescued_status": "partial",
      "parity": "partial",
      "tests_performed": [
        {"action": "Create post", "result": "pass"},
        {"action": "Edit post", "result": "pass"},
        {"action": "Delete post", "result": "pass"},
        {"action": "Rich text editing", "result": "fail"}
      ],
      "notes": "Rich text editor needs manual completion",
      "missing_functionality": ["Rich text formatting", "Image embedding"]
    },
    {
      "name": "Analytics Dashboard",
      "source_status": "incomplete",
      "rescued_status": "missing",
      "parity": "deferred",
      "tests_performed": [],
      "notes": "Deferred to phase 2 per triage decision"
    }
  ],
  "summary": {
    "total_features": 8,
    "complete": 5,
    "partial": 2,
    "missing": 1,
    "parity_percent": 87.5,
    "improved_features": ["User Profile", "Settings"],
    "deferred_features": ["Analytics Dashboard"],
    "known_issues": [
      {
        "feature": "Post Management",
        "issue": "Rich text editor not fully functional",
        "severity": "medium",
        "workaround": "Plain text editing works"
      }
    ]
  }
}
```

Report to stdout:

```
=== FEATURE PARITY VALIDATION ===

Parity: 87.5%

Feature Status:
  - User Authentication: COMPLETE (matched)
  - User Profile: COMPLETE (improved)
  - Post Management: PARTIAL
  - Settings: COMPLETE (improved)
  - Dashboard: COMPLETE (matched)
  - Analytics: MISSING (deferred)

Improved Features:
  - User Profile: Added avatar cropping
  - Settings: Better organization structure

Known Issues:
  1. Post Management - Rich text editor incomplete
     Workaround: Plain text works

Deferred Features:
  - Analytics Dashboard (phase 2)

Recommendation: Feature rescue largely successful
  - Consider completing rich text editor
  - Analytics can wait for phase 2
```

## Validation

- All features from feature_map checked
- Status assigned to each
- Parity percentage calculated
- Known issues documented with workarounds

$ARGUMENTS
