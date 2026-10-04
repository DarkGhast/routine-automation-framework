from configuration.model import ApplicationConfig
from configuration.exception import ConfigurationError
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
        # 保留旧接口；多渠道应通过 NotificationService.send 按策略分发。
        if self.config.notification.channels is not None:
            raise ConfigurationError("多渠道配置请使用 NotificationService.send")
        return create_channel(self.config.notification.channel)
