"""
Prometheus metrics for the ETL Platform.

Exposes application-level metrics at GET /metrics.
All metrics use the etl_ prefix for easy dashboard filtering.

Metric types:
  Counter   — monotonically increasing (requests, pipeline runs, records)
  Histogram — distributions with configurable buckets (latency, duration)
  Gauge     — current value (active pipelines, queue depth, quality scores)

Usage:
    from app.observability.metrics import (
        http_requests_total,
        pipeline_runs_total,
        record_pipeline_run,
        record_http_request,
    )
"""
from __future__ import annotations

from prometheus_client import (
    Counter,
    Gauge,
    Histogram,
    Info,
    REGISTRY,
    generate_latest,
    CONTENT_TYPE_LATEST,
)

# ---------------------------------------------------------------------------
# HTTP metrics
# ---------------------------------------------------------------------------

http_requests_total = Counter(
    "etl_http_requests_total",
    "Total HTTP requests handled",
    ["method", "endpoint", "status"],
)

http_request_duration_seconds = Histogram(
    "etl_http_request_duration_seconds",
    "HTTP request duration in seconds",
    ["method", "endpoint"],
    buckets=[0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0],
)

http_request_size_bytes = Histogram(
    "etl_http_request_size_bytes",
    "HTTP request body size in bytes",
    ["method", "endpoint"],
    buckets=[100, 1_000, 10_000, 100_000, 1_000_000, 10_000_000],
)

http_active_requests = Gauge(
    "etl_http_active_requests",
    "Number of HTTP requests currently being processed",
)

# ---------------------------------------------------------------------------
# Pipeline metrics
# ---------------------------------------------------------------------------

pipeline_runs_total = Counter(
    "etl_pipeline_runs_total",
    "Total pipeline runs by status and dataset",
    ["status", "dataset_type"],
)

pipeline_duration_seconds = Histogram(
    "etl_pipeline_duration_seconds",
    "Pipeline execution duration in seconds",
    ["dataset_type", "status"],
    buckets=[1, 5, 10, 30, 60, 120, 300, 600, 1800, 3600],
)

pipeline_active_runs = Gauge(
    "etl_pipeline_active_runs",
    "Currently running pipeline executions",
)

pipeline_stage_duration_seconds = Histogram(
    "etl_pipeline_stage_duration_seconds",
    "Duration of each pipeline stage in seconds",
    ["stage", "dataset_type"],
    buckets=[0.1, 0.5, 1, 5, 10, 30, 60, 120, 300],
)

pipeline_records_processed = Counter(
    "etl_pipeline_records_processed_total",
    "Total records processed through the pipeline",
    ["stage", "dataset_type", "status"],
)

pipeline_retry_total = Counter(
    "etl_pipeline_retry_total",
    "Total pipeline retry attempts",
    ["dataset_type"],
)

# ---------------------------------------------------------------------------
# Data quality metrics
# ---------------------------------------------------------------------------

quality_score_histogram = Histogram(
    "etl_quality_score",
    "Data quality score distribution",
    ["dataset_type"],
    buckets=[10, 20, 30, 40, 50, 60, 70, 75, 80, 85, 90, 95, 99, 100],
)

quality_violations_total = Counter(
    "etl_quality_violations_total",
    "Total data quality rule violations",
    ["dataset_type", "severity", "rule_code"],
)

# ---------------------------------------------------------------------------
# Load / warehouse metrics
# ---------------------------------------------------------------------------

warehouse_rows_loaded_total = Counter(
    "etl_warehouse_rows_loaded_total",
    "Total rows successfully loaded to warehouse",
    ["dataset_type", "strategy"],
)

warehouse_rows_failed_total = Counter(
    "etl_warehouse_rows_failed_total",
    "Total rows that failed to load",
    ["dataset_type", "strategy"],
)

warehouse_load_duration_seconds = Histogram(
    "etl_warehouse_load_duration_seconds",
    "Warehouse load operation duration in seconds",
    ["dataset_type", "strategy"],
    buckets=[0.1, 0.5, 1, 5, 10, 30, 60, 120],
)

# ---------------------------------------------------------------------------
# Authentication metrics
# ---------------------------------------------------------------------------

auth_login_total = Counter(
    "etl_auth_login_total",
    "Total login attempts",
    ["status"],  # success / failure
)

auth_api_key_requests_total = Counter(
    "etl_auth_api_key_requests_total",
    "Total requests authenticated via API key",
    ["scope"],
)

# ---------------------------------------------------------------------------
# System / application info
# ---------------------------------------------------------------------------

app_info = Info(
    "etl_app",
    "ETL Platform application information",
)


def initialize_app_info(version: str, environment: str) -> None:
    """Set static app metadata labels once at startup."""
    app_info.info({
        "version": version,
        "environment": environment,
        "platform": "fastapi",
    })


# ---------------------------------------------------------------------------
# Helper recording functions
# ---------------------------------------------------------------------------

def record_http_request(
    method: str,
    endpoint: str,
    status_code: int,
    duration_seconds: float,
) -> None:
    """Record a completed HTTP request into all relevant metrics."""
    status = str(status_code)
    http_requests_total.labels(method=method, endpoint=endpoint, status=status).inc()
    http_request_duration_seconds.labels(method=method, endpoint=endpoint).observe(duration_seconds)


def record_pipeline_run(
    dataset_type: str,
    status: str,
    duration_seconds: float,
) -> None:
    """Record a completed pipeline run."""
    pipeline_runs_total.labels(status=status, dataset_type=dataset_type).inc()
    pipeline_duration_seconds.labels(
        dataset_type=dataset_type, status=status
    ).observe(duration_seconds)


def record_stage_duration(
    stage: str,
    dataset_type: str,
    duration_seconds: float,
) -> None:
    """Record a pipeline stage execution duration."""
    pipeline_stage_duration_seconds.labels(
        stage=stage, dataset_type=dataset_type
    ).observe(duration_seconds)


def record_records_processed(
    stage: str,
    dataset_type: str,
    count: int,
    status: str = "success",
) -> None:
    """Record record counts flowing through a stage."""
    pipeline_records_processed.labels(
        stage=stage, dataset_type=dataset_type, status=status
    ).inc(count)


def record_quality_score(dataset_type: str, score: float) -> None:
    """Record a data quality score observation."""
    quality_score_histogram.labels(dataset_type=dataset_type).observe(score)


def record_warehouse_load(
    dataset_type: str,
    strategy: str,
    rows_loaded: int,
    rows_failed: int,
    duration_seconds: float,
) -> None:
    """Record warehouse load metrics."""
    warehouse_rows_loaded_total.labels(dataset_type=dataset_type, strategy=strategy).inc(rows_loaded)
    if rows_failed > 0:
        warehouse_rows_failed_total.labels(dataset_type=dataset_type, strategy=strategy).inc(rows_failed)
    warehouse_load_duration_seconds.labels(
        dataset_type=dataset_type, strategy=strategy
    ).observe(duration_seconds)


# ---------------------------------------------------------------------------
# Metrics endpoint helper
# ---------------------------------------------------------------------------

def get_metrics_response() -> tuple[bytes, str]:
    """Return (metrics_bytes, content_type) for the /metrics endpoint."""
    return generate_latest(REGISTRY), CONTENT_TYPE_LATEST
