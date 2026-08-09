from typing import Any
from pydantic import BaseModel, Field


class TaskItemConfig(BaseModel):
    enabled: bool = True
    config: dict[str, Any] = Field(default_factory=dict)


class NotificationChannelConfig(BaseModel):
    type: str = "console"
    config: dict[str, Any] = Field(default_factory=dict)


class NotificationConfig(BaseModel):
    enabled: bool = True
    policy: str = "always"
    channel: NotificationChannelConfig


class ApplicationConfig(BaseModel):
    logging: dict[str, Any] = Field(default_factory=dict)
    tasks: dict[str, TaskItemConfig] = Field(default_factory=dict)
    notification: NotificationConfig
