"""
Repository layer — all database access objects.

Import repositories from here throughout the application.
No other module should import directly from repository sub-modules.

Usage:
    from app.database.repositories import CustomerRepository, OrderRepository
"""

from app.database.repositories.audit_log_repository import AuditLogRepository
from app.database.repositories.base_repository import BaseRepository
from app.database.repositories.customer_repository import CustomerRepository
from app.database.repositories.ingestion_event_repository import IngestionEventRepository
from app.database.repositories.inventory_repository import InventoryRepository
from app.database.repositories.order_repository import OrderRepository
from app.database.repositories.payment_repository import PaymentRepository
from app.database.repositories.pipeline_run_repository import PipelineRunRepository
from app.database.repositories.product_repository import ProductRepository
from app.database.repositories.report_repository import ReportRepository
from app.database.repositories.supplier_repository import SupplierRepository

__all__ = [
    "BaseRepository",
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
