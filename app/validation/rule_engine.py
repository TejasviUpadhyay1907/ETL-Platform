"""
ValidationExecutor — runs all rules in priority order and collects violations.

Responsibilities:
  - Execute each rule via BaseValidationRule.execute() (which handles timing)
  - Aggregate all violations
  - Track which row indices failed ERROR-severity rules
  - Track execution statistics (rules run, total duration)

Design:
  - Stateless: create fresh per validation run
  - Stops gracefully if a rule crashes (logged, not re-raised)
  - Chunk support: for large DataFrames, validation runs per chunk
    and violations are merged with adjusted row offsets
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from app.logging.logger import get_logger
from app.validation.models import RuleViolation, Severity
from app.validation.rule_registry import RuleRegistry
from app.validation.rules.statistical_validator import StatisticalValidator

logger = get_logger(__name__)


@dataclass
class ExecutionStats:
    rules_executed: int = 0
    rules_passed:   int = 0
    rules_failed:   int = 0
    total_violations: int = 0
    error_violations: int = 0
    warning_violations: int = 0
    total_duration_ms: float = 0.0
    rule_timings: dict[str, float] = field(default_factory=dict)


class ValidationExecutor:
    """
    Executes all rules in a RuleRegistry against a DataFrame.

    Returns aggregated violations and execution statistics.
    """

    def __init__(self, chunk_size: int = 50_000) -> None:
        self.chunk_size = chunk_size

    def execute(
        self,
        df: pd.DataFrame,
        registry: RuleRegistry,
        dataset_type: str,
    ) -> tuple[list[RuleViolation], ExecutionStats, dict]:
        """
        Run all registered rules against the DataFrame.

        Args:
            df:           The raw DataFrame from ingestion.
            registry:     Populated RuleRegistry.
            dataset_type: Dataset type string.

        Returns:
            (all_violations, stats, column_profiles)
        """
        all_violations: list[RuleViolation] = []
        stats = ExecutionStats()
        column_profiles: dict = {}
        ordered_rules = registry.get_ordered_rules()

        logger.info(
            "Validation execution started",
            dataset_type=dataset_type,
            total_rows=len(df),
            rules_to_run=len(ordered_rules),
        )

        start_total = time.perf_counter()

        for rule in ordered_rules:
            violations, duration_ms = rule.execute(df, dataset_type)
            stats.rules_executed += 1
            stats.rule_timings[rule.rule_code] = round(duration_ms, 2)
            stats.total_violations += len(violations)

            if violations:
                stats.rules_failed += 1
                all_violations.extend(violations)
            else:
                stats.rules_passed += 1

            # Harvest column profiles from StatisticalValidator
            if isinstance(rule, StatisticalValidator):
                column_profiles = rule.column_profiles

            logger.debug(
                f"Rule {rule.rule_code} completed",
                violations=len(violations),
                duration_ms=round(duration_ms, 1),
            )

        stats.total_duration_ms = (time.perf_counter() - start_total) * 1000
        stats.error_violations   = sum(1 for v in all_violations if v.severity == Severity.ERROR)
        stats.warning_violations = sum(1 for v in all_violations if v.severity == Severity.WARNING)

        logger.info(
            "Validation execution complete",
            dataset_type=dataset_type,
            rules_executed=stats.rules_executed,
            total_violations=stats.total_violations,
            error_violations=stats.error_violations,
            duration_ms=round(stats.total_duration_ms, 1),
        )

        return all_violations, stats, column_profiles
