from pydantic import BaseModel

from core.exception import TaskTimeoutError
from core.executor import TaskExecutor
from core.result import TaskResult, TaskStatus
from tasks.base import AutomationTask


class EmptyConfig(BaseModel):
    pass


class SuccessTask(AutomationTask):
    def execute(self):
        return TaskResult(self.task_name, TaskStatus.SUCCESS, "ok")


class FailedTask(AutomationTask):
    def execute(self):
        raise RuntimeError("failed")


class TimeoutTask(AutomationTask):
    def execute(self):
        raise TaskTimeoutError("timed out")


def test_executor_preserves_task_names_and_failure_statuses():
    results = TaskExecutor().execute([
        SuccessTask("success"),
        FailedTask("failed"),
        TimeoutTask("timeout"),
    ])

    assert [result.task_name for result in results] == ["success", "failed", "timeout"]
    assert [result.status for result in results] == [
        TaskStatus.SUCCESS,
        TaskStatus.FAILED,
        TaskStatus.TIMEOUT,
    ]
