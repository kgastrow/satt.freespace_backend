"""File management scenario: list files, upload, download."""

import io
from locust import task, tag


class FileScenario:
    """File management tasks. Weight: 15."""

    @task(5)
    @tag("files")
    def list_files(self):
        """List files for the current user."""
        headers = {
            k: v for k, v in self.auth_headers.items() if not k.startswith("_")
        }
        self.client.get(
            "/api/v1/files?limit=50&offset=0",
            headers=headers,
            name="/api/v1/files [list]",
        )

    @task(2)
    @tag("files")
    def get_file_usage(self):
        """Get current user file usage statistics."""
        headers = {
            k: v for k, v in self.auth_headers.items() if not k.startswith("_")
        }
        self.client.get(
            "/api/v1/files/usage",
            headers=headers,
            name="/api/v1/files/usage",
        )

    @task(2)
    @tag("files")
    def get_file_settings(self):
        """Get organization file settings."""
        headers = {
            k: v for k, v in self.auth_headers.items() if not k.startswith("_")
        }
        self.client.get(
            "/api/v1/files/settings",
            headers=headers,
            name="/api/v1/files/settings",
        )

    @task(1)
    @tag("files")
    def upload_small_file(self):
        """Upload a small text file."""
        headers = {
            k: v for k, v in self.auth_headers.items() if not k.startswith("_")
        }
        file_content = b"Performance test file content - " * 10
        files = {
            "file": ("perf_test.txt", io.BytesIO(file_content), "text/plain"),
        }
        self.client.post(
            "/api/v1/files/upload",
            headers=headers,
            files=files,
            name="/api/v1/files/upload",
        )
