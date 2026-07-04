"""
PipelineContext — immutable execution context passed through all stages.

Carries the configuration and correlation identifiers for one pipeline run.
Each stage receives this context so it can log with the correct run_id,
apply the correct dataset_type config, and record results against the
correct pipeline_run record.

Design: frozen=True ensures the context is never accidentally mutated
during execution. All per-stage data lives in PipelineResult, not here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.pipeline.models import RetryPolicy


@dataclass(frozen=True)
class PipelineContext:
    """
    Immutable execution context for one pipeline run.

    Created once by PipelineExecutor and passed unchanged through all stages.
    """

    pipeline_run_id:  str
    pipeline_name:    str
    dataset_type:     str
    source_file_path: str = ""
    original_filename: str = ""
    ingestion_event_id: str | None = None
    triggered_by:     str = "manual"
    trigger_type:     str = "manual"
    retry_policy:     RetryPolicy = field(default_factory=RetryPolicy.default)
    dry_run:          bool = False
    max_runtime_seconds: int = 3600
    extra_config:     dict[str, Any] = field(default_factory=dict)

    def with_ingestion_event(self, event_id: str) -> "PipelineContext":
        """Return a new context with ingestion_event_id set."""
        return PipelineContext(
            pipeline_run_id=self.pipeline_run_id,
            pipeline_name=self.pipeline_name,
            dataset_type=self.dataset_type,
            source_file_path=self.source_file_path,
            original_filename=self.original_filename,
            ingestion_event_id=event_id,
            triggered_by=self.triggered_by,
            trigger_type=self.trigger_type,
            retry_policy=self.retry_policy,
            dry_run=self.dry_run,
            max_runtime_seconds=self.max_runtime_seconds,
            extra_config=self.extra_config,
        )
