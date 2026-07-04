"""
Database models package.

Importing this package makes all ORM models visible to SQLAlchemy's
Base.metadata, which is required for Alembic autogenerate to detect them.

IMPORTANT: Every new model module MUST be imported here to be included
in schema migrations. Forgetting this import is the #1 cause of missing
tables in Alembic autogenerate runs.
"""

# Operational models — business data tables
from app.database.models.operational.customers import Customer
from app.database.models.operational.inventory import Inventory
from app.database.models.operational.orders import Order, OrderItem
from app.database.models.operational.payments import Payment
from app.database.models.operational.products import Product
from app.database.models.operational.suppliers import Supplier

# Pipeline metadata models
from app.database.models.pipeline.ingestion_event import IngestionEvent
from app.database.models.pipeline.pipeline_run import PipelineRun
from app.database.models.pipeline.report import Report
from app.database.models.pipeline.stage_result import StageResult

# Audit and quality models
from app.database.models.audit.audit_log import AuditLog
from app.database.models.audit.cleaning_log import CleaningLog
from app.database.models.audit.quality_score import DataQualityScore
from app.database.models.audit.validation_failure import ValidationFailure

# Auth / security models (Phase 10)
from app.database.models.auth.permission import Permission
from app.database.models.auth.role import Role
from app.database.models.auth.user import User
from app.database.models.auth.api_key import APIKey
from app.database.models.auth.user_session import UserSession

__all__ = [
    # Operational
    "Customer",
    "Supplier",
    "Product",
    "Inventory",
    "Order",
    "OrderItem",
    "Payment",
    # Pipeline
    "PipelineRun",
    "IngestionEvent",
    "StageResult",
    "Report",
    # Audit
    "AuditLog",
    "ValidationFailure",
    "CleaningLog",
    "DataQualityScore",
    # Auth
    "Permission",
    "Role",
    "User",
    "APIKey",
    "UserSession",
]
