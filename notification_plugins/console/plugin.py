from configuration.model import StrictModel
from notification.console import ConsoleChannel
from notification.definition import NotificationDefinition


class ConsoleConfig(StrictModel):
    pass


class ConsolePlugin(ConsoleChannel):
    def __init__(self, config: ConsoleConfig):
        super().__init__(config.model_dump())


PLUGIN = NotificationDefinition(ConsolePlugin, ConsoleConfig)
