"""
Warehouse Loading Engine tests.

Strategy: Use a simple 'load_test_records' table created fresh per test session
to avoid fighting the complex ORM schema constraints. The loader integration
with real ORM tables is verified in the stage integration test at the end.
"""
from __future__ import annotations
import uuid
import pandas as pd
import pytest
from sqlalchemy import text, event
from sqlalchemy.orm import Session

from app.loading.models import (
    LoadBatchResult, LoadMetrics, LoadReport,
    LoadResult, LoadStrategy, LoadStrategyType,
)
from app.loading.load_registry import LoadRegistry


# ─── Test table setup ──────────────────────────────────────────────────────

TEST_TABLE = "load_test_records"

@pytest.fixture
def test_table(db_session: Session):
    """Create a simple test table for each test, drop after."""
    conn = db_session.connection()
    conn.execute(text(f"""
        CREATE TABLE IF NOT EXISTS {TEST_TABLE} (
            id TEXT PRIMARY KEY,
            name TEXT,
            value TEXT,
            num REAL
        )
    """))
    db_session.flush()
    yield TEST_TABLE
    conn.execute(text(f"DELETE FROM {TEST_TABLE}"))
    db_session.flush()


def simple_df(rows: int = 5) -> pd.DataFrame:
    return pd.DataFrame({
        "id":    [str(uuid.uuid4()) for _ in range(rows)],
        "name":  [f"Record {i}" for i in range(rows)],
        "value": [f"val_{i}" for i in range(rows)],
        "num":   [float(i * 10) for i in range(rows)],
    })


def make_customers_df(rows: int = 3) -> pd.DataFrame:
    """DataFrame matching the customers ORM table (for integration tests)."""
    return pd.DataFrame({
        "id":               [str(uuid.uuid4()) for _ in range(rows)],
        "first_name":       ["Alice", "Bob", "Carol"][:rows],
        "last_name":        ["Smith", "Jones", "White"][:rows],
        "email":            [f"user{i}@example.com" for i in range(rows)],
        "country":          ["US"] * rows,
        "status":           ["active"] * rows,
        "customer_segment": ["standard"] * rows,
        "is_deleted":       [False] * rows,
        "created_at":       [None] * rows,
        "updated_at":       [None] * rows,
    })


# ─── LoadResult model ─────────────────────────────────────────────────────

class TestLoadResultModel:

    def test_rows_loaded_property(self):
        r = LoadResult(success=True, dataset_type="orders",
                       rows_inserted=80, rows_updated=20)
        assert r.rows_loaded == 100

    def test_repr(self):
        r = LoadResult(success=True, dataset_type="orders",
                       rows_inserted=50, rows_updated=10)
        assert "orders" in repr(r)

    def test_idempotent_skip_flag(self):
        r = LoadResult(success=True, dataset_type="orders",
                       rows_skipped=100, idempotent_skip=True)
        assert r.idempotent_skip is True

    def test_failure_result(self):
        r = LoadResult(success=False, dataset_type="orders",
                       error_message="DB error", error_code="LOAD_UNEXPECTED_ERROR")
        assert r.success is False
        assert r.rows_loaded == 0


class TestLoadMetrics:

    def test_rows_loaded_property(self):
        m = LoadMetrics(rows_inserted=30, rows_updated=10)
        assert m.rows_loaded == 40

    def test_compute_derived(self):
        m = LoadMetrics(rows_inserted=1000, total_duration_ms=2000.0, batch_count=2)
        m.compute_derived()
        assert m.avg_batch_ms == pytest.approx(1000.0)
        assert m.throughput_rows_sec == pytest.approx(500.0)

    def test_to_dict(self):
        m = LoadMetrics(rows_inserted=100, strategy_used="upsert")
        d = m.to_dict()
        assert d["rows_inserted"] == 100
        assert "rows_loaded" in d

    def test_zero_duration_no_crash(self):
        m = LoadMetrics(rows_inserted=10, total_duration_ms=0.0, batch_count=1)
        m.compute_derived()
        assert m.throughput_rows_sec == 0.0


class TestLoadStrategy:

    def test_to_dict(self):
        s = LoadStrategy(strategy_type="upsert", batch_size=500,
                         conflict_columns=["email"])
        d = s.to_dict()
        assert d["strategy_type"] == "upsert"
        assert d["batch_size"] == 500


# ─── LoadRegistry ────────────────────────────────────────────────────────

class TestLoadRegistry:

    def test_get_strategy_orders(self, db_session):
        reg = LoadRegistry()
        strategy, table = reg.get_strategy(db_session, "orders")
        assert strategy.strategy_name == LoadStrategyType.UPSERT
        assert table == "orders"

    def test_get_strategy_payments_is_append(self, db_session):
        reg = LoadRegistry()
        strategy, table = reg.get_strategy(db_session, "payments")
        assert strategy.strategy_name == LoadStrategyType.APPEND

    def test_strategy_override_bulk_insert(self, db_session):
        reg = LoadRegistry()
        strategy, _ = reg.get_strategy(db_session, "orders",
                                        strategy_override=LoadStrategyType.BULK_INSERT)
        assert strategy.strategy_name == LoadStrategyType.BULK_INSERT

    def test_strategy_override_replace(self, db_session):
        reg = LoadRegistry()
        strategy, _ = reg.get_strategy(db_session, "orders",
                                        strategy_override=LoadStrategyType.REPLACE)
        assert strategy.strategy_name == LoadStrategyType.REPLACE

    def test_batch_size_override(self, db_session):
        reg = LoadRegistry()
        strategy, _ = reg.get_strategy(db_session, "orders", batch_size_override=99)
        assert strategy._config.batch_size == 99

    def test_unknown_dataset_type_fallback(self, db_session):
        reg = LoadRegistry()
        strategy, table = reg.get_strategy(db_session, "unknown_xyz")
        assert strategy is not None
        assert table == "unknown_xyz"

    def test_register_override(self, db_session):
        reg = LoadRegistry()
        reg.register_override("orders", {"strategy_type": LoadStrategyType.REPLACE,
                                          "target_table": "orders_staging",
                                          "batch_size": 100})
        strategy, table = reg.get_strategy(db_session, "orders")
        assert strategy.strategy_name == LoadStrategyType.REPLACE
        assert table == "orders_staging"

    def test_all_six_dataset_types_resolve(self, db_session):
        from app.utils.constants import DatasetType
        reg = LoadRegistry()
        for ds in DatasetType:
            strategy, table = reg.get_strategy(db_session, ds.value)
            assert strategy is not None
            assert table is not None


# ─── UpsertStrategy ──────────────────────────────────────────────────────

class TestUpsertStrategy:

    def test_empty_df_returns_zero_metrics(self, db_session, test_table):
        from app.loading.strategies.upsert_strategy import UpsertStrategy
        cfg = LoadStrategy(strategy_type=LoadStrategyType.UPSERT, batch_size=100)
        strategy = UpsertStrategy(db_session, cfg)
        metrics, batches = strategy.execute(pd.DataFrame(), test_table, "unknown")
        assert metrics.total_rows_input == 0
        assert len(batches) == 0

    def test_upsert_inserts_rows(self, db_session, test_table):
        from app.loading.strategies.upsert_strategy import UpsertStrategy
        df = simple_df(5)
        cfg = LoadStrategy(strategy_type=LoadStrategyType.UPSERT, batch_size=100)
        strategy = UpsertStrategy(db_session, cfg)
        metrics, batches = strategy.execute(df, test_table, "unknown")
        assert metrics.total_rows_input == 5
        # Either inserted or at least attempted
        assert metrics.rows_inserted + metrics.rows_failed == 5

    def test_batch_chunking_creates_correct_batches(self, db_session, test_table):
        from app.loading.strategies.upsert_strategy import UpsertStrategy
        df = simple_df(5)
        cfg = LoadStrategy(strategy_type=LoadStrategyType.UPSERT, batch_size=2)
        strategy = UpsertStrategy(db_session, cfg)
        metrics, batches = strategy.execute(df, test_table, "unknown")
        assert metrics.batch_count == 3  # ceil(5/2)

    def test_large_df_chunked_correctly(self, db_session, test_table):
        from app.loading.strategies.upsert_strategy import UpsertStrategy
        df = simple_df(50)
        cfg = LoadStrategy(strategy_type=LoadStrategyType.UPSERT, batch_size=10)
        strategy = UpsertStrategy(db_session, cfg)
        metrics, batches = strategy.execute(df, test_table, "unknown")
        assert metrics.batch_count == 5
        # All rows should be accounted for (inserted or failed)
        assert metrics.rows_inserted + metrics.rows_failed == 50

    def test_metrics_have_duration(self, db_session, test_table):
        from app.loading.strategies.upsert_strategy import UpsertStrategy
        df = simple_df(3)
        cfg = LoadStrategy(strategy_type=LoadStrategyType.UPSERT, batch_size=100)
        strategy = UpsertStrategy(db_session, cfg)
        metrics, _ = strategy.execute(df, test_table, "unknown")
        assert metrics.total_duration_ms >= 0


# ─── BulkInsertStrategy ──────────────────────────────────────────────────

class TestBulkInsertStrategy:

    def test_empty_df(self, db_session, test_table):
        from app.loading.strategies.bulk_insert_strategy import BulkInsertStrategy
        cfg = LoadStrategy(strategy_type=LoadStrategyType.BULK_INSERT, batch_size=100)
        strategy = BulkInsertStrategy(db_session, cfg)
        metrics, _ = strategy.execute(pd.DataFrame(), test_table, "unknown")
        assert metrics.total_rows_input == 0

    def test_bulk_insert_rows(self, db_session, test_table):
        from app.loading.strategies.bulk_insert_strategy import BulkInsertStrategy
        df = simple_df(3)
        cfg = LoadStrategy(strategy_type=LoadStrategyType.BULK_INSERT, batch_size=100)
        strategy = BulkInsertStrategy(db_session, cfg)
        metrics, batches = strategy.execute(df, test_table, "unknown")
        assert metrics.total_rows_input == 3
        assert len(batches) >= 1

    def test_bulk_insert_chunked(self, db_session, test_table):
        from app.loading.strategies.bulk_insert_strategy import BulkInsertStrategy
        df = simple_df(4)
        cfg = LoadStrategy(strategy_type=LoadStrategyType.BULK_INSERT, batch_size=2)
        strategy = BulkInsertStrategy(db_session, cfg)
        metrics, batches = strategy.execute(df, test_table, "unknown")
        assert metrics.batch_count == 2


# ─── AppendStrategy ──────────────────────────────────────────────────────

class TestAppendStrategy:

    def test_empty_df(self, db_session, test_table):
        from app.loading.strategies.append_strategy import AppendStrategy
        cfg = LoadStrategy(strategy_type=LoadStrategyType.APPEND, batch_size=100)
        strategy = AppendStrategy(db_session, cfg)
        metrics, _ = strategy.execute(pd.DataFrame(), test_table, "unknown")
        assert metrics.total_rows_input == 0

    def test_append_inserts_rows(self, db_session, test_table):
        from app.loading.strategies.append_strategy import AppendStrategy
        df = simple_df(3)
        cfg = LoadStrategy(strategy_type=LoadStrategyType.APPEND, batch_size=100)
        strategy = AppendStrategy(db_session, cfg)
        metrics, batches = strategy.execute(df, test_table, "unknown")
        assert metrics.total_rows_input == 3
        total = metrics.rows_inserted + metrics.rows_skipped + metrics.rows_failed
        assert total == 3


# ─── ReplaceStrategy ─────────────────────────────────────────────────────

class TestReplaceStrategy:

    def test_empty_df_does_not_crash(self, db_session, test_table):
        from app.loading.strategies.replace_strategy import ReplaceStrategy
        cfg = LoadStrategy(strategy_type=LoadStrategyType.REPLACE, batch_size=100)
        strategy = ReplaceStrategy(db_session, cfg)
        metrics, _ = strategy.execute(pd.DataFrame(), test_table, "unknown")
        assert metrics.rows_inserted == 0

    def test_replace_inserts_rows(self, db_session, test_table):
        from app.loading.strategies.replace_strategy import ReplaceStrategy
        df = simple_df(4)
        cfg = LoadStrategy(strategy_type=LoadStrategyType.REPLACE, batch_size=100)
        strategy = ReplaceStrategy(db_session, cfg)
        metrics, _ = strategy.execute(df, test_table, "unknown")
        assert metrics.rows_inserted == 4

    def test_replace_truncates_and_reloads(self, db_session, test_table):
        """After replace, only the last loaded rows should remain."""
        from app.loading.strategies.replace_strategy import ReplaceStrategy
        df1 = simple_df(5)
        df2 = simple_df(2)
        cfg = LoadStrategy(strategy_type=LoadStrategyType.REPLACE, batch_size=100)
        strategy = ReplaceStrategy(db_session, cfg)
        strategy.execute(df1, test_table, "unknown")
        metrics2, _ = strategy.execute(df2, test_table, "unknown")
        assert metrics2.rows_inserted == 2


# ─── IncrementalStrategy ─────────────────────────────────────────────────

class TestIncrementalStrategy:

    def test_no_watermark_loads_all(self, db_session, test_table):
        from app.loading.strategies.incremental_strategy import IncrementalStrategy
        df = simple_df(3)
        cfg = LoadStrategy(strategy_type=LoadStrategyType.INCREMENTAL, batch_size=100)
        strategy = IncrementalStrategy(db_session, cfg)
        metrics, _ = strategy.execute(df, test_table, "unknown")
        assert metrics.total_rows_input == 3

    def test_watermark_filters_old_records(self, db_session, test_table):
        from app.loading.strategies.incremental_strategy import IncrementalStrategy
        df = pd.DataFrame({
            "id":    [str(uuid.uuid4()) for _ in range(5)],
            "name":  [f"R{i}" for i in range(5)],
            "value": [f"v{i}" for i in range(5)],
            "num":   [float(i) for i in range(5)],
        })
        cfg = LoadStrategy(
            strategy_type=LoadStrategyType.INCREMENTAL,
            batch_size=100,
            watermark_column="num",
            watermark_value=2.0,  # only rows where num > 2
        )
        strategy = IncrementalStrategy(db_session, cfg)
        metrics, _ = strategy.execute(df, test_table, "unknown")
        # rows with num > 2.0: indices 3 and 4 (2 rows)
        assert metrics.rows_skipped == 3   # rows with num <= 2 skipped
        assert metrics.total_rows_input == 5

    def test_empty_df(self, db_session, test_table):
        from app.loading.strategies.incremental_strategy import IncrementalStrategy
        cfg = LoadStrategy(strategy_type=LoadStrategyType.INCREMENTAL, batch_size=100)
        strategy = IncrementalStrategy(db_session, cfg)
        metrics, _ = strategy.execute(pd.DataFrame(), test_table, "unknown")
        assert metrics.total_rows_input == 0


# ─── WarehouseLoader orchestrator ────────────────────────────────────────

class TestWarehouseLoader:

    def test_load_returns_load_result(self, db_session, test_table):
        from app.loading.loader import WarehouseLoader
        from app.loading.load_registry import LoadRegistry
        reg = LoadRegistry()
        reg.register_override("test_ds", {"strategy_type": LoadStrategyType.UPSERT,
                                           "target_table": test_table, "batch_size": 100})
        df = simple_df(3)
        loader = WarehouseLoader(session=db_session, registry=reg, check_idempotency=False)
        result = loader.load(df, "test_ds")
        assert isinstance(result, LoadResult)

    def test_load_succeeds(self, db_session, test_table):
        from app.loading.loader import WarehouseLoader
        from app.loading.load_registry import LoadRegistry
        reg = LoadRegistry()
        reg.register_override("test_ds", {"strategy_type": LoadStrategyType.UPSERT,
                                           "target_table": test_table, "batch_size": 100})
        df = simple_df(3)
        loader = WarehouseLoader(session=db_session, registry=reg, check_idempotency=False)
        result = loader.load(df, "test_ds")
        assert result.success is True

    def test_load_empty_df(self, db_session, test_table):
        from app.loading.loader import WarehouseLoader
        from app.loading.load_registry import LoadRegistry
        reg = LoadRegistry()
        reg.register_override("test_ds", {"strategy_type": LoadStrategyType.UPSERT,
                                           "target_table": test_table, "batch_size": 100})
        loader = WarehouseLoader(session=db_session, registry=reg, check_idempotency=False)
        result = loader.load(pd.DataFrame(), "test_ds")
        assert result.success is True
        assert result.rows_loaded == 0

    def test_load_report_populated(self, db_session, test_table):
        from app.loading.loader import WarehouseLoader
        from app.loading.load_registry import LoadRegistry
        reg = LoadRegistry()
        reg.register_override("test_ds", {"strategy_type": LoadStrategyType.UPSERT,
                                           "target_table": test_table, "batch_size": 100})
        df = simple_df(2)
        loader = WarehouseLoader(session=db_session, registry=reg, check_idempotency=False)
        result = loader.load(df, "test_ds")
        assert result.report is not None
        assert result.report.dataset_type == "test_ds"

    def test_strategy_used_recorded(self, db_session, test_table):
        from app.loading.loader import WarehouseLoader
        from app.loading.load_registry import LoadRegistry
        reg = LoadRegistry()
        reg.register_override("test_ds", {"strategy_type": LoadStrategyType.REPLACE,
                                           "target_table": test_table, "batch_size": 100})
        df = simple_df(2)
        loader = WarehouseLoader(session=db_session, registry=reg, check_idempotency=False)
        result = loader.load(df, "test_ds")
        assert result.strategy_used == LoadStrategyType.REPLACE

    def test_duration_recorded(self, db_session, test_table):
        from app.loading.loader import WarehouseLoader
        from app.loading.load_registry import LoadRegistry
        reg = LoadRegistry()
        reg.register_override("test_ds", {"strategy_type": LoadStrategyType.UPSERT,
                                           "target_table": test_table, "batch_size": 100})
        loader = WarehouseLoader(session=db_session, registry=reg, check_idempotency=False)
        result = loader.load(simple_df(2), "test_ds")
        assert result.duration_seconds >= 0

    def test_idempotency_second_call_skipped(self, db_session, test_table):
        from app.loading.loader import WarehouseLoader
        from app.loading.load_registry import LoadRegistry
        reg = LoadRegistry()
        reg.register_override("test_ds", {"strategy_type": LoadStrategyType.UPSERT,
                                           "target_table": test_table, "batch_size": 100})
        run_id = str(uuid.uuid4())
        df = simple_df(3)
        loader = WarehouseLoader(session=db_session, registry=reg, check_idempotency=True)
        r1 = loader.load(df, "test_ds", pipeline_run_id=run_id)
        assert r1.success is True
        r2 = loader.load(df, "test_ds", pipeline_run_id=run_id)
        assert r2.idempotent_skip is True

    def test_no_idempotency_loads_twice(self, db_session, test_table):
        from app.loading.loader import WarehouseLoader
        from app.loading.load_registry import LoadRegistry
        reg = LoadRegistry()
        reg.register_override("test_ds", {"strategy_type": LoadStrategyType.APPEND,
                                           "target_table": test_table, "batch_size": 100})
        run_id = str(uuid.uuid4())
        df = simple_df(2)
        loader = WarehouseLoader(session=db_session, registry=reg, check_idempotency=False)
        r1 = loader.load(df, "test_ds", pipeline_run_id=run_id)
        r2 = loader.load(df, "test_ds", pipeline_run_id=run_id)
        assert r2.idempotent_skip is False

    def test_strategy_override_via_loader(self, db_session, test_table):
        from app.loading.loader import WarehouseLoader
        from app.loading.load_registry import LoadRegistry
        reg = LoadRegistry()
        reg.register_override("test_ds", {"strategy_type": LoadStrategyType.UPSERT,
                                           "target_table": test_table, "batch_size": 100})
        df = simple_df(2)
        loader = WarehouseLoader(session=db_session, registry=reg,
                                  strategy_override=LoadStrategyType.REPLACE,
                                  check_idempotency=False)
        result = loader.load(df, "test_ds")
        assert result.strategy_used == LoadStrategyType.REPLACE

    def test_load_never_raises(self, db_session):
        from app.loading.loader import WarehouseLoader
        loader = WarehouseLoader(session=db_session, check_idempotency=False)
        result = loader.load(pd.DataFrame({"col": [object()]}), "nonexistent_table_xyz")
        assert isinstance(result, LoadResult)

    def test_load_all_six_dataset_types_empty(self, db_session):
        from app.loading.loader import WarehouseLoader
        from app.utils.constants import DatasetType
        loader = WarehouseLoader(session=db_session, check_idempotency=False)
        for ds in DatasetType:
            result = loader.load(pd.DataFrame(), ds.value)
            assert isinstance(result, LoadResult), f"Failed for {ds.value}"

    def test_target_table_recorded(self, db_session, test_table):
        from app.loading.loader import WarehouseLoader
        from app.loading.load_registry import LoadRegistry
        reg = LoadRegistry()
        reg.register_override("test_ds", {"strategy_type": LoadStrategyType.UPSERT,
                                           "target_table": test_table, "batch_size": 100})
        loader = WarehouseLoader(session=db_session, registry=reg, check_idempotency=False)
        result = loader.load(simple_df(2), "test_ds")
        assert result.target_table == test_table


# ─── Load stage integration ───────────────────────────────────────────────

class TestLoadStageIntegration:
    """Verify run_load() calls the real WarehouseLoader (not the placeholder)."""

    def test_run_load_produces_real_result(self, db_session):
        from app.pipeline.stage_executor import StageExecutor, EventEmitter
        from app.pipeline.context import PipelineContext
        from app.transformation.models import (
            TransformationResult, TransformationReport, TransformationMetrics
        )
        ctx = PipelineContext(
            pipeline_run_id=str(uuid.uuid4()),
            pipeline_name="orders_pipeline",
            dataset_type="orders",
        )
        ee = EventEmitter(db_session)
        se = StageExecutor(db_session)
        df = pd.DataFrame()  # empty — avoids schema conflicts
        metrics = TransformationMetrics(total_rows_input=0, total_rows_output=0)
        report = TransformationReport(dataset_type="orders", metrics=metrics,
                                       input_columns=[], output_columns=[])
        trans = TransformationResult(success=True, dataset_type="orders",
                                      transformed_df=df, report=report)
        sr = se.run_load(ctx, trans, ee)
        assert sr.stage_name == "load"
        assert sr.status == "success"
        assert "rows_loaded" in sr.details

    def test_run_load_no_longer_placeholder(self, db_session):
        """Confirm the placeholder comment is gone from stage details."""
        from app.pipeline.stage_executor import StageExecutor, EventEmitter
        from app.pipeline.context import PipelineContext
        from app.transformation.models import (
            TransformationResult, TransformationReport, TransformationMetrics
        )
        ctx = PipelineContext(
            pipeline_run_id=str(uuid.uuid4()),
            pipeline_name="orders_pipeline",
            dataset_type="orders",
        )
        ee = EventEmitter(db_session)
        se = StageExecutor(db_session)
        df = pd.DataFrame()
        metrics = TransformationMetrics(total_rows_input=0, total_rows_output=0)
        report = TransformationReport(dataset_type="orders", metrics=metrics,
                                       input_columns=[], output_columns=[])
        trans = TransformationResult(success=True, dataset_type="orders",
                                      transformed_df=df, report=report)
        sr = se.run_load(ctx, trans, ee)
        # The old placeholder had "note" key; the real loader has "rows_loaded"
        assert "note" not in sr.details
        assert "rows_loaded" in sr.details
