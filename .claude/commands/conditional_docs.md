# Conditional Documentation Guide

Read relevant `app_docs/` files based on your task. Only read what applies.

## Core Documentation

| Trigger | Documentation |
|---------|---------------|
| Backend or frontend work, project structure | `README.md` |
| Client styling changes | `app/frontend/src/style.css` |
| Adding/removing `adws/adw_*.py` files | `.claude/commands/classify_adw.md` |
| Working in `adws/` directory | `adws/README.md` |

## Feature Documentation

| Trigger | Documentation |
|---------|---------------|
| Smoke testing, Playwright, browser testing | `chrome-smoke-testing.md` |
| Theme switching, light/dark mode | `light-mode.md` |
| Loading states, skeleton loaders | `skeleton-loaders.md` |
| SSO, OAuth providers, SSO buttons | `google-sso.md` |
| Frontend version checking, update banners | `frontend-version-control.md` |
| API versioning, breaking changes | `api-versioning.md` |
| OpenAPI, TypeScript type generation | `openapi-typescript-generation.md` |
| Super admin impersonation | `super-admin-impersonation.md` |
| API key authentication | `api-key-authentication.md` |
| Permission gates, `usePermission` hooks | `permission-gate.md` |
| WebSocket, real-time messaging | `websocket-realtime-messaging.md` |
| In-app notifications, NotificationBell | `in-app-notifications.md` |
| Impersonation audit/transparency | `impersonation-transparency.md` |
| i18n, language support, translations | `south-african-languages.md` |
| Localized backend responses, error codes | `localized-backend-responses.md` |
| Announcement banners, dismissible UI | `dismissible-announcement-banner.md` |
| Help center, FAQs, articles | `help-center.md` |
| API key permissions, rate limiting | `api-key-permissions-rate-limits.md` |
| 2FA, TOTP, authenticator apps | `two-factor-authentication.md` |
| Cron jobs, scheduled tasks | `cron-job-management.md` |
| User suspension, account disabling | `user-suspension.md` |
| Image/media upload, S3 storage | `image-upload-s3-storage.md` |
| Request/response logging middleware | `request-response-logging.md` |
| Feature flags, toggles | `feature-flags-system.md` |
| Maintenance mode, system status | `maintenance-mode.md` |
| Multiple bugfixes (issue-147) | `multiple-bugfixes.md` |
| User avatars, profile images | `user-avatar-upload.md` |
| Feedback widget, bug reports | `feedback-widget.md` |
| GDPR data export/deletion | `user-data-export-deletion.md` |
| User onboarding, registration flows | `user-onboarding-flows.md` |
| Email change, identity verification | `email-change.md` |
| Image thumbnails, Pillow | `media-thumbnails.md` |
| Admin navigation, hub pages | `admin-nav-consolidation.md` |
| UI refactoring, permission service, auth hooks, navigation config | `ui-refactoring-optimisations.md` |

All feature docs are in `app_docs/` directory.
