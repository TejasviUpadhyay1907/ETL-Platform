"""
DerivedColumnTransformer — computes new columns from expressions in YAML.

Supported expression functions:
  days_since(col)           — integer days between date col and today
  year(col)                 — calendar year from date column
  month(col)                — month number (1-12)
  multiply(col_a, col_b)    — col_a × col_b (numeric)
  subtract(col_a, col_b)    — col_a - col_b
  divide(col_a, col_b)      — col_a / col_b (safe, returns NaN on /0)
  add(col_a, col_b)         — col_a + col_b
  pct(col_a, col_b)         — col_a / col_b × 100 (percentage)
  if_gte(col, value)        — True if col >= value
  if_gt(col, value)         — True if col > value
  if_lte(col, value)        — True if col <= value
  concat(col_a, sep, col_b) — string concatenation

Priority: 30 — runs after date standardization.
"""

from __future__ import annotations

import re
from datetime import date
from typing import Any

import pandas as pd

from app.transformation.base_transformer import BaseTransformer
from app.transformation.models import TransformationAction


class DerivedColumnTransformer(BaseTransformer):
    """Creates new columns using configurable expression rules."""

    transformer_name = "DerivedColumnTransformer"
    transformer_category = "derived"
    priority = 30

    def __init__(
        self,
        derived_fields: list[dict[str, Any]] | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.derived_fields = derived_fields or []
        self._today = pd.Timestamp(date.today())

    def transform(
        self, df: pd.DataFrame, dataset_type: str
    ) -> tuple[pd.DataFrame, list[TransformationAction]]:
        actions: list[TransformationAction] = []
        result = df.copy()
        col_lower = {c.lower(): c for c in result.columns}

        for rule in self.derived_fields:
            name = rule.get("name", "")
            expr = rule.get("expression", "")
            description = rule.get("description", expr)
            if not name or not expr:
                continue
            try:
                series, src_cols = self._evaluate(expr, result, col_lower)
                result[name] = series
                actions.append(self._action(
                    rule_code=f"DC_{dataset_type[:3].upper()}_{len(actions)+1:03d}",
                    column_name=name,
                    source_columns=src_cols,
                    transformation_type="derive",
                    description=description,
                    rows_affected=int(series.notna().sum()),
                ))
                # Update col_lower so later expressions can reference new columns
                col_lower[name.lower()] = name
            except Exception as exc:
                from app.logging.logger import get_logger
                get_logger(__name__).warning(
                    f"DerivedColumnTransformer: could not compute '{name}': {exc}"
                )

        return result, actions

    def _evaluate(
        self,
        expr: str,
        df: pd.DataFrame,
        col_lower: dict[str, str],
    ) -> tuple[pd.Series, list[str]]:
        """Parse and evaluate an expression string against the DataFrame."""
        expr = expr.strip()

        # days_since(col)
        m = re.fullmatch(r"days_since\((\w+)\)", expr)
        if m:
            col = col_lower.get(m.group(1).lower())
            if col:
                parsed = pd.to_datetime(df[col], errors="coerce")
                return (self._today - parsed).dt.days, [col]

        # year(col) / month(col) / quarter(col) / week(col)
        m = re.fullmatch(r"(year|month|quarter|week)\((\w+)\)", expr)
        if m:
            fn, cname = m.group(1), m.group(2)
            col = col_lower.get(cname.lower())
            if col:
                parsed = pd.to_datetime(df[col], errors="coerce")
                if fn == "year":    return parsed.dt.year, [col]
                if fn == "month":   return parsed.dt.month, [col]
                if fn == "quarter": return parsed.dt.quarter, [col]
                if fn == "week":    return parsed.dt.isocalendar().week.astype("Int64"), [col]

        # multiply(a, b)
        m = re.fullmatch(r"multiply\((\w+),\s*(\w+)\)", expr)
        if m:
            ca, cb = col_lower.get(m.group(1).lower()), col_lower.get(m.group(2).lower())
            if ca and cb:
                a = pd.to_numeric(df[ca], errors="coerce")
                b = pd.to_numeric(df[cb], errors="coerce")
                return a * b, [ca, cb]

        # subtract(a, b)
        m = re.fullmatch(r"subtract\((\w+),\s*(\w+)\)", expr)
        if m:
            ca, cb = col_lower.get(m.group(1).lower()), col_lower.get(m.group(2).lower())
            if ca and cb:
                return pd.to_numeric(df[ca], errors="coerce") - pd.to_numeric(df[cb], errors="coerce"), [ca, cb]

        # divide(a, b)
        m = re.fullmatch(r"divide\((\w+),\s*(\w+)\)", expr)
        if m:
            ca, cb = col_lower.get(m.group(1).lower()), col_lower.get(m.group(2).lower())
            if ca and cb:
                a = pd.to_numeric(df[ca], errors="coerce")
                b = pd.to_numeric(df[cb], errors="coerce").replace(0, float("nan"))
                return a / b, [ca, cb]

        # add(a, b)
        m = re.fullmatch(r"add\((\w+),\s*(\w+)\)", expr)
        if m:
            ca, cb = col_lower.get(m.group(1).lower()), col_lower.get(m.group(2).lower())
            if ca and cb:
                return pd.to_numeric(df[ca], errors="coerce") + pd.to_numeric(df[cb], errors="coerce"), [ca, cb]

        # pct(a, b) — a / b × 100
        m = re.fullmatch(r"pct\((\w+),\s*(\w+)\)", expr)
        if m:
            ca, cb = col_lower.get(m.group(1).lower()), col_lower.get(m.group(2).lower())
            if ca and cb:
                a = pd.to_numeric(df[ca], errors="coerce")
                b = pd.to_numeric(df[cb], errors="coerce").replace(0, float("nan"))
                return (a / b) * 100, [ca, cb]

        # if_gte(col, value)  — col >= value
        m = re.fullmatch(r"if_gte\((\w+),\s*(-?[\d.]+)\)", expr)
        if m:
            col = col_lower.get(m.group(1).lower())
            if col:
                return pd.to_numeric(df[col], errors="coerce") >= float(m.group(2)), [col]

        # if_gt(col, value)
        m = re.fullmatch(r"if_gt\((\w+),\s*(-?[\d.]+)\)", expr)
        if m:
            col = col_lower.get(m.group(1).lower())
            if col:
                return pd.to_numeric(df[col], errors="coerce") > float(m.group(2)), [col]

        # if_lte(col, value)
        m = re.fullmatch(r"if_lte\((\w+),\s*(-?[\d.]+)\)", expr)
        if m:
            col = col_lower.get(m.group(1).lower())
            if col:
                return pd.to_numeric(df[col], errors="coerce") <= float(m.group(2)), [col]

        # concat(a, sep, b)
        m = re.fullmatch(r"concat\((\w+),\s*'([^']*)',\s*(\w+)\)", expr)
        if m:
            ca, sep, cb = col_lower.get(m.group(1).lower()), m.group(2), col_lower.get(m.group(3).lower())
            if ca and cb:
                return df[ca].astype(str).str.cat(df[cb].astype(str), sep=sep), [ca, cb]

        # Fallback: simple col >= numeric_literal (e.g. "order_total >= 1000")
        m = re.fullmatch(r"(\w+)\s*(>=|>|<=|<|==)\s*(-?[\d.]+)", expr)
        if m:
            col = col_lower.get(m.group(1).lower())
            op, val = m.group(2), float(m.group(3))
            if col:
                s = pd.to_numeric(df[col], errors="coerce")
                ops = {">=": s.__ge__, ">": s.__gt__, "<=": s.__le__, "<": s.__lt__, "==": s.__eq__}
                fn = ops.get(op)
                if fn:
                    return fn(val), [col]

        raise ValueError(f"Unsupported expression: '{expr}'")
