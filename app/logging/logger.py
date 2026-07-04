"""
Enterprise logging system using Loguru with structured logging support.

This module provides a centralized logger that:
- Writes to both console and rotating file
- Supports JSON-formatted logs for aggregation systems
- Categorizes logs by component
- Includes execution context (request ID, run ID, etc.)
- Auto-rotates log files based on size

Design: Uses loguru for simplicity and power. While Python's stdlib logging
works, loguru provides a cleaner API and better structured logging without
the boilerplate of handlers/formatters/filters.
"""

import sys
from functools import lru_cache
from pathlib import Path
from typing import Any

from loguru import logger as loguru_logger

from app.core.config import get_config

# Remove default logger (writes to stderr by default)
loguru_logger.remove()


def _setup_console_logging() -> None:
    """Configure console (stdout) logging with color and formatting."""
    config = get_config()

    # Console format: colorized, human-readable
    console_format = (
        "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
        "<level>{level: <8}</level> | "
        "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
        "<level>{message}</level>"
    )

    loguru_logger.add(
        sys.stdout,
        format=console_format,
        level=config.log_level,
        colorize=True,
        backtrace=True,
        diagnose=config.is_development,  # Show variable values in dev
    )


def _setup_file_logging() -> None:
    """Configure rotating file logging with JSON formatting."""
    config = get_config()

    # Ensure log directory exists
    config.log_file_path.parent.mkdir(parents=True, exist_ok=True)

    # File format: JSON for machine parsing
    if config.log_json_format:
        file_format = (
            '{{"timestamp": "{time:YYYY-MM-DD HH:mm:ss.SSS}", '
            '"level": "{level}", '
            '"module": "{name}", '
            '"function": "{function}", '
            '"line": {line}, '
            '"message": "{message}", '
            '"exception": "{exception}"}}'
        )
        serialize = False  # We're building JSON manually in format string
    else:
        # Plain text format for file
        file_format = (
            "{time:YYYY-MM-DD HH:mm:ss.SSS} | "
            "{level: <8} | "
            "{name}:{function}:{line} | "
            "{message}"
        )
        serialize = False

    loguru_logger.add(
        config.log_file_path,
        format=file_format,
        level=config.log_level,
        rotation=f"{config.log_max_size_mb} MB",
        retention=config.log_backup_count,
        compression="gz",  # Compress old log files
        backtrace=True,
        diagnose=False,  # Never include variable values in file logs
        enqueue=True,  # Thread-safe logging
        serialize=serialize,
    )


@lru_cache(maxsize=1)
def setup_logging() -> None:
    """
    Initialize the logging system.

    Called once at application startup. Idempotent — subsequent calls are no-ops.
    """
    _setup_console_logging()
    _setup_file_logging()


def get_logger(name: str | None = None) -> Any:
    """
    Get a logger instance for a specific module.

    Args:
        name: Module name (typically __name__). If None, returns root logger.

    Returns:
        Loguru logger bound to the module name.

    Example:
        >>> from app.logging.logger import get_logger
        >>> logger = get_logger(__name__)
        >>> logger.info("Pipeline started", run_id=run_id, stage="ingestion")
    """
    if name:
        return loguru_logger.bind(name=name)
    return loguru_logger


class StructuredLogger:
    """
    Wrapper for loguru logger providing a consistent structured logging interface.

    Ensures all log calls include module context and support arbitrary extra fields.
    """

    def __init__(self, module_name: str) -> None:
        """
        Initialize the structured logger for a module.

        Args:
            module_name: Name of the module (typically __name__).
        """
        self.module_name = module_name
        self._logger = get_logger(module_name)

    def _log(self, level: str, message: str, **kwargs: Any) -> None:
        """Internal helper to add context and delegate to loguru."""
        # Merge kwargs as extra context fields
        log_context = {"module": self.module_name, **kwargs}
        self._logger.opt(depth=2).bind(**log_context).log(level, message)

    def debug(self, message: str, **kwargs: Any) -> None:
        """Log a debug-level message."""
        self._log("DEBUG", message, **kwargs)

    def info(self, message: str, **kwargs: Any) -> None:
        """Log an info-level message."""
        self._log("INFO", message, **kwargs)

    def warning(self, message: str, **kwargs: Any) -> None:
        """Log a warning-level message."""
        self._log("WARNING", message, **kwargs)

    def error(self, message: str, **kwargs: Any) -> None:
        """Log an error-level message."""
        self._log("ERROR", message, **kwargs)

    def critical(self, message: str, **kwargs: Any) -> None:
        """Log a critical-level message."""
        self._log("CRITICAL", message, **kwargs)

    def exception(self, message: str, **kwargs: Any) -> None:
        """Log an exception with traceback."""
        self._logger.opt(depth=2).exception(message, **kwargs)


# Audit-specific logging (writes to both regular log and audit table — future)
class AuditLogger:
    """
    Specialized logger for audit events.

    Audit logs are significant business events that must be retained for compliance:
    - Pipeline started/completed/failed
    - Validation failures
    - Data cleaning actions
    - API access with user identity

    Future: Also writes to the audit_log database table.
    """

    def __init__(self, module_name: str) -> None:
        self.module_name = module_name
        self._logger = get_logger(f"{module_name}.audit")

    def log_event(
        self,
        event_type: str,
        message: str,
        user_id: str | None = None,
        run_id: str | None = None,
        **kwargs: Any,
    ) -> None:
        """
        Log an audit event.

        Args:
            event_type: Category of event (e.g., "PIPELINE_STARTED", "FILE_UPLOADED").
            message: Human-readable event description.
            user_id: ID of the user who triggered the event (if applicable).
            run_id: Pipeline run ID (if applicable).
            **kwargs: Additional context fields.
        """
        audit_context = {
            "event_type": event_type,
            "module": self.module_name,
            "user_id": user_id,
            "run_id": run_id,
            **kwargs,
        }

        self._logger.info(message, **audit_context)

        # TODO: In future, also write to audit_log database table
        # await audit_repository.create(event_type=event_type, message=message, ...)


# Module-level convenience function
def log_startup_info() -> None:
    """Log application startup information (called from main.py)."""
    config = get_config()
    startup_logger = get_logger("startup")

    startup_logger.info(
        "ETL Platform starting",
        app_name=config.app_name,
        version=config.app_version,
        environment=config.app_env,
        log_level=config.log_level,
    )

    if config.is_production:
        startup_logger.warning(
            "Running in PRODUCTION mode",
            security_warning="Ensure all secrets are properly configured",
        )
