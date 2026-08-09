import pytest

from configuration.exception import ConfigurationError
from configuration.loader import load_config


def write_config(tmp_path, content):
    path = tmp_path / "application.yaml"
    path.write_text(content, encoding="utf-8")
    return path


def test_logging_level_is_normalized(tmp_path):
    config = load_config(write_config(tmp_path, "logging:\n  level: debug\n"))
    assert config.logging.level == "DEBUG"


def test_invalid_logging_level_fails_fast(tmp_path):
    path = write_config(tmp_path, "logging:\n  level: TRACE\n")
    with pytest.raises(ConfigurationError):
        load_config(path)


def test_invalid_notification_policy_fails_fast(tmp_path):
    path = write_config(
        tmp_path,
        "notification:\n  policy: error_olny\n  channel:\n    type: console\n",
    )
    with pytest.raises(ConfigurationError):
        load_config(path)
