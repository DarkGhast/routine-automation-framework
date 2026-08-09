from notification.base import NotificationChannel


class ConsoleChannel(NotificationChannel):

    def __init__(self, config):
        self.config = config

    def send(self, context, config=None):
        for item in context:
            print(
                f"{item.task_name}: {item.status.value} - {item.message}"
            )
