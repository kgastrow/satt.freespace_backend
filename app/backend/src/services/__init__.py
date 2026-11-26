# Application services
#
# Singleton Pattern:
# All services export both the class and a singleton instance (e.g., `AuditService` and `audit_service`).
# Always import and use the singleton instance for consistency.
# Exception: TwoFactorService uses only static methods and doesn't need instantiation.

# Core services
from src.services.audit import (
    AuditService,
    audit_service,
    get_client_ip,
    get_user_agent,
)
from src.services.brute_force_detector import BruteForceDetector, brute_force_detector
from src.services.cache import AsyncCacheService, cache_service
from src.services.cron_scheduler import CronSchedulerService, cron_scheduler_service
from src.services.email import AsyncEmailService, email_service
from src.services.email_change import EmailChangeService, email_change_service
from src.services.feature_flag_cache import FeatureFlagCache, feature_flag_cache
from src.services.job_stats import JobStatsService, job_stats_service
from src.services.onboarding import OnboardingService, onboarding_service
from src.services.onboarding_notifications import (
    OnboardingNotificationService,
    onboarding_notification_service,
)
from src.services.phone_verification import (
    PhoneVerificationService,
    phone_verification_service,
)
from src.services.queue_health import QueueHealthService, queue_health_service
from src.services.tasks import TaskQueue, task_queue
from src.services.thumbnail import ThumbnailService, thumbnail_service
from src.services.two_factor import TwoFactorService
from src.services.user_activity import UserActivityService, user_activity_service
from src.services.user_data_deletion import (
    UserDataDeletionService,
    user_data_deletion_service,
)
from src.services.user_data_export import (
    UserDataExportService,
    user_data_export_service,
)


__all__ = [
    # Audit
    "AuditService",
    "audit_service",
    "get_client_ip",
    "get_user_agent",
    # Auth & Security
    "BruteForceDetector",
    "brute_force_detector",
    "TwoFactorService",
    # Cache
    "AsyncCacheService",
    "cache_service",
    # Cron
    "CronSchedulerService",
    "cron_scheduler_service",
    # Email
    "AsyncEmailService",
    "email_service",
    "EmailChangeService",
    "email_change_service",
    # Feature flags
    "FeatureFlagCache",
    "feature_flag_cache",
    # Jobs
    "JobStatsService",
    "job_stats_service",
    "TaskQueue",
    "task_queue",
    "QueueHealthService",
    "queue_health_service",
    # Onboarding
    "OnboardingService",
    "onboarding_service",
    "OnboardingNotificationService",
    "onboarding_notification_service",
    # Phone
    "PhoneVerificationService",
    "phone_verification_service",
    # Thumbnails
    "ThumbnailService",
    "thumbnail_service",
    # User activity & data
    "UserActivityService",
    "user_activity_service",
    "UserDataDeletionService",
    "user_data_deletion_service",
    "UserDataExportService",
    "user_data_export_service",
]
