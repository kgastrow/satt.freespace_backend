"""Audit log scenario: list audit logs with pagination (read-heavy)."""

from locust import task, tag


class AuditLogScenario:
    """Audit log listing tasks. Weight: 10."""

    @task(5)
    @tag("audit-logs")
    def list_audit_logs(self):
        """List audit logs with default pagination."""
        headers = {
            k: v for k, v in self.auth_headers.items() if not k.startswith("_")
        }
        self.client.get(
            "/api/v1/audit-logs?limit=50&offset=0",
            headers=headers,
            name="/api/v1/audit-logs [list]",
        )

    @task(3)
    @tag("audit-logs")
    def list_audit_logs_filtered(self):
        """List audit logs filtered by resource type."""
        headers = {
            k: v for k, v in self.auth_headers.items() if not k.startswith("_")
        }
        self.client.get(
            "/api/v1/audit-logs?limit=50&offset=0&filter[resource_type]=User",
            headers=headers,
            name="/api/v1/audit-logs [filter:User]",
        )

    @task(2)
    @tag("audit-logs")
    def list_audit_logs_sorted(self):
        """List audit logs sorted by creation time descending."""
        headers = {
            k: v for k, v in self.auth_headers.items() if not k.startswith("_")
        }
        self.client.get(
            "/api/v1/audit-logs?limit=100&offset=0&sort=created_time:desc",
            headers=headers,
            name="/api/v1/audit-logs [sorted]",
        )

    @task(1)
    @tag("audit-logs")
    def list_audit_logs_search(self):
        """Search audit logs."""
        headers = {
            k: v for k, v in self.auth_headers.items() if not k.startswith("_")
        }
        self.client.get(
            "/api/v1/audit-logs?limit=50&offset=0&q=user",
            headers=headers,
            name="/api/v1/audit-logs [search]",
        )
