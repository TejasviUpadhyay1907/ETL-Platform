# Database Design
## Enterprise ETL & Data Quality Platform

**Version:** 1.0.0
**Schema Version:** Milestone 3

---

## Table of Contents

1. ER Diagram (Text)
2. Database Architecture Decisions
3. Table Reference
4. Relationship Explanations
5. Index Strategy
6. Normalization Decisions
7. Migration Guide
8. Repository Usage
9. Seed Data Guide

---

## 1. ER Diagram (Text)

```
SUPPLIERS (100 rows typical)
  id (PK)
  supplier_code (UNIQUE)
  company_name, contact_email, country, status
  └─── supplies ──→ PRODUCTS

PRODUCTS (2,000 rows typical)
  id (PK)
  sku (UNIQUE)
  category, subcategory, unit_price, unit_cost
  supplier_id (FK → SUPPLIERS)
  ├─── has stock in ──→ INVENTORY
  └─── referenced by ──→ ORDER_ITEMS

CUSTOMERS (5,000 rows typical)
  id (PK)
  email (UNIQUE)
  first_name, last_name, country, status
  └─── places ──→ ORDERS

ORDERS (50,000 rows typical)
  id (PK)
  order_number (UNIQUE)
  customer_id (FK → CUSTOMERS)
  order_date, order_total, status
  ├─── contains ──→ ORDER_ITEMS
  └─── paid by ──→ PAYMENTS

ORDER_ITEMS
  id (PK)
  order_id (FK → ORDERS, CASCADE DELETE)
  product_id (FK → PRODUCTS)
  quantity, unit_price_at_sale, line_total

PAYMENTS (20,000 rows typical)
  id (PK)
  order_id (FK → ORDERS)
  payment_method, amount, payment_date, transaction_status

INVENTORY (3,000 rows typical)
  id (PK)
  product_id (FK → PRODUCTS) ─┐
  warehouse_id               ─┘ UNIQUE together
  quantity_on_hand, unit_cost

─────────────────── PIPELINE METADATA ─────────────────────

PIPELINE_RUNS (50+ rows)
  id (PK)
  run_number, dataset_type, status
  total_records, valid_records, loaded_records, quality_score
  ├─── spawns ──→ STAGE_RESULTS
  └─── triggered by ──→ INGESTION_EVENTS

INGESTION_EVENTS
  id (PK)
  original_filename, dataset_type, status
  file_hash (idempotency key)
  pipeline_run_id (FK → PIPELINE_RUNS, SET NULL)

STAGE_RESULTS
  id (PK)
  pipeline_run_id (FK → PIPELINE_RUNS, CASCADE)
  stage_name, stage_order, status
  input_records, output_records, rejected_records

REPORTS
  id (PK)
  pipeline_run_id (no FK — loose coupling)
  report_type, file_format, file_path

─────────────────── AUDIT & QUALITY ───────────────────────

AUDIT_LOGS (INSERT-ONLY)
  id (PK)
  event_type, severity, run_id, user_id
  message, context_data (JSONB)

VALIDATION_FAILURES
  id (PK)
  pipeline_run_id, row_index
  rule_code, field_name, failure_message, severity

CLEANING_LOGS
  id (PK)
  pipeline_run_id, row_index
  action_type, field_name, original_value, cleaned_value

DATA_QUALITY_SCORES
  id (PK)
  pipeline_run_id (UNIQUE)
  quality_score, threshold_breached, threshold_warning
```

---

## 2. Database Architecture Decisions

### Why PostgreSQL?

PostgreSQL is the correct choice for this platform because:

1. **ACID compliance** — pipeline loading stage requires transactional integrity
2. **JSONB columns** — `pipeline_runs.metrics`, `stage_results.details`, `audit_logs.context_data` benefit from JSONB's indexable JSON storage
3. **Partial indexes** — `ix_customers_email_active`, `ix_inventory_low_stock`, `ix_quality_scores_threshold_breached` are only possible in PostgreSQL
4. **gen_random_uuid()** — server-side UUID generation without client round-trips
5. **ON CONFLICT DO UPDATE** — idempotent upsert for all ETL loading operations

### Why UUID Primary Keys?

- **No sequential leakage** — an attacker cannot enumerate records by incrementing an integer ID
- **Multi-source merge safety** — records from different systems can be inserted without PK conflicts
- **Distributed-ready** — UUIDs remain unique across multiple worker nodes

### Why No Global Integer Sequences?

Integer sequences create coordination bottlenecks in distributed systems. For a platform designed to scale to multiple workers, UUID keys are the correct choice.

### Why Soft Delete on Business Entities?

Customers, suppliers, products, and orders are never physically deleted because:
- Orders reference customers — deleting a customer would orphan order history
- Audit trails must reference the original entities
- GDPR "right to be forgotten" is implemented by nullifying PII fields, not by deleting rows

---

## 3. Table Reference

### Operational Tables (Business Data)

| Table | Rows (typical) | Primary Key | Natural Key | Description |
|---|---|---|---|---|
| customers | 5,000 | UUID | email | Customer master record |
| suppliers | 100 | UUID | supplier_code | Vendor/supplier master |
| products | 2,000 | UUID | sku | Product catalog |
| inventory | 3,000 | UUID | (product_id, warehouse_id) | Stock levels per location |
| orders | 50,000 | UUID | order_number | Sales order header |
| order_items | 200,000 | UUID | — | Order line items |
| payments | 20,000 | UUID | gateway_reference | Payment transactions |

### Pipeline Metadata Tables

| Table | Description |
|---|---|
| pipeline_runs | One record per ETL execution |
| ingestion_events | One record per file ingestion |
| stage_results | One record per stage per run |
| reports | One record per generated report file |

### Audit and Quality Tables

| Table | Description |
|---|---|
| audit_logs | Immutable compliance event log |
| validation_failures | Per-record, per-rule validation failures |
| cleaning_logs | Per-record cleaning action history |
| data_quality_scores | Aggregated quality score per run |

---

## 4. Relationship Explanations

### Customer → Orders (one-to-many)
One customer can place many orders. FK: `orders.customer_id → customers.id`.
`ON DELETE RESTRICT` — prevents deleting a customer who has orders.

### Order → OrderItems (one-to-many, cascade)
One order contains one or more line items. FK: `order_items.order_id → orders.id`.
`ON DELETE CASCADE` — deleting an order physically removes its line items.
This is the only cascade delete in the schema — order items have no independent meaning.

### Order → Payments (one-to-many)
One order can have multiple payments (partial payments, refunds).
FK: `payments.order_id → orders.id`. `ON DELETE RESTRICT`.

### Product → OrderItems (one-to-many)
One product appears on many order lines across many orders.
FK: `order_items.product_id → products.id`. `ON DELETE RESTRICT`.

### Product → Inventory (one-to-many)
One product can have stock at multiple warehouses.
Composite UNIQUE on `(product_id, warehouse_id)` ensures one record per location.
FK: `inventory.product_id → products.id`. `ON DELETE RESTRICT`.

### Supplier → Products (one-to-many)
One supplier can supply many products.
FK: `products.supplier_id → suppliers.id`. `ON DELETE SET NULL` — deleting a supplier
does not delete its products, it just clears the supplier reference.

### PipelineRun → StageResults (one-to-many, cascade)
One run produces up to 6 stage results (one per ETL stage).
FK: `stage_results.pipeline_run_id → pipeline_runs.id`. `ON DELETE CASCADE`.

### PipelineRun → IngestionEvents (one-to-many, SET NULL)
An ingestion event triggers a pipeline run. The relationship is nullable — an event
exists before a run is created. FK: `ingestion_events.pipeline_run_id → pipeline_runs.id`.
`ON DELETE SET NULL` — deleting a run does not delete the original file event record.

---

## 5. Index Strategy

### Index Categories

**Primary key indexes** — automatic on all `id` columns.

**Business key indexes** — unique indexes on natural keys:
- `uq_customers_email` — customer lookup by email
- `uq_products_sku` — product lookup by SKU
- `uq_suppliers_code` — supplier lookup by code
- `uq_orders_order_number` — order lookup by reference

**Foreign key indexes** — every FK column is indexed:
- `ix_orders_customer_id`, `ix_order_items_order_id`, `ix_payments_order_id`
- `ix_products_supplier_id`, `ix_inventory_product_id`
- `ix_stage_results_pipeline_run_id`, `ix_ingestion_events_pipeline_run_id`

**Query pattern indexes** — indexed for the most common WHERE clause patterns:
- `ix_orders_order_date` — date-range order reports
- `ix_customers_country_city` (composite) — geographic analytics
- `ix_pipeline_runs_dataset_status` (composite) — dashboard run list
- `ix_payments_method_date` (composite) — payment method analytics
- `ix_audit_logs_event_type_created` (composite) — compliance time-window queries

**Partial indexes** (PostgreSQL-specific — filtered to a subset of rows):
- `ix_customers_email_active` — only active (non-deleted) customers
- `ix_inventory_low_stock` — only items at or below reorder point
- `ix_quality_scores_threshold_breached` — only breached scores (for alerting)
- `ix_payments_gateway_reference_unique` — unique only where not NULL

### Index Design Principle

> Every index must justify its existence by serving a specific query pattern. Unnecessary indexes slow INSERT/UPDATE performance. Every index in this schema was designed for a documented query pattern.

---

## 6. Normalization Decisions

### Third Normal Form (3NF) Compliance

All tables satisfy 3NF:
- Every non-key column depends on the whole key
- No transitive dependencies (non-key columns do not depend on other non-key columns)

### Intentional Denormalization (documented exceptions)

**1. shipping_address on orders (not FK to customer.address)**

The customer's current address may change after the order was placed. Denormalizing
the shipping address onto the order record preserves the historical delivery address.
This is required for correct shipping label regeneration and return logistics.

**2. unit_price_at_sale on order_items (not FK to product.unit_price)**

Product prices change over time. Storing the price at the time of sale on the line item
ensures historical revenue reports are accurate and legal invoices reflect the correct price.

**3. subtotal, tax_amount, order_total on orders**

These are computed from line items but stored for two reasons:
- Performance: avoids re-summing all items on every order query
- Accuracy: totals can include manual adjustments that don't map to line items

**4. Summary counts on pipeline_runs**

`valid_records`, `loaded_records`, `quality_score` etc. are aggregated from stage results
but stored directly on pipeline_runs for fast dashboard queries without re-aggregating.

---

## 7. Migration Guide

### Running migrations (production)

```bash
# Apply all pending migrations
python scripts/run_migrations.py

# Or via Alembic CLI
alembic upgrade head

# Check current revision
alembic current

# View migration history
alembic history --verbose
```

### Creating a new migration

```bash
# After adding/modifying a model, autogenerate the migration
alembic revision --autogenerate -m "add_column_X_to_table_Y"

# Review the generated file in migrations/versions/
# Then apply it
alembic upgrade head
```

### Rolling back

```bash
# Downgrade one step
alembic downgrade -1

# Downgrade to base (drops all tables)
alembic downgrade base
```

### Migration file naming convention

```
YYYYMMDD_NNNN_descriptive_name.py
Example: 20250115_0001_initial_schema.py
```

---

## 8. Repository Usage

### Dependency injection pattern

```python
from app.database.engine import get_session
from app.database.repositories import CustomerRepository

# Using context manager (for scripts and service classes)
with get_session() as session:
    repo = CustomerRepository(session)
    customer = repo.get_by_email("user@example.com")

# Using FastAPI Depends (for API endpoints)
from app.api.dependencies import DbSession
from app.database.repositories import CustomerRepository

@router.get("/customers/{customer_id}")
def get_customer(customer_id: uuid.UUID, db: DbSession):
    repo = CustomerRepository(db)
    return repo.get_by_id_or_raise(customer_id)
```

### Bulk upsert pattern

```python
with get_session() as session:
    repo = CustomerRepository(session)
    customer_dicts = [
        {"email": "a@test.com", "first_name": "Alice", ...},
        {"email": "b@test.com", "first_name": "Bob", ...},
    ]
    result = repo.bulk_upsert(customer_dicts)
    # result = {"inserted": 2, "updated": 0}
```

### Transaction management

```python
from app.database.transaction import atomic

with get_session() as session:
    with atomic(session) as s:
        order_repo = OrderRepository(s)
        payment_repo = PaymentRepository(s)
        order = order_repo.create(...)
        payment = payment_repo.create(order_id=order.id, ...)
        # Both committed together — or both rolled back on exception
```

---

## 9. Seed Data Guide

```bash
# Seed with small volume (fast, ~30 seconds)
python scripts/seed_data.py --count small

# Seed with full production-like volume
python scripts/seed_data.py --count full

# Clear and re-seed
python scripts/seed_data.py --truncate --count small

# Tiny volume for quick smoke tests
python scripts/seed_data.py --count tiny
```

### Volume presets

| Preset | Suppliers | Products | Customers | Orders | Payments |
|---|---|---|---|---|---|
| tiny | 5 | 50 | 100 | 500 | 200 |
| small | 10 | 200 | 500 | 5,000 | 2,000 |
| full | 100 | 2,000 | 5,000 | 50,000 | 20,000 |

### Seed data is deterministic

The seed script uses a fixed random seed (`RANDOM_SEED = 42`).
Running it twice on a truncated database produces identical data.
This enables reproducible test environments.
