"""
PipelineRegistry — loads, stores, and resolves pipeline definitions.

Pipeline definitions are loaded from config/pipelines/*.yaml or registered
programmatically. The registry maps dataset types to pipeline configurations.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.logging.logger import get_logger
from app.pipeline.models import RetryPolicy

logger = get_logger(__name__)


@dataclass
class PipelineDefinition:
    """Configuration definition for one pipeline."""

    name: str
    dataset_type: str
    enabled: bool = True
    stage_order: list[str] = field(default_factory=lambda: [
        "ingestion", "validation", "cleaning", "transformation", "load"
    ])
    retry_policy: RetryPolicy = field(default_factory=RetryPolicy.default)
    max_runtime_seconds: int = 3600
    description: str = ""
    version: str = "1.0"
    tags: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "PipelineDefinition":
        retry_cfg = d.get("retry_policy", {})
        return cls(
            name=d.get("name", d.get("pipeline_name", "")),
            dataset_type=d.get("dataset_type", ""),
            enabled=d.get("enabled", True),
            stage_order=d.get("stage_order", cls.__dataclass_fields__["stage_order"].default_factory()),
            retry_policy=RetryPolicy.from_dict(retry_cfg) if retry_cfg else RetryPolicy.default(),
            max_runtime_seconds=d.get("max_runtime_seconds", 3600),
            description=d.get("description", ""),
            version=d.get("version", "1.0"),
            tags=d.get("tags", []),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "dataset_type": self.dataset_type,
            "enabled": self.enabled,
            "stage_order": self.stage_order,
            "max_runtime_seconds": self.max_runtime_seconds,
            "description": self.description,
            "version": self.version,
        }


class PipelineRegistry:
    """Stores and resolves pipeline definitions by name and dataset type."""

    def __init__(self) -> None:
        self._by_name: dict[str, PipelineDefinition] = {}
        self._by_dataset: dict[str, PipelineDefinition] = {}
        self._load_defaults()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def register(self, definition: PipelineDefinition) -> None:
        self._by_name[definition.name] = definition
        if definition.dataset_type:
            self._by_dataset[definition.dataset_type] = definition
        logger.debug(f"Pipeline registered: {definition.name}")

    def get_by_name(self, name: str) -> PipelineDefinition | None:
        return self._by_name.get(name)

    def get_by_dataset_type(self, dataset_type: str) -> PipelineDefinition | None:
        return self._by_dataset.get(dataset_type)

    def list_all(self) -> list[PipelineDefinition]:
        return list(self._by_name.values())

    def count(self) -> int:
        return len(self._by_name)

    def list_enabled(self) -> list[PipelineDefinition]:
        return [d for d in self._by_name.values() if d.enabled]

    def enable(self, name: str) -> bool:
        defn = self._by_name.get(name)
        if defn:
            defn.enabled = True
            return True
        return False

    def disable(self, name: str) -> bool:
        defn = self._by_name.get(name)
        if defn:
            defn.enabled = False
            return True
        return False

    # ------------------------------------------------------------------
    # Default pipeline definitions (one per dataset type)
    # ------------------------------------------------------------------

    def _load_defaults(self) -> None:
        from app.utils.constants import DatasetType
        for ds in DatasetType:
            defn = PipelineDefinition(
                name=f"{ds.value}_pipeline",
                dataset_type=ds.value,
                enabled=True,
                description=f"Standard ETL pipeline for {ds.value} datasets",
            )
            self.register(defn)
        logger.debug(f"Default pipelines registered: {len(self._by_name)}")


# Module-level singleton
_registry: PipelineRegistry | None = None


def get_registry() -> PipelineRegistry:
    global _registry
    if _registry is None:
        _registry = PipelineRegistry()
    return _registry
