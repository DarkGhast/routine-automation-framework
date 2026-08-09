import logging


DEFAULT_FORMAT = "%(asctime)s %(levelname)s %(name)s - %(message)s"


def init_logging(level: str = "INFO"):
    logging.basicConfig(
        level=getattr(logging, level.upper()),
        format=DEFAULT_FORMAT,
    )


def get_logger(name: str):
    return logging.getLogger(name)
