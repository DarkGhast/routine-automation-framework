import pytest

from configuration.exception import ConfigurationError
from configuration.model import NotificationChannelConfig
from notification.console import ConsoleChannel
from notification.registry import create_channel


def test_console_channel_creation():
    channel = create_channel(NotificationChannelConfig(type="console", config={}))
    assert isinstance(channel, ConsoleChannel)


def test_unknown_channel_fails_fast():
    with pytest.raises(ConfigurationError, match="Unknown notification channel"):
        create_channel(NotificationChannelConfig(type="missing", config={}))


def test_active_channel_rejects_unresolved_environment_variable():
    config = NotificationChannelConfig(
        type="console",
        config={"token": "${MISSING_NOTIFICATION_TOKEN}"},
    )

    with pytest.raises(ConfigurationError, match="MISSING_NOTIFICATION_TOKEN"):
        create_channel(config)
