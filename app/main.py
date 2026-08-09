import tasks.demo

from app.bootstrap import Bootstrap
from configuration.loader import load_config
from core.executor import TaskExecutor
from core.logging import init_logging, get_logger
from notification.console import ConsoleChannel
from notification.service import NotificationService


logger = get_logger(__name__)


def main():
    init_logging()

    config = load_config()
    results = TaskExecutor().execute(
        Bootstrap(config).create_tasks()
    )

    if NotificationService().should_send(
        config.notification.policy,
        results
    ):
        ConsoleChannel({}).send(results)

    logger.info(f"Executed tasks: {len(results)}")


if __name__ == "__main__":
    main()
