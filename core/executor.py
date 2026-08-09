from core.logging import get_logger


logger = get_logger(__name__)


class TaskExecutor:

    def execute(self, tasks):
        results = []

        for task in tasks:
            try:
                results.append(task.execute())
            except Exception:
                logger.exception("Task execution failed")

        return results
