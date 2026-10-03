import shutil
import sys
from typing import Any

from core.console import CYAN, RESET, display_width, supports_color, wrap_lines
from core.result import TaskResult, TaskStatus
from notification.base import NotificationChannel


class ConsoleChannel(NotificationChannel):
    def __init__(self, config: dict[str, Any]):
        # 保留渠道私有配置入口，目前使用统一的控制台样式。
        self.config = config

    def send(self, results: list[TaskResult]) -> None:
        counts = {status: sum(item.status == status for item in results) for status in TaskStatus}
        content = [
            "任务执行通知",
            (
                f"共 {len(results)} 项 | 成功 {counts[TaskStatus.SUCCESS]}"
                f" | 跳过 {counts[TaskStatus.SKIPPED]}"
                f" | 失败 {counts[TaskStatus.FAILED]}"
                f" | 超时 {counts[TaskStatus.TIMEOUT]}"
            ),
            "",
        ]
        for item in results:
            content.append(f"{item.task_name}: {item.status.value} - {item.message}")
        if not results:
            content.append("本次没有执行任务")

        # 中文回退字体未必占两个英文字符宽；省略右边框，不依赖空格补齐。
        # 仍按终端列数估算换行宽度，保留上下横线及左侧边界。
        limit = max(12, min(96, shutil.get_terminal_size(fallback=(96, 24)).columns) - 4)
        lines = [line for text in content for line in wrap_lines(text, limit)]
        width = max(display_width(line) for line in lines)
        rows = ["┌" + "─" * (width + 2), "│"]
        rows.extend(f"│ {line}" if line else "│" for line in lines)
        rows.extend(["│", "└" + "─" * (width + 2)])
        if supports_color(sys.stdout):
            rows = [f"{CYAN}{row}{RESET}" for row in rows]
        print("\n" + "\n".join(rows) + "\n", flush=True)
