from tasks.registry import create_tasks
from notification.registry import create_channel


class Bootstrap:

    def __init__(self, config):
        self.config = config

    def create_tasks(self):
        return create_tasks(self.config)

    def create_notification_channel(self):
        return create_channel(
            self.config.notification.channel
        )
