"""
Core application configuration using Pydantic BaseSettings.

This module defines the central AppConfig class that loads configuration from
environment variables and provides type-safe access throughout the application.

All configuration is externalized — no hardcoded secrets or environment-specific values.
"""

from pathlib import Path

from pydantic import Field, PostgresDsn
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppConfig(BaseSettings):
    """
    Centralized application configuration loaded from environment variables.

    All fields have defaults suitable for development. Production deployments MUST
    override sensitive values (SECRET_KEY, DATABASE_URL, etc.) via environment variables.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",  # Ignore extra env vars not defined here
        env_nested_delimiter=None,
    )

    # -------------------------------------------------------------------------
    # Application Metadata
    # -------------------------------------------------------------------------
    app_name: str = Field(default="ETL Platform", description="Application display name")
    app_version: str = Field(default="1.0.0", description="Semantic version")
    app_env: str = Field(
        default="development",
        description="Environment: development, staging, production",
        pattern="^(development|staging|production)$",
    )

    host: str = Field(default="0.0.0.0", description="FastAPI server bind host")
    port: int = Field(default=8000, ge=1024, le=65535, description="FastAPI server port")

    # -------------------------------------------------------------------------
    # Security
    # -------------------------------------------------------------------------
    secret_key: str = Field(
        default="dev-secret-key-change-in-production",
        min_length=32,
        description="Application secret key for signing tokens",
    )
    api_key_salt: str = Field(
        default="dev-api-key-salt",
        min_length=16,
        description="Salt for API key hashing",
    )

    jwt_secret: str = Field(
        default="dev-jwt-secret-change-in-production",
        min_length=32,
        description="JWT token signing secret (future)",
    )
    jwt_algorithm: str = Field(default="HS256", description="JWT algorithm")
    jwt_expiration_minutes: int = Field(default=1440, ge=1, description="JWT expiration (minutes)")

    # -------------------------------------------------------------------------
    # Database Configuration
    # -------------------------------------------------------------------------
    database_url: PostgresDsn = Field(
        default="postgresql+psycopg2://etl_user:etl_password@localhost:5432/etl_platform",
        description="PostgreSQL connection URL",
    )

    db_pool_size: int = Field(default=10, ge=1, description="Database connection pool size")
    db_max_overflow: int = Field(
        default=20, ge=0, description="Max connections beyond pool_size"
    )
    db_pool_timeout: int = Field(
        default=30, ge=1, description="Connection pool timeout (seconds)"
    )
    db_pool_recycle: int = Field(
        default=3600, ge=60, description="Recycle connections older than (seconds)"
    )
    db_echo: bool = Field(default=False, description="Echo SQL queries to logs")

    # -------------------------------------------------------------------------
    # Logging
    # -------------------------------------------------------------------------
    log_level: str = Field(
        default="INFO",
        description="Log level",
        pattern="^(DEBUG|INFO|WARNING|ERROR|CRITICAL)$",
    )
    log_file_path: Path = Field(
        default=Path("logs/app.log"),
        description="Log file path",
    )
    log_max_size_mb: int = Field(default=100, ge=1, description="Log rotation size (MB)")
    log_backup_count: int = Field(default=10, ge=1, description="Number of log backups to keep")
    log_json_format: bool = Field(default=True, description="Use JSON log format")

    # -------------------------------------------------------------------------
    # File Storage
    # -------------------------------------------------------------------------
    upload_directory: Path = Field(default=Path("data/raw"), description="Raw file upload dir")
    report_directory: Path = Field(default=Path("data/reports"), description="Report output dir")
    archive_directory: Path = Field(default=Path("data/archive"), description="Archive dir")

    max_upload_size_mb: int = Field(default=500, ge=1, description="Max file upload size (MB)")
    allowed_file_types: str = Field(
        default="csv,xlsx,xls",
        description="Comma-separated allowed file extensions",
    )

    @property
    def allowed_file_types_list(self) -> list[str]:
        """Return allowed file types as a parsed list."""
        return [x.strip().lower() for x in self.allowed_file_types.split(",") if x.strip()]

    # -------------------------------------------------------------------------
    # Pipeline Configuration
    # -------------------------------------------------------------------------
    pipeline_chunk_size: int = Field(
        default=10000,
        ge=100,
        description="Chunk size for processing large files",
    )
    pipeline_max_concurrent_runs: int = Field(
        default=5,
        ge=1,
        description="Max concurrent pipeline runs",
    )
    pipeline_stage_timeout_seconds: int = Field(
        default=3600,
        ge=60,
        description="Pipeline stage timeout (seconds)",
    )
    pipeline_enable_scheduler: bool = Field(
        default=True,
        description="Enable scheduled pipeline runs",
    )

    # -------------------------------------------------------------------------
    # API Rate Limiting
    # -------------------------------------------------------------------------
    rate_limit_enabled: bool = Field(default=True, description="Enable API rate limiting")
    rate_limit_per_minute: int = Field(
        default=60, ge=1, description="Requests per minute per key"
    )
    rate_limit_per_hour: int = Field(default=1000, ge=1, description="Requests per hour per key")

    # -------------------------------------------------------------------------
    # CORS Configuration
    # -------------------------------------------------------------------------
    cors_enabled: bool = Field(default=True, description="Enable CORS")
    cors_origins: str = Field(
        default="http://localhost:8000",
        description="Comma-separated allowed CORS origins",
    )
    cors_allow_credentials: bool = Field(default=True, description="Allow credentials in CORS")
    cors_allow_methods: str = Field(
        default="GET,POST,PUT,DELETE,OPTIONS",
        description="Comma-separated allowed HTTP methods",
    )
    cors_allow_headers: str = Field(default="*", description="Comma-separated allowed headers")

    @property
    def cors_origins_list(self) -> list[str]:
        """Return CORS origins as a parsed list."""
        return [x.strip() for x in self.cors_origins.split(",") if x.strip()]

    @property
    def cors_allow_methods_list(self) -> list[str]:
        """Return allowed methods as a parsed list."""
        return [x.strip() for x in self.cors_allow_methods.split(",") if x.strip()]

    @property
    def cors_allow_headers_list(self) -> list[str]:
        """Return allowed headers as a parsed list."""
        return [x.strip() for x in self.cors_allow_headers.split(",") if x.strip()]

    # -------------------------------------------------------------------------
    # Data Quality Thresholds
    # -------------------------------------------------------------------------
    quality_score_warning_threshold: int = Field(
        default=80,
        ge=0,
        le=100,
        description="Quality score below this triggers warning",
    )
    quality_score_failure_threshold: int = Field(
        default=50,
        ge=0,
        le=100,
        description="Quality score below this triggers failure",
    )

    # -------------------------------------------------------------------------
    # Derived Properties
    # -------------------------------------------------------------------------
    @property
    def is_development(self) -> bool:
        """Check if running in development mode."""
        return self.app_env == "development"

    @property
    def is_production(self) -> bool:
        """Check if running in production mode."""
        return self.app_env == "production"

    @property
    def max_upload_size_bytes(self) -> int:
        """Convert MB to bytes for file size validation."""
        return self.max_upload_size_mb * 1024 * 1024

    def ensure_directories_exist(self) -> None:
        """Create all required directories if they don't exist."""
        directories = [
            self.upload_directory,
            self.report_directory,
            self.archive_directory,
            self.log_file_path.parent,
        ]
        for directory in directories:
            directory.mkdir(parents=True, exist_ok=True)


# Singleton instance
_config: AppConfig | None = None


def get_config() -> AppConfig:
    """
    Get the singleton AppConfig instance.

    Loads configuration on first call and returns the cached instance thereafter.
    This ensures configuration is loaded once and reused everywhere.
    """
    global _config
    if _config is None:
        _config = AppConfig()
        _config.ensure_directories_exist()
    return _config
