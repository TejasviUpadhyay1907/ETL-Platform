"""Debug the warehouse loading failure."""
import sys, os, traceback
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pathlib import Path
import pandas as pd

from app.logging.logger import setup_logging
setup_logging()

from app.database.engine import get_session
from app.ingestion.readers.csv_reader import CSVReader
from app.loading.loader import WarehouseLoader
from app.loading.load_registry import LoadRegistry
from app.loading.models import LoadStrategyType

sample = Path("data/sample/orders_valid.csv")
reader = CSVReader()
df, schema = reader.read(sample)
print(f"Raw CSV: {len(df)} rows, {len(df.columns)} cols")
print(f"Columns: {list(df.columns)}")

with get_session() as session:
    # Test column filtering directly
    from app.loading.strategies.upsert_strategy import UpsertStrategy
    from app.loading.models import LoadStrategy

    cfg      = LoadStrategy(strategy_type=LoadStrategyType.UPSERT, batch_size=100)
    strategy = UpsertStrategy(session, cfg)

    # What does _filter_to_table_columns return for orders?
    filtered = strategy._filter_to_table_columns(df, "orders")
    print(f"\nAfter column filter: {len(filtered.columns)} cols")
    print(f"Kept:    {list(filtered.columns)[:10]}")

    # Now try loading
    print("\nAttempting load...")
    try:
        loader = WarehouseLoader(session=session, check_idempotency=False)
        result = loader.load(filtered, "orders", None)
        print(f"Load result: success={result.success}")
        print(f"  rows_inserted={result.rows_inserted}")
        print(f"  rows_failed={result.rows_failed}")
        print(f"  error={result.error_message}")
    except Exception as e:
        print(f"Exception: {e}")
        traceback.print_exc()

    session.rollback()
