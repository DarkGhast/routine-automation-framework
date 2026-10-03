import json
import logging

import pytest

from core.exception import TaskTimeoutError
from core.result import TaskResult, TaskStatus
from plugins.jmcomic.client import JMProtocolError, JMTransportError
from plugins.jmcomic.live_test import run


SECRET = "fake-credential-not-for-output"


@pytest.fixture
def credentials(tmp_path):
    path = tmp_path / "offline-credentials.json"
    path.write_text(json.dumps({"username": "offline", "password": SECRET}), encoding="utf-8")
    return path


@pytest.mark.parametrize("outcome,status", [
    (TaskStatus.SUCCESS, "SUCCESS"), (TaskStatus.SKIPPED, "SKIPPED"),
    (TaskStatus.FAILED, "FAILED"), (JMProtocolError(SECRET), "PROTOCOL_ERROR"),
    (JMTransportError(SECRET), "NETWORK_ERROR"), (TaskTimeoutError(SECRET), "TIMEOUT"),
    (RuntimeError(SECRET), "ERROR"),
])
def test_live_runner_never_returns_raw_output(credentials, monkeypatch, capsys, outcome, status):
    class Task:
        def execute(self):
            import sys
            print(SECRET)
            print(SECRET, file=sys.stderr)
            logging.getLogger("fake-sdk").critical(SECRET)
            if isinstance(outcome, Exception):
                raise outcome
            return TaskResult("offline", outcome, SECRET)

    monkeypatch.setattr("tasks.registry.create_tasks", lambda _: [Task()])
    original_level = logging.root.manager.disable
    result = run(credentials)
    assert result["status"] == status
    assert SECRET not in json.dumps(result)
    assert capsys.readouterr() == ("", "")
    assert logging.root.manager.disable == original_level


@pytest.mark.parametrize("raw", ["invalid-json", "[]", '{"password":"fake"}', '{"username": "", "password": "fake"}'])
def test_invalid_credentials_do_not_escape(tmp_path, raw, capsys):
    path = tmp_path / "invalid.json"
    path.write_text(raw, encoding="utf-8")
    assert run(path)["status"] == "CONFIG_ERROR"
    assert capsys.readouterr() == ("", "")


def test_missing_file_returns_fixed_message(tmp_path):
    assert run(tmp_path / "missing.json")["status"] == "CONFIG_ERROR"
