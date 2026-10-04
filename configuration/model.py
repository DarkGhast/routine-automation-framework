from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class LoggingConfig(StrictModel):
    level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"

    @field_validator("level", mode="before")
    @classmethod
    def normalize_level(cls, value):
        return value.upper() if isinstance(value, str) else value


class TaskItemConfig(StrictModel):
    # 未指定类型时使用任务实例名，兼容原有配置结构。
    type: str | None = None
    enabled: bool = True
    config: dict[str, Any] = Field(default_factory=dict)


class NotificationChannelConfig(StrictModel):
    type: str = "console"
    enabled: bool = True
    policy: Literal["always", "error_only"] = "always"
    config: dict[str, Any] = Field(default_factory=dict)

    @field_validator("type", "policy", mode="before")
    @classmethod
    def normalize_type(cls, value):
        return value.lower() if isinstance(value, str) else value


class NotificationConfig(StrictModel):
    enabled: bool = True
    policy: Literal["always", "error_only"] = "always"
    channel: NotificationChannelConfig = Field(default_factory=NotificationChannelConfig)
    channels: dict[str, NotificationChannelConfig] | None = None

    @model_validator(mode="before")
    @classmethod
    def reject_mixed_formats(cls, value):
        if isinstance(value, dict) and "channels" in value:
            if "channel" in value or "policy" in value:
                raise ValueError("channels 不能与旧版 channel / policy 同时配置")
        return value

    def configured_channels(self) -> dict[str, NotificationChannelConfig]:
        if self.channels is not None:
            return self.channels
        return {"default": self.channel.model_copy(update={"policy": self.policy})}

    @field_validator("policy", mode="before")
    @classmethod
    def normalize_policy(cls, value):
        return value.lower() if isinstance(value, str) else value


class ApplicationConfig(StrictModel):
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    tasks: dict[str, TaskItemConfig] = Field(default_factory=dict)
    notification: NotificationConfig = Field(default_factory=NotificationConfig)
