from configuration.exception import ConfigurationError
from configuration.model import NotificationChannelConfig
from configuration.resolver import ensure_env_resolved
from notification.base import NotificationChannel
from notification.console import ConsoleChannel


CHANNEL_REGISTRY: dict[str, type[NotificationChannel]] = {
    "console": ConsoleChannel,
}


def create_channel(config: NotificationChannelConfig) -> NotificationChannel:
    ensure_env_resolved(config.model_dump(), "notification.channel")

    channel_class = CHANNEL_REGISTRY.get(config.type)
    if channel_class is None:
        raise ConfigurationError(
            f"Unknown notification channel: {config.type}"
        )

    return channel_class(config.config)
