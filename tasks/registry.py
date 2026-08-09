from dataclasses import dataclass


@dataclass
class TaskDefinition:
    task_class: type
    config_class: type


TASK_REGISTRY = {}


def register_task(name, task_class, config_class):
    TASK_REGISTRY[name] = TaskDefinition(task_class, config_class)


def create_tasks(config):
    tasks = []

    for name, item in config.tasks.items():
        if not item.enabled:
            continue

        definition = TASK_REGISTRY.get(name)
        if definition is None:
            continue

        task_config = definition.config_class.model_validate(item.config)
        tasks.append(definition.task_class(task_config))

    return tasks
