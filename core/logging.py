import logging
import sys

from core.console import RESET, supports_color


DEFAULT_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"


class ConsoleFormatter(logging.Formatter):
    def __init__(self, color: bool):
        super().__init__(DEFAULT_FORMAT, datefmt="%H:%M:%S")
        self.color = color

    def format(self, record: logging.LogRecord) -> str:
        text = super().format(record)
        if not self.color:
            return text
        # 从弱提示到强告警逐级强调；INFO 跟随主题，避免浅色主题下白字难读。
        if record.levelno >= logging.CRITICAL:
            color = "\033[1;97;41m"
        elif record.levelno >= logging.ERROR:
            color = "\033[91m"
        elif record.levelno >= logging.WARNING:
            color = "\033[93m"
        elif record.levelno >= logging.INFO:
            color = "\033[39m"
        else:
            color = "\033[90m"
        return f"{color}{text}{RESET}"


def init_logging(level: str = "INFO") -> None:
    # 与控制台通知使用同一个输出流，避免 IDE 将普通日志染红或交错显示。
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(ConsoleFormatter(supports_color(sys.stdout)))
    logging.basicConfig(
        level=getattr(logging, level.upper()),
        handlers=[handler],
        force=True,
    )


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)


def preview_logging() -> None:
    """临时展示各等级样式，不抛异常，不改变正常日志过滤等级。"""
    logger = get_logger("logging.preview")
    original_level = logger.level
    logger.setLevel(logging.DEBUG)
    try:
        for level, message in (
            (logging.DEBUG, "调试信息：用于排查执行细节"),
            (logging.INFO, "普通信息：任务正常执行"),
            (logging.WARNING, "警告信息：需要留意的情况"),
            (logging.ERROR, "错误信息：程序执行异常"),
            (logging.CRITICAL, "严重错误：程序无法继续"),
        ):
            logger.log(level, "[样式预览，非真实事件] %s", message)
    finally:
        logger.setLevel(original_level)
