from configuration.model import ApplicationConfig
from notification.base import NotificationChannel


class Bootstrap:

    def __init__(self, config: ApplicationConfig):
        self.config = config

    def create_tasks(self):
        return []

    def create_notification_channel(self) -> NotificationChannel | None:
        if not self.config.notification.enabled:
            return None

        return None
