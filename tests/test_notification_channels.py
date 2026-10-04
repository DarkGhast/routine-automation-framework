from types import SimpleNamespace
import traceback
import pytest
from pydantic import ValidationError
from configuration.model import NotificationConfig, NotificationChannelConfig
from configuration.exception import ConfigurationError
from core.result import TaskResult, TaskStatus
from notification.service import NotificationService, NotificationDeliveryError
from notification.registry import create_channel


@pytest.mark.parametrize("status,expected", [
    (TaskStatus.SUCCESS, ["console"]), (TaskStatus.SKIPPED, ["console"]),
    (TaskStatus.FAILED, ["console", "email"]), (TaskStatus.TIMEOUT, ["console", "email"]),
])
def test_independent_policies(monkeypatch, status, expected):
    sent = []
    config = NotificationConfig(channels={
        "screen": {"type": "console"},
        "mail": {"type": "email", "policy": "error_only"},
        "off": {"type": "missing", "enabled": False},
    })
    results = [TaskResult("test", status, "测试")]
    monkeypatch.setattr("notification.service.create_channel", lambda c:
        SimpleNamespace(send=lambda r: sent.append((c.type, r))))
    NotificationService().send(config, results)
    assert [name for name, _ in sent] == expected
    assert all(r is results for _, r in sent)


def test_failure_continues_and_hides_secret(monkeypatch, caplog):
    sent = []
    def create(config):
        if config.type == "email":
            raise RuntimeError("PRIVATE-PASSWORD")
        return SimpleNamespace(send=lambda r: sent.append(r))
    monkeypatch.setattr("notification.service.create_channel", create)
    config = NotificationConfig(channels={"mail": {"type": "email"}, "screen": {}})
    with pytest.raises(NotificationDeliveryError) as caught:
        NotificationService().send(config, [])
    assert len(sent) == 1
    assert "PRIVATE-PASSWORD" not in caplog.text + "".join(traceback.format_exception(caught.value))


def test_unused_channels_not_loaded():
    NotificationService().send(NotificationConfig(channels={
        "off": {"type": "nonexistent", "enabled": False},
        "errors": {"type": "nonexistent", "policy": "error_only", "config": {"password": "${UNSET}"}},
    }), [TaskResult("ok", TaskStatus.SUCCESS, "")])
    NotificationService().send(NotificationConfig(enabled=False, channels={"x": {"type": "nonexistent"}}), [])
    NotificationService().send(NotificationConfig(channels={}), [])


@pytest.mark.parametrize("legacy", [{"channel": {}}, {"policy": "always"}])
def test_reject_mixed_config(legacy):
    with pytest.raises(ValidationError):
        NotificationConfig.model_validate({"channels": {}, **legacy})


def test_legacy_config_sends_console(capsys):
    NotificationService().send(NotificationConfig(policy="error_only"), [
        TaskResult("failure", TaskStatus.FAILED, "模拟失败")])
    assert "模拟失败" in capsys.readouterr().out


def test_new_plugin_needs_no_registry_edit(tmp_path, monkeypatch):
    import notification_plugins
    folder = tmp_path / "sample"
    folder.mkdir()
    (folder / "__init__.py").write_text("")
    (folder / "plugin.py").write_text(
        "from notification.base import NotificationChannel\n"
        "from notification.definition import NotificationDefinition\n"
        "from configuration.model import StrictModel\n"
        "class Config(StrictModel):\n    text: str\n"
        "class Channel(NotificationChannel):\n"
        "    def __init__(self, config): self.text = config.text\n"
        "    def send(self, results): pass\n"
        "PLUGIN = NotificationDefinition(Channel, Config)\n", encoding="utf-8")
    monkeypatch.setattr(notification_plugins, "__path__", [str(tmp_path)])
    channel = create_channel(NotificationChannelConfig(type="sample", config={"text": "loaded"}))
    assert channel.text == "loaded"


@pytest.mark.parametrize("channel_type", ["../email", "email.plugin", "bad-name"])
def test_reject_invalid_type(channel_type):
    with pytest.raises(ConfigurationError):
        create_channel(NotificationChannelConfig(type=channel_type))
