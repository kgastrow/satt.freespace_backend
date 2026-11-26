# South African Language Support

**ADW ID:** 20260113101101-39d80ca4
**Date:** 2026-01-13
**Specification:** specs/issue-118-adw-20260113101101-39d80ca4-sdlc_planner-add-south-african-languages.md

## Overview

Added internationalization support for three South African languages: isiZulu (zu), Sepedi (nso), and isiXhosa (xh). The feature includes 21 new translation files (7 namespaces × 3 languages), lazy-loaded i18n configuration, automatic browser language detection, and comprehensive test coverage.

## Implementation

### Architecture

- **i18n Configuration** (`app/frontend/src/i18n/config.ts`):
  - Extended `supportedLanguages` from 2 to 5 languages with `as const` type safety
  - Lazy loading via i18next's `resourcesToBackend`
  - Automatic browser language detection; fallback to English
  - localStorage persistence across page reloads

- **Translation Files**: `app/frontend/src/locales/{language_code}/{namespace}.json`
  - Namespaces: admin, auth, common, dashboard, errors, files, settings
  - ~3,800 lines total; zu: ~808 lines, nso: ~808 lines, xh: ~808 lines

### Files Modified

**Frontend:**
- `app/frontend/src/i18n/config.ts` - Added language codes and configuration
- `app/frontend/src/components/LanguageSwitcher.test.tsx` - Tests for 5 languages
- `app/frontend/src/i18n/config.test.ts` - Language configuration tests
- `app/frontend/src/__tests__/integration/language-switching.integration.test.tsx` - Language switching behavior tests

**Backend:**
- `app/backend/src/api/notification.py` - Updated for language testing
- `app/backend/src/serialisers/notification.py` - Enhanced serializers
- `app/backend/tests/api_tests/test_notification_api.py` - Language-aware tests
- `app/backend/tests/conftest.py` - Test fixtures

**Scripts:**
- `scripts/generate-api-types.sh` - Updated type generation

### Language Codes

| Language | Code | ISO Standard |
|----------|------|--------------|
| isiZulu | zu | 639-1 |
| Sepedi | nso | 639-3 (Northern Sotho) |
| isiXhosa | xh | 639-1 |

## Usage

### Component Usage

```typescript
import { useTranslation } from 'react-i18next'

const MyComponent = () => {
  const { t } = useTranslation('common')
  return <button>{t('buttons.save')}</button>
}
```

### Adding Translation Keys

Update all language files maintaining consistency:
- `en/namespace.json` (source of truth)
- `de/namespace.json`
- `zu/namespace.json`
- `nso/namespace.json`
- `xh/namespace.json`

## Testing

### Unit & Integration Tests
```bash
cd app/frontend
npm run test  # All tests
npm run test -- language-switching.integration.test.tsx  # Language tests
```

Key test files:
- `src/i18n/config.test.ts` - Configuration and initialization
- `src/components/LanguageSwitcher.test.tsx` - Language switcher component
- `src/__tests__/integration/language-switching.integration.test.tsx` - Behavior, persistence, fallback

### E2E Tests
- Specification: `.claude/commands/e2e/test_language_support.md`
- Run: Follow `.claude/commands/test_e2e.md`

### Manual Verification

Verify per language: translations (nav, forms, errors), persistence on reload, console warnings.

## Design Notes

### Translation Quality
- Baseline translations with linguistic knowledge of isiZulu, Sepedi, isiXhosa
- Production use requires professional native speaker review
- Technical terms use English loanwords where direct translations unavailable

### Performance
- Lazy loading: on-demand file loading reduces initial bundle
- Code splitting: namespaces loaded only when needed
- Language switching: instant, no page reload required
- Negligible bundle size impact (~3,800 lines)

### Browser Support
- All modern browsers supported
- Browser language detection via standard APIs
- localStorage persistence (graceful fallback if unavailable)

### Future Enhancements
- Support additional South African languages (Afrikaans, Sesotho, Setswana, siSwati, Tshivenda, Xitsonga)
- Language-specific date/time and number formatting
- Language-specific pluralization rules
- Translation management workflow
