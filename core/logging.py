import logging


DEFAULT_FORMAT = "%(asctime)s %(levelname)s %(name)s - %(message)s"


def init_logging(level: str = "INFO") -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper()),
        format=DEFAULT_FORMAT,
        force=True,
    )


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
