# Execute Component Task

Extract and adapt a UI component for the rescued project.

## Arguments
- `$1` - ADW ID
- `$2` - Source component path (relative to source/)
- `$3` - Migration tier (auto/assisted/manual)
- `$4` - Target path in template

## Context Files to Read (MANDATORY)
- `ai_docs/frontend/context/components.md`
- `ai_docs/frontend/context/i18n.md`
- `ai_docs/frontend/context/styling.md`

## Instructions

### 1. Read Source Component

Read the component at `source/$2`.

Analyze:
- Props interface
- State usage
- API calls
- Styling approach
- Child components used

### 2. Transform Based on Tier

#### AUTO Tier
Direct extraction with minimal changes:

1. **Copy structure** - Preserve component logic
2. **Convert styling to Tailwind**
   - CSS Modules -> Tailwind utilities
   - Styled-components -> Tailwind classes
   - Keep inline styles if simple
3. **Replace API calls** with RTK Query hooks (placeholder)
4. **Add i18n** for all user-facing strings
5. **Update imports** to use template paths

#### ASSISTED Tier
Same as AUTO plus:

1. **Map Redux/Context to template patterns**
   - Redux global state -> RTK Query for server state
   - Context -> Local state or RTK Query
2. **Add review comments** where unclear
3. **Flag potential issues** with `// TODO: REVIEW -`

#### MANUAL Tier
Create skeleton with documentation:

1. **Create basic component structure**
2. **Document original behavior** in comments
3. **Add TODO comments** for manual completion
4. **Preserve prop types** for reference

### 3. i18n Transformation (MANDATORY for all tiers)

Every user-facing string MUST use `t()`:

```tsx
// Before (source)
<h1>Welcome back</h1>
<button>Save changes</button>
<p>No items found</p>

// After (rescued)
import { useTranslation } from 'react-i18next';

export function Component() {
  const { t } = useTranslation();

  return (
    <>
      <h1>{t('component.welcome.title')}</h1>
      <button>{t('common.actions.save')}</button>
      <p>{t('component.items.empty')}</p>
    </>
  );
}
```

Add translations to ALL locale files:
- `app/frontend/src/locales/en/translation.json`
- Any other locale files present

### 4. Styling Transformation

Convert to Tailwind CSS:

```tsx
// Before (styled-components)
const Container = styled.div`
  display: flex;
  flex-direction: column;
  padding: 16px;
  background: #f0f0f0;
  border-radius: 8px;
`;

// After (Tailwind)
<div className="flex flex-col p-4 bg-gray-100 rounded-lg">
```

```tsx
// Before (CSS Modules)
import styles from './Card.module.css';
<div className={styles.card}>

// After (Tailwind)
<div className="rounded-lg shadow-md p-4 bg-white">
```

### 5. State Transformation

| Source Pattern | Target Pattern |
|----------------|----------------|
| Redux (useSelector) | RTK Query hook or local state |
| useContext | RTK Query hook or local state |
| useState (simple) | Keep as useState |
| Zustand | Convert to useState or RTK Query |

### 6. API Call Transformation

```tsx
// Before (fetch)
const [data, setData] = useState(null);
useEffect(() => {
  fetch('/api/users').then(r => r.json()).then(setData);
}, []);

// After (RTK Query - placeholder)
// TODO: Create RTK Query hook in src/features/api/
const { data, isLoading } = useGetUsersQuery();
```

## Output

Create the component at `$4` and report:

1. **Component created** at target path
2. **Transformation notes**:
   - Styling conversions made
   - State mappings applied
   - API calls marked for wiring
3. **i18n keys added** and translations created
4. **Review items** (for ASSISTED/MANUAL tiers)

Example:
```
Created: app/frontend/src/components/features/UserCard.tsx

Transformations:
- Converted styled-components to Tailwind
- Replaced Redux useSelector with placeholder RTK Query hook
- Added 5 i18n keys to en/translation.json

i18n Keys:
- userCard.title
- userCard.editButton
- userCard.deleteButton
- userCard.confirmDelete
- userCard.memberSince

Review Items:
- Line 45: TODO: REVIEW - Complex animation may need adjustment
- Line 78: TODO: Wire to actual API endpoint
```

## Validation

- Component file exists at target path
- All visible strings use t()
- Translations added to locale files
- Uses Tailwind for styling
- TypeScript compiles without errors

$ARGUMENTS
