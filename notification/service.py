from configuration.model import NotificationConfig
from core.result import TaskResult
from core.logging import get_logger
from notification.registry import create_channel


logger = get_logger(__name__)


class NotificationDeliveryError(RuntimeError):
    """所有渠道尝试完毕后报告失败，不携带底层异常中的敏感信息。"""


class NotificationService:
    def should_send(self, config: NotificationConfig, results: list[TaskResult]) -> bool:
        return config.enabled and any(
            channel.enabled and (
                channel.policy == "always" or any(r.status.is_error for r in results)
            )
            for channel in config.configured_channels().values()
        )

    def send(self, config: NotificationConfig, results: list[TaskResult]) -> None:
        if not config.enabled:
            return
        failed = 0
        for name, channel in config.configured_channels().items():
            if not channel.enabled:
                continue
            if channel.policy == "error_only" and not any(r.status.is_error for r in results):
                continue
            try:
                create_channel(channel).send(results)
            except Exception as exc:
                failed += 1
                logger.error("通知渠道 %s 发送失败（%s），继续处理其他渠道", name, type(exc).__name__)
        if failed:
            raise NotificationDeliveryError(f"{failed} 个通知渠道发送失败，请检查渠道配置与网络")
