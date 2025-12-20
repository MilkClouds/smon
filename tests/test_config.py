"""Tests for smon.config module."""

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from smon.config import Config


class TestConfig:
    """Tests for Config class."""

    def test_default_values(self) -> None:
        """Test default configuration values."""
        config = Config()
        assert config.refresh_sec == 5.0
        assert config.user_filter is None
        assert config.partition_filter is None
        assert config.state_filter is None
        assert config.theme == "dark"

    def test_custom_values(self) -> None:
        """Test custom configuration values."""
        config = Config(
            refresh_sec=10.0,
            user_filter="testuser",
            partition_filter="gpu",
            state_filter="RUNNING",
            theme="light",
        )
        assert config.refresh_sec == 10.0
        assert config.user_filter == "testuser"
        assert config.partition_filter == "gpu"
        assert config.state_filter == "RUNNING"
        assert config.theme == "light"

    def test_save_and_load(self, tmp_path: Path) -> None:
        """Test saving and loading configuration."""
        config_file = tmp_path / "smon" / "config.json"

        with patch.object(Config, "config_path", return_value=config_file):
            # Save config
            config = Config(refresh_sec=15.0, theme="light")
            config.save()

            # Verify file exists
            assert config_file.exists()

            # Load config
            loaded = Config.load()
            assert loaded.refresh_sec == 15.0
            assert loaded.theme == "light"

    def test_load_nonexistent_file(self, tmp_path: Path) -> None:
        """Test loading when config file doesn't exist."""
        config_file = tmp_path / "nonexistent" / "config.json"

        with patch.object(Config, "config_path", return_value=config_file):
            config = Config.load()
            # Should return default values
            assert config.refresh_sec == 5.0
            assert config.theme == "dark"

    def test_load_invalid_json(self, tmp_path: Path) -> None:
        """Test loading when config file contains invalid JSON."""
        config_file = tmp_path / "smon" / "config.json"
        config_file.parent.mkdir(parents=True, exist_ok=True)
        config_file.write_text("invalid json {{{")

        with patch.object(Config, "config_path", return_value=config_file):
            config = Config.load()
            # Should return default values
            assert config.refresh_sec == 5.0
            assert config.theme == "dark"

