from pydantic import Field

from configuration.model import StrictModel
from core.result import TaskResult, TaskStatus
from tasks.base import AutomationTask
from tasks.definition import TaskDefinition


class SuccessConfig(StrictModel):
    message: str = Field(default="签到成功（模拟）", min_length=1)


class SuccessTask(AutomationTask):
    def __init__(self, task_name: str, config: SuccessConfig):
        super().__init__(task_name)
        self.config = config

    def execute(self) -> TaskResult:
        """模拟成功，不发送网络请求。"""
        return TaskResult(self.task_name, TaskStatus.SUCCESS, self.config.message)


PLUGIN = TaskDefinition(SuccessTask, SuccessConfig)
