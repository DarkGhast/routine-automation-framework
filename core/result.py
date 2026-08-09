from dataclasses import dataclass
from enum import Enum


class TaskStatus(Enum):
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    TIMEOUT = "TIMEOUT"
    SKIPPED = "SKIPPED"


@dataclass
class TaskResult:
    task_name: str
    status: TaskStatus
    message: str
    duration_ms: int | None = None
