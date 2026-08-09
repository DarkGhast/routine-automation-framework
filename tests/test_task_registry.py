import pytest
from pydantic import BaseModel

from configuration.exception import ConfigurationError
from configuration.model import ApplicationConfig
from core.result import TaskResult, TaskStatus
from tasks.base import AutomationTask
from tasks.registry import TASK_REGISTRY, TaskDefinition, create_tasks


class FakeConfig(BaseModel):
    token: str


class FakeTask(AutomationTask):
    def __init__(self, task_name, config):
        super().__init__(task_name)
        self.config = config

    def execute(self):
        return TaskResult(self.task_name, TaskStatus.SUCCESS, "ok")


def test_enabled_registered_task_is_created(monkeypatch):
    monkeypatch.setitem(TASK_REGISTRY, "fake", TaskDefinition(FakeTask, FakeConfig))
    config = ApplicationConfig.model_validate({
        "tasks": {"fake": {"enabled": True, "config": {"token": "abc"}}}
    })

    tasks = create_tasks(config)
    assert len(tasks) == 1
    assert tasks[0].task_name == "fake"
    assert tasks[0].config.token == "abc"


def test_unknown_enabled_task_fails_fast():
    config = ApplicationConfig.model_validate({
        "tasks": {"unknown": {"enabled": True}}
    })

    with pytest.raises(ConfigurationError, match="not registered"):
        create_tasks(config)


def test_unknown_disabled_task_is_ignored():
    config = ApplicationConfig.model_validate({
        "tasks": {"unknown": {"enabled": False}}
    })
    assert create_tasks(config) == []


def test_missing_env_in_enabled_task_fails(monkeypatch):
    monkeypatch.setitem(TASK_REGISTRY, "fake", TaskDefinition(FakeTask, FakeConfig))
    config = ApplicationConfig.model_validate({
        "tasks": {
            "fake": {
                "enabled": True,
                "config": {"token": "${MISSING_TOKEN}"},
            }
        }
    })

    with pytest.raises(ConfigurationError, match="MISSING_TOKEN"):
        create_tasks(config)


def test_missing_env_in_disabled_task_is_allowed(monkeypatch):
    monkeypatch.setitem(TASK_REGISTRY, "fake", TaskDefinition(FakeTask, FakeConfig))
    config = ApplicationConfig.model_validate({
        "tasks": {
            "fake": {
                "enabled": False,
                "config": {"token": "${MISSING_TOKEN}"},
            }
        }
    })
    assert create_tasks(config) == []
