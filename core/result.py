from dataclasses import dataclass
from enum import Enum


class TaskStatus(Enum):
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    TIMEOUT = "TIMEOUT"
    SKIPPED = "SKIPPED"

    @property
    def is_error(self) -> bool:
        return self in {TaskStatus.FAILED, TaskStatus.TIMEOUT}


@dataclass(slots=True)
class TaskResult:
    task_name: str
    status: TaskStatus
    message: str
