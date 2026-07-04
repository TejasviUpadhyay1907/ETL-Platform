"""
ETL Platform — Locust Load Test
================================

Usage:
    pip install locust
    locust -f benchmarks/locustfile.py --host http://localhost:8000
    locust -f benchmarks/locustfile.py --host http://localhost:8000 --headless -u 50 -r 5 -t 60s

User classes:
  - ReadOnlyUser: simulates analysts browsing dashboards (GET-heavy)
  - OperationsUser: simulates ops engineers triggering and monitoring pipelines
  - AuthStressUser: simulates concurrent authentication requests
"""
from __future__ import annotations

import os
import json
from locust import HttpUser, task, between, events


BENCH_USERNAME = os.getenv("BENCH_USERNAME", "admin")
BENCH_PASSWORD = os.getenv("BENCH_PASSWORD", "admin_password")


class ETLBaseUser(HttpUser):
    """Base class: authenticates on start, stores token."""
    abstract = True
    _token: str | None = None

    def on_start(self) -> None:
        with self.client.post(
            "/api/v1/auth/login",
            json={"username": BENCH_USERNAME, "password": BENCH_PASSWORD},
            name="/api/v1/auth/login",
            catch_response=True,
        ) as resp:
            if resp.status_code == 200:
                self._token = resp.json()["data"]["access_token"]
            else:
                resp.failure(f"Login failed: {resp.status_code}")

    @property
    def auth_headers(self) -> dict:
        return {"Authorization": f"Bearer {self._token}"} if self._token else {}


class ReadOnlyUser(ETLBaseUser):
    """Simulates read-heavy analytics user. 40 concurrent users."""
    wait_time = between(1, 3)
    weight = 4

    @task(5)
    def get_pipelines(self) -> None:
        self.client.get(
            "/api/v1/pipelines?page_size=20",
            headers=self.auth_headers,
            name="/api/v1/pipelines",
        )

    @task(3)
    def get_pipeline_history(self) -> None:
        self.client.get(
            "/api/v1/pipelines/history?page_size=20",
            headers=self.auth_headers,
            name="/api/v1/pipelines/history",
        )

    @task(2)
    def get_load_history(self) -> None:
        self.client.get(
            "/api/v1/load/history",
            headers=self.auth_headers,
            name="/api/v1/load/history",
        )

    @task(2)
    def get_ingestion_events(self) -> None:
        self.client.get(
            "/api/v1/ingest/events?page_size=20",
            headers=self.auth_headers,
            name="/api/v1/ingest/events",
        )

    @task(1)
    def health_ping(self) -> None:
        self.client.get("/api/v1/health/ping", name="/api/v1/health/ping")

    @task(1)
    def get_roles(self) -> None:
        self.client.get(
            "/api/v1/roles",
            headers=self.auth_headers,
            name="/api/v1/roles",
        )


class OperationsUser(ETLBaseUser):
    """Simulates ops engineer — checks pipelines and inspects quality. 10 concurrent users."""
    wait_time = between(2, 6)
    weight = 1

    @task(4)
    def list_pipelines(self) -> None:
        self.client.get(
            "/api/v1/pipelines?status=running&page_size=10",
            headers=self.auth_headers,
            name="/api/v1/pipelines?status=running",
        )

    @task(2)
    def list_users(self) -> None:
        self.client.get(
            "/api/v1/users",
            headers=self.auth_headers,
            name="/api/v1/users",
        )

    @task(2)
    def list_api_keys(self) -> None:
        self.client.get(
            "/api/v1/api-keys",
            headers=self.auth_headers,
            name="/api/v1/api-keys",
        )

    @task(1)
    def get_me(self) -> None:
        self.client.get(
            "/api/v1/auth/me",
            headers=self.auth_headers,
            name="/api/v1/auth/me",
        )


class AuthStressUser(HttpUser):
    """Simulates auth endpoint stress — does NOT use ETLBaseUser token."""
    wait_time = between(5, 15)
    weight = 1

    @task
    def login_attempt(self) -> None:
        with self.client.post(
            "/api/v1/auth/login",
            json={"username": BENCH_USERNAME, "password": BENCH_PASSWORD},
            name="/api/v1/auth/login [stress]",
            catch_response=True,
        ) as resp:
            if resp.status_code not in (200, 401, 429):
                resp.failure(f"Unexpected status: {resp.status_code}")
            else:
                resp.success()


@events.test_start.add_listener
def on_test_start(environment, **kwargs) -> None:
    print(f"\n[Locust] Load test starting against: {environment.host}")
    print("[Locust] User classes: ReadOnlyUser, OperationsUser, AuthStressUser")


@events.test_stop.add_listener
def on_test_stop(environment, **kwargs) -> None:
    stats = environment.stats.total
    print(f"\n[Locust] Test complete:")
    print(f"  Total requests: {stats.num_requests}")
    print(f"  Total failures: {stats.num_failures}")
    print(f"  Avg response:   {stats.avg_response_time:.1f}ms")
    print(f"  P95 response:   {stats.get_response_time_percentile(0.95):.1f}ms")
    print(f"  Peak RPS:       {stats.total_rps:.1f}")
