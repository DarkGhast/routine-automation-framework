from abc import ABC, abstractmethod


class NotificationChannel(ABC):

    @abstractmethod
    def send(self, context, config: dict):
        raise NotImplementedError
