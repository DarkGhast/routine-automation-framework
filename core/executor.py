from core.exception import TaskTimeoutError
from core.logging import get_logger
from core.result import TaskResult, TaskStatus
from tasks.base import AutomationTask


logger = get_logger(__name__)


class TaskExecutor:
    def execute(self, tasks: list[AutomationTask]) -> list[TaskResult]:
        results: list[TaskResult] = []

        for task in tasks:
            try:
                results.append(task.execute())
            except TaskTimeoutError as exc:
                logger.exception("Task timed out: %s", task.task_name)
                results.append(
                    TaskResult(task.task_name, TaskStatus.TIMEOUT, str(exc))
                )
            except Exception as exc:
                logger.exception("Task execution failed: %s", task.task_name)
                results.append(
                    TaskResult(task.task_name, TaskStatus.FAILED, str(exc))
                )

        return results
