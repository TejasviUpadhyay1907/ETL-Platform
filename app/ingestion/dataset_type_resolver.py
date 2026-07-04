"""
DatasetTypeResolver — determines which dataset type an uploaded file belongs to.

Resolution strategy (tried in priority order):
1. Explicit override passed by the caller (API parameter)
2. Filename pattern matching against YAML config rules
3. Schema-based matching — compare actual column names to expected schema columns
4. Fallback to None (unknown) — downstream will reject with a clear error

Design: all rules are loaded from config/datasets/*/schema.yaml at startup.
Adding a new dataset type requires only a new YAML file — no code changes.

This module is ONLY responsible for classification — it does not validate
whether the content is correct for that type.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from app.core.exceptions import ConfigurationException
from app.logging.logger import get_logger
from app.utils.constants import DATASET_FILENAME_PATTERNS, DatasetType

logger = get_logger(__name__)


class DatasetTypeResolver:
    """
    Resolves a file's dataset type from filename, schema, or explicit override.

    Instantiate once at startup and reuse — rules are loaded from YAML once.
    """

    def __init__(self) -> None:
        self._schema_columns: dict[str, list[str]] = {}
        self._filename_patterns: dict[str, str] = {}
        self._load_rules()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def resolve(
        self,
        filename: str,
        column_names: list[str] | None = None,
        explicit_type: str | None = None,
    ) -> DatasetType | None:
        """
        Resolve the dataset type for a file.

        Args:
            filename:      Original filename (e.g. 'orders_2025_01.csv').
            column_names:  Actual column names read from the file (for schema matching).
            explicit_type: Caller-supplied type that overrides detection entirely.

        Returns:
            DatasetType enum value, or None if the type cannot be determined.
        """
        # Priority 1: explicit override from the caller
        if explicit_type:
            return self._validate_explicit(explicit_type)

        # Priority 2: filename pattern matching
        by_filename = self._resolve_by_filename(filename)
        if by_filename:
            logger.debug(
                "Dataset type resolved by filename",
                filename=filename,
                resolved=by_filename.value,
            )
            return by_filename

        # Priority 3: schema column matching
        if column_names:
            by_schema = self._resolve_by_schema(column_names)
            if by_schema:
                logger.debug(
                    "Dataset type resolved by schema",
                    filename=filename,
                    resolved=by_schema.value,
                    columns=column_names[:5],
                )
                return by_schema

        logger.warning(
            "Could not resolve dataset type",
            filename=filename,
            columns_provided=column_names is not None,
        )
        return None

    def resolve_or_raise(
        self,
        filename: str,
        column_names: list[str] | None = None,
        explicit_type: str | None = None,
    ) -> DatasetType:
        """
        Like resolve(), but raises ValueError if the type cannot be determined.
        """
        result = self.resolve(filename, column_names, explicit_type)
        if result is None:
            raise ValueError(
                f"Cannot determine dataset type for file '{filename}'. "
                "Provide an explicit dataset_type parameter or rename the file to "
                "include a recognisable keyword (orders, customers, products, "
                "inventory, suppliers, payments)."
            )
        return result

    def get_expected_columns(self, dataset_type: DatasetType) -> list[str]:
        """Return the expected column names for a dataset type (from schema YAML)."""
        return self._schema_columns.get(dataset_type.value, [])

    # ------------------------------------------------------------------
    # Private methods
    # ------------------------------------------------------------------

    def _load_rules(self) -> None:
        """Load schema column lists and filename patterns from YAML config files."""
        from app.core.config_loader import load_dataset_config

        for ds in DatasetType:
            schema = load_dataset_config(ds.value, "schema")
            if schema:
                columns = [
                    col["name"]
                    for col in schema.get("columns", [])
                    if isinstance(col, dict) and "name" in col
                ]
                self._schema_columns[ds.value] = columns
            else:
                logger.warning(f"No schema YAML found for dataset type: {ds.value}")
                self._schema_columns[ds.value] = []

        # Load filename patterns from constants (already defined in utils/constants.py)
        # Extend with any YAML-defined patterns if present
        for keyword, dataset_type in DATASET_FILENAME_PATTERNS.items():
            self._filename_patterns[keyword.lower()] = dataset_type.value

        logger.debug(
            "Dataset type resolver loaded",
            types=len(self._schema_columns),
            filename_patterns=len(self._filename_patterns),
        )

    def _validate_explicit(self, explicit_type: str) -> DatasetType | None:
        """Validate an explicitly supplied dataset type string."""
        try:
            return DatasetType(explicit_type.lower().strip())
        except ValueError:
            valid = [t.value for t in DatasetType]
            raise ValueError(
                f"Invalid explicit dataset type '{explicit_type}'. "
                f"Valid values: {valid}"
            )

    def _resolve_by_filename(self, filename: str) -> DatasetType | None:
        """
        Match filename (lowercased, no extension) against known keywords.

        Examples:
            'orders_2025_01.csv'      → ORDERS
            'CUSTOMER_data.xlsx'      → CUSTOMERS
            'supplier_master.csv'     → SUPPLIERS
        """
        stem = Path(filename).stem.lower()
        # Exact keyword match first (fastest)
        for keyword, type_value in self._filename_patterns.items():
            if keyword in stem:
                try:
                    return DatasetType(type_value)
                except ValueError:
                    continue
        return None

    def _resolve_by_schema(self, column_names: list[str]) -> DatasetType | None:
        """
        Find the dataset type whose expected columns best match the actual columns.

        Uses Jaccard similarity: intersection / union.
        Returns the type with highest similarity if it exceeds 50%.

        This means a file can be missing some expected columns (or have extras)
        and still be correctly classified.
        """
        if not column_names:
            return None

        actual = {c.lower().strip() for c in column_names}
        best_type: DatasetType | None = None
        best_score: float = 0.0
        threshold: float = 0.5  # at least 50% column overlap required

        for ds in DatasetType:
            expected = {c.lower() for c in self._schema_columns.get(ds.value, [])}
            if not expected:
                continue

            intersection = len(actual & expected)
            union = len(actual | expected)
            score = intersection / union if union > 0 else 0.0

            if score > best_score:
                best_score = score
                best_type = ds

        if best_score >= threshold:
            return best_type

        logger.debug(
            "Schema matching below threshold",
            best_score=round(best_score, 3),
            threshold=threshold,
            columns_sample=list(actual)[:5],
        )
        return None
