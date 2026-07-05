"""
FastAPI application factory.

This module creates and configures the FastAPI application instance.
Using the factory pattern (create_app function) instead of a module-level
global makes the app testable — tests can call create_app() to get a
fresh, isolated instance.

Configured here:
- Application metadata (title, description, version, OpenAPI)
- All middleware (CORS, GZip, security headers, logging, request ID)
- All API routers
- Exception handlers
- Startup and shutdown lifecycle events
"""

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.staticfiles import StaticFiles

from app.core.config import get_config
from app.logging.logger import log_startup_info, setup_logging

APP_DESCRIPTION = """
## Enterprise ETL & Data Quality Platform

A production-grade automated data pipeline system for retail organizations.

### Capabilities

- **Data Ingestion**: Upload CSV/Excel files or poll directories for new data
- **Quality Validation**: Enforce schema and business rules per dataset type
- **Data Cleaning**: Deduplicate, normalize, and standardize incoming records
- **Transformation**: Apply business logic and produce analytics-ready datasets
- **Loading**: Persist clean data to PostgreSQL with full audit trail
- **Reporting**: Generate data quality and business summary reports
- **Monitoring**: Full pipeline run history, quality scores, and audit logs

### Authentication

All endpoints (except health checks) require an API key.
Pass your key in the `X-API-Key` request header.

### Response Format

All responses follow a standard envelope:
```json
{
    "success": true,
    "data": { ... },
    "error": null,
    "meta": { "request_id": "...", "timestamp": "..." }
}
```

### Support

For API access or issues, contact the Data Engineering team.
"""


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """
    Application lifespan context manager.

    Handles startup and shutdown events.
    Code before `yield` runs on startup; code after runs on shutdown.
    """
    # -------------------------------------------------------------------------
    # STARTUP
    # -------------------------------------------------------------------------
    setup_logging()
    log_startup_info()

    config = get_config()

    from app.database.engine import get_engine

    # Initialize database engine (creates connection pool)
    get_engine()

    from app.logging.logger import get_logger as _get_logger
    _startup_logger = _get_logger("startup")

    # Verify DB connectivity (non-fatal in development)
    try:
        from app.database.init_db import initialize_database
        initialize_database(run_migrations_on_startup=False)
    except Exception as e:
        _startup_logger.warning(f"Database initialization skipped: {e}")

    from app.logging.logger import get_logger

    logger = get_logger("startup")
    logger.info(
        "Application startup complete",
        host=config.host,
        port=config.port,
        docs_url="/docs",
        redoc_url="/redoc",
    )

    yield  # Application runs here

    # -------------------------------------------------------------------------
    # SHUTDOWN
    # -------------------------------------------------------------------------
    from app.database.engine import dispose_engine

    dispose_engine()

    logger.info("Application shutdown complete")


def create_app() -> FastAPI:
    """
    Create and configure the FastAPI application.

    Returns:
        Fully configured FastAPI instance ready to serve requests.
    """
    config = get_config()

    app = FastAPI(
        title=config.app_name,
        description=APP_DESCRIPTION,
        version=config.app_version,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        swagger_ui_parameters={
            "defaultModelsExpandDepth": -1,
            "persistAuthorization": True,
            "displayRequestDuration": True,
        },
        lifespan=lifespan,
        # OpenAPI metadata
        contact={
            "name": "Data Engineering Team",
            "email": "data-engineering@company.com",
        },
        license_info={
            "name": "Proprietary",
        },
        terms_of_service="https://internal.company.com/tos",
    )

    # -------------------------------------------------------------------------
    # Register Middleware (ORDER MATTERS — registered in reverse execution order)
    # -------------------------------------------------------------------------
    _register_middleware(app, config)

    # -------------------------------------------------------------------------
    # Register Exception Handlers
    # -------------------------------------------------------------------------
    from app.api.error_handlers import register_exception_handlers

    register_exception_handlers(app)

    # -------------------------------------------------------------------------
    # Register API Routers
    # -------------------------------------------------------------------------
    _register_routers(app)

    # -------------------------------------------------------------------------
    # Mount Static Files
    # -------------------------------------------------------------------------
    _mount_static_files(app)

    return app


def _register_middleware(app: FastAPI, config: "AppConfig") -> None:  # type: ignore[name-defined]
    """Register all middleware on the application."""
    from app.core.config import AppConfig

    # GZip compression (must be added before CORS to compress all responses)
    app.add_middleware(GZipMiddleware, minimum_size=1000)

    # CORS (Cross-Origin Resource Sharing)
    if config.cors_enabled:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=config.cors_origins_list,
            allow_credentials=config.cors_allow_credentials,
            allow_methods=config.cors_allow_methods_list,
            allow_headers=config.cors_allow_headers_list,
        )

    # Trusted host middleware (prevent host header injection)
    if config.is_production:
        app.add_middleware(
            TrustedHostMiddleware,
            allowed_hosts=["*"],  # Configure with actual hostnames in production
        )

    # Custom middleware (executed in reverse registration order for requests)
    from app.middleware.logging_middleware import RequestLoggingMiddleware
    from app.middleware.request_id_middleware import RequestIDMiddleware
    from app.middleware.security_headers_middleware import SecurityHeadersMiddleware

    # Phase 10: Auth + Rate Limiting middleware
    from app.api.middleware.rate_limit_middleware import RateLimitMiddleware
    from app.api.middleware.auth_middleware import JWTAuthMiddleware

    # Phase 12: Prometheus metrics middleware
    from app.middleware.metrics_middleware import PrometheusMetricsMiddleware

    # Note: Middleware execution order for requests is LIFO (last registered = first executed)
    # Registration order (request direction): Security → Logging → RequestID → Auth → RateLimit → Metrics
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(RequestLoggingMiddleware)
    app.add_middleware(RequestIDMiddleware)
    app.add_middleware(JWTAuthMiddleware)
    app.add_middleware(
        RateLimitMiddleware,
        per_minute=config.rate_limit_per_minute,
        per_hour=config.rate_limit_per_hour,
    )
    app.add_middleware(PrometheusMetricsMiddleware)


def _register_routers(app: FastAPI) -> None:
    """Register all API routers under the versioned prefix."""
    from app.api.routers.data_router import router as data_router
    from app.api.routers.health_router import router as health_router
    from app.api.routers.ingest_router import router as ingest_router
    from app.api.routers.pipeline_router import router as pipeline_router
    from app.api.routers.quality_router import router as quality_router
    from app.api.routers.reports_router import router as reports_router
    # Phase 10: Auth, Users, Roles, API Keys
    from app.api.routers.auth_router import router as auth_router
    from app.api.routers.users_router import router as users_router
    from app.api.routers.roles_router import router as roles_router
    from app.api.routers.api_keys_router import router as api_keys_router

    api_v1_prefix = "/api/v1"

    app.include_router(health_router, prefix=api_v1_prefix)
    app.include_router(auth_router, prefix=api_v1_prefix)
    app.include_router(ingest_router, prefix=api_v1_prefix)
    app.include_router(pipeline_router, prefix=api_v1_prefix)
    app.include_router(data_router, prefix=api_v1_prefix)
    app.include_router(quality_router, prefix=api_v1_prefix)
    app.include_router(reports_router, prefix=api_v1_prefix)
    app.include_router(users_router, prefix=api_v1_prefix)
    app.include_router(roles_router, prefix=api_v1_prefix)
    app.include_router(api_keys_router, prefix=api_v1_prefix)

    # Phase 12: Prometheus metrics scrape endpoint (no auth required)
    from app.api.routers.metrics_router import router as metrics_router
    app.include_router(metrics_router)


def _mount_static_files(app: FastAPI) -> None:
    """Mount static file directories for the dashboard."""
    import os

    static_path = "app/static"
    if os.path.exists(static_path):
        app.mount("/static", StaticFiles(directory=static_path), name="static")
