import os
import unicodedata
from typing import TextIO


RESET = "\033[0m"
CYAN = "\033[36m"


def supports_color(stream: TextIO) -> bool:
    """兼容终端、PyCharm 和 Actions；重定向默认不输出颜色控制符。"""
    if "NO_COLOR" in os.environ:
        return False
    if "FORCE_COLOR" in os.environ:
        return os.environ["FORCE_COLOR"] != "0"
    if os.environ.get("TERM") == "dumb":
        return False
    return (
        stream.isatty()
        or os.environ.get("PYCHARM_HOSTED") == "1"
        or os.environ.get("GITHUB_ACTIONS") == "true"
    )


def display_width(text: str) -> int:
    """估算等宽终端的字符列数；IDE 回退字体的实际像素宽度可能不同。"""
    return sum(
        0 if unicodedata.combining(char)
        else 2 if unicodedata.east_asian_width(char) in {"W", "F"}
        else 1
        for char in text
    )


def wrap_lines(text: str, width: int) -> list[str]:
    lines: list[str] = []
    for paragraph in text.expandtabs(4).splitlines() or [""]:
        line = ""
        used = 0
        for char in paragraph:
            size = display_width(char)
            if used + size > width and line:
                lines.append(line)
                line = ""
                used = 0
            line += char
            used += size
        lines.append(line)
    return lines
