from tasks.definition import TaskDefinition

from .config import PicACGConfig
from .task import PicACGTask


PLUGIN = TaskDefinition(task_class=PicACGTask, config_class=PicACGConfig)
