from dataclasses import dataclass

from pydantic import BaseModel, ValidationError

from configuration.exception import ConfigurationError
from configuration.model import ApplicationConfig
from configuration.resolver import ensure_env_resolved
from tasks.base import AutomationTask


@dataclass(frozen=True, slots=True)
class TaskDefinition:
    task_class: type[AutomationTask]
    config_class: type[BaseModel]


# Explicit registry. Real task implementations are added here as the project grows.
# Example for a future JM task:
#
# from tasks.jm.config import JmConfig
# from tasks.jm.task import JmTask
# TASK_REGISTRY = {"jm": TaskDefinition(JmTask, JmConfig)}
TASK_REGISTRY: dict[str, TaskDefinition] = {}


def create_tasks(config: ApplicationConfig) -> list[AutomationTask]:
    tasks: list[AutomationTask] = []

    for name, item in config.tasks.items():
        if not item.enabled:
            continue

        definition = TASK_REGISTRY.get(name)
        if definition is None:
            raise ConfigurationError(
                f"Enabled task is not registered: {name}"
            )

        ensure_env_resolved(item.config, f"tasks.{name}.config")

        try:
            task_config = definition.config_class.model_validate(item.config)
        except ValidationError as exc:
            raise ConfigurationError(
                f"Invalid configuration for task '{name}': {exc}"
            ) from exc

        tasks.append(definition.task_class(name, task_config))

    return tasks
