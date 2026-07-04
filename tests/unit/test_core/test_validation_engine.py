"""
Integration-style unit tests for the ValidationEngine end-to-end pipeline.
Uses in-memory SQLite (db_session) and the existing test CSV fixtures.
"""
from pathlib import Path
from decimal import Decimal
import pandas as pd
import pytest

from app.ingestion.models import Dataset, DatasetSchema, FileMetadata
from app.validation.validator import ValidationEngine
from app.validation.models import ValidationResult, Severity
from app.validation.quality_scorer import QualityScoreCalculator
from app.validation.annotator import ValidationAnnotator
from app.validation.rule_registry import RuleRegistry


def make_dataset(df: pd.DataFrame, dataset_type: str = "orders", filename: str = "test.csv") -> Dataset:
    meta = FileMetadata(
        original_filename=filename,
        stored_filename=filename,
        file_path=Path(f"/tmp/{filename}"),
        file_extension="csv",
        file_size_bytes=1024,
        dataset_type=dataset_type,
    )
    schema = DatasetSchema(
        column_names=list(df.columns),
        column_dtypes={c: "object" for c in df.columns},
        row_count=len(df),
        column_count=len(df.columns),
    )
    return Dataset(metadata=meta, dataframe=df, schema=schema)


class TestValidationEngineEndToEnd:

    def test_valid_orders_high_score(self, db_session, test_data_dir: Path):
        df = pd.read_csv(test_data_dir / "orders_valid.csv", dtype=str)
        dataset = make_dataset(df, "orders", "orders_valid.csv")
        engine = ValidationEngine(session=db_session)
        result = engine.validate(dataset)
        assert result.success is True
        assert result.quality_score >= 50.0
        assert result.letter_grade in ("A+","A","B","C","D","F")

    def test_valid_customers_runs_clean(self, db_session, test_data_dir: Path):
        df = pd.read_csv(test_data_dir / "customers_valid.csv", dtype=str)
        dataset = make_dataset(df, "customers", "customers_valid.csv")
        engine = ValidationEngine(session=db_session)
        result = engine.validate(dataset)
        assert result.success is True

    def test_valid_products_runs_clean(self, db_session, test_data_dir: Path):
        df = pd.read_csv(test_data_dir / "products_valid.csv", dtype=str)
        dataset = make_dataset(df, "products", "products_valid.csv")
        engine = ValidationEngine(session=db_session)
        result = engine.validate(dataset)
        assert result.success is True

    def test_returns_validation_result_type(self, db_session, test_data_dir: Path):
        df = pd.read_csv(test_data_dir / "orders_valid.csv", dtype=str)
        dataset = make_dataset(df)
        engine = ValidationEngine(session=db_session)
        result = engine.validate(dataset)
        assert isinstance(result, ValidationResult)

    def test_valid_df_plus_rejected_df_equals_total(self, db_session, test_data_dir: Path):
        df = pd.read_csv(test_data_dir / "orders_valid.csv", dtype=str)
        dataset = make_dataset(df)
        engine = ValidationEngine(session=db_session)
        result = engine.validate(dataset)
        total = result.valid_count + result.rejected_count + result.warning_count
        assert total == len(df)

    def test_data_never_modified(self, db_session, test_data_dir: Path):
        df = pd.read_csv(test_data_dir / "orders_valid.csv", dtype=str)
        original_values = df.copy()
        dataset = make_dataset(df)
        engine = ValidationEngine(session=db_session)
        engine.validate(dataset)
        pd.testing.assert_frame_equal(df, original_values)

    def test_invalid_data_produces_rejections(self, db_session):
        df = pd.DataFrame({
            "order_id":    [None, "ORD-002", "ORD-003"],
            "customer_id": ["CUST-001", "CUST-002", "CUST-003"],
            "order_date":  ["2025-01-15", "2025-01-16", "2025-01-17"],
            "order_total": ["-100.00", "89.99", "1250.50"],
            "status":      ["delivered", "shipped", "invalid_status"],
            "quantity":    ["2", "1", "5"],
        })
        dataset = make_dataset(df, "orders")
        engine = ValidationEngine(session=db_session)
        result = engine.validate(dataset)
        assert result.rejected_count > 0

    def test_engine_never_raises(self, db_session):
        """Engine must always return ValidationResult, never raise."""
        df = pd.DataFrame()
        dataset = make_dataset(df)
        engine = ValidationEngine(session=db_session)
        result = engine.validate(dataset)
        assert isinstance(result, ValidationResult)

    def test_duration_recorded(self, db_session, test_data_dir: Path):
        df = pd.read_csv(test_data_dir / "orders_valid.csv", dtype=str)
        dataset = make_dataset(df)
        engine = ValidationEngine(session=db_session)
        result = engine.validate(dataset)
        assert result.duration_seconds > 0

    def test_report_has_violations_list(self, db_session, test_data_dir: Path):
        df = pd.read_csv(test_data_dir / "orders_valid.csv", dtype=str)
        dataset = make_dataset(df)
        engine = ValidationEngine(session=db_session)
        result = engine.validate(dataset)
        assert isinstance(result.report.violations, list)

    def test_quality_score_between_0_and_100(self, db_session, test_data_dir: Path):
        df = pd.read_csv(test_data_dir / "orders_valid.csv", dtype=str)
        dataset = make_dataset(df)
        engine = ValidationEngine(session=db_session)
        result = engine.validate(dataset)
        assert 0 <= result.quality_score <= 100


class TestQualityScoreCalculator:

    def test_perfect_data_high_score(self):
        df = pd.DataFrame({"a": ["1","2","3"], "b": ["x","y","z"]})
        calc = QualityScoreCalculator()
        score = calc.calculate(df, [], set(), set(), total_rules_executed=5)
        assert score.overall_score > 80

    def test_all_invalid_low_validity(self):
        df = pd.DataFrame({"a": ["1","2","3"]})
        from app.validation.models import RuleViolation
        violations = [
            RuleViolation("R","b","error","a",0,"x","y","m","f"),
            RuleViolation("R","b","error","a",1,"x","y","m","f"),
            RuleViolation("R","b","error","a",2,"x","y","m","f"),
        ]
        invalid_idx = {0, 1, 2}
        calc = QualityScoreCalculator()
        score = calc.calculate(df, violations, invalid_idx, set(), total_rules_executed=1)
        assert score.validity == 0.0

    def test_compute_overall_called(self):
        df = pd.DataFrame({"a": ["1"]})
        calc = QualityScoreCalculator()
        score = calc.calculate(df, [], set(), set())
        assert score.letter_grade in ("A+","A","B","C","D","F")


class TestValidationAnnotator:

    def test_all_valid_no_error_violations(self):
        df = pd.DataFrame({"a": [1,2,3]})
        annotator = ValidationAnnotator()
        valid_df, rejected_df, warning_df, inv_idx, warn_idx = annotator.annotate(df, [])
        assert len(valid_df) == 3
        assert len(rejected_df) == 0

    def test_one_error_row_rejected(self):
        df = pd.DataFrame({"a": [1,2,3]})
        from app.validation.models import RuleViolation
        violations = [RuleViolation("R","b","error","a",1,"x","y","msg","fix")]
        annotator = ValidationAnnotator()
        valid_df, rejected_df, _, inv_idx, _ = annotator.annotate(df, violations)
        assert 1 in inv_idx
        assert len(rejected_df) == 1

    def test_warning_row_not_rejected(self):
        df = pd.DataFrame({"a": [1,2,3]})
        from app.validation.models import RuleViolation
        violations = [RuleViolation("R","b","warning","a",0,"x","y","msg","fix")]
        annotator = ValidationAnnotator()
        valid_df, rejected_df, warning_df, inv_idx, warn_idx = annotator.annotate(df, violations)
        assert 0 not in inv_idx
        assert 0 in warn_idx

    def test_dataset_level_violation_no_row_effect(self):
        df = pd.DataFrame({"a": [1,2,3]})
        from app.validation.models import RuleViolation
        violations = [RuleViolation("R","schema","error",None,None,None,"x","Dataset empty","fix")]
        annotator = ValidationAnnotator()
        valid_df, rejected_df, _, _, _ = annotator.annotate(df, violations)
        assert len(valid_df) == 3  # row_index=None doesn't mark any rows


class TestRuleRegistry:

    def test_build_for_orders(self):
        registry = RuleRegistry.build_for_dataset("orders")
        assert registry.rule_count() > 0
        assert registry.enabled_count() > 0

    def test_build_for_customers(self):
        registry = RuleRegistry.build_for_dataset("customers")
        assert registry.rule_count() > 0

    def test_rules_ordered_by_priority(self):
        registry = RuleRegistry.build_for_dataset("orders")
        rules = registry.get_ordered_rules()
        priorities = [r.priority for r in rules]
        assert priorities == sorted(priorities)

    def test_register_custom_rule(self):
        from app.validation.rules.base_rule import BaseValidationRule
        from app.validation.models import RuleViolation

        class MyRule(BaseValidationRule):
            rule_code = "MY_001"
            rule_category = "custom"
            def validate(self, df, dataset_type):
                return []

        registry = RuleRegistry()
        registry.register(MyRule())
        assert registry.rule_count() == 1

    def test_get_by_category(self):
        registry = RuleRegistry.build_for_dataset("orders")
        schema_rules = registry.get_by_category("schema")
        assert len(schema_rules) >= 1
