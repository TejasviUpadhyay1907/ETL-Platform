"""
Unit tests for the application configuration system.

Tests verify:
- Configuration loads from environment variables
- Default values are sensible
- Derived properties work correctly
- Validation catches invalid values
"""

import pytest

from app.core.config import AppConfig, get_config


class TestAppConfig:
    """Tests for AppConfig Pydantic model."""

    def test_config_loads_successfully(self):
        """Configuration must load without raising exceptions."""
        config = AppConfig()
        assert config is not None

    def test_default_app_name(self):
        """Default app name is set."""
        config = AppConfig()
        assert config.app_name == "ETL Platform"

    def test_default_environment_is_development(self):
        """Default environment is development."""
        config = AppConfig()
        assert config.app_env == "development"

    def test_is_development_property(self):
        """is_development returns True when env is 'development'."""
        config = AppConfig(app_env="development")
        assert config.is_development is True
        assert config.is_production is False

    def test_is_production_property(self):
        """is_production returns True when env is 'production'."""
        config = AppConfig(app_env="production")
        assert config.is_production is True
        assert config.is_development is False

    def test_max_upload_size_bytes(self):
        """max_upload_size_bytes correctly converts MB to bytes."""
        config = AppConfig(max_upload_size_mb=100)
        assert config.max_upload_size_bytes == 100 * 1024 * 1024

    def test_allowed_file_types_default(self):
        """Default allowed file types include csv, xlsx, xls."""
        config = AppConfig()
        assert "csv" in config.allowed_file_types
        assert "xlsx" in config.allowed_file_types

    def test_allowed_file_types_from_comma_string(self):
        """Comma-separated string is stored as-is; parsed list available via property."""
        config = AppConfig(allowed_file_types="csv,xlsx,xls")
        assert config.allowed_file_types_list == ["csv", "xlsx", "xls"]

    def test_invalid_environment_raises_error(self):
        """Invalid environment value raises ValidationError."""
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            AppConfig(app_env="invalid_env")

    def test_invalid_log_level_raises_error(self):
        """Invalid log level raises ValidationError."""
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            AppConfig(log_level="VERBOSE")

    def test_port_range_validation(self):
        """Port must be in valid range."""
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            AppConfig(port=80)  # Below minimum of 1024

    def test_quality_threshold_bounds(self):
        """Quality thresholds must be 0-100."""
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            AppConfig(quality_score_warning_threshold=150)

    def test_cors_origins_from_comma_string(self):
        """CORS origins are parsed from comma-separated string via property."""
        config = AppConfig(cors_origins="http://localhost:3000,http://localhost:8000")
        assert len(config.cors_origins_list) == 2
        assert "http://localhost:3000" in config.cors_origins_list


class TestGetConfig:
    """Tests for the get_config singleton function."""

    def test_get_config_returns_config(self):
        """get_config() returns an AppConfig instance."""
        config = get_config()
        assert isinstance(config, AppConfig)

    def test_get_config_is_singleton(self):
        """get_config() returns the same instance on repeated calls."""
        config1 = get_config()
        config2 = get_config()
        assert config1 is config2
