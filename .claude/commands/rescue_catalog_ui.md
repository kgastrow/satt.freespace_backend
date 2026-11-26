# Catalog UI Components

Analyze all UI components in the source frontend.

## Arguments
- `$1` - ADW ID
- `$2` - Path to source project

## Context Files to Read
- `ai_docs/frontend/context/components.md` (for template component patterns reference)

## Instructions

Catalog every UI component in the source project's frontend at `$2`.

### For each component, analyze:

#### 1. Basic Info
- File path and component name
- Line count (complexity indicator)
- Purpose (what does it render?)
- Props interface

#### 2. Styling Analysis (CRITICAL - determines migration tier)

Detect styling methods used IN THIS FILE:

| Method | Pattern to Detect |
|--------|-------------------|
| CSS Modules | `import styles from '*.module.css'` |
| Tailwind | `className="flex items-center ..."` with utility classes |
| Styled-components | `styled.div`, `import styled from 'styled-components'` |
| Emotion | `css` prop, `@emotion/react`, `@emotion/styled` |
| Inline styles | `style={{ }}` or `style={variableName}` |
| Global CSS | `import '*.css'` (not module) |
| SASS/SCSS | `import '*.scss'` |

**Flag as `has_css_chaos: true` if 3+ methods are used in the same file.**

#### 3. State Management

Detect state patterns:
- **Redux**: `useSelector`, `useDispatch`, `connect()`
- **Context**: `useContext`, `createContext`
- **Zustand**: `useStore`, `create()`
- **React Query**: `useQuery`, `useMutation`
- **SWR**: `useSWR`
- **Local**: `useState`, `useReducer`

#### 4. API Calls

Identify:
- What endpoints does this component call?
- How? (fetch, axios, React Query, SWR, RTK Query)
- Direct API calls vs through hooks/services

#### 5. Animations

Detect animation usage:
- CSS animations/transitions (check imported CSS)
- Framer Motion (`motion.div`, `animate`, `variants`)
- GSAP (`gsap.to`, `useGSAP`)
- React Spring (`useSpring`)
- Lottie animations

Note if animations reference DOM by class name (structure-locked).

### Migration Tier Assignment

Apply this logic to each component:

```
IF has_css_chaos (3+ styling methods) THEN tier = "manual"
ELSE IF dom_structure_locked THEN tier = "manual"
ELSE IF uses_forked_library THEN tier = "manual"
ELSE
  score = 0
  IF len(styling_methods) > 1 THEN score += 2
  IF uses_redux THEN score += 1
  IF uses_context THEN score += 1
  IF len(uses_other_state) > 0 THEN score += len(uses_other_state)
  IF has_animations THEN score += 2
  IF line_count > 300 THEN score += 1

  IF score <= 1 THEN tier = "auto"
  ELSE IF score <= 3 THEN tier = "assisted"
  ELSE tier = "manual"
```

## Output

Create `discovery/ui_catalog.json`:

```json
{
  "components": [
    {
      "path": "src/components/UserCard.tsx",
      "name": "UserCard",
      "line_count": 85,
      "styling_methods": ["tailwind", "inline"],
      "has_css_chaos": false,
      "uses_context": true,
      "uses_redux": false,
      "uses_other_state": [],
      "api_calls": ["/api/users/{id}"],
      "has_animations": false,
      "animation_library": null,
      "dom_structure_locked": false,
      "imports": ["Button", "Avatar", "@/lib/utils"],
      "migration_tier": "assisted",
      "migration_notes": "Uses context, will need state mapping"
    },
    {
      "path": "src/components/AnimatedHeader.tsx",
      "name": "AnimatedHeader",
      "line_count": 150,
      "styling_methods": ["tailwind", "css_modules", "inline"],
      "has_css_chaos": true,
      "uses_context": false,
      "uses_redux": false,
      "uses_other_state": [],
      "api_calls": [],
      "has_animations": true,
      "animation_library": "framer-motion",
      "dom_structure_locked": true,
      "imports": ["motion", "framer-motion"],
      "migration_tier": "manual",
      "migration_notes": "CSS chaos + locked DOM structure for animations"
    }
  ],
  "global_styles": {
    "css_files": ["globals.css", "variables.css"],
    "tailwind_config": "tailwind.config.js",
    "theme_variables": ["--primary", "--secondary", "--background"]
  },
  "design_tokens": {
    "colors": ["primary", "secondary", "accent"],
    "fonts": ["Inter", "Roboto Mono"],
    "spacing_system": "tailwind default"
  },
  "summary": {
    "total_components": 25,
    "tier_auto": 15,
    "tier_assisted": 7,
    "tier_manual": 3,
    "css_chaos_count": 2,
    "uses_animations": 5
  }
}
```

## Validation

- File exists and is valid JSON
- All component files in source frontend are cataloged
- Each component has `migration_tier` assigned
- Summary counts match component array

$ARGUMENTS
