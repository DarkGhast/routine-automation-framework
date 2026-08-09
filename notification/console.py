from notification.base import NotificationChannel
from notification.registry import register_channel


class ConsoleChannel(NotificationChannel):

    def __init__(self, config):
        self.config = config

    def send(self, context):
        for item in context:
            print(
                f"{item.task_name}: "
                f"{item.status.value} - "
                f"{item.message}"
            )


register_channel("console", ConsoleChannel)
