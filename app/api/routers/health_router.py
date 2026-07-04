"""
Health monitoring endpoints.

Provides standard health check endpoints used by:
- Container orchestration (Kubernetes liveness/readiness probes)
- Load balancers (health-based routing)
- Monitoring systems (Prometheus, Datadog, etc.)
- Operations teams (manual health verification)

Endpoints:
- GET /api/v1/health        — full health check (app + DB + config)
- GET /api/v1/health/ping   — minimal liveness check
- GET /api/v1/health/ready  — readiness check (all dependencies available)
- GET /api/v1/health/live   — liveness check (app is running)
- GET /api/v1/health/version — version information
"""

import time
from datetime import datetime
from typing import Any

from fastapi import APIRouter, status
from fastapi.responses import JSONResponse

from app.api.schemas.base_schemas import APIResponse, HealthStatus, PingResponse, VersionResponse
from app.core.config import get_config
from app.database.engine import check_database_health
from app.logging.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/health", tags=["Health"])

# Track application start time for uptime calculation
_app_start_time = time.time()


@router.get(
    "",
    response_model=APIResponse[HealthStatus],
    summary="Full health check",
    description=(
        "Returns the full system health status including application state, "
        "database connectivity, and configuration validity. "
        "Returns HTTP 200 if healthy, HTTP 503 if degraded or unhealthy."
    ),
)
async def health_check() -> JSONResponse:
    """
    Perform a comprehensive health check.

    Checks:
    1. Application is running
    2. Configuration is loaded
    3. Database is reachable
    4. Required directories exist
    """
    config = get_config()
    uptime = time.time() - _app_start_time
    checks: dict[str, Any] = {}

    # Check database connectivity
    db_healthy = check_database_health()
    checks["database"] = "healthy" if db_healthy else "unhealthy"

    # Check required directories
    directories_ok = all(
        [
            config.upload_directory.exists(),
            config.report_directory.exists(),
            config.archive_directory.exists(),
        ]
    )
    checks["file_system"] = "healthy" if directories_ok else "degraded"

    # Determine overall status
    if not db_healthy:
        overall_status = "unhealthy"
        http_status = status.HTTP_503_SERVICE_UNAVAILABLE
    elif not directories_ok:
        overall_status = "degraded"
        http_status = status.HTTP_200_OK  # Degraded but operational
    else:
        overall_status = "healthy"
        http_status = status.HTTP_200_OK

    health_data = HealthStatus(
        status=overall_status,
        app_name=config.app_name,
        version=config.app_version,
        environment=config.app_env,
        database=checks["database"],
        uptime_seconds=round(uptime, 2),
        timestamp=datetime.utcnow(),
    )

    # Use model_dump with mode="json" so datetime objects become ISO strings
    response_body = APIResponse[HealthStatus].ok(data=health_data).model_dump(mode="json")
    return JSONResponse(status_code=http_status, content=response_body)


@router.get(
    "/ping",
    response_model=PingResponse,
    summary="Minimal liveness check",
    description="Returns 'pong' immediately. No dependency checks. Used by load balancers.",
)
async def ping() -> PingResponse:
    """Minimal liveness probe — just confirms the app is running."""
    return PingResponse()


@router.get(
    "/ready",
    summary="Readiness check",
    description=(
        "Checks whether the application is ready to serve traffic. "
        "Returns HTTP 200 if ready, HTTP 503 if not. "
        "Use this for Kubernetes readiness probes."
    ),
)
async def readiness() -> JSONResponse:
    """
    Readiness probe for container orchestration.

    Returns 200 only when all dependencies (database) are available.
    """
    db_healthy = check_database_health()

    if db_healthy:
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={"ready": True, "timestamp": datetime.utcnow().isoformat()},
        )
    else:
        logger.warning("Readiness check failed: database unreachable")
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "ready": False,
                "reason": "Database unavailable",
                "timestamp": datetime.utcnow().isoformat(),
            },
        )


@router.get(
    "/live",
    summary="Liveness check",
    description=(
        "Checks whether the application process is alive. "
        "Returns HTTP 200 if alive. Used by Kubernetes liveness probes."
    ),
)
async def liveness() -> JSONResponse:
    """
    Liveness probe for container orchestration.

    Only checks if the application is running — no dependency checks.
    If this fails, the container should be restarted.
    """
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={"alive": True, "timestamp": datetime.utcnow().isoformat()},
    )


@router.get(
    "/version",
    response_model=APIResponse[VersionResponse],
    summary="Version information",
    description="Returns application version, name, and environment.",
)
async def version() -> APIResponse[VersionResponse]:
    """Return application version and environment information."""
    config = get_config()

    return APIResponse[VersionResponse].ok(
        data=VersionResponse(
            app_name=config.app_name,
            version=config.app_version,
            environment=config.app_env,
        )
    )
