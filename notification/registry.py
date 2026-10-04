import re
from importlib import import_module
from pydantic import BaseModel, ValidationError
from configuration.exception import ConfigurationError
from configuration.model import NotificationChannelConfig
from configuration.resolver import ensure_env_resolved
from notification.base import NotificationChannel
from notification.definition import NotificationDefinition


def load_definition(channel_type: str) -> NotificationDefinition:
    if not re.fullmatch(r"[a-z][a-z0-9_]*", channel_type):
        raise ConfigurationError("Invalid notification plugin type")
    package = f"notification_plugins.{channel_type}"
    try:
        module = import_module(f"{package}.plugin")
    except ModuleNotFoundError as exc:
        if exc.name in {package, f"{package}.plugin"}:
            raise ConfigurationError(f"Unknown notification channel: {channel_type}") from None
        raise ConfigurationError(f"Notification plugin dependency missing: {channel_type}") from None
    except Exception:
        raise ConfigurationError(f"Unable to import notification plugin: {channel_type}") from None
    definition = getattr(module, "PLUGIN", None)
    if not isinstance(definition, NotificationDefinition) or not (
        isinstance(definition.channel_class, type)
        and issubclass(definition.channel_class, NotificationChannel)
        and isinstance(definition.config_class, type)
        and issubclass(definition.config_class, BaseModel)
    ):
        raise ConfigurationError(f"Invalid notification PLUGIN definition: {channel_type}")
    return definition


def create_channel(config: NotificationChannelConfig) -> NotificationChannel:
    ensure_env_resolved(config.config, "notification.channel.config")
    definition = load_definition(config.type)
    try:
        options = definition.config_class.model_validate(config.config)
    except ValidationError:
        # 不打印验证输入，避免 SMTP 凭据出现在日志中。
        raise ConfigurationError(f"Invalid notification configuration: {config.type}") from None
    try:
        return definition.channel_class(options)
    except Exception:
        raise ConfigurationError(f"Unable to create notification channel: {config.type}") from None
