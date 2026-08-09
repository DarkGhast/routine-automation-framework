from pathlib import Path

import yaml
from pydantic import ValidationError

from configuration.exception import ConfigurationError
from configuration.model import ApplicationConfig
from configuration.resolver import resolve_env


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = PROJECT_ROOT / "config" / "application.yaml"


def load_config(path: Path = DEFAULT_CONFIG) -> ApplicationConfig:
    if not path.exists():
        raise ConfigurationError(f"Configuration file not found: {path}")

    try:
        with path.open("r", encoding="utf-8") as file:
            raw = yaml.safe_load(file) or {}
    except yaml.YAMLError as exc:
        raise ConfigurationError(f"Invalid YAML in {path}: {exc}") from exc

    if not isinstance(raw, dict):
        raise ConfigurationError("Application configuration root must be a mapping")

    resolved = resolve_env(raw)

    try:
        return ApplicationConfig.model_validate(resolved)
    except ValidationError as exc:
        raise ConfigurationError(f"Invalid application configuration: {exc}") from exc
