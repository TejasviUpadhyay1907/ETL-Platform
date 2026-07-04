"""
LookupTransformer — enriches records with reference data.

Joins:
  - Country code → country name + region
  - Currency code → currency name + symbol
  - State code → state name
  - Product category → department
  - Any config-driven static lookup table

Lookups are loaded from in-memory dictionaries (fast, no DB join needed).
For DB-backed lookups, the reference_data dict is pre-fetched by the caller.
Priority: 50
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from app.transformation.base_transformer import BaseTransformer
from app.transformation.models import TransformationAction

# ── Built-in lookup tables ─────────────────────────────────────────────────

COUNTRY_TO_REGION: dict[str, str] = {
    "US": "North America", "CA": "North America", "MX": "North America",
    "GB": "Europe", "DE": "Europe", "FR": "Europe", "IT": "Europe",
    "ES": "Europe", "NL": "Europe", "SE": "Europe", "NO": "Europe",
    "AU": "Oceania", "NZ": "Oceania",
    "JP": "Asia Pacific", "CN": "Asia Pacific", "IN": "Asia Pacific",
    "SG": "Asia Pacific", "HK": "Asia Pacific", "KR": "Asia Pacific",
    "BR": "Latin America", "AR": "Latin America", "CL": "Latin America",
    "ZA": "Africa", "NG": "Africa", "KE": "Africa",
}

CURRENCY_SYMBOLS: dict[str, str] = {
    "USD": "$", "GBP": "£", "EUR": "€", "JPY": "¥", "AUD": "A$",
    "CAD": "C$", "CHF": "Fr", "CNY": "¥", "INR": "₹", "BRL": "R$",
    "ZAR": "R", "MXN": "$", "SGD": "S$", "HKD": "HK$", "KRW": "₩",
}


class LookupTransformer(BaseTransformer):
    """Enriches records with reference data from lookup dictionaries."""

    transformer_name = "LookupTransformer"
    transformer_category = "lookup"
    priority = 50

    def __init__(
        self,
        # {source_column: {lookup_value → enriched_value}}
        lookup_tables: dict[str, dict[str, str]] | None = None,
        # {source_column: new_column_name}
        lookup_targets: dict[str, str] | None = None,
        enrich_country: bool = True,
        enrich_currency: bool = True,
        country_col: str = "country",
        currency_col: str = "currency",
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.lookup_tables = {
            k.lower(): v for k, v in (lookup_tables or {}).items()
        }
        self.lookup_targets = {
            k.lower(): v for k, v in (lookup_targets or {}).items()
        }
        self.enrich_country = enrich_country
        self.enrich_currency = enrich_currency
        self.country_col = country_col.lower()
        self.currency_col = currency_col.lower()

    def transform(
        self, df: pd.DataFrame, dataset_type: str
    ) -> tuple[pd.DataFrame, list[TransformationAction]]:
        actions: list[TransformationAction] = []
        result = df.copy()
        col_lower = {c.lower(): c for c in result.columns}

        # Config-driven custom lookups
        for src_lower, table in self.lookup_tables.items():
            src = col_lower.get(src_lower)
            if src is None:
                continue
            target_col = self.lookup_targets.get(src_lower, f"{src_lower}_enriched")
            result[target_col] = result[src].astype(str).str.strip().str.upper().map(table)
            matched = result[target_col].notna().sum()
            actions.append(self._action(
                "LKP_001", target_col, [src], "enrich",
                f"Lookup enrichment: '{src}' → '{target_col}'",
                int(matched),
            ))
            col_lower[target_col.lower()] = target_col

        # Built-in: country → region
        if self.enrich_country:
            country_orig = col_lower.get(self.country_col)
            if country_orig and "region" not in df.columns:
                result["region"] = (
                    result[country_orig].astype(str).str.strip().str.upper()
                    .map(COUNTRY_TO_REGION)
                    .fillna("Unknown")
                )
                matched = (result["region"] != "Unknown").sum()
                actions.append(self._action(
                    "LKP_002", "region", [country_orig], "enrich",
                    f"Region derived from '{country_orig}'",
                    int(matched),
                ))

        # Built-in: currency → symbol
        if self.enrich_currency:
            currency_orig = col_lower.get(self.currency_col)
            if currency_orig and "currency_symbol" not in df.columns:
                result["currency_symbol"] = (
                    result[currency_orig].astype(str).str.strip().str.upper()
                    .map(CURRENCY_SYMBOLS)
                    .fillna("")
                )
                matched = (result["currency_symbol"] != "").sum()
                if matched > 0:
                    actions.append(self._action(
                        "LKP_003", "currency_symbol", [currency_orig], "enrich",
                        f"Currency symbol from '{currency_orig}'",
                        int(matched),
                    ))

        return result, actions
