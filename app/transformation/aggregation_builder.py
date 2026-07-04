"""
AggregationBuilder — produces summary aggregation DataFrames.

Generates daily/monthly/category aggregations from transformed datasets.
These aggregations supplement the main transformed_df for reporting purposes.

Usage:
    builder = AggregationBuilder()
    daily_sales = builder.daily_revenue(orders_df)
    category_summary = builder.category_revenue(orders_df, products_df)

Note: Aggregations are produced as separate DataFrames — they are NOT
appended to the main transformed_df. The pipeline engine stores them
as separate report artifacts.
"""

from __future__ import annotations

from typing import Any

import pandas as pd


class AggregationBuilder:
    """Builds summary aggregation DataFrames from transformed datasets."""

    def daily_revenue(
        self,
        df: pd.DataFrame,
        date_col: str = "order_date",
        total_col: str = "order_total",
    ) -> pd.DataFrame:
        """Aggregate total revenue by date."""
        date = col_or_none(df, date_col)
        total = col_or_none(df, total_col)
        if date is None or total is None:
            return pd.DataFrame()

        totals_n = pd.to_numeric(df[total], errors="coerce")
        dates_p = pd.to_datetime(df[date], errors="coerce").dt.date

        return (
            pd.DataFrame({"date": dates_p, "revenue": totals_n})
            .dropna()
            .groupby("date")
            .agg(
                order_count=("revenue", "count"),
                total_revenue=("revenue", "sum"),
                avg_order_value=("revenue", "mean"),
            )
            .reset_index()
            .sort_values("date")
        )

    def monthly_revenue(
        self,
        df: pd.DataFrame,
        date_col: str = "order_date",
        total_col: str = "order_total",
    ) -> pd.DataFrame:
        """Aggregate total revenue by year-month."""
        date = col_or_none(df, date_col)
        total = col_or_none(df, total_col)
        if date is None or total is None:
            return pd.DataFrame()

        totals_n = pd.to_numeric(df[total], errors="coerce")
        parsed = pd.to_datetime(df[date], errors="coerce")
        year_month = parsed.dt.to_period("M").astype(str)

        return (
            pd.DataFrame({"year_month": year_month, "revenue": totals_n})
            .dropna()
            .groupby("year_month")
            .agg(
                order_count=("revenue", "count"),
                total_revenue=("revenue", "sum"),
                avg_order_value=("revenue", "mean"),
            )
            .reset_index()
            .sort_values("year_month")
        )

    def category_revenue(
        self,
        df: pd.DataFrame,
        category_col: str = "category",
        total_col: str = "order_total",
    ) -> pd.DataFrame:
        """Aggregate revenue by category."""
        cat = col_or_none(df, category_col)
        total = col_or_none(df, total_col)
        if cat is None or total is None:
            return pd.DataFrame()

        totals_n = pd.to_numeric(df[total], errors="coerce")
        return (
            pd.DataFrame({"category": df[cat], "revenue": totals_n})
            .dropna()
            .groupby("category")
            .agg(
                record_count=("revenue", "count"),
                total_revenue=("revenue", "sum"),
                avg_value=("revenue", "mean"),
            )
            .reset_index()
            .sort_values("total_revenue", ascending=False)
        )

    def status_summary(
        self,
        df: pd.DataFrame,
        status_col: str = "order_status",
    ) -> pd.DataFrame:
        """Count records by status field."""
        stat = col_or_none(df, status_col)
        if stat is None:
            return pd.DataFrame()
        counts = df[stat].value_counts().reset_index()
        counts.columns = ["status", "count"]
        counts["pct"] = (counts["count"] / counts["count"].sum() * 100).round(2)
        return counts


def col_or_none(df: pd.DataFrame, col_name: str) -> str | None:
    """Return col_name if it exists in df (case-insensitive), else None."""
    col_map = {c.lower(): c for c in df.columns}
    return col_map.get(col_name.lower())
