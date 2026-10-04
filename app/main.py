import argparse
from pathlib import Path

from app.bootstrap import Bootstrap
from configuration.loader import DEFAULT_CONFIG, load_config
from core.executor import TaskExecutor
from core.logging import get_logger, init_logging, preview_logging
from notification.service import NotificationService


logger = get_logger(__name__)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="执行配置中的日常自动化任务")
    parser.add_argument(
        "--config", type=Path, default=DEFAULT_CONFIG, help="应用 YAML 配置路径"
    )
    parser.add_argument(
        "--preview-logging", action="store_true",
        help="执行任务前展示各等级日志样式（仅预览，不代表真实异常）",
    )
    args = parser.parse_args(argv)
    config = load_config(args.config)
    init_logging(config.logging.level)
    if args.preview_logging:
        preview_logging()

    bootstrap = Bootstrap(config)
    results = TaskExecutor().execute(bootstrap.create_tasks())

    logger.info("任务执行结束，共 %s 项", len(results))

    NotificationService().send(config.notification, results)


if __name__ == "__main__":
    main()
