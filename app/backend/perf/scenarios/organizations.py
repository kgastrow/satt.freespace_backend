"""Organization CRUD scenario: list orgs, get org, get details."""

from locust import task, tag

from perf.config import TEST_ORG_ID


class OrganizationScenario:
    """Organization management tasks. Weight: 10."""

    @task(5)
    @tag("organizations")
    def list_organizations(self):
        """List organizations."""
        headers = {
            k: v for k, v in self.auth_headers.items() if not k.startswith("_")
        }
        self.client.get(
            "/api/v1/organizations?limit=50&offset=0",
            headers=headers,
            name="/api/v1/organizations [list]",
        )

    @task(3)
    @tag("organizations")
    def get_organization(self):
        """Get a single organization by ID."""
        if not TEST_ORG_ID:
            return
        headers = {
            k: v for k, v in self.auth_headers.items() if not k.startswith("_")
        }
        self.client.get(
            f"/api/v1/organizations/{TEST_ORG_ID}",
            headers=headers,
            name="/api/v1/organizations/[id]",
        )

    @task(2)
    @tag("organizations")
    def get_organization_details(self):
        """Get organization details."""
        if not TEST_ORG_ID:
            return
        headers = {
            k: v for k, v in self.auth_headers.items() if not k.startswith("_")
        }
        self.client.get(
            f"/api/v1/organizations/{TEST_ORG_ID}/details",
            headers=headers,
            name="/api/v1/organizations/[id]/details",
        )

    @task(1)
    @tag("organizations")
    def get_member_count(self):
        """Get organization member count."""
        if not TEST_ORG_ID:
            return
        headers = {
            k: v for k, v in self.auth_headers.items() if not k.startswith("_")
        }
        self.client.get(
            f"/api/v1/organizations/{TEST_ORG_ID}/members/count",
            headers=headers,
            name="/api/v1/organizations/[id]/members/count",
        )
