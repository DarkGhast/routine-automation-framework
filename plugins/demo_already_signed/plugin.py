from pydantic import Field

from configuration.model import StrictModel
from core.result import TaskResult, TaskStatus
from tasks.base import AutomationTask
from tasks.definition import TaskDefinition


class AlreadySignedConfig(StrictModel):
    message: str = Field(default="今日已签到，无需重复签到（模拟）", min_length=1)


class AlreadySignedTask(AutomationTask):
    def __init__(self, task_name: str, config: AlreadySignedConfig):
        super().__init__(task_name)
        self.config = config

    def execute(self) -> TaskResult:
        """模拟服务端报告已签到，跳过本次操作，不视为错误。"""
        return TaskResult(self.task_name, TaskStatus.SKIPPED, self.config.message)


PLUGIN = TaskDefinition(AlreadySignedTask, AlreadySignedConfig)
