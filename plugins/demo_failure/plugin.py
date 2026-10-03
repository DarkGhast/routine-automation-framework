from pydantic import Field

from configuration.model import StrictModel
from core.result import TaskResult, TaskStatus
from tasks.base import AutomationTask
from tasks.definition import TaskDefinition


class FailureConfig(StrictModel):
    message: str = Field(default="签到失败（模拟）", min_length=1)


class FailureTask(AutomationTask):
    def __init__(self, task_name: str, config: FailureConfig):
        super().__init__(task_name)
        self.config = config

    def execute(self) -> TaskResult:
        """模拟业务返回签到失败，不通过异常表达业务结果。"""
        return TaskResult(self.task_name, TaskStatus.FAILED, self.config.message)


PLUGIN = TaskDefinition(FailureTask, FailureConfig)
