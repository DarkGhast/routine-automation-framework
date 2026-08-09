from core.logging import init_logging, get_logger
from configuration.loader import load_config
from app.bootstrap import Bootstrap


logger = get_logger(__name__)


def main():
    init_logging()

    config = load_config()
    bootstrap = Bootstrap(config)

    tasks = bootstrap.create_tasks()

    logger.info("Routine Automation Framework started")
    logger.info(f"Loaded tasks: {len(tasks)}")


if __name__ == "__main__":
    main()
