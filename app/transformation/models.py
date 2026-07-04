"""
Transformation domain models.

These are pure Python dataclasses — NOT ORM models.
They carry data between transformation components and form the contract
between the Transformation Engine and the downstream Loading Engine.

Design hierarchy:
  TransformationAction  — one transformation applied to one column (for lineage)
  TransformationMetrics — execution statistics for the transformation run
  TransformationReport  — complete per-dataset transformation output
  TransformationResult  — top-level object returned to the pipeline engine

The Loading Engine receives TransformationResult and reads:
  - transformed_df  : the analytics-ready DataFrame, schema-mapped and enriched
  - report          : full lineage and metrics for audit trail
  - success         : whether to proceed with loading
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import pandas as pd


# ---------------------------------------------------------------------------
# TransformationAction — one transformation applied to one column
# ---------------------------------------------------------------------------

@dataclass
class TransformationAction:
    """
    Lineage record for a single transformation applied to a column.

    Every derived column, renamed column, or computed value produces
    one TransformationAction. These form the complete lineage trail
    from raw ingested value to analytics-ready value.
    """

    rule_code: str           # e.g. "FM_001", "DC_orders_001", "BIZ_001"
    rule_category: str       # standardization | derived | business | date | currency |
                             # categorical | lookup | aggregation | feature | normalization
    column_name: str         # target column name
    source_columns: list[str] = field(default_factory=list)  # source column(s) used
    transformation_type: str = ""    # rename | cast | derive | calculate | map | enrich
    description: str = ""
    rows_affected: int = 0
    execution_ms: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "rule_code":          self.rule_code,
            "rule_category":      self.rule_category,
            "column_name":        self.column_name,
            "source_columns":     self.source_columns,
            "transformation_type": self.transformation_type,
            "description":        self.description,
            "rows_affected":      self.rows_affected,
            "execution_ms":       round(self.execution_ms, 2),
        }


# ---------------------------------------------------------------------------
# TransformationMetrics — run-level execution statistics
# ---------------------------------------------------------------------------

@dataclass
class TransformationMetrics:
    """Execution statistics for one transformation run."""

    total_rows_input:       int = 0
    total_rows_output:      int = 0
    columns_renamed:        int = 0
    columns_type_cast:      int = 0
    derived_columns_created: int = 0
    business_calcs_applied: int = 0
    lookup_enrichments:     int = 0
    date_transforms:        int = 0
    categorical_maps:       int = 0
    aggregations_created:   int = 0
    features_engineered:    int = 0
    total_actions:          int = 0
    total_duration_ms:      float = 0.0
    transformers_executed:  int = 0
    transformers_skipped:   int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_rows_input":         self.total_rows_input,
            "total_rows_output":        self.total_rows_output,
            "columns_renamed":          self.columns_renamed,
            "derived_columns_created":  self.derived_columns_created,
            "business_calcs_applied":   self.business_calcs_applied,
            "lookup_enrichments":       self.lookup_enrichments,
            "date_transforms":          self.date_transforms,
            "aggregations_created":     self.aggregations_created,
            "features_engineered":      self.features_engineered,
            "total_actions":            self.total_actions,
            "total_duration_ms":        round(self.total_duration_ms, 2),
            "transformers_executed":    self.transformers_executed,
        }


# ---------------------------------------------------------------------------
# TransformationReport — complete per-dataset transformation output
# ---------------------------------------------------------------------------

@dataclass
class TransformationReport:
    """
    Complete record of all transformations applied to a dataset.

    Serializes to JSON / CSV / Excel for lineage audit and pipeline reporting.
    """

    report_id:       str = field(default_factory=lambda: str(uuid.uuid4()))
    pipeline_run_id: str | None = None
    dataset_type:    str = ""
    original_filename: str = ""
    transformed_at:  datetime = field(default_factory=datetime.utcnow)
    duration_seconds: float = 0.0

    # Lineage: every action applied
    actions: list[TransformationAction] = field(default_factory=list)

    # Execution statistics
    metrics: TransformationMetrics = field(default_factory=TransformationMetrics)

    # Schema change summary
    input_columns:  list[str] = field(default_factory=list)
    output_columns: list[str] = field(default_factory=list)
    added_columns:  list[str] = field(default_factory=list)
    renamed_columns: dict[str, str] = field(default_factory=dict)  # old → new

    def to_summary_dict(self) -> dict[str, Any]:
        """Compact summary for API responses."""
        return {
            "report_id":         self.report_id,
            "dataset_type":      self.dataset_type,
            "original_filename": self.original_filename,
            "transformed_at":    self.transformed_at.isoformat(),
            "duration_seconds":  round(self.duration_seconds, 3),
            "metrics":           self.metrics.to_dict(),
            "input_columns":     self.input_columns,
            "output_columns":    self.output_columns,
            "added_columns":     self.added_columns,
            "renamed_columns":   self.renamed_columns,
            "total_actions":     len(self.actions),
        }

    def to_lineage_records(self) -> list[dict[str, Any]]:
        """Full lineage — one dict per TransformationAction."""
        return [a.to_dict() for a in self.actions]


# ---------------------------------------------------------------------------
# TransformationResult — top-level output to the pipeline engine
# ---------------------------------------------------------------------------

@dataclass
class TransformationResult:
    """
    The top-level output of the Transformation Engine.

    Returned by TransformationEngine.transform() to the pipeline engine,
    which passes transformed_df directly to the Loading Engine.

    The transformed_df is a NEW DataFrame — a copy of the cleaned DataFrame
    with all transformations applied. The original cleaned DataFrame is
    never modified.
    """

    success: bool
    dataset_type: str

    # The analytics-ready DataFrame (NEW — original cleaned_df is untouched)
    transformed_df: pd.DataFrame = field(default_factory=pd.DataFrame)

    # Full report
    report: TransformationReport = field(default_factory=TransformationReport)

    # Error information (set when success=False)
    error_message: str | None = None
    error_code: str | None = None

    # Timing
    duration_seconds: float = 0.0

    @property
    def row_count(self) -> int:
        return len(self.transformed_df)

    @property
    def column_count(self) -> int:
        return len(self.transformed_df.columns)

    @property
    def columns(self) -> list[str]:
        return list(self.transformed_df.columns)

    def __repr__(self) -> str:
        return (
            f"TransformationResult("
            f"success={self.success}, "
            f"dataset={self.dataset_type!r}, "
            f"rows={self.row_count}, "
            f"cols={self.column_count})"
        )
