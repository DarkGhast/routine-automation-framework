from core.executor import TaskExecutor
from core.result import TaskStatus


class SuccessTask:
    def execute(self):
        from core.result import TaskResult
        return TaskResult("success", TaskStatus.SUCCESS, "ok")


class FailedTask:
    def execute(self):
        raise RuntimeError("failed")


def test_executor_keeps_failed_result():
    results = TaskExecutor().execute(
        [SuccessTask(), FailedTask()]
    )

    assert len(results) == 2
    assert results[0].status == TaskStatus.SUCCESS
    assert results[1].status == TaskStatus.FAILED
