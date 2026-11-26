# E2E Test Coverage Plan

## Overview

This document tracks all frontend features requiring E2E test coverage. The goal is near 100% coverage of frontend integration points.

**Current Status:**
- Existing E2E tests: 70 scenarios (9 original + 14 Phase 1 + 56 Phase 2)
- Features requiring coverage: 22 remaining (P2)
- **Phase 1 Complete:** All 14 P0 (Critical Path) tests created
- **Phase 2 Complete:** All 56 P1 (Core Features) tests created

---

## Priority Levels

| Priority | Description | Target |
|----------|-------------|--------|
| P0 | Critical path - blocks user workflows | Must have |
| P1 | Core features - primary functionality | Should have |
| P2 | Secondary features - admin/config | Nice to have |
| P3 | Edge cases and accessibility | Future |

---

## Feature Categories

### 1. Authentication (P0) - 10 tests ✅ COMPLETE

| # | Feature | Test Scenario | API Endpoints | Status |
|---|---------|---------------|---------------|--------|
| 1.1 | Login | Email/password login success | POST `/auth/login` | ✅ `test_login_success.md` |
| 1.2 | Login | Invalid credentials error | POST `/auth/login` | ✅ `test_login_invalid_credentials.md` |
| 1.3 | Registration | New user registration with email verification | POST `/user/register`, POST `/user-otp/verify-email` | ✅ `test_registration.md` |
| 1.4 | Forgot Password | Password reset request flow | POST `/auth/password-reset/request` | ✅ `test_forgot_password.md` |
| 1.5 | Reset Password | Password reset with token | POST `/auth/password-reset/confirm` | ✅ `test_reset_password.md` |
| 1.6 | 2FA Setup | Enable 2FA with QR code and backup codes | POST `/two-factor/setup`, POST `/two-factor/verify` | ✅ `test_2fa_setup.md` |
| 1.7 | 2FA Login | Login requiring 2FA verification | POST `/auth/verify-2fa` | ✅ `test_2fa_login.md` |
| 1.8 | 2FA Disable | Disable 2FA with verification | DELETE `/two-factor` | ✅ `test_2fa_disable.md` |
| 1.9 | SSO Login | Google OAuth login flow | GET `/auth/sso/google`, GET `/auth/callback` | ✅ `test_sso_login.md` |
| 1.10 | Logout | Session termination | POST `/auth/logout` | ✅ `test_logout.md` |

### 2. Session Management (P0) - 4 tests ✅ COMPLETE

| # | Feature | Test Scenario | API Endpoints | Status |
|---|---------|---------------|---------------|--------|
| 2.1 | View Sessions | List active sessions | GET `/sessions` | ✅ `test_view_sessions.md` |
| 2.2 | Revoke Session | Terminate specific session | DELETE `/sessions/{id}` | ✅ `test_revoke_session.md` |
| 2.3 | Token Refresh | Automatic token refresh on expiry | POST `/auth/refresh` | ✅ `test_token_refresh.md` |
| 2.4 | Session Expiry | Auto-logout on session expiration | - | ✅ `test_session_expiry.md` |

### 3. User Profile & Settings (P1) - 8 tests ✅ COMPLETE

| # | Feature | Test Scenario | API Endpoints | Status |
|---|---------|---------------|---------------|--------|
| 3.1 | View Profile | Display user profile information | GET `/user/me` | ✅ `test_view_profile.md` |
| 3.2 | Update Profile | Edit name and profile details | PUT `/user/me` | ✅ `test_update_profile.md` |
| 3.3 | Upload Avatar | Upload profile picture | POST `/user/me/avatar` | ✅ `test_upload_avatar.md` |
| 3.4 | Change Password | Update password with current password | POST `/user/me/change-password` | ✅ `test_change_password.md` |
| 3.5 | Change Email | Email change with OTP verification | POST `/user/me/email-change/*` | ✅ `test_change_email.md` |
| 3.6 | Delete Account | Request account deletion (30-day grace) | POST `/users/me/delete` | ✅ `test_delete_account.md` |
| 3.7 | Cancel Deletion | Cancel pending account deletion | POST `/users/me/delete/cancel` | ✅ `test_cancel_deletion.md` |
| 3.8 | Data Export | Request user data export | POST `/users/me/export` | ✅ `test_data_export.md` |

### 4. User Management - Admin (P1) - 8 tests ✅ COMPLETE

| # | Feature | Test Scenario | API Endpoints | Status |
|---|---------|---------------|---------------|--------|
| 4.1 | List Users | View paginated user list with search | GET `/users` | ✅ `test_list_users.md` |
| 4.2 | Create User | Create new user account | POST `/users` | ✅ `test_create_user.md` |
| 4.3 | Edit User | Update user details | PUT `/users/{id}` | ✅ `test_edit_user.md` |
| 4.4 | Delete User | Soft delete user | DELETE `/users/{id}` | ✅ `test_delete_user.md` |
| 4.5 | Suspend User | Suspend/unsuspend user account | PATCH `/users/{id}/suspend` | ✅ `test_suspend_user.md` |
| 4.6 | Assign Role | Assign role to user | POST `/user-roles` | ✅ `test_assign_role.md` |
| 4.7 | Remove Role | Remove role from user | DELETE `/user-roles/{id}` | ✅ `test_remove_role.md` |
| 4.8 | Impersonation | Start/end user impersonation | POST `/admin/impersonate/{id}` | ✅ `test_impersonation.md` |

### 5. Role & Permission Management (P1) - 5 tests ✅ COMPLETE

| # | Feature | Test Scenario | API Endpoints | Status |
|---|---------|---------------|---------------|--------|
| 5.1 | List Roles | View all roles | GET `/roles` | ✅ `test_list_roles.md` |
| 5.2 | Create Role | Create new role with permissions | POST `/roles` | ✅ `test_create_role.md` |
| 5.3 | Edit Role | Update role permissions | PUT `/roles/{id}` | ✅ `test_edit_role.md` |
| 5.4 | Delete Role | Remove role | DELETE `/roles/{id}` | ✅ `test_delete_role.md` |
| 5.5 | Permission Gate | Verify UI respects permissions | - | ✅ `test_permission_gate.md` |

### 6. Organization Management (P1) - 6 tests ✅ COMPLETE

| # | Feature | Test Scenario | API Endpoints | Status |
|---|---------|---------------|---------------|--------|
| 6.1 | View Organization | Display organization details | GET `/organizations/{id}` | ✅ `test_view_organization.md` |
| 6.2 | Update Organization | Edit org name, description, logo | PUT `/organizations/{id}` | ✅ `test_update_organization.md` |
| 6.3 | List Organizations | Super admin org list | GET `/organizations` | ✅ `test_list_organizations.md` |
| 6.4 | Create Organization | Super admin create org | POST `/organizations` | ✅ `test_create_organization.md` |
| 6.5 | Delete Organization | Request org deletion | POST `/organizations/{id}/request-deletion` | ✅ `test_delete_organization.md` |
| 6.6 | Organization Members | View/manage org members | GET `/organizations/{id}/members` | ✅ `test_organization_members.md` |

### 7. File Management (P1) - 6 tests ✅ COMPLETE

| # | Feature | Test Scenario | API Endpoints | Status |
|---|---------|---------------|---------------|--------|
| 7.1 | List Files | View files with grid/list toggle | GET `/files` | ✅ `test_list_files.md` |
| 7.2 | Upload File | Upload file via drag-and-drop | POST `/files/upload` | ✅ `test_upload_file.md` |
| 7.3 | Download File | Download file | GET `/files/{id}/download` | ✅ `test_download_file.md` |
| 7.4 | Delete File | Remove file | DELETE `/files/{id}` | ✅ `test_delete_file.md` |
| 7.5 | Storage Usage | Display storage usage bar | GET `/files/usage` | ✅ `test_storage_usage.md` |
| 7.6 | File Settings | Configure upload limits (admin) | PUT `/files/settings` | ✅ `test_file_settings.md` |

### 8. Notifications (P1) - 8 tests ✅ COMPLETE

| # | Feature | Test Scenario | API Endpoints | Status |
|---|---------|---------------|---------------|--------|
| 8.1 | Notification Bell | Display unread count badge | WebSocket | ✅ `test_notification_bell.md` |
| 8.2 | Notification Panel | View notification list | WebSocket | ✅ `test_notification_panel.md` |
| 8.3 | Mark as Read | Mark notification read | POST `/notifications/{id}/read` | ✅ `test_mark_notification_read.md` |
| 8.4 | Preferences | Update notification preferences | PUT `/notifications/preferences` | ✅ `test_notification_preferences.md` |
| 8.5 | Send Notification | Admin send to user/org | POST `/notifications/send` | ✅ `test_send_notification.md` |
| 8.6 | Bulk Notifications | Create bulk campaign | POST `/notifications/bulk` | ✅ `test_bulk_notifications.md` |
| 8.7 | Templates | Manage notification templates | CRUD `/notifications/templates` | ✅ `test_notification_templates.md` |
| 8.8 | Unsubscribe | Email unsubscribe link | GET `/notifications/unsubscribe` | ✅ `test_notification_unsubscribe.md` |

### 9. Onboarding (P1) - 5 tests ✅ COMPLETE

| # | Feature | Test Scenario | API Endpoints | Status |
|---|---------|---------------|---------------|--------|
| 9.1 | Onboarding Status | Check onboarding progress | GET `/onboarding/status` | ✅ `test_onboarding_status.md` |
| 9.2 | Form Submission | Complete onboarding form | POST `/onboarding/submissions` | ✅ `test_onboarding_form.md` |
| 9.3 | Multi-Step Progress | Navigate between steps | - | ✅ `test_onboarding_multistep.md` |
| 9.4 | Field Rendering | All field types render correctly | - | ✅ `test_onboarding_fields.md` |
| 9.5 | Admin Review | Review/approve submissions | GET/POST `/onboarding/submissions` | ✅ `test_onboarding_admin_review.md` |

### 10. SSO & Security Settings (P1) - 4 tests ✅ COMPLETE

| # | Feature | Test Scenario | API Endpoints | Status |
|---|---------|---------------|---------------|--------|
| 10.1 | SSO Settings | Configure SSO providers | PUT `/organization-sso-settings` | ✅ `test_sso_settings.md` |
| 10.2 | 2FA Enforcement | Enable org-wide 2FA requirement | PUT `/organization-two-factor-settings` | ✅ `test_2fa_enforcement.md` |
| 10.3 | Connected Accounts | View/manage SSO connections | GET `/sso/connections` | ✅ `test_connected_accounts.md` |
| 10.4 | Email Settings | Configure email provider | PUT `/email-settings` | ✅ `test_email_settings.md` |

### 11. Help Center & Feedback (P2) - 5 tests needed

| # | Feature | Test Scenario | API Endpoints | Status |
|---|---------|---------------|---------------|--------|
| 11.1 | Browse Articles | View help categories and articles | GET `/help/categories` | ❌ |
| 11.2 | Read Article | View article content | GET `/help/articles/{slug}` | ❌ |
| 11.3 | Manage Articles | Admin CRUD articles | CRUD `/help/admin/articles` | ❌ |
| 11.4 | Submit Feedback | User feedback form | POST `/feedback` | ❌ |
| 11.5 | View Feedback | Admin feedback list | GET `/feedback` | ❌ |

### 12. System Administration (P2) - 8 tests needed

| # | Feature | Test Scenario | API Endpoints | Status |
|---|---------|---------------|---------------|--------|
| 12.1 | Metrics Dashboard | View system metrics with auto-refresh | GET `/metrics` | ❌ |
| 12.2 | Cron Jobs | Manage scheduled jobs | CRUD `/cron-jobs` | ❌ |
| 12.3 | Feature Flags | Toggle feature flags | CRUD `/feature-flags` | ❌ |
| 12.4 | API Keys | Generate/revoke API keys | CRUD `/api-keys` | ❌ |
| 12.5 | Rate Limits | Configure rate limits | PUT `/api-key-rate-limits` | ❌ |
| 12.6 | System Config | Update system configuration | PUT `/system-config` | ❌ |
| 12.7 | Maintenance Mode | Toggle maintenance | POST `/maintenance` | ❌ |
| 12.8 | Announcements | Create system announcements | CRUD `/announcements` | ❌ |

### 13. Audit & Logging (P2) - 2 tests needed

| # | Feature | Test Scenario | API Endpoints | Status |
|---|---------|---------------|---------------|--------|
| 13.1 | Audit Logs | View audit logs with filtering | GET `/audit-logs` | ❌ |
| 13.2 | Request Logs | View API request logs | GET `/request-logs` | ❌ |

### 14. Navigation & Layout (P1) - 4 tests ✅ COMPLETE

| # | Feature | Test Scenario | API Endpoints | Status |
|---|---------|---------------|---------------|--------|
| 14.1 | Admin Hub | Navigate admin hub cards | - | ✅ `test_admin_hub_navigation.md` |
| 14.2 | Platform Admin Hub | Platform admin navigation | - | ✅ Partial |
| 14.3 | Settings Navigation | Navigate settings pages | - | ✅ `test_settings_navigation.md` |
| 14.4 | Sidebar Navigation | Main sidebar navigation | - | ✅ `test_sidebar_navigation.md` |

### 15. Localization (P1) - 2 tests ✅ COMPLETE

| # | Feature | Test Scenario | API Endpoints | Status |
|---|---------|---------------|---------------|--------|
| 15.1 | Language Switch | Switch between 5 languages | - | ✅ `test_language_support.md` |
| 15.2 | Locale Persistence | Language persists on reload | - | ✅ `test_locale_persistence.md` |

### 16. Real-Time Features (P2) - 4 tests needed

| # | Feature | Test Scenario | API Endpoints | Status |
|---|---------|---------------|---------------|--------|
| 16.1 | WebSocket Connect | Establish WebSocket connection | ws://*/ws | ❌ |
| 16.2 | Announcements | Receive real-time announcements | WebSocket | ❌ |
| 16.3 | Maintenance Alert | Receive maintenance notifications | WebSocket | ❌ |
| 16.4 | Export Progress | Real-time export status | WebSocket | ❌ |

### 17. Error Handling (P2) - 3 tests needed

| # | Feature | Test Scenario | API Endpoints | Status |
|---|---------|---------------|---------------|--------|
| 17.1 | 404 Page | Display not found page | - | ❌ |
| 17.2 | Maintenance Page | Display maintenance page | - | ❌ |
| 17.3 | API Error Toast | Display error messages | - | ❌ |

### 18. Existing Coverage (Already Tested)

| # | Feature | Test File | Status |
|---|---------|-----------|--------|
| E1 | Smoke Test Workflow | `test_smoke_test_workflow.md` | ✅ |
| E2 | Admin Hub Navigation | `test_admin_hub_navigation.md` | ✅ |
| E3 | Language Support | `test_language_support.md` | ✅ |
| E4 | Basic Query | `test_basic_query.md` | ✅ |
| E5 | Complex Query | `test_complex_query.md` | ✅ |
| E6 | Export Functionality | `test_export_functionality.md` | ✅ |
| E7 | Random Query Generator | `test_random_query_generator.md` | ✅ |
| E8 | Disable Input Debounce | `test_disable_input_debounce.md` | ✅ |
| E9 | SQL Injection Protection | `test_sql_injection.md` | ✅ |
| E10 | Login Success | `test_login_success.md` | ✅ |
| E11 | Login Invalid Credentials | `test_login_invalid_credentials.md` | ✅ |
| E12 | Registration | `test_registration.md` | ✅ |
| E13 | Forgot Password | `test_forgot_password.md` | ✅ |
| E14 | Reset Password | `test_reset_password.md` | ✅ |
| E15 | 2FA Setup | `test_2fa_setup.md` | ✅ |
| E16 | 2FA Login | `test_2fa_login.md` | ✅ |
| E17 | 2FA Disable | `test_2fa_disable.md` | ✅ |
| E18 | SSO Login | `test_sso_login.md` | ✅ |
| E19 | Logout | `test_logout.md` | ✅ |
| E20 | View Sessions | `test_view_sessions.md` | ✅ |
| E21 | Revoke Session | `test_revoke_session.md` | ✅ |
| E22 | Token Refresh | `test_token_refresh.md` | ✅ |
| E23 | Session Expiry | `test_session_expiry.md` | ✅ |

---

## Summary Statistics

| Category | Tests Needed | Completed | Priority |
|----------|-------------|-----------|----------|
| Authentication | 10 | ✅ 10 | P0 |
| Session Management | 4 | ✅ 4 | P0 |
| User Profile | 8 | ✅ 8 | P1 |
| User Admin | 8 | ✅ 8 | P1 |
| Roles & Permissions | 5 | ✅ 5 | P1 |
| Organization | 6 | ✅ 6 | P1 |
| Files | 6 | ✅ 6 | P1 |
| Notifications | 8 | ✅ 8 | P1 |
| Onboarding | 5 | ✅ 5 | P1 |
| Security Settings | 4 | ✅ 4 | P1 |
| Help & Feedback | 5 | 0 | P2 |
| System Admin | 8 | 0 | P2 |
| Audit & Logging | 2 | 0 | P2 |
| Navigation | 4 | ✅ 4 | P1 |
| Localization | 2 | ✅ 2 | P1 |
| Real-Time | 4 | 0 | P2 |
| Error Handling | 3 | 0 | P2 |
| **TOTAL** | **92** | **70** | - |

**By Priority:**
- P0 (Critical): 14 tests ✅ **COMPLETE**
- P1 (Core): 56 tests ✅ **COMPLETE**
- P2 (Secondary): 22 tests

---

## Implementation Phases

### Phase 1: Critical Path (P0) - 14 tests ✅ COMPLETE
Focus: Authentication and session management
- ✅ All login/logout flows (test_login_success, test_login_invalid_credentials, test_logout)
- ✅ Registration and password reset (test_registration, test_forgot_password, test_reset_password)
- ✅ 2FA setup and verification (test_2fa_setup, test_2fa_login, test_2fa_disable)
- ✅ SSO Login (test_sso_login)
- ✅ Session management (test_view_sessions, test_revoke_session, test_token_refresh, test_session_expiry)

### Phase 2: Core Features (P1) - 56 tests ✅ COMPLETE
Focus: Primary user functionality
- ✅ User profile management (8 tests)
- ✅ User/role/org administration (19 tests)
- ✅ File management (6 tests)
- ✅ Notifications (8 tests)
- ✅ Onboarding (5 tests)
- ✅ SSO & Security Settings (4 tests)
- ✅ Navigation and localization (6 tests)

### Phase 3: Admin & Secondary (P2) - 22 tests
Focus: Administrative and edge cases
- System administration
- Help center
- Real-time features
- Error handling

---

## Test Generation Workflow

For each feature, create a test spec file in `.claude/commands/e2e/`:

1. **File naming**: `test_<feature_name>.md`
2. **Content structure**:
   - User story
   - Preconditions
   - Test steps with selectors
   - Expected results
   - Success criteria

3. **Run test**: Use `/e2e:test_<feature_name>` skill

4. **Update status**: Mark as ✅ in this document

---

## Notes

- All tests require authentication setup via `/setup_test_auth`
- Use `data-testid` attributes for reliable selectors
- Verify selectors exist in component source before adding to tests
- Tests run via Playwright in headless mode by default
