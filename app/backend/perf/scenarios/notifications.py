"""Notification scenario: list in-app notifications, mark read, preferences."""

from locust import task, tag


class NotificationScenario:
    """Notification tasks. Weight: 20."""

    @task(5)
    @tag("notifications")
    def list_in_app_notifications(self):
        """List in-app notifications for the current user."""
        headers = {
            k: v for k, v in self.auth_headers.items() if not k.startswith("_")
        }
        self.client.get(
            "/api/v1/notifications/in-app?limit=20&offset=0",
            headers=headers,
            name="/api/v1/notifications/in-app [list]",
        )

    @task(4)
    @tag("notifications")
    def get_unread_count(self):
        """Get unread notification count (polled frequently)."""
        headers = {
            k: v for k, v in self.auth_headers.items() if not k.startswith("_")
        }
        self.client.get(
            "/api/v1/notifications/in-app/unread-count",
            headers=headers,
            name="/api/v1/notifications/in-app/unread-count",
        )

    @task(2)
    @tag("notifications")
    def get_notification_preferences(self):
        """Get user notification preferences."""
        headers = {
            k: v for k, v in self.auth_headers.items() if not k.startswith("_")
        }
        self.client.get(
            "/api/v1/notifications/preferences",
            headers=headers,
            name="/api/v1/notifications/preferences [get]",
        )

    @task(1)
    @tag("notifications")
    def mark_all_read(self):
        """Mark all in-app notifications as read."""
        headers = {
            k: v for k, v in self.auth_headers.items() if not k.startswith("_")
        }
        self.client.post(
            "/api/v1/notifications/in-app/mark-all-read",
            headers=headers,
            name="/api/v1/notifications/in-app/mark-all-read",
        )

    @task(1)
    @tag("notifications")
    def get_category_preferences(self):
        """Get notification category preferences."""
        headers = {
            k: v for k, v in self.auth_headers.items() if not k.startswith("_")
        }
        self.client.get(
            "/api/v1/notifications/preferences/categories",
            headers=headers,
            name="/api/v1/notifications/preferences/categories",
        )
