import tasks.demo
import notification.console

from app.bootstrap import Bootstrap
from configuration.loader import load_config
from core.executor import TaskExecutor
from core.logging import init_logging, get_logger
from notification.service import NotificationService


logger = get_logger(__name__)


def main():
    init_logging()

    config = load_config()
    bootstrap = Bootstrap(config)

    results = TaskExecutor().execute(
        bootstrap.create_tasks()
    )

    if NotificationService().should_send(
        config.notification.policy,
        results
    ):
        bootstrap.create_notification_channel().send(results)

    logger.info(f"Executed tasks: {len(results)}")


if __name__ == "__main__":
    main()
