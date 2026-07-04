"""
Pytest configuration and shared fixtures.

Provides:
- Application fixture (session-scoped)
- HTTP test client (session-scoped)
- In-memory SQLite engine for fast unit tests
- PostgreSQL session for integration tests (skipped if DB unavailable)
- Pre-built model instance factories for every domain entity
"""

import os
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

# ── Environment setup (before any app import) ─────────────────────────────
os.environ.setdefault("APP_ENV", "development")
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+psycopg2://etl_user:etl_password@localhost:5432/etl_platform_test",
)
os.environ.setdefault("LOG_LEVEL", "WARNING")
os.environ.setdefault("LOG_JSON_FORMAT", "False")
os.environ.setdefault("PIPELINE_ENABLE_SCHEDULER", "False")

# ── File system fixtures ───────────────────────────────────────────────────

@pytest.fixture(scope="session")
def test_data_dir():
    """
    Path to the tests/fixtures directory containing sample CSV/Excel files.

    Session-scoped: same path object for all tests.
    """
    from pathlib import Path
    return Path(__file__).parent / "fixtures"


# ── Application / API ──────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def app():
    from app.core.application import create_app
    return create_app()


@pytest.fixture(scope="session")
def client(app) -> Generator:
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c


# ── In-memory SQLite engine (unit tests, no Postgres needed) ──────────────

@pytest.fixture(scope="session")
def sqlite_engine():
    """
    In-memory SQLite engine for fast, isolated unit tests.

    Uses StaticPool. Replaces PostgreSQL-specific JSONB/UUID types for SQLite.
    Session-scoped — one engine for the entire test run.
    """
    from app.database.base import Base
    import app.database.models  # populate Base.metadata
    from sqlalchemy import JSON
    from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID

    # Patch JSONB → JSON for SQLite compatibility (same Python behavior)
    for table in Base.metadata.tables.values():
        for col in table.columns:
            if isinstance(col.type, JSONB):
                col.type = JSON()

    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        echo=False,
    )

    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_conn, _):
        dbapi_conn.execute("PRAGMA foreign_keys=ON")

    # Drop all first to ensure a clean slate, then create
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture(scope="function")
def db_session(sqlite_engine) -> Generator[Session, None, None]:
    """
    Clean database session for each test.

    Wraps each test in a transaction that is rolled back after the test,
    so tests are fully isolated without needing to truncate tables.
    """
    connection = sqlite_engine.connect()
    transaction = connection.begin()
    SessionLocal = sessionmaker(bind=connection, autocommit=False, autoflush=False)
    session = SessionLocal()

    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()


# ── PostgreSQL integration session (skipped if DB unavailable) ────────────

@pytest.fixture(scope="session")
def pg_engine():
    """Real PostgreSQL engine for integration tests."""
    from app.database.engine import create_database_engine, dispose_engine
    from app.database.init_db import create_all_tables

    try:
        engine = create_database_engine()
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        create_all_tables()
        yield engine
        dispose_engine()
    except Exception:
        pytest.skip("PostgreSQL not available — skipping integration tests")


@pytest.fixture(scope="function")
def pg_session(pg_engine) -> Generator[Session, None, None]:
    """Rollback-isolated PostgreSQL session per test."""
    conn = pg_engine.connect()
    tx = conn.begin()
    SessionLocal = sessionmaker(bind=conn, autocommit=False, autoflush=False)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
        tx.rollback()
        conn.close()


# ── Configuration ──────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def config():
    from app.core.config import get_config
    return get_config()


# ── Model factories ────────────────────────────────────────────────────────

@pytest.fixture
def make_supplier(db_session: Session):
    """Factory: create a Supplier and add to session."""
    counter = {"n": 0}
    def _make(**kwargs):
        counter["n"] += 1
        n = counter["n"]
        from app.database.models.operational.suppliers import Supplier
        sup = Supplier(
            supplier_code=kwargs.pop("supplier_code", f"SUP-TEST-{n:04d}"),
            company_name=kwargs.pop("company_name", f"Test Supplier {n}"),
            contact_email=kwargs.pop("contact_email", f"supplier{n}@test.com"),
            country=kwargs.pop("country", "US"),
            status=kwargs.pop("status", "active"),
            payment_terms=kwargs.pop("payment_terms", "net_30"),
            currency=kwargs.pop("currency", "USD"),
            **kwargs,
        )
        db_session.add(sup)
        db_session.flush()
        return sup
    return _make


@pytest.fixture
def make_product(db_session: Session, make_supplier):
    """Factory: create a Product and add to session."""
    counter = {"n": 0}
    def _make(**kwargs):
        counter["n"] += 1
        n = counter["n"]
        from app.database.models.operational.products import Product
        if "supplier_id" not in kwargs:
            sup = make_supplier()
            kwargs["supplier_id"] = sup.id
        prod = Product(
            sku=kwargs.pop("sku", f"TST-SKU-{n:06d}"),
            product_name=kwargs.pop("product_name", f"Test Product {n}"),
            category=kwargs.pop("category", "Electronics"),
            unit_price=kwargs.pop("unit_price", Decimal("29.99")),
            unit_cost=kwargs.pop("unit_cost", Decimal("12.00")),
            currency=kwargs.pop("currency", "USD"),
            status=kwargs.pop("status", "active"),
            **kwargs,
        )
        db_session.add(prod)
        db_session.flush()
        return prod
    return _make


@pytest.fixture
def make_customer(db_session: Session):
    """Factory: create a Customer and add to session."""
    counter = {"n": 0}
    def _make(**kwargs):
        counter["n"] += 1
        n = counter["n"]
        from app.database.models.operational.customers import Customer
        cust = Customer(
            first_name=kwargs.pop("first_name", "Test"),
            last_name=kwargs.pop("last_name", f"User{n}"),
            email=kwargs.pop("email", f"testuser{n}@example.com"),
            country=kwargs.pop("country", "US"),
            status=kwargs.pop("status", "active"),
            customer_segment=kwargs.pop("customer_segment", "standard"),
            **kwargs,
        )
        db_session.add(cust)
        db_session.flush()
        return cust
    return _make


@pytest.fixture
def make_order(db_session: Session, make_customer, make_product):
    """Factory: create an Order (with one line item) and add to session."""
    counter = {"n": 0}
    def _make(**kwargs):
        counter["n"] += 1
        n = counter["n"]
        from app.database.models.operational.orders import Order, OrderItem
        if "customer_id" not in kwargs:
            kwargs["customer_id"] = make_customer().id
        prod = make_product()
        price = Decimal("49.99")
        order = Order(
            order_number=kwargs.pop("order_number", f"ORD-TEST-{n:06d}"),
            order_date=kwargs.pop("order_date", date.today()),
            subtotal=kwargs.pop("subtotal", price),
            discount_amount=kwargs.pop("discount_amount", Decimal("0")),
            tax_amount=kwargs.pop("tax_amount", Decimal("4.12")),
            shipping_amount=kwargs.pop("shipping_amount", Decimal("5.00")),
            order_total=kwargs.pop("order_total", price + Decimal("9.12")),
            currency=kwargs.pop("currency", "USD"),
            status=kwargs.pop("status", "delivered"),
            payment_status=kwargs.pop("payment_status", "paid"),
            fulfillment_channel=kwargs.pop("fulfillment_channel", "standard"),
            **kwargs,
        )
        item = OrderItem(
            product_id=prod.id,
            quantity=1,
            unit_price_at_sale=price,
            discount_amount=Decimal("0"),
            line_total=price,
        )
        order.items.append(item)
        db_session.add(order)
        db_session.flush()
        return order
    return _make


@pytest.fixture
def make_payment(db_session: Session, make_order):
    """Factory: create a Payment and add to session."""
    counter = {"n": 0}
    def _make(**kwargs):
        counter["n"] += 1
        from app.database.models.operational.payments import Payment
        if "order_id" not in kwargs:
            kwargs["order_id"] = make_order().id
        pay = Payment(
            transaction_type=kwargs.pop("transaction_type", "payment"),
            transaction_status=kwargs.pop("transaction_status", "settled"),
            payment_method=kwargs.pop("payment_method", "credit_card"),
            payment_date=kwargs.pop("payment_date", date.today()),
            amount=kwargs.pop("amount", Decimal("59.11")),
            currency=kwargs.pop("currency", "USD"),
            **kwargs,
        )
        db_session.add(pay)
        db_session.flush()
        return pay
    return _make


@pytest.fixture
def make_pipeline_run(db_session: Session):
    """Factory: create a PipelineRun and add to session."""
    counter = {"n": 0}
    def _make(**kwargs):
        counter["n"] += 1
        n = counter["n"]
        from app.database.models.pipeline.pipeline_run import PipelineRun
        run = PipelineRun(
            run_number=kwargs.pop("run_number", f"20250115-{n:04d}"),
            pipeline_name=kwargs.pop("pipeline_name", "orders_pipeline"),
            dataset_type=kwargs.pop("dataset_type", "orders"),
            status=kwargs.pop("status", "completed"),
            total_records=kwargs.pop("total_records", 1000),
            valid_records=kwargs.pop("valid_records", 950),
            invalid_records=kwargs.pop("invalid_records", 50),
            cleaned_records=kwargs.pop("cleaned_records", 950),
            loaded_records=kwargs.pop("loaded_records", 940),
            failed_records=kwargs.pop("failed_records", 60),
            quality_score=kwargs.pop("quality_score", Decimal("95.00")),
            triggered_by=kwargs.pop("triggered_by", "test"),
            trigger_type=kwargs.pop("trigger_type", "manual"),
            **kwargs,
        )
        db_session.add(run)
        db_session.flush()
        return run
    return _make
