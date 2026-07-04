"""
BaseValidationRule — abstract interface all validation rules implement.

Strategy Pattern: the ValidationExecutor works against this interface only.
Each concrete rule is a self-contained, independently-testable strategy.

Design decisions:
- validate() receives the full DataFrame and returns a list of RuleViolation objects
  (empty list = all records pass this rule)
- Rules NEVER modify the DataFrame — they only read it
- Rules are stateless between calls — safe for reuse across multiple datasets
- The rule_code, category, and severity are immutable class attributes
  (or set via constructor for config-loaded rules)
- enabled / priority allow the RuleRegistry to filter and order execution
"""

from __future__ import annotations

import abc
import time
from typing import Any

import pandas as pd

from app.validation.models import RuleViolation


class BaseValidationRule(abc.ABC):
    """Abstract base class for all validation rules."""

    # Override in subclasses or set via constructor
    rule_code: str = "BASE_RULE"
    rule_category: str = "base"
    default_severity: str = "error"
    description: str = ""
    enabled: bool = True
    priority: int = 100   # lower = runs first

    def __init__(
        self,
        severity: str | None = None,
        enabled: bool = True,
        priority: int | None = None,
        params: dict[str, Any] | None = None,
    ) -> None:
        """
        Args:
            severity: Override the default severity ('error', 'warning', 'info').
            enabled:  Whether this rule participates in validation runs.
            priority: Execution order (lower = runs first).
            params:   Rule-specific parameters from YAML config.
        """
        if severity is not None:
            self.default_severity = severity
        self.enabled = enabled
        if priority is not None:
            self.priority = priority
        self.params: dict[str, Any] = params or {}

    @abc.abstractmethod
    def validate(self, df: pd.DataFrame, dataset_type: str) -> list[RuleViolation]:
        """
        Analyze the DataFrame and return all violations found.

        Args:
            df:           The raw DataFrame from the ingestion stage.
                          MUST NOT be modified.
            dataset_type: The dataset type string (e.g. 'orders').

        Returns:
            List of RuleViolation objects. Empty list means no violations.
        """

    def execute(self, df: pd.DataFrame, dataset_type: str) -> tuple[list[RuleViolation], float]:
        """
        Execute the rule with timing.

        Returns (violations, duration_ms).
        Safe wrapper around validate() that catches unexpected exceptions.
        """
        if not self.enabled:
            return [], 0.0

        start = time.perf_counter()
        try:
            violations = self.validate(df, dataset_type)
        except Exception as exc:
            from app.logging.logger import get_logger
            logger = get_logger(__name__)
            logger.error(
                f"Rule {self.rule_code} raised an unexpected error: {exc}",
                rule=self.rule_code,
                dataset_type=dataset_type,
                exc_info=True,
            )
            violations = []
        duration_ms = (time.perf_counter() - start) * 1000
        return violations, duration_ms

    def _violation(
        self,
        field_name: str | None,
        row_index: int | None,
        actual_value: Any,
        expected: str,
        message: str,
        suggested_fix: str = "",
        severity: str | None = None,
    ) -> RuleViolation:
        """Convenience factory for building RuleViolation instances."""
        return RuleViolation(
            rule_code=self.rule_code,
            rule_category=self.rule_category,
            severity=severity or self.default_severity,
            field_name=field_name,
            row_index=row_index,
            actual_value=actual_value,
            expected=expected,
            message=message,
            suggested_fix=suggested_fix,
            rule_description=self.description,
        )

    def __repr__(self) -> str:
        return (
            f"{self.__class__.__name__}("
            f"code={self.rule_code!r}, "
            f"severity={self.default_severity!r}, "
            f"enabled={self.enabled})"
        )
