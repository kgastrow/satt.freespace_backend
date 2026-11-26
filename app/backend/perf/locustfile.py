"""
Main Locust entry point for load testing the AYZER Webapp API.

Usage:
    # Headless mode:
    cd app/backend/perf && locust -f locustfile.py --headless -u 50 -r 5 -t 5m --csv=results/run

    # Web UI mode:
    cd app/backend/perf && locust -f locustfile.py
"""

from locust import HttpUser, between

from perf.scenarios.auth import AuthScenario
from perf.scenarios.users import UserScenario
from perf.scenarios.organizations import OrganizationScenario
from perf.scenarios.files import FileScenario
from perf.scenarios.notifications import NotificationScenario
from perf.scenarios.audit_logs import AuditLogScenario
from perf.utils import login


class WebAppUser(
    AuthScenario,
    UserScenario,
    OrganizationScenario,
    FileScenario,
    NotificationScenario,
    AuditLogScenario,
    HttpUser,
):
    """
    Simulated user that exercises all major API endpoints.

    Scenario weights (via @task decorators in each mixin):
        Auth:           30% (login, refresh, check-email)
        Users:          15% (list, search, paginate)
        Organizations:  10% (list, get, details, member count)
        Files:          15% (list, usage, settings, upload)
        Notifications:  20% (in-app list, unread count, preferences, mark read)
        Audit Logs:     10% (list, filter, sort, search)
    """

    wait_time = between(1, 3)
    host = "http://localhost:8000"

    def on_start(self):
        """Authenticate once when the simulated user starts."""
        self.auth_headers = login(self.client)
