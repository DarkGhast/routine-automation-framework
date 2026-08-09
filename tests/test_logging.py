import logging

from core.logging import init_logging


def test_logging_level_is_applied():
    init_logging("DEBUG")
    assert logging.getLogger().level == logging.DEBUG
