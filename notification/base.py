from abc import ABC, abstractmethod


class NotificationChannel(ABC):

    @abstractmethod
    def send(self, context):
        raise NotImplementedError
