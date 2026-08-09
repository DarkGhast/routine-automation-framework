from configuration.model import ApplicationConfig
from notification.base import NotificationChannel
from notification.registry import create_channel
from tasks.base import AutomationTask
from tasks.registry import create_tasks


class Bootstrap:
    def __init__(self, config: ApplicationConfig):
        self.config = config

    def create_tasks(self) -> list[AutomationTask]:
        return create_tasks(self.config)

    def create_notification_channel(self) -> NotificationChannel:
        return create_channel(self.config.notification.channel)
