import pytest

from configuration.model import NotificationConfig
from core.result import TaskResult, TaskStatus
from notification.service import NotificationService


@pytest.mark.parametrize(
    ("policy", "statuses", "expected"),
    [
        ("always", [TaskStatus.SUCCESS, TaskStatus.SUCCESS], True),
        ("always", [TaskStatus.SUCCESS, TaskStatus.FAILED], True),
        ("error_only", [TaskStatus.SUCCESS, TaskStatus.SUCCESS], False),
        ("error_only", [TaskStatus.SUCCESS, TaskStatus.SKIPPED], False),
        ("error_only", [TaskStatus.SKIPPED], False),
        ("error_only", [TaskStatus.SUCCESS, TaskStatus.FAILED], True),
        ("error_only", [TaskStatus.SUCCESS, TaskStatus.TIMEOUT], True),
    ],
)
def test_notification_policy(policy, statuses, expected):
    config = NotificationConfig.model_validate({"enabled": True, "policy": policy})
    results = [
        TaskResult(f"task-{index}", status, "test")
        for index, status in enumerate(statuses)
    ]

    assert NotificationService().should_send(config, results) is expected


def test_disabled_notification_never_sends():
    config = NotificationConfig.model_validate({
        "enabled": False,
        "policy": "always",
    })
    results = [TaskResult("failed", TaskStatus.FAILED, "failed")]

    assert NotificationService().should_send(config, results) is False
