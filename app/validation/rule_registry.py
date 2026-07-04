"""
RuleRegistry — loads, stores, and provides ordered validation rules.

The registry is the single source of truth for which rules run on a dataset.
Rules are constructed from:
  1. YAML config (config/datasets/{type}/rules.yaml)
  2. YAML schema (config/datasets/{type}/schema.yaml)
  3. Programmatic registration for cross-dataset/referential rules

Design: rules are grouped by category and sorted by priority so the executor
always runs schema checks before business rules, and business rules before
statistical profiling.
"""

from __future__ import annotations

from typing import Any

from app.logging.logger import get_logger
from app.utils.constants import DatasetType
from app.validation.rules.base_rule import BaseValidationRule

logger = get_logger(__name__)


class RuleRegistry:
    """
    Holds all validation rules for a single dataset validation run.

    Instantiate fresh per validation call — rules carry dataset-specific config.
    """

    def __init__(self) -> None:
        self._rules: list[BaseValidationRule] = []

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def register(self, rule: BaseValidationRule) -> None:
        """Add a rule to the registry."""
        self._rules.append(rule)

    def get_ordered_rules(self) -> list[BaseValidationRule]:
        """Return enabled rules sorted by priority (ascending)."""
        return sorted(
            [r for r in self._rules if r.enabled],
            key=lambda r: r.priority,
        )

    def get_by_category(self, category: str) -> list[BaseValidationRule]:
        """Return all enabled rules of a specific category."""
        return [r for r in self._rules if r.rule_category == category and r.enabled]

    def rule_count(self) -> int:
        return len(self._rules)

    def enabled_count(self) -> int:
        return sum(1 for r in self._rules if r.enabled)

    @classmethod
    def build_for_dataset(
        cls,
        dataset_type: str,
        references: dict[str, set[str]] | None = None,
    ) -> "RuleRegistry":
        """
        Factory method: construct a complete rule set for a dataset type.

        Loads all rules from YAML config and constructs validator instances.

        Args:
            dataset_type:  One of the DatasetType values.
            references:    {fk_column: reference_value_set} for referential checks.

        Returns:
            Populated RuleRegistry ready for execution.
        """
        registry = cls()

        from app.core.config_loader import load_dataset_config
        schema_cfg = load_dataset_config(dataset_type, "schema")
        rules_cfg  = load_dataset_config(dataset_type, "rules")

        # ── 1. Schema validator ─────────────────────────────────────────
        expected_cols = [
            c["name"] for c in schema_cfg.get("columns", [])
            if isinstance(c, dict) and "name" in c
        ]
        required_cols = [
            c["name"] for c in schema_cfg.get("columns", [])
            if isinstance(c, dict) and c.get("required", False)
        ]
        dedup_keys = schema_cfg.get("deduplication_key", [])

        from app.validation.rules.schema_validator import SchemaValidator
        registry.register(SchemaValidator(
            expected_columns=expected_cols,
            required_columns=required_cols,
            allow_extra_columns=True,
        ))

        # ── 2. Missing value validator ──────────────────────────────────
        from app.validation.rules.missing_value_validator import MissingValueValidator
        registry.register(MissingValueValidator(
            required_fields=required_cols,
            null_threshold_pct=50.0,
        ))

        # ── 3. Data type validator ──────────────────────────────────────
        field_types = {
            c["name"]: c["type"]
            for c in schema_cfg.get("columns", [])
            if isinstance(c, dict) and "name" in c and "type" in c
        }
        if field_types:
            from app.validation.rules.data_type_validator import DataTypeValidator
            registry.register(DataTypeValidator(field_types=field_types))

        # ── 4. Duplicate validator ──────────────────────────────────────
        from app.validation.rules.duplicate_validator import DuplicateValidator
        registry.register(DuplicateValidator(
            key_fields=dedup_keys if isinstance(dedup_keys, list) else [dedup_keys],
            check_full_row_duplicates=True,
        ))

        # ── 5. Business rule validator ──────────────────────────────────
        business_rules = rules_cfg.get("rules", [])
        if business_rules:
            from app.validation.rules.business_rule_validator import BusinessRuleValidator
            registry.register(BusinessRuleValidator(rules=business_rules))

        # ── 6. Format validator ─────────────────────────────────────────
        email_fields = [
            c["name"] for c in schema_cfg.get("columns", [])
            if isinstance(c, dict) and c.get("type") == "string"
            and "email" in c.get("name", "").lower()
        ]
        phone_fields = [
            c["name"] for c in schema_cfg.get("columns", [])
            if isinstance(c, dict)
            and "phone" in c.get("name", "").lower()
        ]
        string_fields = [
            c["name"] for c in schema_cfg.get("columns", [])
            if isinstance(c, dict) and c.get("type") in ("string",)
        ]
        from app.validation.rules.format_validator import FormatValidator
        registry.register(FormatValidator(
            check_whitespace_fields=string_fields,
            email_fields=email_fields,
            phone_fields=phone_fields,
        ))

        # ── 7. Categorical validator ────────────────────────────────────
        cat_fields = cls._extract_categorical_fields(dataset_type, rules_cfg)
        if cat_fields:
            from app.validation.rules.categorical_validator import CategoricalValidator
            registry.register(CategoricalValidator(categorical_fields=cat_fields))

        # ── 8. Statistical validator ────────────────────────────────────
        from app.validation.rules.statistical_validator import StatisticalValidator
        registry.register(StatisticalValidator())

        # ── 9. Referential integrity ────────────────────────────────────
        if references:
            from app.validation.rules.referential_integrity_validator import (
                ReferentialIntegrityValidator,
            )
            registry.register(ReferentialIntegrityValidator(references=references))

        logger.debug(
            "RuleRegistry built",
            dataset_type=dataset_type,
            total_rules=registry.rule_count(),
            enabled_rules=registry.enabled_count(),
        )
        return registry

    @staticmethod
    def _extract_categorical_fields(
        dataset_type: str,
        rules_cfg: dict[str, Any],
    ) -> dict[str, list[str]]:
        """Extract in_list rules and build a categorical field map."""
        cat_fields: dict[str, list[str]] = {}
        for rule in rules_cfg.get("rules", []):
            if rule.get("check") == "in_list" and "field" in rule and "values" in rule:
                cat_fields[rule["field"]] = rule["values"]
        return cat_fields

