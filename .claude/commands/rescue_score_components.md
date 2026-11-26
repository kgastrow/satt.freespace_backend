# Score Components

Score UI components for migration complexity and priority.

## Arguments
- `$1` - ADW ID

## Input Files
- `discovery/ui_catalog.json`
- `discovery/feature_map.json`

## Instructions

Analyze the UI catalog and assign detailed scores for migration planning.

### 1. Complexity Scoring

For each component, calculate scores (0-10) for:

**Styling Complexity:**
- 0: Single styling method (Tailwind only)
- 3: Two styling methods
- 6: Three styling methods
- 10: CSS chaos (3+ methods in single file)

**State Complexity:**
- 0: No state or local useState only
- 2: useContext
- 4: Redux/Zustand
- 6: Multiple state solutions
- 8: Complex state with side effects
- 10: State chaos (3+ approaches)

**API Complexity:**
- 0: No API calls
- 2: Single API call
- 4: Multiple API calls
- 6: Complex data fetching (pagination, infinite scroll)
- 8: Real-time updates (WebSocket)
- 10: Multiple real-time + REST combined

**Animation Complexity:**
- 0: No animations
- 2: CSS transitions only
- 4: CSS animations
- 6: Framer Motion/React Spring
- 8: Complex orchestrated animations
- 10: GSAP or DOM-locked animations

### 2. Priority Scoring

Determine rescue priority based on:

**User-facing importance:**
- Core feature components (high priority)
- Secondary feature components (medium priority)
- Admin/settings components (low priority)

**Dependency analysis:**
- Components used by many others (high priority)
- Leaf components (lower priority)
- Shared/common components (high priority)

### 3. Effort Estimation

Calculate estimated hours per component:

```
base_hours = line_count / 50  # ~50 LOC per hour for straightforward code
complexity_multiplier = (styling + state + api + animation) / 40 + 1
tier_multiplier = {auto: 0.5, assisted: 1.0, manual: 2.0}

estimated_hours = base_hours * complexity_multiplier * tier_multiplier
```

## Output

Create `triage/component_scores.json`:

```json
{
  "components": [
    {
      "path": "src/components/UserCard.tsx",
      "name": "UserCard",
      "scores": {
        "styling": 3,
        "state": 2,
        "api": 2,
        "animation": 0,
        "total": 7
      },
      "priority": "high",
      "priority_reason": "Used in 5 other components",
      "migration_tier": "assisted",
      "estimated_hours": 1.5,
      "dependencies": ["Button", "Avatar"],
      "dependents": ["UserList", "ProfilePage", "CommentCard"]
    }
  ],
  "summary": {
    "total_components": 25,
    "total_estimated_hours": 45,
    "by_priority": {
      "high": 8,
      "medium": 12,
      "low": 5
    },
    "by_tier": {
      "auto": 15,
      "assisted": 7,
      "manual": 3
    },
    "highest_complexity": ["AnimatedHeader", "DataTable", "RichTextEditor"],
    "most_dependencies": ["Button", "Card", "Input"]
  }
}
```

## Validation

- File exists and is valid JSON
- All components from ui_catalog.json are scored
- Scores are within 0-10 range
- Estimated hours are reasonable (0.5-20 per component)

$ARGUMENTS
