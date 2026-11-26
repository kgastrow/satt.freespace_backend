# Frontend Version Control

**ADW ID:** 20260109234345-22956caa | **Date:** 2026-01-10
**Specification:** specs/multi-phase/issue-99-adw-20260109234345-22956caa-multi-phase.md

## Overview

Automatic update detection system that embeds build metadata (git commit hash, version, timestamp) at build time, generates `version.json`, and displays a dismissible banner when updates are detected.

## Implementation

### Files Modified

- `app/frontend/vite.config.ts`: Plugin generates `version.json` in `public/` (dev) and `dist/` (production) with `version`, `commit_hash`, and `build_time` fields; build-time injection of git commit hash
- `app/frontend/src/types/version.ts`: Version interface
- `app/frontend/src/hooks/useVersionCheck.ts`: Custom hook fetches `/version.json` every 5 minutes (configurable) with cache-busting, compares commit hashes, stores in localStorage to prevent false positives
- `app/frontend/src/components/UpdateBanner.tsx`: Fixed-position banner with refresh (clears caches and reloads) and dismiss buttons
- `app/frontend/src/main.tsx`: Integrated UpdateBanner
- `app/frontend/src/locales/{en,de}/common.json`: Translations for `updateBanner.message`, `updateBanner.refresh`, `updateBanner.dismiss`
- `app/frontend/.gitignore`: Added `public/version.json`

### Build-Time Configuration

- `VITE_BUILD_VERSION`: From package.json
- `VITE_BUILD_COMMIT`: From `git rev-parse HEAD`
- `VITE_BUILD_TIME`: ISO-8601 timestamp

### Key Features

- **Commit hash comparison**: Most reliable indicator of code changes
- **False positive prevention**: Only appears after first mismatch detected; localStorage tracks last known version
- **Non-intrusive UX**: Fixed banner, dismissible, non-blocking
- **Cache clearing**: Clears localStorage version data and sessionStorage while preserving auth tokens
- **Backend-independent**: Entirely frontend-based; works with independent frontend/backend deployments
- **Cache-busting**: Fetches version.json with query parameter to bypass browser cache

## Developer Usage

Customize polling interval via hook options:
```typescript
const { hasUpdate, refresh } = useVersionCheck({
  interval: 10 * 60 * 1000, // 10 minutes (default: 5 minutes)
  enabled: true
})
```

## Testing

From `app/frontend/`:
```bash
npm run build   # Verify version.json generation and metadata injection
npm run test    # Run tests
npm run lint    # Lint check
```

**Manual:** Edit `public/version.json` commit_hash to simulate update; verify banner appears within 5 minutes; click refresh to reload with fresh assets.
