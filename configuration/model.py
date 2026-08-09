from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class LoggingConfig(StrictModel):
    level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"

    @field_validator("level", mode="before")
    @classmethod
    def normalize_level(cls, value):
        return value.upper() if isinstance(value, str) else value


class TaskItemConfig(StrictModel):
    enabled: bool = True
    config: dict[str, Any] = Field(default_factory=dict)


class NotificationChannelConfig(StrictModel):
    type: str = "console"
    config: dict[str, Any] = Field(default_factory=dict)

    @field_validator("type", mode="before")
    @classmethod
    def normalize_type(cls, value):
        return value.lower() if isinstance(value, str) else value


class NotificationConfig(StrictModel):
    enabled: bool = True
    policy: Literal["always", "error_only"] = "always"
    channel: NotificationChannelConfig = Field(default_factory=NotificationChannelConfig)

    @field_validator("policy", mode="before")
    @classmethod
    def normalize_policy(cls, value):
        return value.lower() if isinstance(value, str) else value


class ApplicationConfig(StrictModel):
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    tasks: dict[str, TaskItemConfig] = Field(default_factory=dict)
    notification: NotificationConfig = Field(default_factory=NotificationConfig)
