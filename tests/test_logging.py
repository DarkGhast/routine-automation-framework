import logging

from core.logging import ConsoleFormatter, init_logging, preview_logging


def test_logging_level_is_applied():
    init_logging("DEBUG")
    assert logging.getLogger().level == logging.DEBUG


def test_info_logs_use_stdout(monkeypatch, capsys):
    monkeypatch.setenv("NO_COLOR", "1")
    init_logging()
    logging.getLogger("example").info("普通运行信息")
    captured = capsys.readouterr()
    assert "INFO" in captured.out
    assert "普通运行信息" in captured.out
    assert "\033[" not in captured.out
    assert captured.err == ""


def test_color_formatter_preserves_exception_details():
    try:
        raise RuntimeError("程序异常")
    except RuntimeError:
        import sys
        record = logging.LogRecord("example", logging.ERROR, __file__, 1, "执行异常", (), sys.exc_info())
    output = ConsoleFormatter(color=True).format(record)
    assert output.startswith("\033[91m")
    assert "RuntimeError: 程序异常" in output
    assert output.endswith("\033[0m")


def test_preview_shows_all_levels_and_restores_filter(monkeypatch, capsys):
    monkeypatch.setenv("NO_COLOR", "1")
    init_logging("INFO")
    preview_logging()
    output = capsys.readouterr().out
    for level in ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"):
        assert level in output
    assert output.count("[样式预览，非真实事件]") == 5
    logging.getLogger("logging.preview").debug("不应继续输出")
    assert capsys.readouterr().out == ""
