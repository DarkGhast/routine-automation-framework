from configuration.model import NotificationConfig
from core.result import TaskResult


class NotificationService:
    def should_send(
        self,
        config: NotificationConfig,
        results: list[TaskResult],
    ) -> bool:
        if not config.enabled:
            return False

        if config.policy == "always":
            return True

        return any(result.status.is_error for result in results)
