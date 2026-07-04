"""
LookupEnricher — standalone utility for FK resolution from the database.

Used by the Transformation Engine when reference data needs to be fetched
from PostgreSQL rather than from in-memory lookup tables.

For static lookups (country → region, currency → symbol), use LookupTransformer.
For DB-backed lookups (customer_id → customer_name), use this module.
"""

from __future__ import annotations

from typing import Any

import pandas as pd
from sqlalchemy.orm import Session


class LookupEnricher:
    """
    Fetches reference data from the database and enriches a DataFrame.

    Usage:
        enricher = LookupEnricher(session)
        df = enricher.enrich_fk(
            df=orders_df,
            fk_col="customer_id",
            ref_table="customers",
            ref_key="id",
            ref_value="email",
            target_col="customer_email",
        )
    """

    def __init__(self, session: Session) -> None:
        self._session = session

    def enrich_fk(
        self,
        df: pd.DataFrame,
        fk_col: str,
        ref_table: str,
        ref_key: str,
        ref_value: str,
        target_col: str | None = None,
    ) -> pd.DataFrame:
        """
        Enrich df[fk_col] with a resolved value from a reference table.

        Args:
            df:         Source DataFrame.
            fk_col:     FK column in df (e.g. customer_id).
            ref_table:  Reference table name (e.g. customers).
            ref_key:    Key column in reference table (e.g. id).
            ref_value:  Value column to fetch (e.g. email).
            target_col: Name for the new enriched column. Defaults to ref_value.

        Returns:
            DataFrame with enriched column added.
        """
        target = target_col or ref_value
        col_lower = {c.lower(): c for c in df.columns}
        fk_orig = col_lower.get(fk_col.lower())
        if fk_orig is None:
            return df

        try:
            from sqlalchemy import text
            fk_values = df[fk_orig].dropna().unique().tolist()
            if not fk_values:
                return df

            placeholders = ", ".join([f"'{v}'" for v in fk_values[:1000]])
            stmt = text(
                f"SELECT {ref_key}, {ref_value} FROM {ref_table} "
                f"WHERE {ref_key} IN ({placeholders})"
            )
            rows = self._session.execute(stmt).fetchall()
            lookup: dict[str, Any] = {str(r[0]): r[1] for r in rows}

            result = df.copy()
            result[target] = result[fk_orig].astype(str).map(lookup)
            return result

        except Exception as exc:
            from app.logging.logger import get_logger
            get_logger(__name__).warning(
                f"LookupEnricher.enrich_fk failed for '{fk_col}': {exc}"
            )
            return df
