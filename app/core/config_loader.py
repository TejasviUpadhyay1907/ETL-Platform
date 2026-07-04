"""
Configuration loader — merges YAML defaults with environment variable overrides.

Reads application-level YAML config files and makes their values available
as a dictionary that can supplement the Pydantic AppConfig. Environment
variables always take precedence over YAML values (12-factor app principle).

Usage is internal — use get_config() from config.py as the single access point.
"""

from pathlib import Path
from typing import Any

import yaml

from app.logging.logger import get_logger

logger = get_logger(__name__)

CONFIG_DIR = Path("config")


def load_yaml_config(file_path: Path) -> dict[str, Any]:
    """
    Load a YAML configuration file and return its contents as a dictionary.

    Args:
        file_path: Path to the YAML file.

    Returns:
        Parsed YAML contents as a dict. Returns empty dict if file not found.
    """
    if not file_path.exists():
        logger.debug(f"Config file not found, skipping: {file_path}")
        return {}

    try:
        with file_path.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
            return data if isinstance(data, dict) else {}
    except yaml.YAMLError as e:
        logger.error(f"Failed to parse YAML config at {file_path}: {e}")
        return {}


def load_app_yaml() -> dict[str, Any]:
    """Load the application-level YAML defaults from config/app.yaml."""
    return load_yaml_config(CONFIG_DIR / "app.yaml")


def load_logging_yaml() -> dict[str, Any]:
    """Load the logging configuration from config/logging.yaml."""
    return load_yaml_config(CONFIG_DIR / "logging.yaml")


def load_dataset_config(dataset_type: str, config_type: str) -> dict[str, Any]:
    """
    Load a dataset-specific configuration file.

    Args:
        dataset_type: One of: orders, customers, products, inventory, suppliers, payments.
        config_type: One of: schema, rules, cleaning, transformations.

    Returns:
        Parsed YAML contents as a dict.
    """
    file_path = CONFIG_DIR / "datasets" / dataset_type / f"{config_type}.yaml"
    config = load_yaml_config(file_path)

    if not config:
        logger.warning(
            f"Dataset config not found or empty",
            dataset_type=dataset_type,
            config_type=config_type,
            path=str(file_path),
        )

    return config


def load_all_dataset_configs() -> dict[str, dict[str, Any]]:
    """
    Load all dataset configurations for all six dataset types.

    Returns:
        Nested dict: {dataset_type: {config_type: config_data}}
    """
    from app.utils.constants import DatasetType

    all_configs: dict[str, dict[str, Any]] = {}

    for dataset in DatasetType:
        dataset_name = dataset.value
        all_configs[dataset_name] = {
            "schema": load_dataset_config(dataset_name, "schema"),
            "rules": load_dataset_config(dataset_name, "rules"),
            "cleaning": load_dataset_config(dataset_name, "cleaning"),
            "transformations": load_dataset_config(dataset_name, "transformations"),
        }
        logger.debug(f"Loaded config for dataset: {dataset_name}")

    return all_configs
