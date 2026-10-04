"""沿真实配置加载链测试；仅使用临时文件及虚构凭据，不访问 config-test。"""

import json
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml
from pydantic import ValidationError

from configuration.exception import ConfigurationError
from configuration.loader import load_config
from core.executor import TaskExecutor
from core.result import TaskStatus
from plugins.picacg.client import PicACGClient
from plugins.picacg.config import PicACGConfig
from tasks.registry import create_tasks
from tests.test_picacg import FakeOpener, LOGIN, signed_profile


def write_config(tmp_path, task_config, enabled=True):
    path = tmp_path / "application.yaml"
    path.write_text(yaml.safe_dump({"tasks": {"pica": {
        "type": "picacg", "enabled": enabled, "config": task_config,
    }}}), encoding="utf-8")
    return path


def test_framework_resolves_env_and_masks_secrets(tmp_path, monkeypatch):
    monkeypatch.setenv("PICA_USERNAME", "fake-account")
    monkeypatch.setenv("PICA_PASSWORD", " fake-password ")
    path = write_config(tmp_path, {"username": "${PICA_USERNAME}", "password": "${PICA_PASSWORD}", "timeout": "${PICA_TIMEOUT:12}"})
    with patch("plugins.picacg.task.PicACGClient", side_effect=AssertionError("construction must not create client")):
        task = create_tasks(load_config(path))[0]
    assert (task.config.username.get_secret_value(), task.config.password.get_secret_value()) == ("fake-account", " fake-password ")
    assert task.config.timeout == 12
    assert "fake-account" not in repr(task.config)
    assert "fake-password" not in repr(task.config)


@pytest.mark.parametrize("enabled", [True, False])
def test_missing_env_only_rejected_for_enabled_task(tmp_path, monkeypatch, enabled):
    monkeypatch.delenv("PICA_USERNAME", raising=False)
    monkeypatch.delenv("PICA_PASSWORD", raising=False)
    path = write_config(tmp_path, {"username": "${PICA_USERNAME}", "password": "${PICA_PASSWORD}"}, enabled)
    if enabled:
        with pytest.raises(ConfigurationError, match="Unresolved environment"):
            create_tasks(load_config(path))
    else:
        assert create_tasks(load_config(path)) == []


@pytest.mark.parametrize("fields", [
    {}, {"username": "only-user"}, {"password": "only-password"},
    {"username": "  ", "password": "hidden"},
    {"username": "fake", "password": " "},
    {"credentials_file": "unused.json", "username": "hidden", "password": "hidden"},
    {"credentials_file": "unused.json", "password": "hidden"},
    {"username_env": "PICA_USERNAME", "password_env": "PICA_PASSWORD"},
])
def test_invalid_credential_sources_rejected_without_input_echo(fields):
    with pytest.raises(ValidationError) as exc:
        PicACGConfig(**fields)
    assert "hidden" not in str(exc.value)
    assert "only-password" not in str(exc.value)


def test_public_example_uses_framework_placeholders(monkeypatch):
    # 公共示例不是本地运行配置，不含真实账号。
    path = Path(__file__).resolve().parents[1] / "config/application-example.yaml"
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    item = raw["tasks"]["picacg"]
    assert item["enabled"] is False
    assert item["config"]["username"] == "${PICA_USERNAME}"
    assert item["config"]["password"] == "${PICA_PASSWORD}"
    monkeypatch.delenv("PICA_USERNAME", raising=False)
    monkeypatch.delenv("PICA_PASSWORD", raising=False)
    assert create_tasks(load_config(path)) == []


def test_module_example_can_construct_without_accessing_real_file(monkeypatch):
    monkeypatch.setenv("PICA_USERNAME", "example-user")
    monkeypatch.setenv("PICA_PASSWORD", "example-password")
    path = Path(__file__).resolve().parents[1] / "plugins/picacg/application.example.yaml"
    with patch("plugins.picacg.task.PicACGClient", side_effect=AssertionError("construction must not create client")):
        tasks = create_tasks(load_config(path))
    assert len(tasks) == 1
    assert (tasks[0].config.username.get_secret_value(), tasks[0].config.password.get_secret_value()) == ("example-user", "example-password")


def test_multi_instance_isolation_and_failure_does_not_stop_next(tmp_path):
    path = tmp_path / "application.yaml"
    task_items = {
        name: {"type": "picacg", "config": {
            "username": name, "password": "fake-password-" + name,
            "proxy_mode": "direct", "max_retries": 0,
        }} for name in ("first", "second")
    }
    path.write_text(yaml.safe_dump({"tasks": task_items}), encoding="utf-8")
    tasks = create_tasks(load_config(path))
    openers = [FakeOpener(TimeoutError("sensitive network details")), FakeOpener(LOGIN, signed_profile())]
    clients = []
    for task, opener in zip(tasks, openers):
        def factory(config, audit, opener=opener):
            client = PicACGClient(config, audit, opener=opener)
            clients.append(client)
            return client
        task.client_factory = factory
    results = TaskExecutor().execute(tasks)
    assert [r.status for r in results] == [TaskStatus.TIMEOUT, TaskStatus.SKIPPED]
    assert clients[0] is not clients[1]
    assert all(client._token is None for client in clients)
    for name, opener in zip(task_items, openers):
        req = opener.requests[0][0]
        assert json.loads(req.data)["email"] == name
        assert req.get_header("Authorization") is None
    assert not (tmp_path / "logs").exists()
