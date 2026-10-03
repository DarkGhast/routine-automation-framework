from tasks.definition import TaskDefinition

from .config import JMComicConfig
from .task import JMComicTask


PLUGIN = TaskDefinition(task_class=JMComicTask, config_class=JMComicConfig)
