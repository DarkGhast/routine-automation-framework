"""仅用临时虚构凭据验证测试入口，不读取真实文件、不联网。"""
import json

import pytest

from core.exception import TaskTimeoutError
from core.result import TaskResult, TaskStatus
from plugins.picacg.live_test import run
from plugins.picacg.task import PicACGTask


@pytest.mark.parametrize("status", [TaskStatus.SUCCESS, TaskStatus.SKIPPED, TaskStatus.FAILED])
def test_file_only_used_by_test_entry(tmp_path, monkeypatch, status):
    path = tmp_path / "fake.json"
    path.write_text(json.dumps({"username": "fake-account", "password": " fake-password "}), encoding="utf-8-sig")
    def execute(task):
        assert task.config.username.get_secret_value() == "fake-account"
        assert task.config.password.get_secret_value() == " fake-password "
        assert not hasattr(task.config, "credentials_file")
        return TaskResult(task.task_name, status, "固定脱敏结果")
    monkeypatch.setattr(PicACGTask, "execute", execute)
    result = run(path)
    assert result["status"] == status.value
    assert "fake-password" not in str(result)


@pytest.mark.parametrize("content", ['{"username":"PRIVATE","password": broken}', '{"username":"PRIVATE"}', '{"username":"PRIVATE","password":""}'])
def test_bad_test_input_never_reaches_task(tmp_path, monkeypatch, content):
    path = tmp_path / "bad.json"
    path.write_text(content, encoding="utf-8")
    monkeypatch.setattr(PicACGTask, "execute", lambda _: pytest.fail("must not execute"))
    result = run(path)
    assert result["status"] == "CONFIG_ERROR"
    assert "PRIVATE" not in str(result)


@pytest.mark.parametrize("error,status", [(TaskTimeoutError("private"), "TIMEOUT"), (RuntimeError("private"), "ERROR")])
def test_exception_output_hidden(tmp_path, monkeypatch, error, status):
    path = tmp_path / "fake.json"
    path.write_text(json.dumps({"username": "fake", "password": "fake"}), encoding="utf-8")
    def execute(_):
        raise error
    monkeypatch.setattr(PicACGTask, "execute", execute)
    result = run(path)
    assert result["status"] == status
    assert "private" not in str(result)
