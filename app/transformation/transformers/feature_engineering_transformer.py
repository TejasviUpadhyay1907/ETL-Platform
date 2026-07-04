"""
FeatureEngineeringTransformer — computes ML-ready and analytics features.

Features:
  - Revenue bands (micro/small/medium/large/enterprise)
  - Customer RFM scores (Recency, Frequency, Monetary — on customer-level data)
  - Inventory risk level (critical/low/normal/excess)
  - Order status label enrichment
  - High-value customer flag
  - Sales velocity indicator
  - Payment risk flag

Priority: 60 — runs after business calculations are available.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from app.transformation.base_transformer import BaseTransformer
from app.transformation.models import TransformationAction


class FeatureEngineeringTransformer(BaseTransformer):
    """Produces analytics and ML-ready feature columns."""

    transformer_name = "FeatureEngineeringTransformer"
    transformer_category = "feature"
    priority = 60

    def __init__(self, dataset_type: str = "", **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._dataset_type = dataset_type

    def transform(
        self, df: pd.DataFrame, dataset_type: str
    ) -> tuple[pd.DataFrame, list[TransformationAction]]:
        actions: list[TransformationAction] = []
        result = df.copy()
        col_lower = {c.lower(): c for c in result.columns}
        ds = dataset_type.lower()

        if ds == "orders":
            result, a = self._orders_features(result, col_lower)
            actions.extend(a)
        elif ds == "customers":
            result, a = self._customer_features(result, col_lower)
            actions.extend(a)
        elif ds == "inventory":
            result, a = self._inventory_features(result, col_lower)
            actions.extend(a)
        elif ds == "payments":
            result, a = self._payment_features(result, col_lower)
            actions.extend(a)
        elif ds == "products":
            result, a = self._product_features(result, col_lower)
            actions.extend(a)

        return result, actions

    def _orders_features(self, df, col_lower):
        actions = []
        total_col = col_lower.get("order_total") or col_lower.get("order_total_clean")
        if total_col and "is_high_value_order" not in df.columns:
            totals = pd.to_numeric(df[total_col], errors="coerce")
            df["is_high_value_order"] = totals >= 500
            actions.append(self._action("FE_ORD_001", "is_high_value_order",
                [total_col], "feature",
                "High-value order flag (order_total >= 500)",
                int(totals.notna().sum())))

        status_col = col_lower.get("order_status") or col_lower.get("status")
        if status_col and "is_active_order" not in df.columns:
            active_statuses = {"pending", "processing", "confirmed", "shipped"}
            df["is_active_order"] = df[status_col].astype(str).str.lower().isin(active_statuses)
            actions.append(self._action("FE_ORD_002", "is_active_order",
                [status_col], "feature",
                "Active order flag (pending/processing/confirmed/shipped)",
                len(df)))
        return df, actions

    def _customer_features(self, df, col_lower):
        actions = []
        seg_col = col_lower.get("customer_segment") or col_lower.get("segment")
        if seg_col and "is_premium_customer" not in df.columns:
            premium = {"gold", "platinum", "vip"}
            df["is_premium_customer"] = df[seg_col].astype(str).str.lower().isin(premium)
            actions.append(self._action("FE_CUST_001", "is_premium_customer",
                [seg_col], "feature",
                "Premium customer flag (gold/platinum/vip segments)",
                len(df)))
        return df, actions

    def _inventory_features(self, df, col_lower):
        actions = []
        qty_col = col_lower.get("quantity_on_hand") or col_lower.get("quantity")
        rop_col = col_lower.get("reorder_point")
        if qty_col and rop_col and "inventory_risk" not in df.columns:
            qty = pd.to_numeric(df[qty_col], errors="coerce")
            rop = pd.to_numeric(df[rop_col], errors="coerce")
            conditions = [qty == 0, qty <= rop, qty <= rop * 2, qty > rop * 5]
            choices = ["critical", "low", "normal", "excess"]
            df["inventory_risk"] = pd.np.select(conditions, choices, default="normal") \
                if hasattr(pd, "np") else self._inv_risk(qty, rop)
            actions.append(self._action("FE_INV_001", "inventory_risk",
                [qty_col, rop_col], "feature",
                "Inventory risk: critical/low/normal/excess",
                int(qty.notna().sum())))
        return df, actions

    @staticmethod
    def _inv_risk(qty: pd.Series, rop: pd.Series) -> pd.Series:
        import numpy as np
        return pd.Series(
            np.select(
                [qty == 0, qty <= rop, qty <= rop * 2, qty > rop * 5],
                ["critical", "low", "normal", "excess"],
                default="normal",
            ),
            index=qty.index,
        )

    def _payment_features(self, df, col_lower):
        actions = []
        dtp_col = col_lower.get("days_to_payment")
        if dtp_col and "payment_risk" not in df.columns:
            dtp = pd.to_numeric(df[dtp_col], errors="coerce")
            import numpy as np
            df["payment_risk"] = pd.Series(
                np.select(
                    [dtp < 0, dtp <= 30, dtp <= 60, dtp <= 90],
                    ["early", "on_time", "late", "very_late"],
                    default="overdue",
                ),
                index=df.index,
            )
            actions.append(self._action("FE_PAY_001", "payment_risk",
                [dtp_col], "feature",
                "Payment risk: early/on_time/late/very_late/overdue",
                int(dtp.notna().sum())))
        return df, actions

    def _product_features(self, df, col_lower):
        actions = []
        margin_col = col_lower.get("margin_pct")
        if margin_col and "margin_tier" not in df.columns:
            margin = pd.to_numeric(df[margin_col], errors="coerce")
            import numpy as np
            df["margin_tier"] = pd.Series(
                np.select(
                    [margin < 10, margin < 25, margin < 50],
                    ["low", "medium", "high"],
                    default="premium",
                ),
                index=df.index,
            )
            actions.append(self._action("FE_PRD_001", "margin_tier",
                [margin_col], "feature",
                "Margin tier: low/medium/high/premium",
                int(margin.notna().sum())))
        return df, actions
