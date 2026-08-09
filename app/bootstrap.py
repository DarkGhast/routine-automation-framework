from tasks.registry import create_tasks


class Bootstrap:

    def __init__(self, config):
        self.config = config

    def create_tasks(self):
        return create_tasks(self.config)
