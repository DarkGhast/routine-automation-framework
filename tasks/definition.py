from dataclasses import dataclass

from pydantic import BaseModel

from tasks.base import AutomationTask


@dataclass(frozen=True, slots=True)
class TaskDefinition:
    """插件入口：配置模型及接受 (实例名, 配置) 的任务类。"""

    task_class: type[AutomationTask]
    config_class: type[BaseModel]
