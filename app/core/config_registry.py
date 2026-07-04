"""
Configuration registry — provides a single access point for all configuration.

Wraps the AppConfig singleton and the dataset-specific YAML configurations.
All application code should access configuration exclusively through this module
or directly via get_config() for the AppConfig instance.

This registry pattern ensures:
- Configuration is loaded once and cached
- Dataset configs are lazily loaded on first access
- Invalid dataset type requests fail fast with a clear error
"""

from typing import Any

from app.core.exceptions import ConfigurationException
from app.logging.logger import get_logger
from app.utils.constants import DatasetType

logger = get_logger(__name__)

# Module-level cache for dataset configurations
_dataset_configs: dict[str, dict[str, Any]] | None = None


def get_dataset_schema(dataset_type: DatasetType | str) -> dict[str, Any]:
    """
    Retrieve the schema definition for a given dataset type.

    Args:
        dataset_type: DatasetType enum value or string name.

    Returns:
        Schema configuration dictionary.

    Raises:
        ConfigurationException: If the dataset type is unknown or config is missing.
    """
    configs = _get_all_dataset_configs()
    name = dataset_type.value if isinstance(dataset_type, DatasetType) else dataset_type

    if name not in configs:
        raise ConfigurationException(
            message=f"No configuration found for dataset type: '{name}'. "
            f"Supported types: {[d.value for d in DatasetType]}",
            missing_key=f"datasets.{name}",
        )

    return configs[name].get("schema", {})


def get_dataset_rules(dataset_type: DatasetType | str) -> dict[str, Any]:
    """Retrieve the validation rules config for a dataset type."""
    configs = _get_all_dataset_configs()
    name = dataset_type.value if isinstance(dataset_type, DatasetType) else dataset_type
    return configs.get(name, {}).get("rules", {})


def get_dataset_cleaning_config(dataset_type: DatasetType | str) -> dict[str, Any]:
    """Retrieve the cleaning strategies config for a dataset type."""
    configs = _get_all_dataset_configs()
    name = dataset_type.value if isinstance(dataset_type, DatasetType) else dataset_type
    return configs.get(name, {}).get("cleaning", {})


def get_dataset_transformation_config(dataset_type: DatasetType | str) -> dict[str, Any]:
    """Retrieve the transformation rules config for a dataset type."""
    configs = _get_all_dataset_configs()
    name = dataset_type.value if isinstance(dataset_type, DatasetType) else dataset_type
    return configs.get(name, {}).get("transformations", {})


def _get_all_dataset_configs() -> dict[str, dict[str, Any]]:
    """Lazily load and cache all dataset configurations."""
    global _dataset_configs

    if _dataset_configs is None:
        from app.core.config_loader import load_all_dataset_configs

        _dataset_configs = load_all_dataset_configs()
        logger.info(
            "Dataset configurations loaded",
            dataset_count=len(_dataset_configs),
        )

    return _dataset_configs


def reload_dataset_configs() -> None:
    """
    Force reload all dataset configurations from disk.

    Use this if configuration files are updated at runtime (e.g., in tests).
    """
    global _dataset_configs
    _dataset_configs = None
    logger.info("Dataset configuration cache cleared — will reload on next access")
