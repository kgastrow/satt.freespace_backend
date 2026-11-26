"""User CRUD scenario: list users, get user, update profile."""

from locust import task, tag


class UserScenario:
    """User management tasks. Weight: 15."""

    @task(5)
    @tag("users")
    def list_users(self):
        """List users with default pagination."""
        headers = {
            k: v for k, v in self.auth_headers.items() if not k.startswith("_")
        }
        self.client.get(
            "/api/v1/users?limit=10&offset=0",
            headers=headers,
            name="/api/v1/users [list]",
        )

    @task(3)
    @tag("users")
    def list_users_with_search(self):
        """List users with search query."""
        headers = {
            k: v for k, v in self.auth_headers.items() if not k.startswith("_")
        }
        self.client.get(
            "/api/v1/users?limit=10&offset=0&q=test",
            headers=headers,
            name="/api/v1/users [search]",
        )

    @task(2)
    @tag("users")
    def list_users_paginated(self):
        """List users with offset pagination."""
        headers = {
            k: v for k, v in self.auth_headers.items() if not k.startswith("_")
        }
        self.client.get(
            "/api/v1/users?limit=50&offset=0",
            headers=headers,
            name="/api/v1/users [page50]",
        )
