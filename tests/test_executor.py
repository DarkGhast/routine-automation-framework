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


def test_executor_preserves_task_names_and_failure_statuses(caplog):
    results = TaskExecutor().execute([
        SuccessTask("success"),
        FailedTask("failed"),
        TimeoutTask("timeout"),
        SuccessTask("after_errors"),
    ])

    assert [result.task_name for result in results] == [
        "success", "failed", "timeout", "after_errors",
    ]
    assert [result.status for result in results] == [
        TaskStatus.SUCCESS,
        TaskStatus.FAILED,
        TaskStatus.TIMEOUT,
        TaskStatus.SUCCESS,
    ]
    # 程序异常保留堆栈供排查，并且不会中断后续任务。
    errors = [record for record in caplog.records if record.name == "core.executor"]
    assert len(errors) == 2
    assert all(record.exc_info is not None for record in errors)
