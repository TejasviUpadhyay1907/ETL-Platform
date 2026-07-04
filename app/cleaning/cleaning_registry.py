"""
CleaningRegistry — assembles the ordered cleaner pipeline for a dataset type.

Loads all strategy configuration from config/datasets/{type}/cleaning.yaml
and constructs the appropriate cleaner instances in priority order.

Design: adding a new cleaner requires only registering it here — zero engine changes.
"""

from __future__ import annotations

from typing import Any

from app.cleaning.base_cleaner import BaseCleaningRule
from app.logging.logger import get_logger

logger = get_logger(__name__)


class CleaningRegistry:
    """Holds all cleaners for one cleaning run, ordered by priority."""

    def __init__(self) -> None:
        self._cleaners: list[BaseCleaningRule] = []

    def register(self, cleaner: BaseCleaningRule) -> None:
        self._cleaners.append(cleaner)

    def get_ordered(self) -> list[BaseCleaningRule]:
        return sorted(
            [c for c in self._cleaners if c.enabled],
            key=lambda c: c.priority,
        )

    def count(self) -> int:
        return len(self._cleaners)

    @classmethod
    def build_for_dataset(cls, dataset_type: str) -> "CleaningRegistry":
        """
        Factory: construct a full cleaner pipeline for a dataset type.

        Reads config/datasets/{type}/cleaning.yaml and builds cleaners.
        """
        registry = cls()
        from app.core.config_loader import load_dataset_config
        from app.core.config import get_config

        cleaning_cfg = load_dataset_config(dataset_type, "cleaning")
        schema_cfg   = load_dataset_config(dataset_type, "schema")
        rules_cfg    = load_dataset_config(dataset_type, "rules")

        field_strategies: dict[str, dict[str, Any]] = cleaning_cfg.get("field_strategies", {})
        dedup_key = schema_cfg.get("deduplication_key", [])

        # ── 1. Null Handler (priority 10) ───────────────────────────────
        from app.cleaning.null_handler import NullHandler
        registry.register(NullHandler(field_strategies=field_strategies))

        # ── 2. Deduplication (priority 20) ─────────────────────────────
        from app.cleaning.deduplication import DeduplicationHandler
        registry.register(DeduplicationHandler(
            key_columns=dedup_key if isinstance(dedup_key, list) else [dedup_key],
            keep_strategy="keep_first",
        ))

        # ── 3. String Normalizer (priority 30) ─────────────────────────
        from app.cleaning.string_normalizer import StringNormalizer
        registry.register(StringNormalizer(
            field_strategies=field_strategies,
            global_trim=True,
            global_control_chars=True,
        ))

        # ── 4. Numeric Cleaner (priority 35) ───────────────────────────
        numeric_fields = _extract_numeric_fields(field_strategies)
        if numeric_fields:
            from app.cleaning.numeric_cleaner import NumericCleaner
            registry.register(NumericCleaner(field_strategies=numeric_fields))

        # ── 5. Date Standardizer (priority 40) ─────────────────────────
        date_fields = _extract_date_fields(field_strategies, schema_cfg)
        if date_fields:
            from app.cleaning.date_standardizer import DateStandardizer
            registry.register(DateStandardizer(field_strategies=date_fields))

        # ── 6. Categorical Cleaner (priority 45) ───────────────────────
        cat_fields = _extract_categorical_fields(field_strategies, rules_cfg)
        if cat_fields:
            from app.cleaning.categorical_cleaner import CategoricalCleaner
            registry.register(CategoricalCleaner(field_strategies=cat_fields))

        # ── 7. Business Rule Cleaner (priority 50) ─────────────────────
        biz_rules = cleaning_cfg.get("business_rules", {})
        if biz_rules:
            from app.cleaning.business_rule_cleaner import BusinessRuleCleaner
            registry.register(BusinessRuleCleaner(field_rules=biz_rules))

        logger.debug(
            "CleaningRegistry built",
            dataset_type=dataset_type,
            cleaner_count=registry.count(),
        )
        return registry


# ── Config extraction helpers ──────────────────────────────────────────────

def _extract_numeric_fields(
    field_strategies: dict[str, dict[str, Any]]
) -> dict[str, dict[str, Any]]:
    numeric_keys = {"strip_currency", "strip_whitespace", "percentage_parse",
                    "rounding", "negative_as_zero", "clip_outliers", "winsorize"}
    return {
        k: v for k, v in field_strategies.items()
        if any(key in v for key in numeric_keys)
    }


def _extract_date_fields(
    field_strategies: dict[str, dict[str, Any]],
    schema_cfg: dict,
) -> dict[str, dict[str, Any]]:
    # From explicit cleaning config
    date_fields = {
        k: v for k, v in field_strategies.items()
        if v.get("standardize_date")
    }
    # Also auto-detect date columns from schema type
    for col_def in schema_cfg.get("columns", []):
        if not isinstance(col_def, dict):
            continue
        name = col_def.get("name", "").lower()
        if col_def.get("type") in ("date", "datetime") and name not in date_fields:
            date_fields[name] = {"standardize_date": True}
    return date_fields


def _extract_categorical_fields(
    field_strategies: dict[str, dict[str, Any]],
    rules_cfg: dict,
) -> dict[str, dict[str, Any]]:
    # From cleaning.yaml explicit categorical config
    cat_fields: dict[str, dict[str, Any]] = {
        k: v for k, v in field_strategies.items()
        if "string_case" in v or "alias_map" in v or "allowed_values" in v
    }
    # Auto-detect status/category fields from in_list validation rules
    for rule in rules_cfg.get("rules", []):
        if rule.get("check") == "in_list" and "field" in rule and "values" in rule:
            fld = rule["field"].lower()
            if fld not in cat_fields:
                cfg = field_strategies.get(fld, {}).copy()
                cfg.setdefault("allowed_values", rule["values"])
                cat_fields[fld] = cfg
    return cat_fields
