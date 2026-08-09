from pathlib import Path
import yaml

from configuration.model import ApplicationConfig
from configuration.resolver import resolve_env


DEFAULT_CONFIG = Path("config/application.yaml")


def load_config(path: Path = DEFAULT_CONFIG) -> ApplicationConfig:
    if not path.exists():
        raise FileNotFoundError(
            f"Configuration file not found: {path}"
        )

    with path.open("r", encoding="utf-8") as file:
        raw = yaml.safe_load(file)

    resolved = resolve_env(raw)

    return ApplicationConfig.model_validate(resolved)
