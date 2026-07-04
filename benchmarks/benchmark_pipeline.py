"""
ETL Platform — Pipeline Throughput Benchmark
============================================

Measures pipeline throughput, records/sec, memory, and API latency.

Usage:
    python benchmarks/benchmark_pipeline.py
    python benchmarks/benchmark_pipeline.py --api-url http://localhost:8000 --rows 10000
    python benchmarks/benchmark_pipeline.py --output benchmark_report.json

Prerequisites:
    pip install httpx psutil
    ETL Platform API must be running and seeded with credentials.
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import os
import statistics
import sys
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

try:
    import httpx
    import psutil
except ImportError:
    print("Install missing deps: pip install httpx psutil")
    sys.exit(1)


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DEFAULT_API_URL = "http://localhost:8000"
DEFAULT_USERNAME = os.getenv("BENCH_USERNAME", "admin")
DEFAULT_PASSWORD = os.getenv("BENCH_PASSWORD", "admin_password")


def _login(api_url: str, username: str, password: str) -> str:
    """Authenticate and return a bearer token."""
    resp = httpx.post(
        f"{api_url}/api/v1/auth/login",
        json={"username": username, "password": password},
        timeout=15,
    )
    if resp.status_code != 200:
        print(f"Login failed ({resp.status_code}): {resp.text}")
        sys.exit(1)
    return resp.json()["data"]["access_token"]


def _headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# Benchmark helpers
# ---------------------------------------------------------------------------

def _make_csv(rows: int) -> bytes:
    """Generate synthetic orders CSV for benchmarking."""
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["order_number", "order_date", "customer_email",
                     "product_sku", "quantity", "unit_price", "status"])
    for i in range(rows):
        writer.writerow([
            f"ORD-BENCH-{i:08d}",
            "2024-06-15",
            f"bench_customer_{i % 1000}@example.com",
            f"BENCH-SKU-{i % 500:04d}",
            str((i % 10) + 1),
            f"{19.99 + (i % 200):.2f}",
            "delivered",
        ])
    return buf.getvalue().encode("utf-8")


class BenchmarkResult:
    """Stores results for one benchmark scenario."""

    def __init__(self, name: str):
        self.name = name
        self.latencies: list[float] = []
        self.errors: int = 0
        self.start_time: float = 0.0
        self.end_time: float = 0.0
        self.rows_processed: int = 0
        self.memory_mb_before: float = 0.0
        self.memory_mb_after: float = 0.0
        self.metadata: dict[str, Any] = {}

    @property
    def total_seconds(self) -> float:
        return self.end_time - self.start_time

    @property
    def throughput_rps(self) -> float:
        return len(self.latencies) / max(0.001, self.total_seconds)

    @property
    def rows_per_second(self) -> float:
        return self.rows_processed / max(0.001, self.total_seconds)

    @property
    def p50_ms(self) -> float:
        return statistics.median(self.latencies) * 1000 if self.latencies else 0

    @property
    def p95_ms(self) -> float:
        if not self.latencies:
            return 0
        s = sorted(self.latencies)
        return s[int(len(s) * 0.95)] * 1000

    @property
    def p99_ms(self) -> float:
        if not self.latencies:
            return 0
        s = sorted(self.latencies)
        return s[int(len(s) * 0.99)] * 1000

    @property
    def mean_ms(self) -> float:
        return statistics.mean(self.latencies) * 1000 if self.latencies else 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "total_requests": len(self.latencies),
            "errors": self.errors,
            "total_seconds": round(self.total_seconds, 3),
            "throughput_rps": round(self.throughput_rps, 2),
            "rows_processed": self.rows_processed,
            "rows_per_second": round(self.rows_per_second, 2),
            "latency_ms": {
                "mean": round(self.mean_ms, 2),
                "p50": round(self.p50_ms, 2),
                "p95": round(self.p95_ms, 2),
                "p99": round(self.p99_ms, 2),
                "min": round(min(self.latencies) * 1000, 2) if self.latencies else 0,
                "max": round(max(self.latencies) * 1000, 2) if self.latencies else 0,
            },
            "memory_delta_mb": round(self.memory_mb_after - self.memory_mb_before, 2),
            "metadata": self.metadata,
        }


def _get_memory_mb() -> float:
    proc = psutil.Process()
    return proc.memory_info().rss / 1024 / 1024


# ---------------------------------------------------------------------------
# Benchmark scenarios
# ---------------------------------------------------------------------------

def bench_health(api_url: str, n: int = 100) -> BenchmarkResult:
    """Benchmark the health/ping endpoint (establishes baseline latency)."""
    r = BenchmarkResult("health_ping")
    r.start_time = time.perf_counter()
    for _ in range(n):
        t0 = time.perf_counter()
        try:
            httpx.get(f"{api_url}/api/v1/health/ping", timeout=5)
            r.latencies.append(time.perf_counter() - t0)
        except Exception:
            r.errors += 1
    r.end_time = time.perf_counter()
    r.metadata = {"n": n}
    return r


def bench_pipeline_list(api_url: str, token: str, n: int = 50) -> BenchmarkResult:
    """Benchmark pipeline list endpoint with authentication."""
    r = BenchmarkResult("pipeline_list")
    r.start_time = time.perf_counter()
    for _ in range(n):
        t0 = time.perf_counter()
        try:
            httpx.get(f"{api_url}/api/v1/pipelines?page_size=20",
                      headers=_headers(token), timeout=10)
            r.latencies.append(time.perf_counter() - t0)
        except Exception:
            r.errors += 1
    r.end_time = time.perf_counter()
    r.metadata = {"n": n}
    return r


def bench_csv_parse(rows: int) -> BenchmarkResult:
    """Benchmark in-process CSV parsing (no HTTP — measures data throughput)."""
    import csv as _csv
    r = BenchmarkResult("csv_parse_in_process")
    r.memory_mb_before = _get_memory_mb()
    r.start_time = time.perf_counter()

    data = _make_csv(rows).decode("utf-8")
    reader = _csv.DictReader(io.StringIO(data))
    count = 0
    t0 = time.perf_counter()
    for _ in reader:
        count += 1
    r.latencies.append(time.perf_counter() - t0)
    r.rows_processed = count
    r.end_time = time.perf_counter()
    r.memory_mb_after = _get_memory_mb()
    r.metadata = {"rows": rows}
    return r


def bench_auth_login(api_url: str, username: str, password: str, n: int = 20) -> BenchmarkResult:
    """Benchmark the login endpoint (includes bcrypt verification)."""
    r = BenchmarkResult("auth_login")
    r.start_time = time.perf_counter()
    for _ in range(n):
        t0 = time.perf_counter()
        try:
            httpx.post(f"{api_url}/api/v1/auth/login",
                       json={"username": username, "password": password}, timeout=15)
            r.latencies.append(time.perf_counter() - t0)
        except Exception:
            r.errors += 1
    r.end_time = time.perf_counter()
    r.metadata = {"n": n}
    return r


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------

def print_result(r: BenchmarkResult) -> None:
    d = r.to_dict()
    print(f"\n{'='*60}")
    print(f"  Benchmark: {d['name']}")
    print(f"{'='*60}")
    print(f"  Requests:       {d['total_requests']} (errors: {d['errors']})")
    print(f"  Duration:       {d['total_seconds']:.2f}s")
    print(f"  Throughput:     {d['throughput_rps']:.1f} req/s")
    if d["rows_processed"]:
        print(f"  Rows/sec:       {d['rows_per_second']:,.0f}")
    print(f"  Latency (ms):")
    for k, v in d["latency_ms"].items():
        print(f"    {k:8}: {v:.2f} ms")
    if d["memory_delta_mb"]:
        print(f"  Memory delta:   {d['memory_delta_mb']:+.1f} MB")


def main() -> None:
    parser = argparse.ArgumentParser(description="ETL Platform Benchmark")
    parser.add_argument("--api-url",  default=DEFAULT_API_URL)
    parser.add_argument("--username", default=DEFAULT_USERNAME)
    parser.add_argument("--password", default=DEFAULT_PASSWORD)
    parser.add_argument("--rows",     type=int, default=10_000)
    parser.add_argument("--output",   default=None)
    args = parser.parse_args()

    print(f"\nETL Platform Benchmark — {datetime.now().isoformat()}")
    print(f"API: {args.api_url}  |  Rows: {args.rows:,}\n")

    results: list[BenchmarkResult] = []

    # 1. Health baseline
    print("Running: health ping baseline (100 requests)...")
    results.append(bench_health(args.api_url, n=100))

    # 2. CSV parsing
    print(f"Running: CSV parse benchmark ({args.rows:,} rows)...")
    results.append(bench_csv_parse(args.rows))

    # 3. Authenticated endpoints (skip if server unreachable)
    token = None
    try:
        print("Running: auth login benchmark (20 requests)...")
        results.append(bench_auth_login(args.api_url, args.username, args.password, n=20))
        token = _login(args.api_url, args.username, args.password)
        print("Running: pipeline list benchmark (50 requests)...")
        results.append(bench_pipeline_list(args.api_url, token, n=50))
    except Exception as exc:
        print(f"Skipping authenticated benchmarks (server not available): {exc}")

    # Print results
    for r in results:
        print_result(r)

    # Save report
    if args.output:
        report = {
            "timestamp": datetime.now().isoformat(),
            "api_url": args.api_url,
            "results": [r.to_dict() for r in results],
        }
        Path(args.output).write_text(json.dumps(report, indent=2))
        print(f"\nReport saved: {args.output}")

    print(f"\n{'='*60}")
    print("Benchmark complete.")


if __name__ == "__main__":
    main()
