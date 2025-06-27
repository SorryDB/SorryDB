import os
from pathlib import Path

import pytest
from pydantic import ValidationError

from sorrydb.cli.settings import SorryDBSettings


def test_load_from_toml_file(tmp_path: Path):
    config_content = """
log_level = "DEBUG"
log_file = "/tmp/test_log_from_toml.log"
    """
    # TomlConfigSettingsSource in SorryDBSettings looks for 'sorrydb_config.toml'
    config_file = tmp_path / "sorrydb_config.toml"
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
    monkeypatch.setenv("SORRYDB_LOG_LEVEL", "WARNING")
    monkeypatch.setenv("SORRYDB_LOG_FILE", "/tmp/test_log_from_env.log")

    settings = SorryDBSettings()

    assert settings.log_level == "WARNING"
    assert settings.log_file == Path("/tmp/test_log_from_env.log")


def test_environment_variables_override_toml(tmp_path: Path, monkeypatch):
    config_content = """
log_level = "INFO"
log_file = "/tmp/default_from_toml.log"
    """
    config_file = tmp_path / "sorrydb_config.toml"
    config_file.write_text(config_content)

    monkeypatch.setenv("SORRYDB_LOG_LEVEL", "ERROR")

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


def test_default_values():
    settings = SorryDBSettings()

    assert settings.log_level == "INFO"
    assert settings.log_file is None


def test_load_ignore_from_toml_file(tmp_path: Path):
    config_content = """
[[ignore]]
repo = "opencompl/lean-mlir"

[[ignore]]
repo = "leanprover-community/mathlib4"
paths = ["MathlibTest/"]
    """
    config_file = tmp_path / "sorrydb_config.toml"
    config_file.write_text(config_content)

    original_cwd = Path.cwd()
    os.chdir(tmp_path)
    try:
        settings = SorryDBSettings()
        assert len(settings.ignore) == 2
        assert settings.ignore[0].repo == "opencompl/lean-mlir"
        assert settings.ignore[0].paths is None
        assert settings.ignore[1].repo == "leanprover-community/mathlib4"
        assert settings.ignore[1].paths == [Path("MathlibTest")]
    finally:
        os.chdir(original_cwd)


def test_invalid_log_level_validation(monkeypatch):
    monkeypatch.setenv("SORRYDB_LOG_LEVEL", "INVALID_LEVEL")
    with pytest.raises(ValidationError) as excinfo:
        SorryDBSettings()
