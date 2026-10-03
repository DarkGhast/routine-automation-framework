import importlib
import sys
import textwrap

import pytest

import plugins
from configuration.exception import ConfigurationError
from configuration.model import ApplicationConfig
from tasks.registry import create_tasks


@pytest.fixture
def local_plugin(tmp_path, monkeypatch):
    # 仅添加插件目录；不修改框架注册表或加载函数。
    monkeypatch.setattr(plugins, "__path__", [*plugins.__path__, str(tmp_path)])
    package = tmp_path / "temporary_example"
    package.mkdir()
    (package / "__init__.py").write_text("", encoding="utf-8")

    def write(source):
        (package / "plugin.py").write_text(textwrap.dedent(source), encoding="utf-8")
        importlib.invalidate_caches()
        return "temporary_example"

    yield write
    for name in list(sys.modules):
        if name == "plugins.temporary_example" or name.startswith("plugins.temporary_example."):
            sys.modules.pop(name, None)


def application(task_type, config=None, enabled=True):
    return ApplicationConfig.model_validate({
        "tasks": {
            "instance": {
                "type": task_type,
                "enabled": enabled,
                "config": {} if config is None else config,
            }
        }
    })


def test_new_directory_plugin_loads_without_registration(local_plugin):
    task_type = local_plugin("""
        from configuration.model import StrictModel
        from core.result import TaskResult, TaskStatus
        from tasks.base import AutomationTask
        from tasks.definition import TaskDefinition

        class Config(StrictModel):
            token: str

        class Task(AutomationTask):
            def __init__(self, task_name, config):
                super().__init__(task_name)
                self.config = config

            def execute(self):
                return TaskResult(self.task_name, TaskStatus.SUCCESS, self.config.token)

        PLUGIN = TaskDefinition(Task, Config)
    """)
    tasks = create_tasks(application(task_type, {"token": "abc"}))
    assert len(tasks) == 1
    assert tasks[0].task_name == "instance"
    assert tasks[0].execute().message == "abc"


def test_unknown_enabled_task_fails_fast():
    with pytest.raises(ConfigurationError, match="plugin not found"):
        create_tasks(application("nonexistent_plugin"))


def test_disabled_plugin_is_not_imported(local_plugin):
    task_type = local_plugin('raise RuntimeError("不应导入禁用模块")')
    assert create_tasks(application(task_type, {"token": "${MISSING_TOKEN}"}, enabled=False)) == []
    assert "plugins.temporary_example.plugin" not in sys.modules


def test_unknown_disabled_task_is_ignored():
    assert create_tasks(application("nonexistent_plugin", enabled=False)) == []


def test_missing_env_in_enabled_task_fails():
    with pytest.raises(ConfigurationError, match="MISSING_TOKEN"):
        create_tasks(application("demo_success", {"message": "${MISSING_TOKEN}"}))


def test_missing_env_in_enabled_type_fails():
    with pytest.raises(ConfigurationError, match="MISSING_TYPE"):
        create_tasks(application("${MISSING_TYPE}"))


def test_missing_dependency_is_not_reported_as_missing_plugin(local_plugin):
    task_type = local_plugin("import nonexistent_raf_test_dependency")
    with pytest.raises(ConfigurationError, match="missing dependency: nonexistent_raf_test_dependency"):
        create_tasks(application(task_type))


def test_import_error_identifies_plugin(local_plugin):
    task_type = local_plugin('raise RuntimeError("模块导入失败")')
    with pytest.raises(ConfigurationError, match="Unable to import task plugin 'temporary_example'"):
        create_tasks(application(task_type))


@pytest.mark.parametrize("source", [
    "PLUGIN = None",
    """
    from tasks.definition import TaskDefinition
    PLUGIN = TaskDefinition(object, object)
    """,
])
def test_invalid_plugin_contract_is_rejected(local_plugin, source):
    task_type = local_plugin(source)
    with pytest.raises(ConfigurationError, match="must"):
        create_tasks(application(task_type))


@pytest.mark.parametrize("task_type", ["", "../demo_success", "demo_success.plugin", "Demo"])
def test_invalid_plugin_type_is_rejected(task_type):
    with pytest.raises(ConfigurationError, match="Invalid task plugin type"):
        create_tasks(application(task_type))


@pytest.mark.parametrize("config", [{"message": ""}, {"unknown_field": 1}])
def test_plugin_config_validation_identifies_instance(config):
    with pytest.raises(ConfigurationError, match="Invalid configuration for task 'instance'"):
        create_tasks(application("demo_success", config))


def test_same_plugin_supports_independent_instances():
    config = ApplicationConfig.model_validate({
        "tasks": {
            "first": {"type": "demo_success", "config": {"message": "A"}},
            "second": {"type": "demo_success", "config": {"message": "B"}},
        }
    })
    first, second = create_tasks(config)
    assert first is not second
    assert first.config is not second.config
    assert (first.execute().task_name, first.execute().message) == ("first", "A")
    assert (second.execute().task_name, second.execute().message) == ("second", "B")


def test_omitted_type_defaults_to_instance_name():
    config = ApplicationConfig.model_validate({"tasks": {"demo_success": {}}})
    assert create_tasks(config)[0].task_name == "demo_success"


def test_constructor_error_identifies_instance(local_plugin):
    task_type = local_plugin("""
        from configuration.model import StrictModel
        from tasks.base import AutomationTask
        from tasks.definition import TaskDefinition

        class Task(AutomationTask):
            def __init__(self, task_name, config):
                raise RuntimeError("构造失败")

            def execute(self):
                pass

        PLUGIN = TaskDefinition(Task, StrictModel)
    """)
    with pytest.raises(ConfigurationError, match="Unable to create task 'instance'"):
        create_tasks(application(task_type))
