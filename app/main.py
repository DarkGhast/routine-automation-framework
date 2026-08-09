from app.bootstrap import Bootstrap
from configuration.loader import load_config
from core.executor import TaskExecutor
from core.logging import get_logger, init_logging
from notification.service import NotificationService


logger = get_logger(__name__)


def main() -> None:
    config = load_config()
    init_logging(config.logging.level)

    bootstrap = Bootstrap(config)
    results = TaskExecutor().execute(bootstrap.create_tasks())

    if NotificationService().should_send(config.notification, results):
        bootstrap.create_notification_channel().send(results)

    logger.info("Executed tasks: %s", len(results))


if __name__ == "__main__":
    main()
