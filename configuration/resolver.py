import os
import re


PATTERN = re.compile(r"\$\{([^}:]+)(?::([^}]*))?\}")


def resolve_env(value):
    if isinstance(value, dict):
        return {k: resolve_env(v) for k, v in value.items()}

    if isinstance(value, list):
        return [resolve_env(v) for v in value]

    if isinstance(value, str):
        def replace(match):
            key = match.group(1)
            default = match.group(2)
            return os.getenv(key, default if default is not None else match.group(0))

        return PATTERN.sub(replace, value)

    return value
