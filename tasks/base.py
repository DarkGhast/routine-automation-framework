from abc import ABC, abstractmethod

from core.result import TaskResult


class AutomationTask(ABC):
    """Base contract for every automation task."""

    def __init__(self, task_name: str):
        self.task_name = task_name

    @abstractmethod
    def execute(self) -> TaskResult:
        raise NotImplementedError
