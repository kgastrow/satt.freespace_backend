"""
CRUD (Create, Read, Update, Delete) operations for all models.

All CRUD functions are async and use SQLAlchemy 2.0 with AsyncSession.
Tenant-scoped CRUD functions require organization_id parameter for multi-tenancy isolation.
"""

# User CRUD
# Announcement CRUD
from .announcement import (
    create_announcement,
    get_active_announcements,
    get_announcement_by_id,
    get_announcements,
    soft_delete_announcement,
    update_announcement,
)

# AnnouncementDismissal CRUD
from .announcement_dismissal import (
    create_dismissal,
    get_dismissal_by_ids,
    get_dismissals_for_announcement,
    get_user_dismissals,
    is_dismissed,
)

# ApiKey CRUD
from .api_key import (
    assign_permissions,
    create_api_key,
    delete_api_key,
    get_api_key_by_id,
    get_api_key_permissions,
    get_api_keys_by_organization,
    remove_permissions,
    update_api_key,
    validate_api_key,
)

# ApiKeyRateLimit CRUD
from .api_key_rate_limit import (
    create_rate_limit,
    delete_rate_limit,
    get_all_rate_limits,
    get_rate_limit_by_permission,
    update_rate_limit,
)

# BulkNotification CRUD
from .bulk_notification import (
    cancel_bulk_notification,
    create_bulk_notification,
    get_bulk_notification,
    get_bulk_notifications,
    get_pending_bulk_notifications,
    soft_delete_bulk_notification,
    update_bulk_progress,
)

# CronJob CRUD
from .cron_job import (
    calculate_next_run_time,
    create_cron_job,
    get_cron_job_by_code,
    get_cron_job_by_id,
    get_cron_jobs,
    get_due_cron_jobs,
    get_executions,
    get_latest_execution,
    is_valid_cron_expression,
    record_execution_complete,
    record_execution_start,
    soft_delete_cron_job,
    update_cron_job,
    update_next_run_time,
)

# FeatureFlag CRUD
from .feature_flag import (
    create_feature_flag,
    create_override,
    delete_feature_flag,
    delete_override,
    get_all_feature_flags,
    get_feature_flag_by_id,
    get_feature_flag_by_key,
    get_override,
    get_overrides_for_flag,
    get_resolved_flags_for_organization,
    update_feature_flag,
)

# Feedback CRUD
from .feedback import (
    create_feedback,
    create_feedback_attachment,
    delete_attachment,
    get_attachments_by_feedback_id,
    get_feedback_by_id,
    get_feedbacks_list,
    get_user_feedbacks,
    soft_delete_feedback,
    update_feedback,
)

# File CRUD
from .file import (
    create_file,
    get_file_by_id,
    get_files,
    increment_download_count,
    soft_delete_file,
    update_file_metadata,
    update_file_status,
)

# File Settings CRUD
from .file_settings import (
    check_file_allowed,
    check_quota,
    get_file_settings,
    get_file_settings_by_id,
    update_file_settings,
)

# File Usage CRUD
from .file_usage import (
    get_all_user_usage,
    get_or_create_usage,
    get_organization_usage,
    get_user_usage,
    update_usage_on_delete,
    update_usage_on_upload,
)
from .help_center import (
    create_article,
    create_faq,
    get_article_by_id,
    get_article_by_slug,
    get_articles,
    get_faq_by_id,
    get_faqs,
    search_articles,
    search_faqs,
    soft_delete_article,
    soft_delete_faq,
    update_article,
    update_faq,
)

# HelpCenter CRUD
from .help_center import (
    create_category as create_help_category,
)
from .help_center import (
    get_categories as get_help_categories,
)
from .help_center import (
    get_category_by_id as get_help_category_by_id,
)
from .help_center import (
    get_category_by_slug as get_help_category_by_slug,
)
from .help_center import (
    soft_delete_category as soft_delete_help_category,
)
from .help_center import (
    update_category as update_help_category,
)

# ImpersonationSession CRUD
from .impersonation_session import (
    create_session,
    end_session,
    get_active_session_by_impersonator,
    get_active_sessions_for_target,
    get_session_history,
)

# Notification CRUD
from .notification import (
    create_notification,
    get_notification_by_id,
    get_notifications,
    get_notifications_for_retry,
    soft_delete_notification,
    update_notification_status,
)

# NotificationCategory CRUD
from .notification_category import (
    create_category,
    create_system_category,
    delete_category,
    get_categories,
    get_category_by_code,
    get_category_by_id,
    get_system_categories,
    update_category,
)

# NotificationTemplate CRUD
from .notification_template import (
    create_system_template,
    create_template,
    delete_template,
    get_system_templates,
    get_template_by_code,
    get_template_by_id,
    get_templates,
    update_template,
)
from .onboarding_step import (
    create as create_onboarding_step,
)
from .onboarding_step import (
    get_all_for_user_type as get_onboarding_steps_for_user_type,
)
from .onboarding_step import (
    get_by_id as get_onboarding_step_by_id,
)
from .onboarding_step import (
    reorder as reorder_onboarding_steps,
)
from .onboarding_step import (
    soft_delete as soft_delete_onboarding_step,
)
from .onboarding_step import (
    update as update_onboarding_step,
)

# Organization CRUD
from .organization import (
    create_organization,
    delete_organization,
    get_organization_by_id,
    get_organization_by_slug,
    get_organizations,
    update_organization,
)

# Organization Member CRUD
from .organization_member import (
    get_organization_member_count,
    get_organization_members,
    remove_user_from_organization,
)

# OrganizationSSOSettings CRUD
from .organization_sso_settings import (
    create_organization_sso_settings,
    get_enabled_providers,
    get_organization_sso_settings,
    update_organization_sso_settings,
)

# Permission CRUD
from .permission import (
    create_permission,
    delete_permission,
    get_all_permissions,
    get_distinct_resources,
    get_permission_by_code,
    get_permission_by_id,
    update_permission,
)
from .phone_verification import (
    cleanup_expired as cleanup_expired_phone_verifications,
)
from .phone_verification import (
    count_recent_requests as count_phone_verification_requests,
)
from .phone_verification import (
    create_otp as create_phone_verification_otp,
)
from .phone_verification import (
    get_active_for_user as get_active_phone_verification,
)
from .phone_verification import (
    increment_attempts as increment_phone_verification_attempts,
)
from .phone_verification import (
    mark_verified as mark_phone_verified,
)
from .phone_verification import (
    verify_otp as verify_phone_otp,
)

# RefreshToken CRUD
from .refresh_token import (
    create_refresh_token,
    delete_all_refresh_tokens_for_user,
    delete_refresh_token,
    get_refresh_token,
)

# RequestLog CRUD
from .request_log import (
    create_request_log,
    delete_old_request_logs,
    get_request_log_by_id,
    get_request_logs,
)

# Role CRUD
from .role import (
    create_role,
    delete_role,
    get_role_by_id,
    get_role_by_name,
    list_roles,
    update_role,
)

# RolePermission CRUD
from .role_permission import (
    get_permission_matrix,
    get_role_permissions,
    get_user_permissions,
    grant_permission_to_role,
    revoke_permission_from_role,
    user_has_permission,
)
from .user import (
    create_user,
    delete_user,
    get_user_by_email,
    get_user_by_id,
    get_users,
    update_user,
)

# UserNotification CRUD (in-app notifications)
from .user_notification import (
    bulk_dismiss,
    create_user_notification,
    get_unread_count,
    get_user_notification_by_id,
    get_user_notifications,
    mark_all_as_read,
    mark_as_read,
    soft_delete_user_notification,
)
from .user_onboarding_progress import (
    create as create_onboarding_progress,
)
from .user_onboarding_progress import (
    get_progress_for_user_type,
    get_step_progress,
)
from .user_onboarding_progress import (
    update as update_onboarding_progress,
)

# UserOTP CRUD
from .user_otp import create_otp, generate_otp, verify_otp

# UserRole CRUD
from .user_role import (
    assign_role,
    get_all_user_roles_history,
    get_user_roles,
    revoke_role,
    user_has_role,
)
from .user_type import (
    create as create_user_type,
)

# Onboarding CRUD
from .user_type import (
    get_all as get_all_user_types,
)
from .user_type import (
    get_by_code as get_user_type_by_code,
)
from .user_type import (
    get_by_id as get_user_type_by_id,
)
from .user_type import (
    get_default as get_default_user_type,
)
from .user_type import (
    soft_delete as soft_delete_user_type,
)
from .user_type import (
    update as update_user_type,
)
from .user_user_type import (
    create as create_user_user_type,
)
from .user_user_type import (
    get_all_for_user as get_user_user_types,
)
from .user_user_type import (
    get_by_user_and_type,
)
from .user_user_type import (
    update_status as update_user_user_type_status,
)


__all__ = [
    # User
    "get_users",
    "get_user_by_id",
    "get_user_by_email",
    "create_user",
    "update_user",
    "delete_user",
    # Organization
    "create_organization",
    "get_organization_by_id",
    "get_organization_by_slug",
    "get_organizations",
    "update_organization",
    "delete_organization",
    # Role
    "create_role",
    "get_role_by_id",
    "get_role_by_name",
    "list_roles",
    "update_role",
    "delete_role",
    # UserRole
    "assign_role",
    "revoke_role",
    "get_user_roles",
    "get_all_user_roles_history",
    "user_has_role",
    # Permission
    "create_permission",
    "get_permission_by_code",
    "get_permission_by_id",
    "get_all_permissions",
    "update_permission",
    "delete_permission",
    "get_distinct_resources",
    # RolePermission
    "grant_permission_to_role",
    "revoke_permission_from_role",
    "get_role_permissions",
    "get_user_permissions",
    "user_has_permission",
    "get_permission_matrix",
    # Organization Member
    "get_organization_members",
    "remove_user_from_organization",
    "get_organization_member_count",
    # UserOTP
    "generate_otp",
    "create_otp",
    "verify_otp",
    # RefreshToken
    "create_refresh_token",
    "get_refresh_token",
    "delete_refresh_token",
    "delete_all_refresh_tokens_for_user",
    # File
    "create_file",
    "get_file_by_id",
    "get_files",
    "update_file_status",
    "soft_delete_file",
    "increment_download_count",
    "update_file_metadata",
    # File Usage
    "get_or_create_usage",
    "update_usage_on_upload",
    "update_usage_on_delete",
    "get_user_usage",
    "get_organization_usage",
    "get_all_user_usage",
    # File Settings
    "get_file_settings",
    "update_file_settings",
    "get_file_settings_by_id",
    "check_file_allowed",
    "check_quota",
    # Notification
    "create_notification",
    "get_notification_by_id",
    "get_notifications",
    "update_notification_status",
    "get_notifications_for_retry",
    "soft_delete_notification",
    # NotificationTemplate
    "get_template_by_code",
    "get_templates",
    "get_template_by_id",
    "create_template",
    "update_template",
    "delete_template",
    "create_system_template",
    "get_system_templates",
    # NotificationCategory
    "get_categories",
    "get_category_by_code",
    "get_category_by_id",
    "create_category",
    "update_category",
    "delete_category",
    "create_system_category",
    "get_system_categories",
    # BulkNotification
    "create_bulk_notification",
    "get_bulk_notification",
    "update_bulk_progress",
    "get_bulk_notifications",
    "cancel_bulk_notification",
    "get_pending_bulk_notifications",
    "soft_delete_bulk_notification",
    # OrganizationSSOSettings
    "get_organization_sso_settings",
    "create_organization_sso_settings",
    "update_organization_sso_settings",
    "get_enabled_providers",
    # ImpersonationSession
    "create_session",
    "get_active_session_by_impersonator",
    "get_active_sessions_for_target",
    "end_session",
    "get_session_history",
    # ApiKey
    "create_api_key",
    "get_api_key_by_id",
    "get_api_keys_by_organization",
    "update_api_key",
    "delete_api_key",
    "validate_api_key",
    "assign_permissions",
    "remove_permissions",
    "get_api_key_permissions",
    # ApiKeyRateLimit
    "create_rate_limit",
    "get_rate_limit_by_permission",
    "get_all_rate_limits",
    "update_rate_limit",
    "delete_rate_limit",
    # UserNotification (in-app)
    "create_user_notification",
    "get_user_notifications",
    "get_unread_count",
    "get_user_notification_by_id",
    "mark_as_read",
    "mark_all_as_read",
    "bulk_dismiss",
    "soft_delete_user_notification",
    # Announcement
    "create_announcement",
    "get_announcement_by_id",
    "get_active_announcements",
    "get_announcements",
    "update_announcement",
    "soft_delete_announcement",
    # AnnouncementDismissal
    "create_dismissal",
    "get_user_dismissals",
    "is_dismissed",
    "get_dismissal_by_ids",
    "get_dismissals_for_announcement",
    # RequestLog
    "create_request_log",
    "get_request_logs",
    "get_request_log_by_id",
    "delete_old_request_logs",
    # HelpCenter
    "create_help_category",
    "get_help_category_by_id",
    "get_help_category_by_slug",
    "get_help_categories",
    "update_help_category",
    "soft_delete_help_category",
    "create_article",
    "get_article_by_id",
    "get_article_by_slug",
    "get_articles",
    "search_articles",
    "update_article",
    "soft_delete_article",
    "create_faq",
    "get_faq_by_id",
    "get_faqs",
    "search_faqs",
    "update_faq",
    "soft_delete_faq",
    # CronJob
    "create_cron_job",
    "get_cron_job_by_id",
    "get_cron_job_by_code",
    "get_cron_jobs",
    "update_cron_job",
    "soft_delete_cron_job",
    "get_due_cron_jobs",
    "update_next_run_time",
    "calculate_next_run_time",
    "is_valid_cron_expression",
    "record_execution_start",
    "record_execution_complete",
    "get_executions",
    "get_latest_execution",
    # FeatureFlag
    "create_feature_flag",
    "get_feature_flag_by_id",
    "get_feature_flag_by_key",
    "get_all_feature_flags",
    "update_feature_flag",
    "delete_feature_flag",
    "create_override",
    "get_override",
    "delete_override",
    "get_overrides_for_flag",
    "get_resolved_flags_for_organization",
    # Feedback
    "create_feedback",
    "get_feedback_by_id",
    "get_feedbacks_list",
    "get_user_feedbacks",
    "update_feedback",
    "soft_delete_feedback",
    "create_feedback_attachment",
    "get_attachments_by_feedback_id",
    "delete_attachment",
    # Onboarding - UserType
    "get_all_user_types",
    "get_user_type_by_id",
    "get_user_type_by_code",
    "get_default_user_type",
    "create_user_type",
    "update_user_type",
    "soft_delete_user_type",
    # Onboarding - UserUserType
    "get_by_user_and_type",
    "get_user_user_types",
    "create_user_user_type",
    "update_user_user_type_status",
    # Onboarding - OnboardingStep
    "get_onboarding_steps_for_user_type",
    "get_onboarding_step_by_id",
    "create_onboarding_step",
    "update_onboarding_step",
    "reorder_onboarding_steps",
    "soft_delete_onboarding_step",
    # Onboarding - UserOnboardingProgress
    "get_progress_for_user_type",
    "get_step_progress",
    "create_onboarding_progress",
    "update_onboarding_progress",
    # Onboarding - PhoneVerification
    "create_phone_verification_otp",
    "verify_phone_otp",
    "get_active_phone_verification",
    "increment_phone_verification_attempts",
    "mark_phone_verified",
    "count_phone_verification_requests",
    "cleanup_expired_phone_verifications",
]
