from __future__ import annotations

from locust import HttpUser, between, task


class FoundationUser(HttpUser):
    """Exercise business-neutral process and readiness diagnostics."""

    wait_time = between(0.1, 0.5)

    @task(9)
    def liveness(self) -> None:
        with self.client.get(
            "/health/live",
            name="/health/live",
            catch_response=True,
        ) as response:
            if response.status_code != 200:
                response.failure(f"unexpected status {response.status_code}")
            elif response.json().get("status") != "alive":
                response.failure("process did not report alive")

    @task(1)
    def readiness(self) -> None:
        with self.client.get(
            "/health/ready",
            name="/health/ready",
            catch_response=True,
        ) as response:
            if response.status_code != 200:
                response.failure(f"unexpected status {response.status_code}")
            elif response.json().get("status") != "ready":
                response.failure("dependencies did not report ready")
