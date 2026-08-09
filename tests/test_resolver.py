import pytest

from configuration.exception import ConfigurationError
from configuration.resolver import ensure_env_resolved, resolve_env


def test_resolve_environment_value(monkeypatch):
    monkeypatch.setenv("EXAMPLE_VALUE", "resolved")
    assert resolve_env("${EXAMPLE_VALUE}") == "resolved"


def test_resolve_default_value(monkeypatch):
    monkeypatch.delenv("MISSING_VALUE", raising=False)
    assert resolve_env("${MISSING_VALUE:default}") == "default"


def test_required_placeholder_stays_unresolved_until_component_validation(monkeypatch):
    monkeypatch.delenv("MISSING_SECRET", raising=False)
    value = resolve_env({"secret": "${MISSING_SECRET}"})

    with pytest.raises(ConfigurationError, match="MISSING_SECRET"):
        ensure_env_resolved(value, "test.component")
