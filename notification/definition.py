from dataclasses import dataclass
from pydantic import BaseModel
from notification.base import NotificationChannel


@dataclass(frozen=True)
class NotificationDefinition:
    channel_class: type[NotificationChannel]
    config_class: type[BaseModel]
