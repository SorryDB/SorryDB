from enum import Enum
from pathlib import Path
from typing import Optional

from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
    TomlConfigSettingsSource,
)


class LogLevel(str, Enum):
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class SorryDBSettings(BaseSettings):
    log_level: LogLevel = LogLevel.INFO
    log_file: Optional[Path] = None

    model_config = SettingsConfigDict(env_prefix="SORRYDB_", toml_file="config.toml")

    # Implementing this method is required to load settings from a TOML file
    # See the Pydantic docs: https://docs.pydantic.dev/latest/concepts/pydantic_settings/#other-settings-source
    # TODO: We should support loading settings from enviornment variables as well
    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        return (env_settings, TomlConfigSettingsSource(settings_cls))
