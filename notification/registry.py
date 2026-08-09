_CHANNEL_REGISTRY = {}


def register_channel(name: str, channel_class: type):
    _CHANNEL_REGISTRY[name] = channel_class


def create_channel(config):
    channel_type = config.type

    channel_class = _CHANNEL_REGISTRY.get(channel_type)

    if channel_class is None:
        raise ValueError(
            f"Unknown notification channel: {channel_type}"
        )

    return channel_class(config.config)
