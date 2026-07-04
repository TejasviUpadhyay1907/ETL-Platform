"""
DateTransformer — standardizes dates and derives temporal features.

Applied to all columns declared as type=date in schema.yaml.

Derived columns (for each date field):
  {field}_year        — calendar year
  {field}_month       — month (1–12)
  {field}_quarter     — quarter (1–4)
  {field}_week        — ISO week number
  {field}_day_of_week — day name (Monday…Sunday)
  {field}_is_weekend  — True for Saturday/Sunday
  {field}_age_days    — days since the date (relative to today)

Priority: 20 — runs after standardization so column names are finalized.
"""

from __future__ import annotations

from datetime import date
from typing import Any

import pandas as pd

from app.transformation.base_transformer import BaseTransformer
from app.transformation.models import TransformationAction


class DateTransformer(BaseTransformer):
    """Converts date columns to datetime and derives temporal features."""

    transformer_name = "DateTransformer"
    transformer_category = "date"
    priority = 20

    def __init__(
        self,
        date_fields: list[str] | None = None,
        derive_year: bool = True,
        derive_month: bool = True,
        derive_quarter: bool = True,
        derive_week: bool = True,
        derive_day_of_week: bool = True,
        derive_is_weekend: bool = True,
        derive_age_days: bool = True,
        reference_date: date | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.date_fields = [f.lower() for f in (date_fields or [])]
        self.derive_year = derive_year
        self.derive_month = derive_month
        self.derive_quarter = derive_quarter
        self.derive_week = derive_week
        self.derive_day_of_week = derive_day_of_week
        self.derive_is_weekend = derive_is_weekend
        self.derive_age_days = derive_age_days
        self.ref_date = pd.Timestamp(reference_date or date.today())

    def transform(
        self, df: pd.DataFrame, dataset_type: str
    ) -> tuple[pd.DataFrame, list[TransformationAction]]:
        actions: list[TransformationAction] = []
        result = df.copy()

        col_lower = {c.lower(): c for c in result.columns}

        for fld in self.date_fields:
            orig = col_lower.get(fld)
            if orig is None:
                continue

            # Parse to datetime (coerce errors → NaT)
            parsed = pd.to_datetime(result[orig], errors="coerce")
            if parsed.isna().all():
                continue  # nothing parseable — skip

            non_null = parsed.notna().sum()

            if self.derive_year:
                col = f"{fld}_year"
                result[col] = parsed.dt.year
                actions.append(self._action("DT_001", col, [orig], "derive",
                    f"Year extracted from {orig}", non_null))

            if self.derive_month:
                col = f"{fld}_month"
                result[col] = parsed.dt.month
                actions.append(self._action("DT_002", col, [orig], "derive",
                    f"Month extracted from {orig}", non_null))

            if self.derive_quarter:
                col = f"{fld}_quarter"
                result[col] = parsed.dt.quarter
                actions.append(self._action("DT_003", col, [orig], "derive",
                    f"Quarter extracted from {orig}", non_null))

            if self.derive_week:
                col = f"{fld}_week"
                result[col] = parsed.dt.isocalendar().week.astype("Int64")
                actions.append(self._action("DT_004", col, [orig], "derive",
                    f"ISO week extracted from {orig}", non_null))

            if self.derive_day_of_week:
                col = f"{fld}_day_of_week"
                result[col] = parsed.dt.day_name()
                actions.append(self._action("DT_005", col, [orig], "derive",
                    f"Day of week from {orig}", non_null))

            if self.derive_is_weekend:
                col = f"{fld}_is_weekend"
                result[col] = parsed.dt.dayofweek >= 5
                actions.append(self._action("DT_006", col, [orig], "derive",
                    f"Weekend flag from {orig}", non_null))

            if self.derive_age_days:
                col = f"{fld}_age_days"
                result[col] = (self.ref_date - parsed).dt.days
                actions.append(self._action("DT_007", col, [orig], "derive",
                    f"Age in days from {orig} to today", non_null))

        return result, actions

