"""
TransformationRegistry — builds the ordered transformer pipeline for a dataset.

Loads configuration from:
  config/datasets/{type}/transformations.yaml
  config/datasets/{type}/schema.yaml

Constructs and registers all applicable transformers in execution order.
Adding a new transformer requires only registering it here — no engine changes.
"""

from __future__ import annotations

from typing import Any

from app.logging.logger import get_logger
from app.transformation.base_transformer import BaseTransformer

logger = get_logger(__name__)


class TransformationRegistry:
    """Holds all transformers for one dataset transformation run."""

    def __init__(self) -> None:
        self._transformers: list[BaseTransformer] = []

    def register(self, transformer: BaseTransformer) -> None:
        self._transformers.append(transformer)

    def get_ordered(self) -> list[BaseTransformer]:
        return sorted(
            [t for t in self._transformers if t.enabled],
            key=lambda t: t.priority,
        )

    def count(self) -> int:
        return len(self._transformers)

    @classmethod
    def build_for_dataset(
        cls,
        dataset_type: str,
        extra_lookups: dict[str, dict[str, str]] | None = None,
    ) -> "TransformationRegistry":
        """
        Factory: construct a full transformer pipeline for a dataset type.

        Args:
            dataset_type:   One of: orders, customers, products, inventory, suppliers, payments
            extra_lookups:  Additional lookup tables {source_col: {val: enriched_val}}
        """
        registry = cls()
        from app.core.config_loader import load_dataset_config

        trans_cfg  = load_dataset_config(dataset_type, "transformations")
        schema_cfg = load_dataset_config(dataset_type, "schema")
        rules_cfg  = load_dataset_config(dataset_type, "rules")

        field_mappings = trans_cfg.get("field_mappings", {})
        derived_fields = trans_cfg.get("derived_fields", [])
        business_rules = trans_cfg.get("business_rules", [])
        category_maps  = trans_cfg.get("category_mappings", {})
        case_norms     = trans_cfg.get("case_normalizations", {})

        # ── 1. Standardization (rename + snake_case) ────────────────────
        from app.transformation.transformers.standardization_transformer import StandardizationTransformer
        registry.register(StandardizationTransformer(
            field_mappings=field_mappings,
            normalize_names=True,
        ))

        # ── 2. Type casting ─────────────────────────────────────────────
        type_map = _build_type_map(schema_cfg)
        if type_map:
            from app.transformation.transformers.type_cast_transformer import TypeCastTransformer
            registry.register(TypeCastTransformer(type_map=type_map))

        # ── 3. Date transformations ─────────────────────────────────────
        date_fields = [
            c["name"] for c in schema_cfg.get("columns", [])
            if isinstance(c, dict) and c.get("type") in ("date", "datetime")
        ]
        if date_fields:
            from app.transformation.transformers.date_transformer import DateTransformer
            registry.register(DateTransformer(date_fields=date_fields))

        # ── 4. Derived columns (YAML expressions) ──────────────────────
        if derived_fields:
            from app.transformation.transformers.derived_column_transformer import DerivedColumnTransformer
            registry.register(DerivedColumnTransformer(derived_fields=derived_fields))

        # ── 5. Business calculations ────────────────────────────────────
        from app.transformation.transformers.business_rule_transformer import BusinessRuleTransformer
        registry.register(BusinessRuleTransformer(
            dataset_type=dataset_type,
            rules=business_rules,
        ))

        # ── 6. Categorical normalization ────────────────────────────────
        # Auto-detect status / category fields from in_list rules
        cat_fields = _extract_categorical_maps(rules_cfg)
        cat_fields.update(category_maps)
        if cat_fields or case_norms:
            from app.transformation.transformers.categorical_transformer import CategoricalTransformer
            registry.register(CategoricalTransformer(
                category_mappings=cat_fields,
                case_normalizations=case_norms,
            ))

        # ── 7. Lookup enrichment ────────────────────────────────────────
        has_country  = any(c.get("name","").lower() == "country" for c in schema_cfg.get("columns", []) if isinstance(c, dict))
        has_currency = any(c.get("name","").lower() == "currency" for c in schema_cfg.get("columns", []) if isinstance(c, dict))
        from app.transformation.transformers.lookup_transformer import LookupTransformer
        registry.register(LookupTransformer(
            lookup_tables=extra_lookups or {},
            enrich_country=has_country,
            enrich_currency=has_currency,
        ))

        # ── 8. Feature engineering ──────────────────────────────────────
        from app.transformation.transformers.feature_engineering_transformer import FeatureEngineeringTransformer
        registry.register(FeatureEngineeringTransformer(dataset_type=dataset_type))

        logger.debug(
            "TransformationRegistry built",
            dataset_type=dataset_type,
            transformer_count=registry.count(),
        )
        return registry


def _build_type_map(schema_cfg: dict) -> dict[str, str]:
    """Build a {column_name: cast_type} map from schema column type declarations."""
    type_mapping = {
        "decimal":  "numeric", "float": "numeric", "numeric": "numeric",
        "integer":  "integer", "int": "integer",
        "date":     "date",    "datetime": "date",
        "boolean":  "boolean", "bool": "boolean",
        "currency": "currency",
    }
    result = {}
    for col in schema_cfg.get("columns", []):
        if not isinstance(col, dict):
            continue
        name = col.get("name", "")
        col_type = col.get("type", "").lower()
        cast = type_mapping.get(col_type)
        if cast and name:
            result[name] = cast
    return result


def _extract_categorical_maps(rules_cfg: dict) -> dict[str, dict[str, str]]:
    """Extract in_list rules and return {field: {val: val}} identity maps for case normalization."""
    # We don't remap values here — just flag which fields have controlled vocabularies
    return {}
