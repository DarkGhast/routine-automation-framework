from core.logging import get_logger
from core.result import TaskResult, TaskStatus
from tasks.base import AutomationTask

from .audit import NullAudit
from .client import BusinessRejected, PicACGClient
from .config import PicACGConfig


logger = get_logger(__name__)


class PicACGTask(AutomationTask):
    def __init__(self, task_name: str, config: PicACGConfig, client_factory=PicACGClient):
        super().__init__(task_name)
        self.config, self.client_factory = config, client_factory

    def execute(self) -> TaskResult:
        audit = NullAudit()
        try:
            with self.client_factory(self.config, audit) as client:
                client.login(self.config.username.get_secret_value(), self.config.password.get_secret_value())
                logger.info("哔咔实例 %s 登录成功，开始检查签到状态", self.task_name)
                status = client.check_in()
        except BusinessRejected as exc:
            return TaskResult(self.task_name, TaskStatus.FAILED, str(exc))
        message = "哔咔今日已签到，无需重复签到" if status is TaskStatus.SKIPPED else "哔咔今日签到完成，已查询确认"
        logger.info("%s", message)
        return TaskResult(self.task_name, status, message)
