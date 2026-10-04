from datetime import date
from pathlib import Path

import pytest
from pydantic import ValidationError

from configuration.loader import load_config
from configuration.model import ApplicationConfig
from core.exception import TaskTimeoutError
from core.executor import TaskExecutor
from core.result import TaskStatus
from plugins.jmcomic.client import (
    BusinessRejected, JMProtocolError, checkin_status, signed_today, site_today,
)
from plugins.jmcomic.config import JMComicConfig
from plugins.jmcomic.task import JMComicTask
from tasks.registry import create_tasks


def config(**changes):
    return JMComicConfig(username="offline-user", password="offline-password", **changes)


class FakeClient:
    def __init__(self, cfg, status=TaskStatus.SUCCESS, error=None):
        self.config = cfg
        self.status = status
        self.error = error
        self.calls = []
        self.closed = False

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.closed = True

    def prepare(self):
        self.calls.append("prepare")

    def login(self):
        self.calls.append("login")
        if self.error:
            raise self.error

    def check_in(self):
        self.calls.append("check_in")
        return self.status


@pytest.mark.parametrize("status", [TaskStatus.SUCCESS, TaskStatus.SKIPPED])
def test_task_status_and_cleanup(status):
    client = FakeClient(config(), status)
    result = JMComicTask("jm", client.config, lambda _: client).execute()
    assert result.status is status
    assert result.task_name == "jm"
    assert client.calls == ["prepare", "login", "check_in"]
    assert client.closed


def test_login_rejection_is_business_failure_without_checkin(caplog):
    client = FakeClient(config(), error=BusinessRejected("登录被服务端拒绝"))
    result = JMComicTask("jm", client.config, lambda _: client).execute()
    assert result.status is TaskStatus.FAILED
    assert "登录" in result.message
    assert client.calls == ["prepare", "login"]
    assert client.closed
    assert not caplog.records


@pytest.mark.parametrize("error", [JMProtocolError("协议异常"), RuntimeError("程序异常"), TaskTimeoutError("超时")])
def test_exceptions_reach_executor_and_cleanup(error):
    client = FakeClient(config(), error=error)
    task = JMComicTask("jm", client.config, lambda _: client)
    with pytest.raises(type(error)):
        task.execute()
    assert client.closed
    assert "check_in" not in client.calls
    result = TaskExecutor().execute([task])[0]
    assert result.status is (TaskStatus.TIMEOUT if isinstance(error, TaskTimeoutError) else TaskStatus.FAILED)


@pytest.mark.parametrize("changes", [
    {"username": ""}, {"password": " "}, {"username": None}, {"password": 123},
    {"timeout": 0}, {"timeout": -1}, {"timeout": 121}, {"timeout": float("inf")},
    {"timeout": float("nan")}, {"api_domain": "https://example.com"},
    {"api_domain": "example.com/path"}, {"api_domain": "user:pass@example.com"},
    {"unknown": "sensitive-input"},
])
def test_invalid_config_hides_input(changes):
    values = {"username": "private-user", "password": "private-password", **changes}
    with pytest.raises(ValidationError) as caught:
        JMComicConfig.model_validate(values)
    text = str(caught.value)
    assert "private-user" not in text
    assert "private-password" not in text
    assert "sensitive-input" not in text


def test_missing_credentials_and_secret_repr():
    with pytest.raises(ValidationError):
        JMComicConfig()
    cfg = JMComicConfig(username="private-user", password=" password with spaces ")
    assert "private-user" not in repr(cfg)
    assert "password with spaces" not in repr(cfg)
    assert cfg.password.get_secret_value() == " password with spaces "


def test_registry_construction_is_offline_and_instances_are_independent(monkeypatch):
    def no_network(*_):
        raise AssertionError("构造阶段不得创建网络客户端")
    monkeypatch.setattr("plugins.jmcomic.client.JMComicClient.__enter__", no_network)
    tasks = create_tasks(ApplicationConfig.model_validate({"tasks": {
        name: {"type": "jmcomic", "config": {"username": name, "password": "fake"}}
        for name in ("first", "second")
    }}))
    assert len(tasks) == 2
    assert tasks[0].config is not tasks[1].config
    assert tasks[0].config.username.get_secret_value() == "first"
    assert tasks[1].config.username.get_secret_value() == "second"


def test_example_is_disabled_without_credentials(monkeypatch):
    monkeypatch.delenv("JM_USERNAME", raising=False)
    monkeypatch.delenv("JM_PASSWORD", raising=False)
    root = Path(__file__).resolve().parents[1]
    cfg = load_config(root / "config/application-example.yaml")
    # 公共示例允许新增其他站点，JM 的默认禁用约定保持不变。
    assert "jm" in cfg.tasks
    assert cfg.tasks["jm"].enabled is False
    assert create_tasks(cfg) == []


@pytest.mark.parametrize("value,expected", [(True, True), (False, False), (None, False)])
def test_calendar_boolean_semantics(value, expected):
    assert signed_today({"record": [[{"date": "04", "signed": value}]]}, 4) is expected


@pytest.mark.parametrize("data", [
    {}, {"signed": "false"}, {"signed": 1}, {"record": {}}, {"record": [None]},
    {"record": [["bad"]]}, {"record": [[{"date": "04", "signed": "false"}]]},
    {"record": [[{"date": "04", "signed": 1}]]},
    {"record": [[{"date": "03", "signed": True}]]},
    {"record": [[{"date": "04", "signed": True}, {"date": 4, "signed": False}]]},
    {"record": [[{"date": 40, "signed": False}]]},
])
def test_unknown_calendar_is_not_treated_as_unsigned(data):
    with pytest.raises(JMProtocolError):
        signed_today(data, 4)


def test_top_level_flag_and_calendar_padding():
    assert signed_today({"signed": True}, 4)
    assert not signed_today({"signed": False}, 4)
    assert signed_today({"record": [[{"date": ""}, {"date": "04", "signed": True}]]}, 4)


def test_site_date_uses_utc_plus_eight(monkeypatch):
    class Clock:
        @staticmethod
        def now(tz):
            from datetime import datetime, timezone
            return datetime(2026, 10, 3, 16, 1, tzinfo=timezone.utc).astimezone(tz)
    monkeypatch.setattr("plugins.jmcomic.client.datetime", Clock)
    assert site_today() == date(2026, 10, 4)


@pytest.mark.parametrize("data,expected", [
    ({"msg": "Jcoin:40 EXP:40"}, TaskStatus.SUCCESS),
    ({"status": "ok"}, TaskStatus.SUCCESS),
    ({"msg": "簽到成功"}, TaskStatus.SUCCESS),
    ({"msg": "今天已經簽到過了"}, TaskStatus.SKIPPED),
    ({"msg": "今日已签到"}, TaskStatus.SKIPPED),
])
def test_post_business_markers(data, expected):
    assert checkin_status(data) is expected


@pytest.mark.parametrize("data", [
    {}, {"msg": "unknown"}, {"msg": "签到未成功"}, {"msg": None}, {"status": "new"},
    {"msg": "领取 Jcoin:40 失败"},
])
def test_unknown_post_result_does_not_mean_success(data):
    with pytest.raises(JMProtocolError):
        checkin_status(data)
