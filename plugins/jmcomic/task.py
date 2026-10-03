import random
import time

from core.logging import get_logger
from core.result import TaskResult, TaskStatus
from tasks.base import AutomationTask

from .client import BusinessRejected, JMComicClient
from .config import JMComicConfig


logger = get_logger(__name__)


class JMComicTask(AutomationTask):
    def __init__(self, task_name: str, config: JMComicConfig, client_factory=JMComicClient):
        super().__init__(task_name)
        self.config = config
        self.client_factory = client_factory

    def execute(self) -> TaskResult:
        if self.config.random_delay_seconds > 0:
            delay = random.uniform(0, self.config.random_delay_seconds)
            logger.info("JMComic 随机等待 %.1f 秒后开始执行", delay)
            time.sleep(delay)
        try:
            with self.client_factory(self.config) as client:
                client.prepare()
                client.login()
                logger.info("JMComic 登录成功，开始检查签到状态")
                status = client.check_in()
        except BusinessRejected as exc:
            return TaskResult(self.task_name, TaskStatus.FAILED, str(exc))
        message = "今日已签到，无需重复签到" if status is TaskStatus.SKIPPED else "签到成功"
        return TaskResult(self.task_name, status, message)
