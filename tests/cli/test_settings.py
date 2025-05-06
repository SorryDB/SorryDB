import os
from pathlib import Path

import pytest
from pydantic import ValidationError

from sorrydb.cli.settings import SorryDBSettings


def test_load_from_toml_file(tmp_path: Path):
    """
    Tests loading settings from a TOML configuration file (config.toml).
    """
    config_content = """
log_level = "DEBUG"
log_file = "/tmp/test_log_from_toml.log"
    """
    # TomlConfigSettingsSource in SorryDBSettings looks for 'config.toml'
    config_file = tmp_path / "config.toml"
    config_file.write_text(config_content)

    original_cwd = Path.cwd()
    os.chdir(tmp_path)  # Change CWD so TomlConfigSettingsSource finds the file
    try:
        settings = SorryDBSettings()
        assert settings.log_level == "DEBUG"
        assert settings.log_file == Path("/tmp/test_log_from_toml.log")
    finally:
        os.chdir(original_cwd)


def test_load_from_environment_variables(monkeypatch):
    """
    Tests loading settings from environment variables.
    """
    monkeypatch.setenv("SORRYDB_LOG_LEVEL", "WARNING")
    monkeypatch.setenv("SORRYDB_LOG_FILE", "/tmp/test_log_from_env.log")

    settings = SorryDBSettings()

    assert settings.log_level == "WARNING"
    assert settings.log_file == Path("/tmp/test_log_from_env.log")


def test_environment_variables_override_toml(tmp_path: Path, monkeypatch):
    """
    Tests that environment variables override settings from a TOML file.
    """
    config_content = """
log_level = "INFO"
log_file = "/tmp/default_from_toml.log"
    """
    config_file = tmp_path / "config.toml"
    config_file.write_text(config_content)

    monkeypatch.setenv("SORRYDB_LOG_LEVEL", "ERROR")
    # log_file will be taken from TOML in the first instantiation

    original_cwd = Path.cwd()
    os.chdir(tmp_path)
    try:
        settings = SorryDBSettings()
        assert settings.log_level == "ERROR"  # This is overridden by env
        assert settings.log_file == Path(
            "/tmp/default_from_toml.log"
        )  # This comes from TOML
    finally:
        os.chdir(original_cwd)

    # Test overriding log_file as well with a new settings instance
    monkeypatch.setenv("SORRYDB_LOG_FILE", "/tmp/override_log_from_env.log")

    os.chdir(tmp_path)  # Ensure CWD is correct for TomlConfigSettingsSource
    try:
        # Re-instantiate settings to pick up the new environment variable
        settings_after_log_file_env_change = SorryDBSettings()
        assert (
            settings_after_log_file_env_change.log_level == "ERROR"
        )  # Still overridden by env
        assert settings_after_log_file_env_change.log_file == Path(
            "/tmp/override_log_from_env.log"
        )  # This is now overridden by env
    finally:
        os.chdir(original_cwd)


def test_default_values():
    """
    Tests that default values are used when no other source provides them.
    """
    # Assuming SorryDBSettings has defaults defined:
    # log_level: LogLevel = LogLevel.INFO
    # log_file: Optional[Path] = None

    settings = SorryDBSettings()

    assert settings.log_level == "INFO"  # Default from SorryDBSettings model
    assert settings.log_file is None  # Default from SorryDBSettings model


def test_invalid_log_level_validation(monkeypatch):
    """
    Tests validation for the log_level field.
    """
    monkeypatch.setenv("SORRYDB_LOG_LEVEL", "INVALID_LEVEL")
    with pytest.raises(ValidationError) as excinfo:
        SorryDBSettings()
