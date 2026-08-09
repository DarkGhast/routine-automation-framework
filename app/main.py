from core.logging import init_logging, get_logger
from configuration.loader import load_config


logger = get_logger(__name__)


def main():
    init_logging()

    config = load_config()

    logger.info("Routine Automation Framework started")
    logger.info(f"Notification channel: {config.notification.channel.type}")


if __name__ == "__main__":
    main()
