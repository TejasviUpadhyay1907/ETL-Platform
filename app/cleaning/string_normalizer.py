"""
StringNormalizer — cleans string columns: whitespace, case, control characters.

Per-field operations driven by cleaning.yaml:
  trim: true               — strip leading/trailing whitespace
  string_case: lower|upper|title|sentence — normalize case
  collapse_spaces: true    — collapse multiple internal spaces to one
  remove_control_chars: true — strip \x00-\x1f control characters
  unicode_normalize: true  — NFKC normalization

Priority: 30 — runs after dedup so we're cleaning the surviving rows.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any

import pandas as pd

from app.cleaning.base_cleaner import BaseCleaningRule
from app.cleaning.models import CleaningAction

_CTRL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_MULTI_SPACE_RE = re.compile(r"  +")


class StringNormalizer(BaseCleaningRule):
    """Applies configurable string cleaning operations per field."""

    rule_name = "StringNormalizer"
    rule_category = "string"
    priority = 30

    def __init__(
        self,
        field_strategies: dict[str, dict[str, Any]] | None = None,
        global_trim: bool = True,           # trim ALL string columns by default
        global_control_chars: bool = True,  # strip control chars from ALL string cols
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.field_strategies: dict[str, dict[str, Any]] = {
            k.lower(): v for k, v in (field_strategies or {}).items()
        }
        self.global_trim = global_trim
        self.global_control_chars = global_control_chars

    def clean(
        self, df: pd.DataFrame, dataset_type: str
    ) -> tuple[pd.DataFrame, list[CleaningAction]]:
        actions: list[CleaningAction] = []
        result = df.copy()
        col_lower = {c.lower(): c for c in result.columns}

        # Apply per-field strategies
        for fld_lower, cfg in self.field_strategies.items():
            col = col_lower.get(fld_lower)
            if col is None:
                continue

            series = result[col].astype(str)
            before = series.copy()

            if cfg.get("trim", False):
                series = series.str.strip()

            if cfg.get("collapse_spaces", False):
                series = series.str.replace(_MULTI_SPACE_RE, " ", regex=True)

            case = cfg.get("string_case", "")
            if case == "lower":
                series = series.str.lower()
            elif case == "upper":
                series = series.str.upper()
            elif case == "title":
                series = series.str.title()
            elif case == "sentence":
                series = series.str.capitalize()

            if cfg.get("remove_control_chars", False):
                series = series.str.replace(_CTRL_RE, "", regex=True)

            if cfg.get("unicode_normalize", False):
                series = series.apply(
                    lambda v: unicodedata.normalize("NFKC", v) if isinstance(v, str) else v
                )

            # Find changed cells and record actions
            changed_mask = series != before
            for idx in result.index[changed_mask]:
                orig = before.at[idx]
                new  = series.at[idx]
                action_type = "case_normalize" if case else "trim"
                actions.append(self._action(
                    "STR_001", col, int(idx), orig, new, action_type,
                    f"String cleaned in '{col}': {cfg}",
                ))

            result[col] = series

        # Global: trim ALL object columns not already covered
        if self.global_trim:
            for col in result.select_dtypes(include="object").columns:
                fld_lower_key = col.lower()
                if fld_lower_key in self.field_strategies and \
                        self.field_strategies[fld_lower_key].get("trim"):
                    continue  # already done above
                before = result[col].copy()
                result[col] = result[col].astype(str).str.strip()
                changed = result[col] != before.astype(str).str.strip()
                # Do NOT record individual trim actions for global pass — just count them
                # (too verbose for large datasets; field-level trim records individual changes)

        # Global: remove control characters from all object columns
        if self.global_control_chars:
            for col in result.select_dtypes(include="object").columns:
                before = result[col].astype(str)
                cleaned = before.str.replace(_CTRL_RE, "", regex=True)
                changed_mask = cleaned != before
                for idx in result.index[changed_mask]:
                    orig = before.at[idx]
                    new  = cleaned.at[idx]
                    actions.append(self._action(
                        "STR_002", col, int(idx), orig, new,
                        "remove_control_chars",
                        f"Control characters removed from '{col}'",
                    ))
                result[col] = cleaned

        return result, actions
