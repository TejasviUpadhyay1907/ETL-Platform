"""
Application-wide constants and enumerations.

All magic numbers, string literals, and fixed sets of values are defined here.
Never use raw strings for dataset types, statuses, or event types anywhere
in the codebase — always reference these constants.
"""

from enum import Enum


# =============================================================================
# Dataset Types
# =============================================================================


class DatasetType(str, Enum):
    """
    Enumeration of all supported dataset types.

    Each value corresponds to:
    - A filename pattern for ingestion detection
    - A config directory under config/datasets/
    - A target database table for loading
    """

    ORDERS = "orders"
    CUSTOMERS = "customers"
    PRODUCTS = "products"
    INVENTORY = "inventory"
    SUPPLIERS = "suppliers"
    PAYMENTS = "payments"


# =============================================================================
# Pipeline Run States
# =============================================================================


class PipelineStatus(str, Enum):
    """
    Possible states for a pipeline run.

    State transitions:
    PENDING → RUNNING → COMPLETED
    PENDING → RUNNING → FAILED
    PENDING → RUNNING → PARTIAL (some stages passed, failed at a specific stage)
    RUNNING → CANCELLED
    """

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    PARTIAL = "partial"
    CANCELLED = "cancelled"


# =============================================================================
# Pipeline Stage Names
# =============================================================================


class PipelineStage(str, Enum):
    """
    Named pipeline stages in execution order.

    Used in stage_results records to identify which stage produced a result.
    """

    INGESTION = "ingestion"
    VALIDATION = "validation"
    CLEANING = "cleaning"
    TRANSFORMATION = "transformation"
    LOADING = "loading"
    REPORTING = "reporting"


# =============================================================================
# Stage Result States
# =============================================================================


class StageStatus(str, Enum):
    """Possible states for a single pipeline stage result."""

    SUCCESS = "success"
    WARNING = "warning"
    FAILED = "failed"
    SKIPPED = "skipped"


# =============================================================================
# Validation Rule Severities
# =============================================================================


class RuleSeverity(str, Enum):
    """Severity level of a validation rule failure."""

    ERROR = "error"  # Rejects the record
    WARNING = "warning"  # Flags but does not reject
    INFO = "info"  # Informational only


# =============================================================================
# Record Validation Status
# =============================================================================


class RecordStatus(str, Enum):
    """Status applied to individual records after validation."""

    VALID = "valid"
    INVALID = "invalid"
    WARNING = "warning"


# =============================================================================
# Cleaning Action Types
# =============================================================================


class CleaningAction(str, Enum):
    """Types of cleaning transformations that can be applied to a record."""

    DUPLICATE_REMOVED = "duplicate_removed"
    NULL_FILLED = "null_filled"
    NULL_DROPPED = "null_dropped"
    NULL_FLAGGED = "null_flagged"
    STRING_TRIMMED = "string_trimmed"
    CASE_NORMALIZED = "case_normalized"
    DATE_STANDARDIZED = "date_standardized"
    NUMERIC_CLEANED = "numeric_cleaned"
    REGEX_APPLIED = "regex_applied"


# =============================================================================
# Audit Event Types
# =============================================================================


class AuditEventType(str, Enum):
    """Audit log event categories for compliance and traceability."""

    # Pipeline events
    PIPELINE_STARTED = "PIPELINE_STARTED"
    PIPELINE_COMPLETED = "PIPELINE_COMPLETED"
    PIPELINE_FAILED = "PIPELINE_FAILED"
    PIPELINE_CANCELLED = "PIPELINE_CANCELLED"

    # Stage events
    STAGE_STARTED = "STAGE_STARTED"
    STAGE_COMPLETED = "STAGE_COMPLETED"
    STAGE_FAILED = "STAGE_FAILED"

    # Data events
    FILE_INGESTED = "FILE_INGESTED"
    FILE_REJECTED = "FILE_REJECTED"
    RECORD_LOADED = "RECORD_LOADED"
    RECORD_REJECTED = "RECORD_REJECTED"
    VALIDATION_FAILURE = "VALIDATION_FAILURE"
    CLEANING_ACTION = "CLEANING_ACTION"

    # API events
    API_REQUEST = "API_REQUEST"
    API_ERROR = "API_ERROR"

    # System events
    CONFIG_LOADED = "CONFIG_LOADED"
    SYSTEM_STARTUP = "SYSTEM_STARTUP"
    SYSTEM_SHUTDOWN = "SYSTEM_SHUTDOWN"


# =============================================================================
# Report Types
# =============================================================================


class ReportType(str, Enum):
    """Types of reports that can be generated."""

    DATA_QUALITY = "data_quality"
    BUSINESS_SUMMARY = "business_summary"


class ReportFormat(str, Enum):
    """Supported report export formats."""

    CSV = "csv"
    EXCEL = "xlsx"


# =============================================================================
# File-related Constants
# =============================================================================

ALLOWED_FILE_EXTENSIONS: frozenset[str] = frozenset({"csv", "xlsx", "xls"})

DATASET_FILENAME_PATTERNS: dict[str, DatasetType] = {
    "order": DatasetType.ORDERS,
    "customer": DatasetType.CUSTOMERS,
    "product": DatasetType.PRODUCTS,
    "inventory": DatasetType.INVENTORY,
    "supplier": DatasetType.SUPPLIERS,
    "payment": DatasetType.PAYMENTS,
}

# =============================================================================
# API Constants
# =============================================================================

API_V1_PREFIX = "/api/v1"
DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100
API_KEY_HEADER = "X-API-Key"
REQUEST_ID_HEADER = "X-Request-ID"
PROCESS_TIME_HEADER = "X-Process-Time-Ms"
