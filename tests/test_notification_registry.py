import notification.console
from notification.registry import create_channel


def test_console_channel_creation():
    class Config:
        type = "console"
        config = {}

    channel = create_channel(Config())

    assert channel.__class__.__name__ == "ConsoleChannel"
