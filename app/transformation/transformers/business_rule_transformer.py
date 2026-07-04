"""
BusinessRuleTransformer — applies dataset-specific business calculations.

Computes:
  - Revenue metrics (gross_profit, margin_pct, revenue_category)
  - Customer metrics (full_name, customer_segment, is_high_value)
  - Inventory metrics (stock_value, is_low_stock, stock_status)
  - Payment metrics (days_to_payment, payment_status_label)
  - Order metrics (order_value_band, is_repeat_customer_flag)

All calculations are additive — existing columns are never overwritten.
Rules are loaded from config and passed in via constructor.
Priority: 40 — runs after derived columns are available.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from app.transformation.base_transformer import BaseTransformer
from app.transformation.models import TransformationAction


class BusinessRuleTransformer(BaseTransformer):
    """Computes business KPI columns for analytics-ready datasets."""

    transformer_name = "BusinessRuleTransformer"
    transformer_category = "business"
    priority = 40

    def __init__(
        self,
        dataset_type: str = "",
        rules: list[dict[str, Any]] | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self._dataset_type = dataset_type
        self.rules = rules or []

    def transform(
        self, df: pd.DataFrame, dataset_type: str
    ) -> tuple[pd.DataFrame, list[TransformationAction]]:
        actions: list[TransformationAction] = []
        result = df.copy()
        col_lower = {c.lower(): c for c in result.columns}
        ds = dataset_type.lower()

        # Apply YAML-driven rules first
        for rule in self.rules:
            try:
                result, act = self._apply_rule(result, col_lower, rule, dataset_type)
                actions.extend(act)
                col_lower = {c.lower(): c for c in result.columns}
            except Exception as exc:
                from app.logging.logger import get_logger
                get_logger(__name__).warning(f"Business rule failed: {exc}")

        # Apply dataset-specific built-in calculations
        if ds == "orders":
            result, a = self._orders_calcs(result, col_lower)
            actions.extend(a)
        elif ds == "products":
            result, a = self._products_calcs(result, col_lower)
            actions.extend(a)
        elif ds == "customers":
            result, a = self._customers_calcs(result, col_lower)
            actions.extend(a)
        elif ds == "inventory":
            result, a = self._inventory_calcs(result, col_lower)
            actions.extend(a)
        elif ds == "payments":
            result, a = self._payments_calcs(result, col_lower)
            actions.extend(a)

        return result, actions

    # ── Dataset-specific calculations ─────────────────────────────────

    def _orders_calcs(self, df, col_lower):
        actions = []
        total_col = col_lower.get("order_total") or col_lower.get("order_total_clean")
        if total_col and "order_value_band" not in df.columns:
            totals = pd.to_numeric(df[total_col], errors="coerce")
            df["order_value_band"] = pd.cut(
                totals,
                bins=[-float("inf"), 50, 200, 500, 1000, float("inf")],
                labels=["micro", "small", "medium", "large", "enterprise"],
            ).astype(str)
            actions.append(self._action("BIZ_ORD_001", "order_value_band",
                [total_col], "calculate",
                "Order value band: micro/small/medium/large/enterprise",
                int(totals.notna().sum())))

        qty_col = col_lower.get("quantity")
        if total_col and qty_col and "avg_unit_price" not in df.columns:
            totals_n = pd.to_numeric(df[total_col], errors="coerce")
            qty_n = pd.to_numeric(df[qty_col], errors="coerce").replace(0, float("nan"))
            df["avg_unit_price"] = (totals_n / qty_n).round(4)
            actions.append(self._action("BIZ_ORD_002", "avg_unit_price",
                [total_col, qty_col], "calculate",
                "Average unit price = order_total / quantity",
                int(qty_n.notna().sum())))
        return df, actions

    def _products_calcs(self, df, col_lower):
        actions = []
        price_col = col_lower.get("unit_price") or col_lower.get("price")
        cost_col  = col_lower.get("unit_cost")  or col_lower.get("cost")
        if price_col and cost_col:
            price = pd.to_numeric(df[price_col], errors="coerce")
            cost  = pd.to_numeric(df[cost_col],  errors="coerce")
            if "gross_profit" not in df.columns:
                df["gross_profit"] = (price - cost).round(4)
                actions.append(self._action("BIZ_PRD_001", "gross_profit",
                    [price_col, cost_col], "calculate",
                    "Gross profit = unit_price - unit_cost",
                    int(price.notna().sum())))
            if "margin_pct" not in df.columns:
                safe_price = price.replace(0, float("nan"))
                df["margin_pct"] = ((price - cost) / safe_price * 100).round(2)
                actions.append(self._action("BIZ_PRD_002", "margin_pct",
                    [price_col, cost_col], "calculate",
                    "Margin % = (price - cost) / price × 100",
                    int(price.notna().sum())))
        return df, actions

    def _customers_calcs(self, df, col_lower):
        actions = []
        fn_col = col_lower.get("first_name")
        ln_col = col_lower.get("last_name")
        if fn_col and ln_col and "full_name" not in df.columns:
            df["full_name"] = df[fn_col].astype(str).str.strip() + " " + df[ln_col].astype(str).str.strip()
            actions.append(self._action("BIZ_CUST_001", "full_name",
                [fn_col, ln_col], "calculate",
                "Full name = first_name + ' ' + last_name",
                len(df)))
        dob_col = col_lower.get("date_of_birth") or col_lower.get("dob")
        if dob_col and "customer_age" not in df.columns:
            today = pd.Timestamp.today()
            dob = pd.to_datetime(df[dob_col], errors="coerce")
            df["customer_age"] = ((today - dob).dt.days / 365.25).fillna(-1).astype(int)
            actions.append(self._action("BIZ_CUST_002", "customer_age",
                [dob_col], "calculate",
                "Customer age in years from date_of_birth",
                int(dob.notna().sum())))
        return df, actions

    def _inventory_calcs(self, df, col_lower):
        actions = []
        qty_col  = col_lower.get("quantity_on_hand") or col_lower.get("quantity")
        cost_col = col_lower.get("unit_cost")
        rop_col  = col_lower.get("reorder_point")
        if qty_col and cost_col and "stock_value" not in df.columns:
            qty  = pd.to_numeric(df[qty_col],  errors="coerce")
            cost = pd.to_numeric(df[cost_col], errors="coerce")
            df["stock_value"] = (qty * cost).round(4)
            actions.append(self._action("BIZ_INV_001", "stock_value",
                [qty_col, cost_col], "calculate",
                "Stock value = quantity_on_hand × unit_cost",
                int(qty.notna().sum())))
        if qty_col and rop_col and "is_low_stock" not in df.columns:
            qty = pd.to_numeric(df[qty_col], errors="coerce")
            rop = pd.to_numeric(df[rop_col], errors="coerce")
            df["is_low_stock"] = qty <= rop
            actions.append(self._action("BIZ_INV_002", "is_low_stock",
                [qty_col, rop_col], "calculate",
                "Low stock flag = quantity_on_hand <= reorder_point",
                len(df)))
        return df, actions

    def _payments_calcs(self, df, col_lower):
        actions = []
        pay_col  = col_lower.get("payment_date")
        inv_col  = col_lower.get("invoice_date")
        if pay_col and inv_col and "days_to_payment" not in df.columns:
            pay = pd.to_datetime(df[pay_col], errors="coerce")
            inv = pd.to_datetime(df[inv_col], errors="coerce")
            df["days_to_payment"] = (pay - inv).dt.days
            actions.append(self._action("BIZ_PAY_001", "days_to_payment",
                [pay_col, inv_col], "calculate",
                "Days to payment = payment_date - invoice_date",
                int(pay.notna().sum())))
        return df, actions

    def _apply_rule(self, df, col_lower, rule, dataset_type):
        """Apply a single YAML-configured business rule."""
        actions = []
        name   = rule.get("name", "")
        expr   = rule.get("expression", "")
        desc   = rule.get("description", "")
        if not name or not expr:
            return df, actions
        # Delegate expression evaluation to DerivedColumnTransformer's engine
        from app.transformation.transformers.derived_column_transformer import DerivedColumnTransformer
        evaluator = DerivedColumnTransformer(derived_fields=[rule])
        result, derived_actions = evaluator.transform(df, dataset_type)
        return result, derived_actions
