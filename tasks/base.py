from abc import ABC, abstractmethod


class AutomationTask(ABC):

    @abstractmethod
    def execute(self):
        raise NotImplementedError
