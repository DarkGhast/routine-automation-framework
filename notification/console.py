from typing import Any

from core.result import TaskResult
from notification.base import NotificationChannel


class ConsoleChannel(NotificationChannel):
    def __init__(self, config: dict[str, Any]):
        # Console currently has no private fields. Keep the full config so the
        # channel contract stays identical to future implementations.
        self.config = config

    def send(self, results: list[TaskResult]) -> None:
        for item in results:
            print(f"{item.task_name}: {item.status.value} - {item.message}")
