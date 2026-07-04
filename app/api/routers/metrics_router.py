"""
Prometheus metrics endpoint.

GET /metrics  — standard Prometheus scrape endpoint
GET /api/v1/health/metrics-info — human-readable metrics summary
"""
from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import Response

router = APIRouter(tags=["Observability"])


@router.get(
    "/metrics",
    include_in_schema=False,  # Hide from OpenAPI — for Prometheus scraper only
    summary="Prometheus metrics",
)
def prometheus_metrics() -> Response:
    """
    Prometheus metrics scrape endpoint.

    Returns all registered metrics in Prometheus text exposition format.
    Configure Prometheus to scrape: GET /metrics
    """
    from app.observability.metrics import get_metrics_response
    data, content_type = get_metrics_response()
    return Response(content=data, media_type=content_type)
