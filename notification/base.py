from abc import ABC, abstractmethod

from core.result import TaskResult


class NotificationChannel(ABC):
    @abstractmethod
    def send(self, results: list[TaskResult]) -> None:
        raise NotImplementedError
