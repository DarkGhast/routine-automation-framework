import os
import re
from typing import Any

from configuration.exception import ConfigurationError


ENV_PATTERN = re.compile(r"\$\{([^}:]+)(?::([^}]*))?\}")


def resolve_env(value: Any) -> Any:
    """Resolve ${ENV} and ${ENV:default} placeholders recursively."""
    if isinstance(value, dict):
        return {key: resolve_env(item) for key, item in value.items()}

    if isinstance(value, list):
        return [resolve_env(item) for item in value]

    if isinstance(value, str):
        def replace(match: re.Match[str]) -> str:
            key = match.group(1)
            default = match.group(2)

            if key in os.environ:
                return os.environ[key]

            if default is not None:
                return default

            # Do not fail globally here. A missing secret inside a disabled task
            # should be allowed. Active components validate unresolved placeholders
            # when they are instantiated.
            return match.group(0)

        return ENV_PATTERN.sub(replace, value)

    return value


def ensure_env_resolved(value: Any, path: str) -> None:
    """Reject unresolved environment placeholders inside an active component."""
    unresolved = _find_unresolved(value)

    if not unresolved:
        return

    names = ", ".join(sorted(unresolved))
    raise ConfigurationError(
        f"Unresolved environment variable(s) in {path}: {names}"
    )


def _find_unresolved(value: Any) -> set[str]:
    result: set[str] = set()

    if isinstance(value, dict):
        for item in value.values():
            result.update(_find_unresolved(item))
        return result

    if isinstance(value, list):
        for item in value:
            result.update(_find_unresolved(item))
        return result

    if isinstance(value, str):
        result.update(match.group(1) for match in ENV_PATTERN.finditer(value))

    return result
