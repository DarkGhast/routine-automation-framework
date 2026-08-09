from core.logging import get_logger
from core.result import TaskResult, TaskStatus


logger = get_logger(__name__)


class TaskExecutor:

    def execute(self, tasks):
        results = []

        for task in tasks:
            try:
                results.append(task.execute())
            except Exception as e:
                logger.exception("Task execution failed")
                results.append(
                    TaskResult(
                        task.__class__.__name__,
                        TaskStatus.FAILED,
                        str(e)
                    )
                )

        return results
