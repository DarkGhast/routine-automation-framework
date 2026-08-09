from pydantic import BaseModel
from tasks.base import AutomationTask
from tasks.registry import register_task
from core.result import TaskResult, TaskStatus


class DemoConfig(BaseModel):
    message: str = "demo"


class SuccessDemoTask(AutomationTask):

    def __init__(self, config):
        self.config = config

    def execute(self):
        return TaskResult(
            "success_demo",
            TaskStatus.SUCCESS,
            self.config.message
        )


class FailedDemoTask(AutomationTask):

    def __init__(self, config):
        self.config = config

    def execute(self):
        raise RuntimeError(self.config.message)


register_task("success_demo", SuccessDemoTask, DemoConfig)
register_task("failed_demo", FailedDemoTask, DemoConfig)
