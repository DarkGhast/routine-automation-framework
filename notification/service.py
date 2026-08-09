from core.result import TaskStatus


class NotificationService:

    def should_send(self, policy, results):
        if policy == "always":
            return True

        if policy == "error_only":
            return any(
                result.status == TaskStatus.FAILED
                for result in results
            )

        return False
