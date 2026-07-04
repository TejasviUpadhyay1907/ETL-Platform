"""Initial schema — all 14 application tables.

Revision ID: 20250115_0001
Revises:
Create Date: 2025-01-15 00:00:00.000000

Description:
    Creates the complete initial database schema for the Enterprise ETL Platform.

    Operational tables (business data):
        customers, suppliers, products, inventory, orders, order_items, payments

    Pipeline metadata tables:
        pipeline_runs, ingestion_events, stage_results

    Audit and quality tables:
        audit_logs, validation_failures, cleaning_logs, data_quality_scores

    All tables include:
        - UUID primary keys (gen_random_uuid())
        - Timestamps (created_at, updated_at where applicable)
        - CHECK constraints for status and enum fields
        - Foreign key constraints with named references
        - Indexes on foreign keys, status columns, and common query patterns
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20250115_0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create all tables and indexes."""

    # ------------------------------------------------------------------
    # SUPPLIERS
    # ------------------------------------------------------------------
    op.create_table(
        "suppliers",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("supplier_code", sa.String(50), nullable=False),
        sa.Column("company_name", sa.String(255), nullable=False),
        sa.Column("trade_name", sa.String(255), nullable=True),
        sa.Column("contact_name", sa.String(200), nullable=True),
        sa.Column("contact_email", sa.String(255), nullable=False),
        sa.Column("contact_phone", sa.String(30), nullable=True),
        sa.Column("address_line1", sa.String(255), nullable=True),
        sa.Column("city", sa.String(100), nullable=True),
        sa.Column("state", sa.String(100), nullable=True),
        sa.Column("country", sa.String(2), server_default="US", nullable=False),
        sa.Column("postal_code", sa.String(20), nullable=True),
        sa.Column("payment_terms", sa.String(50), server_default="net_30", nullable=False),
        sa.Column("currency", sa.String(3), server_default="USD", nullable=False),
        sa.Column("rating", sa.Numeric(3, 2), nullable=True),
        sa.Column("status", sa.String(20), server_default="active", nullable=False),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("is_deleted", sa.Boolean, server_default="false", nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("created_by", sa.String(255), nullable=True),
        sa.Column("updated_by", sa.String(255), nullable=True),
        sa.CheckConstraint("status IN ('active','inactive','on_hold','blacklisted')", name="ck_suppliers_status"),
        sa.CheckConstraint("rating IS NULL OR (rating >= 0 AND rating <= 5)", name="ck_suppliers_rating"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("supplier_code", name="uq_suppliers_code"),
        comment="Supplier and vendor master data",
    )
    op.create_index("ix_suppliers_supplier_code", "suppliers", ["supplier_code"])
    op.create_index("ix_suppliers_contact_email", "suppliers", ["contact_email"])
    op.create_index("ix_suppliers_status", "suppliers", ["status"])
    op.create_index("ix_suppliers_country_status", "suppliers", ["country", "status"])
    op.create_index("ix_suppliers_is_deleted", "suppliers", ["is_deleted"])

    # ------------------------------------------------------------------
    # CUSTOMERS
    # ------------------------------------------------------------------
    op.create_table(
        "customers",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("first_name", sa.String(100), nullable=False),
        sa.Column("last_name", sa.String(100), nullable=False),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("phone", sa.String(30), nullable=True),
        sa.Column("gender", sa.String(20), nullable=True),
        sa.Column("date_of_birth", sa.Date, nullable=True),
        sa.Column("address_line1", sa.String(255), nullable=True),
        sa.Column("address_line2", sa.String(255), nullable=True),
        sa.Column("city", sa.String(100), nullable=True),
        sa.Column("state", sa.String(100), nullable=True),
        sa.Column("country", sa.String(2), server_default="US", nullable=False),
        sa.Column("postal_code", sa.String(20), nullable=True),
        sa.Column("customer_segment", sa.String(50), server_default="standard", nullable=False),
        sa.Column("status", sa.String(30), server_default="active", nullable=False),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("source_system", sa.String(100), nullable=True),
        sa.Column("external_id", sa.String(255), nullable=True),
        sa.Column("is_deleted", sa.Boolean, server_default="false", nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("created_by", sa.String(255), nullable=True),
        sa.Column("updated_by", sa.String(255), nullable=True),
        sa.CheckConstraint("status IN ('active','inactive','suspended','pending_verification')", name="ck_customers_status"),
        sa.CheckConstraint("gender IN ('male','female','non_binary','prefer_not_to_say') OR gender IS NULL", name="ck_customers_gender"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email", name="uq_customers_email"),
        comment="Customer master data — anchor for all business transactions",
    )
    op.create_index("ix_customers_email", "customers", ["email"])
    op.create_index("ix_customers_status", "customers", ["status"])
    op.create_index("ix_customers_city", "customers", ["city"])
    op.create_index("ix_customers_external_id", "customers", ["external_id"])
    op.create_index("ix_customers_is_deleted", "customers", ["is_deleted"])
    op.create_index("ix_customers_country_city", "customers", ["country", "city"])
    op.create_index("ix_customers_email_active", "customers", ["email"],
                    postgresql_where=sa.text("is_deleted = false"))

    # ------------------------------------------------------------------
    # PRODUCTS
    # ------------------------------------------------------------------
    op.create_table(
        "products",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("sku", sa.String(100), nullable=False),
        sa.Column("product_name", sa.String(255), nullable=False),
        sa.Column("short_name", sa.String(100), nullable=True),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("brand", sa.String(150), nullable=True),
        sa.Column("category", sa.String(100), nullable=False),
        sa.Column("subcategory", sa.String(100), nullable=True),
        sa.Column("unit_price", sa.Numeric(12, 4), nullable=False),
        sa.Column("unit_cost", sa.Numeric(12, 4), server_default="0.0000", nullable=False),
        sa.Column("currency", sa.String(3), server_default="USD", nullable=False),
        sa.Column("weight_grams", sa.Integer, nullable=True),
        sa.Column("unit_of_measure", sa.String(20), server_default="each", nullable=False),
        sa.Column("status", sa.String(20), server_default="active", nullable=False),
        sa.Column("is_taxable", sa.Boolean, server_default="true", nullable=False),
        sa.Column("tax_rate", sa.Numeric(5, 4), server_default="0.0000", nullable=False),
        sa.Column("supplier_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("is_deleted", sa.Boolean, server_default="false", nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("created_by", sa.String(255), nullable=True),
        sa.Column("updated_by", sa.String(255), nullable=True),
        sa.CheckConstraint("unit_price >= 0", name="ck_products_price_non_negative"),
        sa.CheckConstraint("unit_cost >= 0", name="ck_products_cost_non_negative"),
        sa.CheckConstraint("status IN ('active','inactive','discontinued','out_of_stock','draft')", name="ck_products_status"),
        sa.CheckConstraint("weight_grams IS NULL OR weight_grams >= 0", name="ck_products_weight_non_negative"),
        sa.ForeignKeyConstraint(["supplier_id"], ["suppliers.id"], name="fk_products_supplier", ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("sku", name="uq_products_sku"),
        comment="Product catalog master data",
    )
    op.create_index("ix_products_sku", "products", ["sku"])
    op.create_index("ix_products_brand", "products", ["brand"])
    op.create_index("ix_products_category", "products", ["category"])
    op.create_index("ix_products_status", "products", ["status"])
    op.create_index("ix_products_supplier_id", "products", ["supplier_id"])
    op.create_index("ix_products_is_deleted", "products", ["is_deleted"])
    op.create_index("ix_products_category_status", "products", ["category", "status"])
    op.create_index("ix_products_supplier_category", "products", ["supplier_id", "category"])

    # ------------------------------------------------------------------
    # INVENTORY
    # ------------------------------------------------------------------
    op.create_table(
        "inventory",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("product_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("warehouse_id", sa.String(50), nullable=False),
        sa.Column("quantity_on_hand", sa.Integer, server_default="0", nullable=False),
        sa.Column("reserved_quantity", sa.Integer, server_default="0", nullable=False),
        sa.Column("reorder_point", sa.Integer, server_default="10", nullable=False),
        sa.Column("reorder_quantity", sa.Integer, server_default="50", nullable=False),
        sa.Column("unit_cost", sa.Numeric(12, 4), server_default="0.0000", nullable=False),
        sa.Column("currency", sa.String(3), server_default="USD", nullable=False),
        sa.Column("last_counted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_received_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("created_by", sa.String(255), nullable=True),
        sa.Column("updated_by", sa.String(255), nullable=True),
        sa.CheckConstraint("quantity_on_hand >= 0", name="ck_inventory_quantity_non_negative"),
        sa.CheckConstraint("reserved_quantity >= 0", name="ck_inventory_reserved_non_negative"),
        sa.CheckConstraint("reorder_point >= 0", name="ck_inventory_reorder_point_non_negative"),
        sa.CheckConstraint("unit_cost >= 0", name="ck_inventory_unit_cost_non_negative"),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], name="fk_inventory_product", ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("product_id", "warehouse_id", name="uq_inventory_product_warehouse"),
        comment="Stock level tracking per product per warehouse",
    )
    op.create_index("ix_inventory_product_id", "inventory", ["product_id"])
    op.create_index("ix_inventory_warehouse_id", "inventory", ["warehouse_id"])
    op.create_index("ix_inventory_low_stock", "inventory", ["product_id", "warehouse_id"],
                    postgresql_where=sa.text("quantity_on_hand <= reorder_point"))

    # ------------------------------------------------------------------
    # ORDERS
    # ------------------------------------------------------------------
    op.create_table(
        "orders",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("order_number", sa.String(50), nullable=False),
        sa.Column("customer_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("order_date", sa.Date, nullable=False),
        sa.Column("required_date", sa.Date, nullable=True),
        sa.Column("shipped_date", sa.Date, nullable=True),
        sa.Column("delivered_date", sa.Date, nullable=True),
        sa.Column("subtotal", sa.Numeric(14, 4), server_default="0.0000", nullable=False),
        sa.Column("discount_amount", sa.Numeric(14, 4), server_default="0.0000", nullable=False),
        sa.Column("tax_amount", sa.Numeric(14, 4), server_default="0.0000", nullable=False),
        sa.Column("shipping_amount", sa.Numeric(10, 4), server_default="0.0000", nullable=False),
        sa.Column("order_total", sa.Numeric(14, 4), server_default="0.0000", nullable=False),
        sa.Column("currency", sa.String(3), server_default="USD", nullable=False),
        sa.Column("status", sa.String(20), server_default="pending", nullable=False),
        sa.Column("payment_status", sa.String(20), server_default="unpaid", nullable=False),
        sa.Column("fulfillment_channel", sa.String(50), server_default="standard", nullable=False),
        sa.Column("shipping_address_line1", sa.String(255), nullable=True),
        sa.Column("shipping_address_line2", sa.String(255), nullable=True),
        sa.Column("shipping_city", sa.String(100), nullable=True),
        sa.Column("shipping_state", sa.String(100), nullable=True),
        sa.Column("shipping_country", sa.String(2), nullable=True),
        sa.Column("shipping_postal_code", sa.String(20), nullable=True),
        sa.Column("tracking_number", sa.String(100), nullable=True),
        sa.Column("source_system", sa.String(100), nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("is_deleted", sa.Boolean, server_default="false", nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("created_by", sa.String(255), nullable=True),
        sa.Column("updated_by", sa.String(255), nullable=True),
        sa.CheckConstraint("status IN ('pending','processing','confirmed','shipped','delivered','cancelled','refunded','on_hold')", name="ck_orders_status"),
        sa.CheckConstraint("order_total >= 0", name="ck_orders_total_non_negative"),
        sa.CheckConstraint("discount_amount >= 0", name="ck_orders_discount_non_negative"),
        sa.CheckConstraint("tax_amount >= 0", name="ck_orders_tax_non_negative"),
        sa.ForeignKeyConstraint(["customer_id"], ["customers.id"], name="fk_orders_customer", ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("order_number", name="uq_orders_order_number"),
        comment="Sales order header records",
    )
    op.create_index("ix_orders_order_number", "orders", ["order_number"])
    op.create_index("ix_orders_customer_id", "orders", ["customer_id"])
    op.create_index("ix_orders_order_date", "orders", ["order_date"])
    op.create_index("ix_orders_status", "orders", ["status"])
    op.create_index("ix_orders_is_deleted", "orders", ["is_deleted"])
    op.create_index("ix_orders_customer_date", "orders", ["customer_id", "order_date"])
    op.create_index("ix_orders_status_date", "orders", ["status", "order_date"])

    # ------------------------------------------------------------------
    # ORDER ITEMS
    # ------------------------------------------------------------------
    op.create_table(
        "order_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("order_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("product_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("quantity", sa.Integer, nullable=False),
        sa.Column("unit_price_at_sale", sa.Numeric(12, 4), nullable=False),
        sa.Column("discount_amount", sa.Numeric(12, 4), server_default="0.0000", nullable=False),
        sa.Column("line_total", sa.Numeric(14, 4), nullable=False),
        sa.Column("notes", sa.String(500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("quantity > 0", name="ck_order_items_quantity_positive"),
        sa.CheckConstraint("unit_price_at_sale >= 0", name="ck_order_items_price_non_negative"),
        sa.CheckConstraint("discount_amount >= 0", name="ck_order_items_discount_non_negative"),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"], name="fk_order_items_order", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], name="fk_order_items_product", ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        comment="Order line items — one row per product per order",
    )
    op.create_index("ix_order_items_order_id", "order_items", ["order_id"])
    op.create_index("ix_order_items_product_id", "order_items", ["product_id"])

    # ------------------------------------------------------------------
    # PAYMENTS
    # ------------------------------------------------------------------
    op.create_table(
        "payments",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("order_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("transaction_type", sa.String(20), server_default="payment", nullable=False),
        sa.Column("transaction_status", sa.String(20), server_default="pending", nullable=False),
        sa.Column("payment_method", sa.String(30), nullable=False),
        sa.Column("payment_date", sa.Date, nullable=False),
        sa.Column("due_date", sa.Date, nullable=True),
        sa.Column("amount", sa.Numeric(14, 4), nullable=False),
        sa.Column("currency", sa.String(3), server_default="USD", nullable=False),
        sa.Column("exchange_rate", sa.Numeric(12, 6), nullable=True),
        sa.Column("base_currency_amount", sa.Numeric(14, 4), nullable=True),
        sa.Column("payment_gateway", sa.String(50), nullable=True),
        sa.Column("gateway_reference", sa.String(255), nullable=True),
        sa.Column("authorization_code", sa.String(100), nullable=True),
        sa.Column("card_last_four", sa.String(4), nullable=True),
        sa.Column("card_brand", sa.String(20), nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("created_by", sa.String(255), nullable=True),
        sa.Column("updated_by", sa.String(255), nullable=True),
        sa.CheckConstraint("transaction_type IN ('payment','refund','partial_refund','adjustment','chargeback')", name="ck_payments_transaction_type"),
        sa.CheckConstraint("payment_method IN ('credit_card','debit_card','bank_transfer','cash','cheque','paypal','stripe','apple_pay','google_pay','store_credit')", name="ck_payments_method"),
        sa.CheckConstraint("transaction_status IN ('pending','authorized','captured','settled','failed','cancelled','refunded','disputed')", name="ck_payments_status"),
        sa.CheckConstraint("amount > 0", name="ck_payments_amount_positive"),
        sa.CheckConstraint("exchange_rate IS NULL OR exchange_rate > 0", name="ck_payments_exchange_rate_positive"),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"], name="fk_payments_order", ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        comment="Payment transaction records linked to orders",
    )
    op.create_index("ix_payments_order_id", "payments", ["order_id"])
    op.create_index("ix_payments_payment_date", "payments", ["payment_date"])
    op.create_index("ix_payments_transaction_status", "payments", ["transaction_status"])
    op.create_index("ix_payments_payment_method", "payments", ["payment_method"])
    op.create_index("ix_payments_gateway_reference", "payments", ["gateway_reference"])
    op.create_index("ix_payments_gateway_reference_unique", "payments", ["gateway_reference"],
                    unique=True, postgresql_where=sa.text("gateway_reference IS NOT NULL"))
    op.create_index("ix_payments_method_date", "payments", ["payment_method", "payment_date"])

    # ------------------------------------------------------------------
    # PIPELINE RUNS
    # ------------------------------------------------------------------
    op.create_table(
        "pipeline_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("run_number", sa.String(30), nullable=False),
        sa.Column("pipeline_name", sa.String(100), nullable=False),
        sa.Column("dataset_type", sa.String(50), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_seconds", sa.Numeric(10, 3), nullable=True),
        sa.Column("status", sa.String(20), server_default="pending", nullable=False),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("error_stage", sa.String(50), nullable=True),
        sa.Column("total_records", sa.Integer, server_default="0", nullable=False),
        sa.Column("valid_records", sa.Integer, server_default="0", nullable=False),
        sa.Column("invalid_records", sa.Integer, server_default="0", nullable=False),
        sa.Column("cleaned_records", sa.Integer, server_default="0", nullable=False),
        sa.Column("loaded_records", sa.Integer, server_default="0", nullable=False),
        sa.Column("failed_records", sa.Integer, server_default="0", nullable=False),
        sa.Column("warning_count", sa.Integer, server_default="0", nullable=False),
        sa.Column("quality_score", sa.Numeric(5, 2), nullable=True),
        sa.Column("triggered_by", sa.String(100), server_default="system", nullable=False),
        sa.Column("trigger_type", sa.String(20), server_default="manual", nullable=False),
        sa.Column("execution_host", sa.String(255), nullable=True),
        sa.Column("metrics", postgresql.JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("status IN ('pending','running','completed','failed','partial','cancelled')", name="ck_pipeline_runs_status"),
        sa.CheckConstraint("dataset_type IN ('orders','customers','products','inventory','suppliers','payments')", name="ck_pipeline_runs_dataset_type"),
        sa.PrimaryKeyConstraint("id"),
        comment="Pipeline execution history — one row per ETL run",
    )
    op.create_index("ix_pipeline_runs_run_number", "pipeline_runs", ["run_number"])
    op.create_index("ix_pipeline_runs_dataset_type", "pipeline_runs", ["dataset_type"])
    op.create_index("ix_pipeline_runs_status", "pipeline_runs", ["status"])
    op.create_index("ix_pipeline_runs_started_at", "pipeline_runs", ["started_at"])
    op.create_index("ix_pipeline_runs_dataset_status", "pipeline_runs", ["dataset_type", "status"])
    op.create_index("ix_pipeline_runs_status_started", "pipeline_runs", ["status", "started_at"])

    # ------------------------------------------------------------------
    # INGESTION EVENTS
    # ------------------------------------------------------------------
    op.create_table(
        "ingestion_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("original_filename", sa.String(500), nullable=False),
        sa.Column("stored_filename", sa.String(500), nullable=False),
        sa.Column("file_path", sa.Text, nullable=False),
        sa.Column("file_extension", sa.String(10), nullable=False),
        sa.Column("file_size_bytes", sa.BigInteger, nullable=False),
        sa.Column("file_hash", sa.String(64), nullable=True),
        sa.Column("row_count_raw", sa.Integer, nullable=True),
        sa.Column("row_count_data", sa.Integer, nullable=True),
        sa.Column("dataset_type", sa.String(50), nullable=False),
        sa.Column("status", sa.String(20), server_default="received", nullable=False),
        sa.Column("rejection_reason", sa.Text, nullable=True),
        sa.Column("source_type", sa.String(20), server_default="upload", nullable=False),
        sa.Column("uploaded_by", sa.String(255), nullable=True),
        sa.Column("source_ip", sa.String(45), nullable=True),
        sa.Column("pipeline_run_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("status IN ('received','processing','processed','rejected','duplicate')", name="ck_ingestion_events_status"),
        sa.CheckConstraint("dataset_type IN ('orders','customers','products','inventory','suppliers','payments')", name="ck_ingestion_events_dataset_type"),
        sa.CheckConstraint("file_size_bytes > 0", name="ck_ingestion_events_file_size_positive"),
        sa.ForeignKeyConstraint(["pipeline_run_id"], ["pipeline_runs.id"], name="fk_ingestion_events_pipeline_run", ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        comment="Raw file ingestion event log",
    )
    op.create_index("ix_ingestion_events_dataset_type", "ingestion_events", ["dataset_type"])
    op.create_index("ix_ingestion_events_status", "ingestion_events", ["status"])
    op.create_index("ix_ingestion_events_file_hash", "ingestion_events", ["file_hash"])
    op.create_index("ix_ingestion_events_pipeline_run_id", "ingestion_events", ["pipeline_run_id"])

    # ------------------------------------------------------------------
    # STAGE RESULTS
    # ------------------------------------------------------------------
    op.create_table(
        "stage_results",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("pipeline_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("stage_name", sa.String(50), nullable=False),
        sa.Column("stage_order", sa.Integer, nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_ms", sa.Integer, nullable=True),
        sa.Column("status", sa.String(20), server_default="success", nullable=False),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("input_records", sa.Integer, server_default="0", nullable=False),
        sa.Column("output_records", sa.Integer, server_default="0", nullable=False),
        sa.Column("rejected_records", sa.Integer, server_default="0", nullable=False),
        sa.Column("warning_records", sa.Integer, server_default="0", nullable=False),
        sa.Column("quality_score", sa.Numeric(5, 2), nullable=True),
        sa.Column("details", postgresql.JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("stage_name IN ('ingestion','validation','cleaning','transformation','loading','reporting')", name="ck_stage_results_stage_name"),
        sa.CheckConstraint("status IN ('success','warning','failed','skipped')", name="ck_stage_results_status"),
        sa.CheckConstraint("stage_order >= 0", name="ck_stage_results_order_non_negative"),
        sa.ForeignKeyConstraint(["pipeline_run_id"], ["pipeline_runs.id"], name="fk_stage_results_pipeline_run", ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        comment="Per-stage execution results within a pipeline run",
    )
    op.create_index("ix_stage_results_pipeline_run_id", "stage_results", ["pipeline_run_id"])
    op.create_index("ix_stage_results_run_order", "stage_results", ["pipeline_run_id", "stage_order"])

    # ------------------------------------------------------------------
    # AUDIT LOGS
    # ------------------------------------------------------------------
    op.create_table(
        "audit_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("event_type", sa.String(50), nullable=False),
        sa.Column("severity", sa.String(10), server_default="INFO", nullable=False),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("stage", sa.String(50), nullable=True),
        sa.Column("user_id", sa.String(255), nullable=True),
        sa.Column("source_ip", sa.String(45), nullable=True),
        sa.Column("request_id", sa.String(36), nullable=True),
        sa.Column("entity_type", sa.String(100), nullable=True),
        sa.Column("entity_id", sa.String(255), nullable=True),
        sa.Column("message", sa.Text, nullable=False),
        sa.Column("context_data", postgresql.JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "event_type IN ('PIPELINE_STARTED','PIPELINE_COMPLETED','PIPELINE_FAILED','PIPELINE_CANCELLED',"
            "'STAGE_STARTED','STAGE_COMPLETED','STAGE_FAILED',"
            "'FILE_INGESTED','FILE_REJECTED','RECORD_LOADED','RECORD_REJECTED',"
            "'VALIDATION_FAILURE','CLEANING_ACTION','API_REQUEST','API_ERROR',"
            "'CONFIG_LOADED','SYSTEM_STARTUP','SYSTEM_SHUTDOWN')",
            name="ck_audit_logs_event_type",
        ),
        sa.PrimaryKeyConstraint("id"),
        comment="Immutable compliance and traceability event log",
    )
    op.create_index("ix_audit_logs_event_type", "audit_logs", ["event_type"])
    op.create_index("ix_audit_logs_run_id", "audit_logs", ["run_id"])
    op.create_index("ix_audit_logs_event_type_created", "audit_logs", ["event_type", "created_at"])
    op.create_index("ix_audit_logs_entity", "audit_logs", ["entity_type", "entity_id"])
    op.create_index("ix_audit_logs_user_created", "audit_logs", ["user_id", "created_at"])

    # ------------------------------------------------------------------
    # VALIDATION FAILURES
    # ------------------------------------------------------------------
    op.create_table(
        "validation_failures",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("pipeline_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("ingestion_event_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("row_index", sa.Integer, nullable=False),
        sa.Column("dataset_type", sa.String(50), nullable=False),
        sa.Column("rule_code", sa.String(50), nullable=False),
        sa.Column("rule_description", sa.String(500), nullable=True),
        sa.Column("field_name", sa.String(100), nullable=True),
        sa.Column("original_value", sa.String(1000), nullable=True),
        sa.Column("failure_message", sa.Text, nullable=False),
        sa.Column("severity", sa.String(10), server_default="error", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("severity IN ('error','warning','info')", name="ck_validation_failures_severity"),
        sa.PrimaryKeyConstraint("id"),
        comment="Per-record validation rule failure details",
    )
    op.create_index("ix_validation_failures_run_id", "validation_failures", ["pipeline_run_id"])
    op.create_index("ix_validation_failures_rule_code", "validation_failures", ["rule_code"])
    op.create_index("ix_validation_failures_run_rule", "validation_failures", ["pipeline_run_id", "rule_code"])

    # ------------------------------------------------------------------
    # CLEANING LOGS
    # ------------------------------------------------------------------
    op.create_table(
        "cleaning_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("pipeline_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("row_index", sa.Integer, nullable=False),
        sa.Column("dataset_type", sa.String(50), nullable=False),
        sa.Column("action_type", sa.String(50), nullable=False),
        sa.Column("field_name", sa.String(100), nullable=False),
        sa.Column("original_value", sa.String(1000), nullable=True),
        sa.Column("cleaned_value", sa.String(1000), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "action_type IN ('duplicate_removed','null_filled','null_dropped','null_flagged',"
            "'string_trimmed','case_normalized','date_standardized','numeric_cleaned','regex_applied')",
            name="ck_cleaning_logs_action_type",
        ),
        sa.PrimaryKeyConstraint("id"),
        comment="Per-record cleaning transformation audit log",
    )
    op.create_index("ix_cleaning_logs_run_id", "cleaning_logs", ["pipeline_run_id"])
    op.create_index("ix_cleaning_logs_action_type", "cleaning_logs", ["action_type"])

    # ------------------------------------------------------------------
    # DATA QUALITY SCORES
    # ------------------------------------------------------------------
    op.create_table(
        "data_quality_scores",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("pipeline_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("dataset_type", sa.String(50), nullable=False),
        sa.Column("total_records", sa.Integer, server_default="0", nullable=False),
        sa.Column("valid_records", sa.Integer, server_default="0", nullable=False),
        sa.Column("invalid_records", sa.Integer, server_default="0", nullable=False),
        sa.Column("warning_records", sa.Integer, server_default="0", nullable=False),
        sa.Column("duplicate_records", sa.Integer, server_default="0", nullable=False),
        sa.Column("loaded_records", sa.Integer, server_default="0", nullable=False),
        sa.Column("quality_score", sa.Numeric(5, 2), nullable=False),
        sa.Column("warning_threshold", sa.Numeric(5, 2), server_default="80.00", nullable=False),
        sa.Column("failure_threshold", sa.Numeric(5, 2), server_default="50.00", nullable=False),
        sa.Column("threshold_breached", sa.Boolean, server_default="false", nullable=False),
        sa.Column("threshold_warning", sa.Boolean, server_default="false", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("quality_score >= 0 AND quality_score <= 100", name="ck_quality_scores_range"),
        sa.CheckConstraint("total_records >= 0", name="ck_quality_scores_total_non_negative"),
        sa.CheckConstraint("dataset_type IN ('orders','customers','products','inventory','suppliers','payments')", name="ck_quality_scores_dataset_type"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("pipeline_run_id", name="uq_quality_scores_run_id"),
        comment="Aggregated data quality scores per pipeline run",
    )
    op.create_index("ix_quality_scores_pipeline_run_id", "data_quality_scores", ["pipeline_run_id"])
    op.create_index("ix_quality_scores_dataset_created", "data_quality_scores", ["dataset_type", "created_at"])
    op.create_index("ix_quality_scores_threshold_breached", "data_quality_scores", ["threshold_breached"],
                    postgresql_where=sa.text("threshold_breached = true"))


def downgrade() -> None:
    """Drop all tables in reverse dependency order."""
    # Audit / quality (no FKs to operational tables)
    op.drop_table("data_quality_scores")
    op.drop_table("cleaning_logs")
    op.drop_table("validation_failures")
    op.drop_table("audit_logs")
    # Pipeline metadata
    op.drop_table("stage_results")
    op.drop_table("ingestion_events")
    op.drop_table("pipeline_runs")
    # Operational (FK-dependent order)
    op.drop_table("payments")
    op.drop_table("order_items")
    op.drop_table("orders")
    op.drop_table("inventory")
    op.drop_table("products")
    op.drop_table("customers")
    op.drop_table("suppliers")
