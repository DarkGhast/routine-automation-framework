from abc import ABC, abstractmethod
from core.result import TaskResult


class AutomationTask(ABC):

    @abstractmethod
    def execute(self) -> TaskResult:
        raise NotImplementedError
