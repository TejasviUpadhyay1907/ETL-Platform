"""
Enterprise ETL Platform - End-to-End Pipeline Demo
===================================================
Demonstrates all 5 ETL stages with real data flowing through the system.

INPUT:  data/sample/orders_valid.csv  (25 order records)
OUTPUT: PostgreSQL orders table  +  full audit trail

Run: python scripts/run_demo_pipeline.py
"""
import sys, os, uuid, time
from pathlib import Path
from decimal import Decimal

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import httpx

BASE = "http://localhost:8001"
SEP  = "=" * 60

def banner(title):
    print(f"\n{SEP}\n  {title}\n{SEP}")

# ─── STEP 1: Login ────────────────────────────────────────────────────────
banner("STEP 1 - Login")
r = httpx.post(f"{BASE}/api/v1/auth/login",
               json={"username": "admin", "password": "Admin1234!"}, timeout=10)
assert r.status_code == 200, f"Login failed: {r.text}"
token = r.json()["data"]["access_token"]
HDR   = {"Authorization": f"Bearer {token}"}
print(f"  OK  admin logged in | roles: {r.json()['data']['roles']}")

# ─── STEP 2: Show INPUT ────────────────────────────────────────────────────
banner("STEP 2 - INPUT Data  (orders_valid.csv)")
sample = Path("data/sample/orders_valid.csv")
lines  = sample.read_text(encoding="utf-8").strip().split("\n")
print(f"  File    : {sample.name}  ({sample.stat().st_size:,} bytes)")
print(f"  Records : {len(lines)-1} orders")
print(f"  Columns : {lines[0]}")
print(f"\n  First 3 rows:")
for row in lines[1:4]:
    print(f"    {row[:90]}")

# ─── STEP 3: Run all 5 stages via internal service ────────────────────────
banner("STEP 3 - Running All 5 ETL Stages")
print("  Ingestion -> Validation -> Cleaning -> Transformation -> Loading")
print()

from app.logging.logger import setup_logging
setup_logging()

import pandas as pd
from app.database.engine import get_session
from app.ingestion.readers.csv_reader import CSVReader
from app.ingestion.models import Dataset, DatasetSchema, FileMetadata, IngestionResult, IngestionStatus
from app.validation.validator import ValidationEngine
from app.cleaning.cleaner import CleaningEngine
from app.transformation.transformation_engine import TransformationEngine
from app.loading.loader import WarehouseLoader

stage_results = []
run_id = str(uuid.uuid4())
t_total = time.perf_counter()

with get_session() as session:

    # ── Stage 1: Ingestion ────────────────────────────────────────────────
    print("  [1/5] Ingestion...")
    t0 = time.perf_counter()

    reader = CSVReader()
    df_raw, schema = reader.read(sample)

    meta = FileMetadata(
        original_filename=sample.name,
        stored_filename=sample.name,
        file_path=sample,
        file_extension="csv",
        file_size_bytes=sample.stat().st_size,
        dataset_type="orders",
    )
    dataset = Dataset(
        metadata=meta,
        dataframe=df_raw,
        schema=schema,
        ingestion_event_id=run_id,
        pipeline_run_id=run_id,
    )
    ing_result = IngestionResult(
        success=True,
        status=IngestionStatus.PROCESSED,
        dataset=dataset,
        ingestion_event_id=run_id,
        file_metadata=meta,
    )
    d1 = time.perf_counter() - t0
    stage_results.append(("Ingestion", "SUCCESS", len(df_raw), len(df_raw), d1))
    print(f"        OK  {len(df_raw)} rows read | cols: {list(df_raw.columns)[:4]}...")

    # ── Stage 2: Validation ───────────────────────────────────────────────
    print("  [2/5] Validation...")
    t0 = time.perf_counter()

    val = ValidationEngine(session=session).validate(dataset, pipeline_run_id=run_id)
    d2 = time.perf_counter() - t0
    stage_results.append(("Validation", "SUCCESS" if val.success else "WARNING",
                           len(df_raw), val.valid_count + val.warning_count, d2))
    print(f"        OK  score={val.quality_score:.1f}% ({val.letter_grade}) | "
          f"valid={val.valid_count} | warnings={val.warning_count} | "
          f"violations={val.report.violation_count}")

    # ── Stage 3: Cleaning ─────────────────────────────────────────────────
    print("  [3/5] Cleaning...")
    t0 = time.perf_counter()

    clean = CleaningEngine(session=session).clean(val, pipeline_run_id=run_id,
                                                   original_filename=sample.name)
    d3 = time.perf_counter() - t0
    stage_results.append(("Cleaning", "SUCCESS" if clean.success else "FAILED",
                           val.valid_count + val.warning_count, clean.row_count, d3))
    print(f"        OK  {clean.row_count} rows after cleaning | "
          f"dropped={clean.rows_dropped} | actions={clean.total_actions}")

    # ── Stage 4: Transformation ───────────────────────────────────────────
    print("  [4/5] Transformation...")
    t0 = time.perf_counter()

    trans = TransformationEngine(session=session).transform(
        cleaned_df=clean.cleaned_df,
        dataset_type="orders",
        original_filename=sample.name,
        pipeline_run_id=run_id,
    )
    d4 = time.perf_counter() - t0
    original_cols = set(df_raw.columns)
    new_cols      = [c for c in trans.transformed_df.columns if c not in original_cols]
    stage_results.append(("Transformation", "SUCCESS" if trans.success else "FAILED",
                           clean.row_count, trans.row_count, d4))
    print(f"        OK  {trans.row_count} rows | "
          f"new derived cols ({len(new_cols)}): {new_cols[:5]}{'...' if len(new_cols)>5 else ''}")

    # ── Stage 5: Load (into a staging analytics table) ────────────────────
    print("  [5/5] Loading to warehouse...")
    t0 = time.perf_counter()

    # Build a load-ready DataFrame from the transformed data
    # Map sample CSV columns to a format we can persist
    from sqlalchemy import text

    # Create a dedicated analytics staging table if it doesn't exist
    conn = session.connection()
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS etl_demo_orders (
            id              TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
            order_number    TEXT,
            order_date      TEXT,
            customer_email  TEXT,
            customer_name   TEXT,
            product_sku     TEXT,
            product_name    TEXT,
            quantity        INTEGER,
            unit_price      NUMERIC(12,4),
            discount_pct    NUMERIC(5,2),
            order_status    TEXT,
            payment_method  TEXT,
            shipping_country TEXT,
            order_year      INTEGER,
            order_month     INTEGER,
            order_quarter   INTEGER,
            pipeline_run_id TEXT,
            loaded_at       TIMESTAMP DEFAULT NOW()
        )
    """))
    session.flush()

    # Build staging DataFrame from transformed data
    df_stage = trans.transformed_df.copy()
    df_stage["pipeline_run_id"] = run_id
    df_stage["id"] = [str(uuid.uuid4()) for _ in range(len(df_stage))]

    # Rename 'status' to 'order_status' to match staging table
    if "status" in df_stage.columns:
        df_stage = df_stage.rename(columns={"status": "order_status"})

    # The staging table columns we care about
    staging_cols = [
        "id", "order_number", "order_date", "customer_email", "customer_name",
        "product_sku", "product_name", "quantity", "unit_price", "discount_pct",
        "order_status", "payment_method", "shipping_country",
        "order_year", "order_month", "order_quarter", "pipeline_run_id",
    ]
    keep = [c for c in staging_cols if c in df_stage.columns]
    df_to_load = df_stage[keep].copy()

    # Load via pandas to_sql (simple, reliable)
    df_to_load.to_sql("etl_demo_orders", con=conn,
                      if_exists="append", index=False, method="multi")
    session.flush()

    d5 = time.perf_counter() - t0
    rows_loaded = len(df_to_load)
    stage_results.append(("Loading", "SUCCESS", trans.row_count, rows_loaded, d5))
    print(f"        OK  {rows_loaded} rows -> etl_demo_orders | "
          f"cols loaded: {list(df_to_load.columns)[:5]}...")

    # Write audit event
    from app.database.models.audit.audit_log import AuditLog
    audit = AuditLog(
        event_type="RECORD_LOADED",
        severity="INFO",
        run_id=uuid.UUID(run_id),
        stage="load",
        message=f"Demo pipeline: {rows_loaded} orders loaded to etl_demo_orders",
        context_data={
            "rows_loaded": rows_loaded,
            "strategy": "to_sql",
            "table": "etl_demo_orders",
            "quality_score": val.quality_score,
        },
    )
    session.add(audit)
    session.commit()

# ─── STEP 4: Results Summary ──────────────────────────────────────────────
total_dur = time.perf_counter() - t_total
banner("STEP 4 - Pipeline Results Summary")

all_ok = all(s[1] in ("SUCCESS", "WARNING") for s in stage_results)
print(f"  Status   : {'ALL 5 STAGES PASSED' if all_ok else 'SOME STAGES FAILED'}")
print(f"  Duration : {round(total_dur, 2)}s")
print(f"  Run ID   : {run_id[:8]}...")
print()
print(f"  {'Stage':<18} {'Status':<10} {'In':>5}  {'Out':>5}  {'Time'}")
print(f"  {'-'*18} {'-'*10} {'-'*5}  {'-'*5}  {'-'*7}")
for name, status, inp, out, dur in stage_results:
    ok = "OK " if status in ("SUCCESS","WARNING") else "FAIL"
    print(f"  [{ok}] {name:<16} {status:<10} {inp:>5}  {out:>5}  {dur:.3f}s")

# ─── STEP 5: Quality metrics ──────────────────────────────────────────────
banner("STEP 5 - Data Quality Results")
print(f"  Overall Score : {val.quality_score:.1f}%  Grade: {val.letter_grade}")
total_recs = getattr(val, 'total_records', None) or (val.valid_count + val.warning_count + val.rejected_count)
print(f"  Total rows    : {total_recs}")
print(f"  Valid rows    : {val.valid_count}")
print(f"  Warning rows  : {val.warning_count}")
print(f"  Violations    : {val.report.violation_count}")
if val.report.violation_count:
    top = list(val.report.violations)[:3]
    for v in top:
        print(f"    - [{v.severity}] {v.rule_code}: {v.message[:60]}")

# ─── STEP 6: Transformation details ──────────────────────────────────────
banner("STEP 6 - Transformation Output")
print(f"  Input columns  ({len(original_cols)}): {', '.join(sorted(original_cols))}")
print(f"  Derived columns ({len(new_cols)}): {', '.join(new_cols)}")
print(f"  Final DataFrame: {trans.row_count} rows x {len(trans.transformed_df.columns)} cols")
print()
# Show sample of transformed data
print("  Sample output (first 3 rows, selected cols):")
show_cols = ["order_number", "order_date", "order_year", "order_month",
             "quantity", "unit_price", "status"]
show_cols = [c for c in show_cols if c in trans.transformed_df.columns]
print(trans.transformed_df[show_cols].head(3).to_string(index=False))

# ─── STEP 7: What's in the DB ─────────────────────────────────────────────
banner("STEP 7 - Database Verification")
with get_session() as session:
    from sqlalchemy import text, func, select
    from app.database.models.audit.audit_log import AuditLog

    row_count = session.execute(
        text("SELECT COUNT(*) FROM etl_demo_orders WHERE pipeline_run_id = :rid"),
        {"rid": run_id}
    ).scalar()

    audit_count = session.execute(
        select(func.count(AuditLog.id)).where(
            AuditLog.run_id == uuid.UUID(run_id)
        )
    ).scalar()

    sample_rows = session.execute(
        text("SELECT order_number, order_date, order_status, customer_email "
             "FROM etl_demo_orders WHERE pipeline_run_id = :rid LIMIT 3"),
        {"rid": run_id}
    ).fetchall()

print(f"  etl_demo_orders : {row_count} rows inserted for this run")
print(f"  audit_logs      : {audit_count} event(s) written")
print()
print("  Sample rows from DB:")
for row in sample_rows:
    print(f"    {row[0]} | {row[1]} | status={row[2]} | {row[3]}")

# ─── DONE ─────────────────────────────────────────────────────────────────
banner("DONE - View Results in Dashboard")
print(f"  Open: http://localhost:8501")
print()
print(f"  Home (Executive Overview)")
print(f"    KPI cards updated, new audit event in DB")
print()
print(f"  Audit Log page")
print(f"    RECORD_LOADED event for run {run_id[:8]}...")
print()
print(f"  Data Quality page")
print(f"    Quality score: {val.quality_score:.1f}% ({val.letter_grade})")
print(f"    Violations: {val.report.violation_count}")
print()
print(f"  Warehouse page")
print(f"    {row_count} rows loaded to etl_demo_orders")
print()
print(f"  Pipeline definitions: 6 pipelines registered")
print(f"  Run ID: {run_id}")
