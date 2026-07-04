"""
TypeCastTransformer — casts string columns to proper Python/pandas types.

The ingestion stage reads everything as str (dtype=str). This transformer
converts columns to their correct types for downstream analytics:
  - Numeric columns → float64 / Int64
  - Date columns → datetime64[ns]
  - Boolean columns → bool
  - Currency columns → float64 (after stripping symbols)

Priority: 15 — runs after standardization/rename, before derived columns.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from app.transformation.base_transformer import BaseTransformer
from app.transformation.models import TransformationAction


class TypeCastTransformer(BaseTransformer):
    """Casts string columns to their target analytical types."""

    transformer_name = "TypeCastTransformer"
    transformer_category = "type_cast"
    priority = 15

    def __init__(
        self,
        # {column_name: "numeric" | "date" | "boolean" | "integer" | "currency"}
        type_map: dict[str, str] | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.type_map: dict[str, str] = {
            k.lower(): v.lower() for k, v in (type_map or {}).items()
        }

    def transform(
        self, df: pd.DataFrame, dataset_type: str
    ) -> tuple[pd.DataFrame, list[TransformationAction]]:
        actions: list[TransformationAction] = []
        result = df.copy()
        col_lower = {c.lower(): c for c in result.columns}

        for fld_lower, target_type in self.type_map.items():
            orig = col_lower.get(fld_lower)
            if orig is None:
                continue

            try:
                before_nulls = result[orig].isna().sum()
                if target_type in ("numeric", "float", "decimal", "currency"):
                    cleaned = result[orig].astype(str).str.replace(
                        r"[£$€¥₹,\s]", "", regex=True
                    )
                    result[orig] = pd.to_numeric(cleaned, errors="coerce")
                    cast_type = "float64"
                elif target_type == "integer":
                    cleaned = result[orig].astype(str).str.replace(r"[,\s]", "", regex=True)
                    result[orig] = pd.to_numeric(cleaned, errors="coerce")
                    result[orig] = result[orig].astype("Int64")
                    cast_type = "Int64"
                elif target_type in ("date", "datetime"):
                    result[orig] = pd.to_datetime(result[orig], errors="coerce")
                    cast_type = "datetime64[ns]"
                elif target_type == "boolean":
                    bool_map = {
                        "true": True, "false": False,
                        "yes": True, "no": False,
                        "1": True, "0": False, "t": True, "f": False,
                    }
                    result[orig] = result[orig].astype(str).str.lower().str.strip().map(bool_map)
                    cast_type = "bool"
                else:
                    continue

                after_nulls = result[orig].isna().sum()
                failed = max(0, after_nulls - before_nulls)
                rows_cast = len(result) - failed
                actions.append(self._action(
                    "TC_001", orig, [orig], "cast",
                    f"Cast '{orig}' from str to {cast_type} ({rows_cast} rows, {failed} failed)",
                    rows_cast,
                ))
            except Exception as exc:
                from app.logging.logger import get_logger
                get_logger(__name__).warning(f"TypeCast failed for '{orig}': {exc}")

        return result, actions

