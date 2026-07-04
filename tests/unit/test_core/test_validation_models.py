"""Unit tests for validation domain models."""
import pytest
import pandas as pd
from app.validation.models import (
    RuleViolation, ColumnProfile, QualityScore, ValidationReport,
    ValidationResult, Severity
)


class TestQualityScore:
    def test_letter_grades(self):
        cases = [(99, "A+"), (93, "A"), (85, "B"), (73, "C"), (62, "D"), (40, "F")]
        for score, expected in cases:
            qs = QualityScore()
            qs.overall_score = score
            assert QualityScore._to_letter_grade(score) == expected

    def test_compute_overall_uses_weights(self):
        qs = QualityScore(
            completeness=100, validity=100, consistency=100,
            uniqueness=100, integrity=100, timeliness=100
        )
        qs.compute_overall()
        assert qs.overall_score == 100.0
        assert qs.letter_grade == "A+"

    def test_compute_overall_partial(self):
        qs = QualityScore(
            completeness=80, validity=80, consistency=80,
            uniqueness=80, integrity=80, timeliness=80
        )
        qs.compute_overall()
        assert qs.overall_score == 80.0
        assert qs.letter_grade == "B"

    def test_to_dict_keys(self):
        qs = QualityScore()
        qs.compute_overall()
        d = qs.to_dict()
        for key in ("overall_score", "letter_grade", "completeness", "validity",
                    "total_records", "valid_records"):
            assert key in d

    def test_zero_score_is_f(self):
        qs = QualityScore()
        qs.compute_overall()
        assert qs.letter_grade == "F"


class TestRuleViolation:
    def test_to_dict_contains_required_fields(self):
        v = RuleViolation(
            rule_code="ORD_001", rule_category="business", severity="error",
            field_name="order_id", row_index=5, actual_value=None,
            expected="Not null", message="order_id is null", suggested_fix="Provide a value",
        )
        d = v.to_dict()
        assert d["rule_code"] == "ORD_001"
        assert d["field_name"] == "order_id"
        assert d["row_index"] == 5
        assert d["severity"] == "error"

    def test_actual_value_none_serializes(self):
        v = RuleViolation(
            rule_code="T", rule_category="schema", severity="error",
            field_name=None, row_index=None, actual_value=None,
            expected="x", message="msg", suggested_fix="fix",
        )
        d = v.to_dict()
        assert d["actual_value"] is None

    def test_actual_value_string_serialized(self):
        v = RuleViolation(
            rule_code="T", rule_category="schema", severity="error",
            field_name="col", row_index=0, actual_value="bad value",
            expected="Good value", message="msg", suggested_fix="fix",
        )
        d = v.to_dict()
        assert d["actual_value"] == "bad value"


class TestValidationReport:
    def _make_report(self):
        from app.validation.models import QualityScore
        qs = QualityScore(completeness=90, validity=85, consistency=88,
                          uniqueness=95, integrity=100, timeliness=100)
        qs.compute_overall()
        return ValidationReport(
            dataset_type="orders",
            original_filename="orders.csv",
            quality_score=qs,
        )

    def test_error_violations_filtered(self):
        report = self._make_report()
        report.violations = [
            RuleViolation("R1","b","error",None,None,None,"x","m","f"),
            RuleViolation("R2","b","warning",None,None,None,"x","m","f"),
        ]
        assert len(report.error_violations) == 1
        assert len(report.warning_violations) == 1

    def test_has_errors_true(self):
        report = self._make_report()
        report.violations = [RuleViolation("R1","b","error",None,None,None,"x","m","f")]
        assert report.has_errors is True

    def test_has_errors_false(self):
        report = self._make_report()
        assert report.has_errors is False

    def test_to_summary_dict(self):
        report = self._make_report()
        d = report.to_summary_dict()
        assert d["dataset_type"] == "orders"
        assert "quality_score" in d
        assert "total_violations" in d

    def test_violation_count(self):
        report = self._make_report()
        report.violations = [
            RuleViolation("R1","b","error",None,None,None,"x","m","f"),
            RuleViolation("R2","b","warning",None,None,None,"x","m","f"),
        ]
        assert report.violation_count == 2


class TestValidationResult:
    def test_success_result_properties(self):
        df_valid = pd.DataFrame({"a": [1, 2, 3]})
        df_rejected = pd.DataFrame({"a": [4]})
        result = ValidationResult(
            success=True, dataset_type="orders",
            valid_df=df_valid, rejected_df=df_rejected,
            quality_score=90.0, letter_grade="A",
        )
        assert result.valid_count == 3
        assert result.rejected_count == 1
        assert "90.0" in repr(result)

    def test_failure_result(self):
        result = ValidationResult(
            success=False, dataset_type="orders",
            error_code="VALIDATION_UNEXPECTED_ERROR",
            error_message="Something went wrong",
        )
        assert result.valid_count == 0
        assert result.success is False
