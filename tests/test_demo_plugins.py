from pathlib import Path

from app.main import main
from configuration.loader import load_config
from configuration.model import ApplicationConfig, NotificationConfig
from core.executor import TaskExecutor
from core.result import TaskStatus
from notification.service import NotificationService
from tasks.registry import create_tasks


EXAMPLE_CONFIG = Path(__file__).resolve().parents[1] / "config" / "application-example.yaml"


def test_example_config_runs_all_three_scenarios():
    config = load_config(EXAMPLE_CONFIG)
    results = TaskExecutor().execute(create_tasks(config))
    assert [result.task_name for result in results] == ["success", "already_signed", "failure"]
    assert [result.status for result in results] == [
        TaskStatus.SUCCESS, TaskStatus.SKIPPED, TaskStatus.FAILED,
    ]
    assert "已签到" in results[1].message


def test_failure_does_not_prevent_following_plugins():
    config = ApplicationConfig.model_validate({
        "tasks": {
            "failure": {"type": "demo_failure"},
            "success": {"type": "demo_success"},
            "already_signed": {"type": "demo_already_signed"},
        }
    })
    results = TaskExecutor().execute(create_tasks(config))
    assert [result.status for result in results] == [
        TaskStatus.FAILED, TaskStatus.SUCCESS, TaskStatus.SKIPPED,
    ]
    service = NotificationService()
    policy = NotificationConfig(policy="error_only")
    assert service.should_send(policy, results)
    assert not service.should_send(policy, results[1:])


def test_cli_runs_example_and_sends_console_results(monkeypatch, capsys):
    # 固定示例中的环境变量，避免用户本地通知设置影响测试。
    monkeypatch.setenv("LOG_LEVEL", "INFO")
    monkeypatch.setenv("NOTIFICATION_ENABLED", "true")
    monkeypatch.setenv("NOTIFICATION_POLICY", "always")
    main(["--config", str(EXAMPLE_CONFIG)])
    captured = capsys.readouterr()
    output = captured.out
    assert "success: SUCCESS - 签到成功（模拟）" in output
    assert "already_signed: SKIPPED - 今日已签到" in output
    assert "failure: FAILED - 签到失败（模拟）" in output
    assert "ERROR" not in captured.err
    assert "Traceback" not in captured.err
