"""
Cleaning domain models.

These are pure Python dataclasses — NOT ORM models.
They carry data between cleaning components and form the exact contract
the already-implemented TransformationEngine expects.

CRITICAL CONTRACT (do not change):
  TransformationEngine.transform() is called as:
    engine.transform(
        cleaned_df=result.cleaned_df,
        dataset_type=result.dataset_type,
        original_filename=...,
        pipeline_run_id=result.pipeline_run_id,
    )

The TransformationEngine requires cleaned_df to be a plain pandas DataFrame.
All other fields on CleaningResult are additive and backward-compatible.

Design hierarchy:
  CleaningAction   — one modification applied to one cell/row (full lineage record)
  CleaningMetrics  — run-level execution statistics
  CleaningReport   — complete audit trail for one cleaning run
  CleaningResult   — top-level object returned to the pipeline engine
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import pandas as pd


# ---------------------------------------------------------------------------
# CleaningAction — atomic lineage record
# ---------------------------------------------------------------------------

@dataclass
class CleaningAction:
    """
    Records a single modification applied to a single cell or row.

    Every change made by the Cleaning Engine produces one CleaningAction.
    This is the atomic unit of lineage: field, row, before, after, why.

    Immutable once created — the cleaning audit trail must never be altered.
    """

    rule_code: str        # e.g. "MV_001", "DUP_001", "STR_001"
    rule_category: str    # missing | duplicate | string | numeric | date |
                          # categorical | business | outlier | format
    field_name: str | None   # None for row-level actions (drop row, dedup)
    row_index: int | None    # None for dataset-level actions
    original_value: Any      # Value BEFORE cleaning (may be None)
    cleaned_value: Any       # Value AFTER cleaning (may be None)
    action_type: str         # fill_null | drop_row | trim | case_normalize |
                             # strip_currency | parse_date | map_category |
                             # clip_outlier | remove_duplicate | remove_control_chars
    reason: str              # Human-readable explanation of why this change was made
    confidence: float = 1.0  # 0.0–1.0 confidence in the fix (1.0 = certain)
    cleaning_rule_name: str = ""  # Name of the CleaningRule that made this change

    def to_dict(self) -> dict[str, Any]:
        return {
            "rule_code":          self.rule_code,
            "rule_category":      self.rule_category,
            "field_name":         self.field_name,
            "row_index":          self.row_index,
            "original_value":     str(self.original_value) if self.original_value is not None else None,
            "cleaned_value":      str(self.cleaned_value)  if self.cleaned_value  is not None else None,
            "action_type":        self.action_type,
            "reason":             self.reason,
            "confidence":         round(self.confidence, 3),
            "cleaning_rule_name": self.cleaning_rule_name,
        }


# ---------------------------------------------------------------------------
# CleaningMetrics — execution statistics
# ---------------------------------------------------------------------------

@dataclass
class CleaningMetrics:
    """Aggregated statistics for one cleaning run."""

    total_rows_input:       int = 0
    total_rows_output:      int = 0
    rows_dropped:           int = 0
    rows_modified:          int = 0
    cells_modified:         int = 0
    nulls_filled:           int = 0
    nulls_dropped:          int = 0
    duplicates_removed:     int = 0
    strings_trimmed:        int = 0
    cases_normalized:       int = 0
    dates_standardized:     int = 0
    currencies_cleaned:     int = 0
    categories_mapped:      int = 0
    outliers_clipped:       int = 0
    control_chars_removed:  int = 0
    total_actions:          int = 0
    rules_executed:         int = 0
    total_duration_ms:      float = 0.0
    cleaning_pct:           float = 0.0    # % of rows that had at least one change

    def compute_cleaning_pct(self) -> None:
        """Compute cleaning_pct from rows_modified / total_rows_input."""
        if self.total_rows_input > 0:
            self.cleaning_pct = round(
                self.rows_modified / self.total_rows_input * 100, 2
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_rows_input":      self.total_rows_input,
            "total_rows_output":     self.total_rows_output,
            "rows_dropped":          self.rows_dropped,
            "rows_modified":         self.rows_modified,
            "cells_modified":        self.cells_modified,
            "nulls_filled":          self.nulls_filled,
            "nulls_dropped":         self.nulls_dropped,
            "duplicates_removed":    self.duplicates_removed,
            "strings_trimmed":       self.strings_trimmed,
            "cases_normalized":      self.cases_normalized,
            "dates_standardized":    self.dates_standardized,
            "currencies_cleaned":    self.currencies_cleaned,
            "categories_mapped":     self.categories_mapped,
            "outliers_clipped":      self.outliers_clipped,
            "total_actions":         self.total_actions,
            "rules_executed":        self.rules_executed,
            "total_duration_ms":     round(self.total_duration_ms, 2),
            "cleaning_pct":          self.cleaning_pct,
        }


# ---------------------------------------------------------------------------
# CleaningReport — full audit trail
# ---------------------------------------------------------------------------

@dataclass
class CleaningReport:
    """
    Complete audit trail for one cleaning run.

    Every action is recorded so the cleaning is fully reproducible and
    every change can be traced from original value to cleaned value.
    """

    report_id:       str = field(default_factory=lambda: str(uuid.uuid4()))
    pipeline_run_id: str | None = None
    dataset_type:    str = ""
    original_filename: str = ""
    cleaned_at:      datetime = field(default_factory=datetime.utcnow)
    duration_seconds: float = 0.0

    # Full lineage: every atomic change
    actions: list[CleaningAction] = field(default_factory=list)

    # Aggregated metrics
    metrics: CleaningMetrics = field(default_factory=CleaningMetrics)

    # Schema information
    input_columns:  list[str] = field(default_factory=list)
    output_columns: list[str] = field(default_factory=list)

    # Rows dropped (by index) — for rollback support
    dropped_row_indices: list[int] = field(default_factory=list)

    # Warnings and non-fatal errors
    warnings: list[str] = field(default_factory=list)
    errors:   list[str] = field(default_factory=list)

    def add_action(self, action: CleaningAction) -> None:
        """Append an action and update the relevant metric counter."""
        self.actions.append(action)

    def to_summary_dict(self) -> dict[str, Any]:
        return {
            "report_id":         self.report_id,
            "dataset_type":      self.dataset_type,
            "original_filename": self.original_filename,
            "cleaned_at":        self.cleaned_at.isoformat(),
            "duration_seconds":  round(self.duration_seconds, 3),
            "metrics":           self.metrics.to_dict(),
            "input_columns":     self.input_columns,
            "output_columns":    self.output_columns,
            "dropped_rows":      len(self.dropped_row_indices),
            "total_actions":     len(self.actions),
            "warnings":          self.warnings,
            "errors":            self.errors,
        }

    def to_lineage_records(self) -> list[dict[str, Any]]:
        """Full lineage — one dict per CleaningAction."""
        return [a.to_dict() for a in self.actions]


# ---------------------------------------------------------------------------
# CleaningResult — the top-level output (Transformation Engine contract)
# ---------------------------------------------------------------------------

@dataclass
class CleaningResult:
    """
    The top-level output of the Cleaning Engine.

    Contract with the TransformationEngine (DO NOT CHANGE):
      - cleaned_df       : pandas DataFrame, ready for transformation
      - dataset_type     : string matching DatasetType enum values
      - pipeline_run_id  : UUID string for DB correlation (may be None)

    Additional fields are backward-compatible additions:
      - cleaning_report  : full audit trail
      - cleaning_metrics : aggregated statistics (also in report.metrics)
      - execution_time   : total seconds taken
      - success          : whether cleaning completed without fatal errors
      - warnings         : non-fatal issues detected
      - errors           : fatal issues (cleaning aborted if any)
      - original_df      : snapshot of pre-cleaning DataFrame for diff/rollback
      - rejected_df      : rows that were dropped during cleaning
    """

    # ── TransformationEngine contract (immutable) ──────────────────────
    cleaned_df:      pd.DataFrame   # The cleaned DataFrame → goes to TransformationEngine
    dataset_type:    str            # e.g. "orders", "customers"
    pipeline_run_id: str | None = None

    # ── Cleaning audit (additive, backward-compatible) ─────────────────
    cleaning_report:  CleaningReport  = field(default_factory=CleaningReport)
    cleaning_metrics: CleaningMetrics = field(default_factory=CleaningMetrics)
    execution_time:   float = 0.0     # seconds
    success:          bool = True
    warnings: list[str] = field(default_factory=list)
    errors:   list[str] = field(default_factory=list)

    # ── Lineage / rollback support ─────────────────────────────────────
    original_df:  pd.DataFrame = field(default_factory=pd.DataFrame)  # pre-cleaning snapshot
    rejected_df:  pd.DataFrame = field(default_factory=pd.DataFrame)  # rows dropped

    @property
    def row_count(self) -> int:
        return len(self.cleaned_df)

    @property
    def rows_dropped(self) -> int:
        return len(self.rejected_df)

    @property
    def total_actions(self) -> int:
        return len(self.cleaning_report.actions)

    def diff(self) -> pd.DataFrame:
        """
        Return a DataFrame showing before/after for every modified cell.

        Useful for preview mode and dry-run comparisons.
        """
        records = []
        for action in self.cleaning_report.actions:
            if action.original_value != action.cleaned_value:
                records.append({
                    "row_index":      action.row_index,
                    "field_name":     action.field_name,
                    "original_value": action.original_value,
                    "cleaned_value":  action.cleaned_value,
                    "rule_code":      action.rule_code,
                    "action_type":    action.action_type,
                    "reason":         action.reason,
                })
        return pd.DataFrame(records)

    def __repr__(self) -> str:
        return (
            f"CleaningResult("
            f"success={self.success}, "
            f"dataset={self.dataset_type!r}, "
            f"rows_in={len(self.original_df)}, "
            f"rows_out={self.row_count}, "
            f"dropped={self.rows_dropped}, "
            f"actions={self.total_actions})"
        )
