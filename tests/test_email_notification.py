import ssl
from unittest.mock import MagicMock
import pytest
from pydantic import ValidationError
from configuration.model import NotificationChannelConfig
from configuration.exception import ConfigurationError
from core.result import TaskResult, TaskStatus
from notification.registry import create_channel
from notification_plugins.email.plugin import EmailConfig, EmailChannel


def options(**changes):
    return dict(host="smtp.example.com", sender="sender@example.com",
                recipients=["one@example.com", "two@example.com"],
                username="sender@example.com", password="fake-secret", **changes)


@pytest.mark.parametrize("security,port", [("ssl", 465), ("starttls", 587)])
def test_encrypted_delivery(monkeypatch, security, port):
    smtp = MagicMock()
    smtp.__enter__.return_value = smtp
    smtp.send_message.return_value = {}
    constructor = MagicMock(return_value=smtp)
    monkeypatch.setattr("notification_plugins.email.plugin.smtplib.SMTP_SSL", constructor)
    monkeypatch.setattr("notification_plugins.email.plugin.smtplib.SMTP", constructor)
    EmailChannel(EmailConfig(**options(security=security, port=port))).send([
        TaskResult("failure", TaskStatus.FAILED, "签到失败"),
        TaskResult("skipped", TaskStatus.SKIPPED, "今日已签到"),
    ])
    assert constructor.call_args.args == ("smtp.example.com", port)
    assert constructor.call_args.kwargs["timeout"] == 20
    smtp.login.assert_called_once_with("sender@example.com", "fake-secret")
    message = smtp.send_message.call_args.args[0]
    assert "签到失败" in message.get_content()
    assert "今日已签到" in message.get_content()
    assert "fake-secret" not in message.as_string()
    assert smtp.send_message.call_args.kwargs["to_addrs"] == ["one@example.com", "two@example.com"]
    if security == "starttls":
        context = smtp.starttls.call_args.kwargs["context"]
        calls = [c[0] for c in smtp.method_calls]
        assert calls.index("starttls") < calls.index("login") < calls.index("send_message")
    else:
        context = constructor.call_args.kwargs["context"]
        smtp.starttls.assert_not_called()
    assert context.check_hostname and context.verify_mode == ssl.CERT_REQUIRED
    smtp.__exit__.assert_called_once()


def test_tls_failure_never_logs_in(monkeypatch):
    smtp = MagicMock()
    smtp.__enter__.return_value = smtp
    smtp.starttls.side_effect = RuntimeError("TLS unavailable")
    monkeypatch.setattr("notification_plugins.email.plugin.smtplib.SMTP", lambda *a, **kw: smtp)
    with pytest.raises(RuntimeError):
        EmailChannel(EmailConfig(**options(security="starttls", port=587))).send([])
    smtp.login.assert_not_called()
    smtp.send_message.assert_not_called()


def test_partial_refusal_is_failure(monkeypatch):
    smtp = MagicMock()
    smtp.__enter__.return_value = smtp
    smtp.send_message.return_value = {"one@example.com": (550, b"refused")}
    monkeypatch.setattr("notification_plugins.email.plugin.smtplib.SMTP_SSL", lambda *a, **kw: smtp)
    with pytest.raises(RuntimeError, match="收件人"):
        EmailChannel(EmailConfig(**options())).send([])


@pytest.mark.parametrize("field,value", [
    ("security", "plain"), ("port", 0), ("timeout", 0), ("timeout", float("inf")),
    ("recipients", []), ("recipients", ["a@b\nBcc:x@y"]),
    ("sender", "a@b,c@d"), ("subject", "hello\r\nBcc:x@y"), ("password", ""),
])
def test_invalid_options(field, value):
    raw = options()
    raw[field] = value
    with pytest.raises(ValidationError):
        EmailConfig(**raw)


def test_validation_error_does_not_leak_password():
    raw = options()
    raw["port"] = "fake-secret"
    with pytest.raises(ConfigurationError) as caught:
        create_channel(NotificationChannelConfig(type="email", config=raw))
    assert "fake-secret" not in str(caught.value)


@pytest.mark.parametrize("status,sent_count", [("SUCCESS", 0), ("SKIPPED", 0), ("FAILED", 1)])
def test_cli_console_and_email(tmp_path, monkeypatch, capsys, status, sent_count):
    import yaml
    from app.main import main
    smtp = MagicMock()
    smtp.__enter__.return_value = smtp
    smtp.send_message.return_value = {}
    connect = MagicMock(return_value=smtp)
    monkeypatch.setattr("notification_plugins.email.plugin.smtplib.SMTP_SSL", connect)
    task_type = {"SUCCESS": "demo_success", "SKIPPED": "demo_already_signed", "FAILED": "demo_failure"}[status]
    config = {
        "tasks": {"demo": {"type": task_type}},
        "notification": {"channels": {
            "screen": {"type": "console"},
            "mail": {"type": "email", "policy": "error_only", "config": options()},
        }},
    }
    path = tmp_path / "application.yaml"
    path.write_text(yaml.safe_dump(config), encoding="utf-8")
    main(["--config", str(path)])
    assert f"demo: {status}" in capsys.readouterr().out
    assert connect.call_count == sent_count
    assert smtp.send_message.call_count == sent_count


@pytest.mark.parametrize("name", [None, "日常签到助手", '签到, \"助手\"'])
def test_sender_display_name_round_trip(monkeypatch, name):
    from email import policy
    from email.parser import BytesParser
    smtp = MagicMock()
    smtp.__enter__.return_value = smtp
    smtp.send_message.return_value = {}
    monkeypatch.setattr("notification_plugins.email.plugin.smtplib.SMTP_SSL", lambda *a, **kw: smtp)
    EmailChannel(EmailConfig(**options(sender_name=name))).send([])
    message = smtp.send_message.call_args.args[0]
    parsed = BytesParser(policy=policy.default).parsebytes(message.as_bytes())
    address = parsed["From"].addresses[0]
    assert address.display_name == (name or "")
    assert address.addr_spec == "sender@example.com"
    assert smtp.send_message.call_args.kwargs["from_addr"] == "sender@example.com"


@pytest.mark.parametrize("name", ["bad\r\nBcc: other@example.com", "bad\nname", "   "])
def test_sender_name_rejects_header_injection(name):
    with pytest.raises(ValidationError):
        EmailConfig(**options(sender_name=name))


@pytest.mark.parametrize("failure_stage", ["connect", "login", "send_message"])
def test_smtp_failure_isolated_and_redacted(monkeypatch, capsys, caplog, failure_stage):
    import smtplib
    import traceback
    from configuration.model import NotificationConfig
    from notification.service import NotificationService, NotificationDeliveryError
    smtp = MagicMock()
    smtp.__enter__.return_value = smtp
    smtp.send_message.return_value = {}
    constructor = MagicMock(return_value=smtp)
    error = smtplib.SMTPException("server echoed fake-secret")
    if failure_stage == "connect":
        constructor.side_effect = TimeoutError("fake-secret")
    else:
        getattr(smtp, failure_stage).side_effect = error
    monkeypatch.setattr("notification_plugins.email.plugin.smtplib.SMTP_SSL", constructor)
    config = NotificationConfig(channels={
        "mail": {"type": "email", "policy": "error_only", "config": options()},
        "screen": {"type": "console"},
    })
    with pytest.raises(NotificationDeliveryError) as caught:
        NotificationService().send(config, [TaskResult("demo", TaskStatus.FAILED, "模拟失败")])
    output = capsys.readouterr().out
    assert "demo: FAILED" in output
    assert "fake-secret" not in output + caplog.text + "".join(traceback.format_exception(caught.value))
    if failure_stage == "login":
        smtp.send_message.assert_not_called()
    if failure_stage != "connect":
        smtp.__exit__.assert_called_once()


def test_multiple_recipients_visible_in_header(monkeypatch):
    smtp = MagicMock()
    smtp.__enter__.return_value = smtp
    smtp.send_message.return_value = {}
    monkeypatch.setattr("notification_plugins.email.plugin.smtplib.SMTP_SSL", lambda *a, **kw: smtp)
    EmailChannel(EmailConfig(**options())).send([])
    message = smtp.send_message.call_args.args[0]
    expected = ["one@example.com", "two@example.com"]
    assert [a.addr_spec for a in message["To"].addresses] == expected
    assert smtp.send_message.call_args.kwargs["to_addrs"] == expected
