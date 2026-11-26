# Plan UI Rescue

Create detailed UI rescue plan for component migration.

## Arguments
- `$1` - ADW ID

## Input Files
- `discovery/ui_catalog.json`
- `triage/component_scores.json`
- `discovery/structure_report.json`

## Context Files to Read
- `ai_docs/frontend/context/components.md`
- `ai_docs/frontend/context/i18n.md`
- `ai_docs/frontend/context/styling.md`

## Instructions

Create a comprehensive plan for rescuing UI components.

### 1. Styling Strategy

Based on source styling methods, determine conversion strategy:

**Tailwind (source) -> Tailwind (target):**
- Direct copy with minor adjustments
- Update color/spacing tokens to match template theme

**CSS Modules -> Tailwind:**
- Extract styles and convert to utility classes
- Preserve responsive breakpoints

**Styled-components/Emotion -> Tailwind:**
- Convert dynamic styles to Tailwind + CSS variables
- Handle props-based styling with conditional classes

**Multiple Methods (CSS Chaos):**
- Identify primary styling to preserve
- Convert secondary methods to Tailwind
- May require full rewrite

### 2. State Migration Strategy

Map source state patterns to template patterns:

| Source | Target | Migration Strategy |
|--------|--------|-------------------|
| Redux (global) | RTK Query | Convert to API-based state |
| Redux (UI) | React state | Localize state |
| Context | RTK Query or local | Depends on data type |
| Zustand | React state | Simple conversion |
| React Query | RTK Query | Similar patterns |

### 3. Component Grouping

Group components for efficient migration:

**Shared/Base Components (migrate first):**
- Button, Input, Card, Modal
- These are dependencies for others

**Feature Components (migrate by feature):**
- Group by feature to maintain coherence
- Test feature end-to-end after migration

**Complex Components (migrate last):**
- Data tables, rich text editors
- May need significant rework

### 4. i18n Planning

For each component, identify:
- Hardcoded strings to extract
- Translation key naming convention
- Pluralization needs
- Date/number formatting

## Output

Create `triage/ui_rescue_plan.md`:

```markdown
# UI Rescue Plan

## Styling Strategy

**Source Primary:** {tailwind | css_modules | styled-components}
**Target:** Tailwind CSS

### Conversion Approach
{Detailed conversion strategy}

### Theme Mapping
| Source Token | Target Token |
|--------------|--------------|
| --primary | primary (Tailwind) |
| --gray-100 | gray-100 |

## State Migration

### Redux -> RTK Query
{List of Redux slices and their migration plan}

### Context Removal
{List of contexts and replacement strategy}

## Migration Order

### Phase 1: Base Components (Week 1)
1. Button - AUTO - 0.5h
2. Input - AUTO - 0.5h
3. Card - AUTO - 0.5h
...

### Phase 2: Feature: User Management (Week 1-2)
1. LoginForm - ASSISTED - 2h
2. ProfileCard - ASSISTED - 1.5h
...

### Phase 3: Feature: Dashboard (Week 2)
1. StatCard - AUTO - 0.5h
2. DataChart - MANUAL - 4h
...

### Phase 4: Complex Components (Week 3)
1. RichTextEditor - MANUAL - 8h
2. DataTable - MANUAL - 6h
...

## i18n Extraction

### Translation Keys
Total strings to extract: {count}

### Key Naming Convention
```
{feature}.{component}.{element}
Example: profile.userCard.editButton
```

## Risk Areas

### High Risk Components
| Component | Risk | Mitigation |
|-----------|------|------------|
| AnimatedHeader | CSS chaos + animations | May need full rewrite |
| DataTable | Complex state | Consider using template DataTable |

## Estimated Effort

| Category | Hours |
|----------|-------|
| Base Components | 4h |
| Feature Components | 20h |
| Complex Components | 18h |
| i18n Extraction | 6h |
| Integration Testing | 8h |
| **Total** | **56h** |
```

## Validation

- File `triage/ui_rescue_plan.md` exists
- All components from ui_catalog are included
- Migration order respects dependencies
- Effort estimates are provided

$ARGUMENTS
