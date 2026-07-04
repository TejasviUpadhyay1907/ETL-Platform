"""
RetryManager — manages retry logic with configurable backoff strategies.

Supports:
  immediate   — retry immediately with no delay
  linear      — delay increases linearly: delay × attempt
  exponential — delay doubles each attempt: delay × multiplier^attempt

Design:
- Stateless: tracks nothing between calls
- The PipelineExecutor holds retry state (current attempt count)
- Delays are computed deterministically from RetryPolicy
"""

from __future__ import annotations

import time
from typing import Any

from app.logging.logger import get_logger
from app.pipeline.models import RetryPolicy

logger = get_logger(__name__)


class RetryManager:
    """Computes retry delays and determines whether to retry a failed stage."""

    def __init__(self, policy: RetryPolicy) -> None:
        self.policy = policy

    def should_retry(
        self,
        attempt: int,
        failed_stage: str | None = None,
        exception: Exception | None = None,
    ) -> bool:
        """
        Determine whether another retry attempt should be made.

        Args:
            attempt:      Current attempt number (0 = first try, 1 = first retry).
            failed_stage: Name of the stage that failed (for stage-scoped policies).
            exception:    The exception that caused the failure.

        Returns:
            True if a retry should be attempted.
        """
        if attempt >= self.policy.max_retries:
            logger.debug(
                "Max retries reached",
                attempt=attempt,
                max_retries=self.policy.max_retries,
            )
            return False

        # Stage-scoped retry: only retry specific stages
        if self.policy.retry_on_stages and failed_stage:
            if failed_stage not in self.policy.retry_on_stages:
                logger.debug(
                    f"Stage '{failed_stage}' not in retry_on_stages list — no retry",
                    stage=failed_stage,
                )
                return False

        return True

    def wait(self, attempt: int) -> None:
        """
        Block for the computed delay for the given retry attempt.

        Args:
            attempt: Current attempt number (0-indexed).
        """
        delay = self.policy.get_delay(attempt)
        if delay > 0:
            logger.info(
                f"Retry {attempt + 1}/{self.policy.max_retries} — waiting {delay:.1f}s",
                attempt=attempt + 1,
                delay_seconds=delay,
                strategy=self.policy.backoff_strategy,
            )
            time.sleep(delay)
        else:
            logger.info(
                f"Retry {attempt + 1}/{self.policy.max_retries} — immediate",
                attempt=attempt + 1,
            )

    def get_delay_seconds(self, attempt: int) -> float:
        """Return the delay in seconds for the given attempt without sleeping."""
        return self.policy.get_delay(attempt)
