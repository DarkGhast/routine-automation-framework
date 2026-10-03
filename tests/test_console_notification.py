from io import StringIO
import re

from core.console import display_width, supports_color
from core.result import TaskResult, TaskStatus
from notification.console import ConsoleChannel


def test_multiline_notification_wraps_without_right_padding(monkeypatch, capsys):
    monkeypatch.setenv("NO_COLOR", "1")
    monkeypatch.setenv("COLUMNS", "60")
    ConsoleChannel({}).send([
        TaskResult("示例", TaskStatus.SUCCESS, "中文长消息" * 25 + "\n第二行"),
    ])
    lines = capsys.readouterr().out.strip().splitlines()
    assert lines[0].startswith("┌") and lines[-1].startswith("└")
    assert lines[0][1:] == lines[-1][1:]
    assert all(line.startswith("│") for line in lines[1:-1])
    assert all(line == line.rstrip() for line in lines)
    assert max(display_width(line) for line in lines) <= 60
    assert "\033[" not in "".join(lines)


def test_empty_notification_and_forced_color(monkeypatch, capsys):
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.setenv("FORCE_COLOR", "1")
    ConsoleChannel({}).send([])
    output = capsys.readouterr().out
    assert "本次没有执行任务" in output
    assert "\033[36m" in output
    assert "┌" in re.sub(r"\033\[[0-9;]*m", "", output)


def test_color_detection_for_pycharm_and_plain_output(monkeypatch):
    for name in ("NO_COLOR", "FORCE_COLOR", "PYCHARM_HOSTED", "GITHUB_ACTIONS", "TERM"):
        monkeypatch.delenv(name, raising=False)
    stream = StringIO()
    assert not supports_color(stream)
    monkeypatch.setenv("PYCHARM_HOSTED", "1")
    assert supports_color(stream)
    monkeypatch.setenv("NO_COLOR", "1")
    assert not supports_color(stream)
