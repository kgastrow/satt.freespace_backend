# i18n Validation Checklist

This checklist ensures all user-facing text is properly internationalized. Use it during code reviews and development to prevent hardcoded strings from entering the codebase.

## Requirement

**All user-facing text must use i18n.** This is a mandatory requirement for this codebase (see CLAUDE.md). Hardcoded strings in components will cause issues when additional languages are added.

---

## Quick Reference: Using i18n

### Basic Usage

```typescript
import { useTranslation } from 'react-i18next'

function MyComponent() {
  const { t } = useTranslation()

  return (
    <div>
      <h1>{t('common:navigation.dashboard')}</h1>
      <p>{t('auth:login.subtitle')}</p>
    </div>
  )
}
```

### Key Format

Keys use the format `namespace:key.subkey`:

| Namespace | Purpose | File |
|-----------|---------|------|
| `common` | Shared UI elements, navigation, buttons | `common.json` |
| `auth` | Authentication flows | `auth.json` |
| `admin` | Admin pages | `admin.json` |
| `platformAdmin` | Platform admin pages | `platformAdmin.json` |
| `dashboard` | Dashboard page | `dashboard.json` |
| `files` | File management | `files.json` |
| `settings` | Settings pages | `settings.json` |
| `errors` | Error messages | `errors.json` |
| `backend` | API response messages | `backend.json` |
| `feedback` | Feedback feature | `feedback.json` |
| `helpCenter` | Help center | `helpCenter.json` |
| `media` | Media/upload features | `media.json` |
| `onboarding` | Onboarding flow | `onboarding.json` |

### Using Multiple Namespaces

```typescript
const { t } = useTranslation(['common', 'settings'])

// Access translations from either namespace
return (
  <div>
    <button>{t('common:buttons.save')}</button>
    <h1>{t('settings:nav.account.title')}</h1>
  </div>
)
```

### Dynamic Values (Interpolation)

```typescript
// Translation file: "greeting": "Hello, {{name}}!"
t('common:greeting', { name: user.firstName })

// Translation file: "count": "{{count}} items"
t('common:count', { count: items.length })
```

### Pluralization

```typescript
// Translation file:
// "item_one": "{{count}} item"
// "item_other": "{{count}} items"
t('common:item', { count: items.length })
```

---

## Adding Translations

### Step 1: Choose the Correct Namespace

Select the appropriate namespace based on where the text will be used:
- UI shared across pages -> `common`
- Authentication pages -> `auth`
- Admin functionality -> `admin` or `platformAdmin`
- Feature-specific -> Use that feature's namespace

### Step 2: Add to Locale File

Add your key to `src/locales/en/<namespace>.json`:

```json
{
  "myFeature": {
    "title": "My Feature Title",
    "description": "A description of the feature"
  }
}
```

### Step 3: Add to ALL Locale Directories

**Critical:** When multiple languages are configured, you must add the translation to every locale directory:
- `src/locales/en/<namespace>.json`
- `src/locales/<other-lang>/<namespace>.json` (for each supported language)

Currently, only English (`en`) is configured, but this will change as the application scales.

### Step 4: Use in Component

```typescript
const { t } = useTranslation()
return <h1>{t('namespace:myFeature.title')}</h1>
```

---

## Code Review Checklist

### What to Look For

| Item | Check |
|------|-------|
| JSX text content | No literal strings between tags |
| Button labels | Uses `t()` function |
| Form labels and placeholders | Uses `t()` function |
| Error messages | Uses `t()` function |
| Toast notifications | Uses `t()` function |
| Alt text for images | Uses `t()` function |
| ARIA labels | Uses `t()` function |
| Tooltip content | Uses `t()` function |
| Modal titles and content | Uses `t()` function |
| Table headers | Uses `t()` function |
| Confirmation dialogs | Uses `t()` function |

### Acceptable Exceptions

These do NOT need i18n:
- Technical identifiers (CSS class names, data attributes)
- URLs and paths
- Console.log messages (development only)
- Test data/mock data
- Code comments
- Environment variable names
- Third-party library configuration

### Red Flags in Code Review

```typescript
// BAD: Hardcoded strings
<Button>Submit</Button>
<label>Email Address</label>
toast.error('Failed to save')
alert('Are you sure?')

// GOOD: Using i18n
<Button>{t('common:buttons.submit')}</Button>
<label>{t('auth:login.email')}</label>
toast.error(t('errors:saveFailed'))
```

---

## Common Mistakes to Avoid

### 1. Hardcoded Strings

```typescript
// WRONG
return <h1>Welcome to Dashboard</h1>

// CORRECT
return <h1>{t('dashboard:welcome.title')}</h1>
```

### 2. String Concatenation

```typescript
// WRONG
return <p>{'Hello, ' + user.name + '!'}</p>

// CORRECT (use interpolation)
// Translation: "greeting": "Hello, {{name}}!"
return <p>{t('common:greeting', { name: user.name })}</p>
```

### 3. Wrong Namespace

```typescript
// WRONG - using common for auth-specific text
t('common:login.title')

// CORRECT - using the auth namespace
t('auth:login.title')
```

### 4. Missing Namespace Prefix

```typescript
// WRONG - missing namespace (only works for common namespace)
t('buttons.submit')

// CORRECT - explicit namespace
t('common:buttons.submit')
```

### 5. Forgetting to Add Translations for New Languages

When a new language is added, every new translation key must be added to ALL locale files. Missing translations will show the key string or fall back to English.

### 6. Hardcoding in Zod Schemas

```typescript
// WRONG
const schema = z.object({
  email: z.string().email('Invalid email address'),
})

// CORRECT - use factory function
const createSchema = (t: (key: string) => string) =>
  z.object({
    email: z.string().email(t('auth:validation.emailInvalid')),
  })

// Usage in component
const { t } = useTranslation()
const schema = createSchema(t)
```

---

## Testing i18n Compliance

### Manual Review Process

1. Search for potential hardcoded strings:
   ```bash
   # From app/frontend/ directory
   grep -rn ">[A-Z][a-z]" src/ --include="*.tsx" | grep -v "test" | grep -v ".d.ts"
   ```

2. Check for string literals in JSX:
   ```bash
   grep -rn "'[A-Z][a-z].*'" src/components --include="*.tsx"
   grep -rn '"[A-Z][a-z].*"' src/components --include="*.tsx"
   ```

### Test Setup

The test setup (`src/test/setup.ts`) mocks i18n to return translation keys directly. This makes it easy to verify the correct keys are used:

```typescript
// In tests, t('auth:login.title') returns 'auth:login.title'
expect(screen.getByText('auth:login.title')).toBeInTheDocument()
```

### Integration Tests

The codebase includes i18n integration tests in:
- `src/i18n/config.test.ts` - Configuration validation
- `src/__tests__/integration/language-switching.integration.test.tsx` - Language switching

---

## Adding a New Language

When the time comes to add a new language:

1. **Update `src/i18n/config.ts`**:
   ```typescript
   export const supportedLanguages = ['en', 'es'] as const

   export const languageNames: Record<SupportedLanguage, string> = {
     en: 'English',
     es: 'Español',
   }
   ```

2. **Create locale directory**:
   ```bash
   cp -r src/locales/en src/locales/es
   ```

3. **Translate all JSON files** in `src/locales/es/`

4. The `LanguageSwitcher` component will automatically appear when multiple languages are configured.

---

## Summary

| Do | Don't |
|----|-------|
| Use `t()` for all user-facing text | Hardcode strings in JSX |
| Use interpolation for dynamic values | Concatenate strings with variables |
| Choose the correct namespace | Put all translations in `common` |
| Add translations to ALL locale files | Forget other language files |
| Use factory functions for Zod schemas | Hardcode validation messages |
| Review PRs for hardcoded strings | Approve code with literal UI text |
