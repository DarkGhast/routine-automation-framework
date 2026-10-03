import re
from importlib import import_module

from pydantic import BaseModel, ValidationError

from configuration.exception import ConfigurationError
from configuration.model import ApplicationConfig
from configuration.resolver import ensure_env_resolved
from tasks.base import AutomationTask
from tasks.definition import TaskDefinition


def load_definition(task_type: str) -> TaskDefinition:
    """按约定导入启用的本地插件，不扫描或导入其他插件。"""
    if not re.fullmatch(r"[a-z][a-z0-9_]*", task_type):
        raise ConfigurationError(f"Invalid task plugin type: {task_type!r}")

    package_name = f"plugins.{task_type}"
    module_name = f"{package_name}.plugin"
    try:
        module = import_module(module_name)
    except ModuleNotFoundError as exc:
        if exc.name in {package_name, module_name}:
            raise ConfigurationError(
                f"Task plugin not found: {task_type} (expected {module_name})"
            ) from exc
        raise ConfigurationError(
            f"Task plugin '{task_type}' requires missing dependency: {exc.name}"
        ) from exc
    except Exception as exc:
        raise ConfigurationError(
            f"Unable to import task plugin '{task_type}': {exc}"
        ) from exc

    definition = getattr(module, "PLUGIN", None)
    if not isinstance(definition, TaskDefinition):
        raise ConfigurationError(
            f"Task plugin '{task_type}' must export PLUGIN as TaskDefinition"
        )
    if not (
        isinstance(definition.task_class, type)
        and issubclass(definition.task_class, AutomationTask)
        and isinstance(definition.config_class, type)
        and issubclass(definition.config_class, BaseModel)
    ):
        raise ConfigurationError(
            f"Task plugin '{task_type}' must provide an AutomationTask subclass "
            "and a Pydantic configuration model"
        )
    return definition


def create_tasks(config: ApplicationConfig) -> list[AutomationTask]:
    tasks: list[AutomationTask] = []

    for name, item in config.tasks.items():
        if not item.enabled:
            continue

        task_type = item.type if item.type is not None else name
        ensure_env_resolved(task_type, f"tasks.{name}.type")
        ensure_env_resolved(item.config, f"tasks.{name}.config")
        definition = load_definition(task_type)

        try:
            task_config = definition.config_class.model_validate(item.config)
        except ValidationError as exc:
            raise ConfigurationError(
                f"Invalid configuration for task '{name}' ({task_type}): {exc}"
            ) from exc

        try:
            task = definition.task_class(name, task_config)
        except Exception as exc:
            raise ConfigurationError(
                f"Unable to create task '{name}' ({task_type}): {exc}"
            ) from exc
        tasks.append(task)

    return tasks
