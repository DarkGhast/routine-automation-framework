from typing import Any
from pydantic import BaseModel, Field


class TaskItemConfig(BaseModel):
    enabled: bool = True
    username: str | None = None
    password: str | None = None


class TasksConfig(BaseModel):
    jm: TaskItemConfig | None = None


class NotificationChannelConfig(BaseModel):
    type: str = "console"
    config: dict[str, Any] = Field(default_factory=dict)


class NotificationConfig(BaseModel):
    enabled: bool = True
    policy: str = "always"
    channel: NotificationChannelConfig


class LoggingConfig(BaseModel):
    level: str = "INFO"


class ApplicationConfig(BaseModel):
    logging: LoggingConfig
    tasks: TasksConfig
    notification: NotificationConfig
