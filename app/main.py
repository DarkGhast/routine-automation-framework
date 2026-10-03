import argparse
from pathlib import Path

from app.bootstrap import Bootstrap
from configuration.loader import DEFAULT_CONFIG, load_config
from core.executor import TaskExecutor
from core.logging import get_logger, init_logging
from notification.service import NotificationService


logger = get_logger(__name__)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="执行配置中的日常自动化任务")
    parser.add_argument(
        "--config", type=Path, default=DEFAULT_CONFIG, help="应用 YAML 配置路径"
    )
    args = parser.parse_args(argv)
    config = load_config(args.config)
    init_logging(config.logging.level)

    bootstrap = Bootstrap(config)
    results = TaskExecutor().execute(bootstrap.create_tasks())

    if NotificationService().should_send(config.notification, results):
        bootstrap.create_notification_channel().send(results)

    logger.info("Executed tasks: %s", len(results))


if __name__ == "__main__":
    main()
