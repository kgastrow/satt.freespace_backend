"""
FastAPI API v1 router module.

This module aggregates all v1 API routers and exports the main v1_router
that can be included in the FastAPI application.
"""

from fastapi import APIRouter

from src.api import (
    about,
    account_linking,
    admin,
    announcement,
    api_key,
    api_key_rate_limit,
    audit_log,
    auth,
    background_jobs,
    # Changelog router
    changelog,
    cron_jobs,
    email_change,
    email_settings,
    feature_flag,
    feedback,
    file,
    file_serve,
    freespace_events,
    freespace_keys,
    freespace_push,
    freespace_sites,
    freespace_stats,
    freespace_zones,
    help_center,
    impersonation,
    invitation,
    maintenance,
    metrics,
    notification,
    onboarding,
    onboarding_review,
    onboarding_step,
    organization,
    organization_sso_settings,
    organization_two_factor_settings,
    payment_methods,
    payment_settings,
    # Payment routers
    payments,
    phone_verification,
    push,
    # Report routers
    report,
    report_schedule,
    request_log,
    role,
    sessions,
    sso,
    system_config,
    two_factor,
    user,
    user_data,
    user_identities,
    user_notification,
    user_otp,
    user_role,
    user_type,
    users,
    # Notification webhooks
    webhooks_notifications,
    webhooks_payments,
)


# Create the main v1 API router
v1_router = APIRouter()

# Include all sub-routers
# Auth router (no prefix, it has its own /auth prefix)
v1_router.include_router(auth.router)

# Account linking router (has /auth/sso prefix) - for SSO account linking
v1_router.include_router(account_linking.router)

# Sessions router (has /sessions prefix) - for session management
v1_router.include_router(sessions.router)

# User router (no prefix, it has its own /user prefix) - for self-service user operations
v1_router.include_router(user.router)

# User identities router (has /user/me/identities prefix) - for managing connected accounts
v1_router.include_router(user_identities.router)

# Users router (has /api/users prefix) - for admin user management
v1_router.include_router(users.router)

# Organization router (has /api/organizations prefix)
v1_router.include_router(organization.router)

# Role router (has /api/roles prefix)
v1_router.include_router(role.router)

# User role router (has /api/user-roles prefix)
v1_router.include_router(user_role.router)

# User OTP router (no prefix, it has its own /user-otp prefix)
v1_router.include_router(user_otp.router)

# Audit log router (has /api/audit-logs prefix)
v1_router.include_router(audit_log.router)

# Metrics router (has /api/metrics prefix)
v1_router.include_router(metrics.router)

# File router (has /files prefix)
v1_router.include_router(file.router)

# File serve router (has /files/serve prefix) - for local storage file serving
v1_router.include_router(file_serve.router)

# Admin router (has /admin prefix) - super admin only
v1_router.include_router(admin.router)

# User notification router (has /notifications/in-app prefix) - user's own in-app notifications
# NOTE: Must be included BEFORE notification router to avoid path conflicts
v1_router.include_router(user_notification.router)

# Web Push router (has /notifications/push prefix) - must come BEFORE the
# notification router, whose /notifications/{notification_id} route would
# otherwise swallow /notifications/push/... as an id.
v1_router.include_router(push.router)

# Notification router (has /notifications prefix)
v1_router.include_router(notification.router)

# SSO router (has /sso prefix)
v1_router.include_router(sso.router)

# Organization SSO settings router (has /organization-sso-settings prefix)
v1_router.include_router(organization_sso_settings.router)

# API key router (has /api-keys prefix)
v1_router.include_router(api_key.router)

# API key rate limit router (has /admin/api-key-rate-limits prefix) - super admin only
v1_router.include_router(api_key_rate_limit.router)

# Impersonation router (has /admin/impersonate prefix) - super admin only
v1_router.include_router(impersonation.router)

# User impersonation router (has /impersonate prefix) - user-facing impersonation history
v1_router.include_router(impersonation.user_router)

v1_router.include_router(announcement.router)

# Help Center router (has /help prefix) - public and admin endpoints
v1_router.include_router(help_center.router)

# Two-factor authentication router (has /two-factor prefix)
v1_router.include_router(two_factor.router)

# Organization Two-Factor Settings router (has /organization-two-factor-settings prefix)
v1_router.include_router(organization_two_factor_settings.router)
# Cron Jobs router (has /cron-jobs prefix) - super admin only
v1_router.include_router(cron_jobs.router)
# Request Log router (has /admin/request-logs prefix) - super admin only
v1_router.include_router(request_log.router)

# Feature Flag router (has /feature-flags and /admin/feature-flags prefixes)
v1_router.include_router(feature_flag.router)
# Maintenance router (has /maintenance prefix) - includes public status endpoint
v1_router.include_router(maintenance.router)
# Feedback router (has /feedback prefix) - user submissions and admin management
v1_router.include_router(feedback.router)
# User data router (has /users/me prefix) - for data export and deletion
v1_router.include_router(user_data.router)

# User Type router (has /user-types and /admin/user-types prefixes)
v1_router.include_router(user_type.router)
# Onboarding Step router (has /admin/onboarding-steps prefix) - super admin only
v1_router.include_router(onboarding_step.router)
# Onboarding Review router (has /onboarding/review prefix) - org admin only
v1_router.include_router(onboarding_review.router)
# Onboarding router (has /onboarding prefix) - user-facing onboarding endpoints
v1_router.include_router(onboarding.router)

# Email change router (has /users/me/email prefix) - user's own email change
v1_router.include_router(email_change.router)

# System Config router (has /admin/system-config prefix) - super admin only
v1_router.include_router(system_config.router)

# Email Settings router (has /email-settings prefix) - org admin with permissions
v1_router.include_router(email_settings.router)

# Phone verification router (has /user/me/phone prefix) - user-facing phone verification
v1_router.include_router(phone_verification.router)

# Payment routers
v1_router.include_router(payments.router)
v1_router.include_router(payment_settings.router)
v1_router.include_router(payment_methods.router)
v1_router.include_router(webhooks_payments.router)

# Notification webhooks router (has /webhooks/notifications prefix)
v1_router.include_router(webhooks_notifications.router)

# Background Jobs router (has /background-jobs prefix) - super admin only
v1_router.include_router(background_jobs.router)

# About page router (has /about prefix) - public read, admin write
v1_router.include_router(about.router)

# Report routers (have /reports and /report-schedules prefixes)
v1_router.include_router(report.router)
v1_router.include_router(report_schedule.router)

# Changelog router (has /changelogs prefix)
v1_router.include_router(changelog.router)

# Invitation router (has /invitations prefix) - org admin with users:write permission
# NOTE: /invitations/validate/{token} public route is registered first inside the router
v1_router.include_router(invitation.router)

# Freespace back-office routers (all under /admin/sites..., /admin/app-keys).
# ORDER MATTERS (CLAUDE.md rule 13): freespace_stats owns the literal
# single-segment routes /admin/sites/summary and /admin/sites/device-stats, so
# it must come BEFORE freespace_sites, whose /admin/sites/{site_id} would
# otherwise capture them. freespace_sites stays last.
v1_router.include_router(freespace_stats.router)
v1_router.include_router(freespace_events.router)
v1_router.include_router(freespace_push.router)
v1_router.include_router(freespace_keys.router)
v1_router.include_router(freespace_keys.app_keys_router)
v1_router.include_router(freespace_zones.router)
v1_router.include_router(freespace_sites.router)

__all__ = ["v1_router"]
