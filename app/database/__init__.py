"""
Database layer package.

Exposes the public interface for the entire database layer.
All application code imports from here — never from sub-modules directly.

Example usage:
    from app.database import get_session, Base
    from app.database import CustomerRepository, OrderRepository
    from app.database.models import Customer, Order, Product
"""

# Core engine and session management
from app.database.engine import (
    check_database_health,
    dispose_engine,
    get_engine,
    get_session,
    get_db_session,
)

# Base classes and mixins
from app.database.base import (
    AuditMixin,
    Base,
    SoftDeleteMixin,
    TimestampMixin,
    UUIDMixin,
)

# Transaction utilities
from app.database.transaction import TransactionManager, atomic, savepoint

# Repositories (all of them)
from app.database.repositories import (
    AuditLogRepository,
    CustomerRepository,
    IngestionEventRepository,
    InventoryRepository,
    OrderRepository,
    PaymentRepository,
    PipelineRunRepository,
    ProductRepository,
    ReportRepository,
    SupplierRepository,
)

__all__ = [
    # Engine & session
    "get_engine",
    "get_session",
    "get_db_session",
    "check_database_health",
    "dispose_engine",
    # ORM base
    "Base",
    "TimestampMixin",
    "UUIDMixin",
    "SoftDeleteMixin",
    "AuditMixin",
    # Transactions
    "TransactionManager",
    "atomic",
    "savepoint",
    # Repositories
    "CustomerRepository",
    "SupplierRepository",
    "ProductRepository",
    "InventoryRepository",
    "OrderRepository",
    "PaymentRepository",
    "PipelineRunRepository",
    "IngestionEventRepository",
    "ReportRepository",
    "AuditLogRepository",
]
