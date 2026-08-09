from core.result import TaskResult, TaskStatus
from notification.service import NotificationService


def test_always_with_all_success():
    results = [
        TaskResult("task1", TaskStatus.SUCCESS, "ok"),
        TaskResult("task2", TaskStatus.SUCCESS, "ok"),
    ]

    assert NotificationService().should_send("always", results) is True


def test_always_with_failure():
    results = [
        TaskResult("task1", TaskStatus.SUCCESS, "ok"),
        TaskResult("task2", TaskStatus.FAILED, "failed"),
    ]

    assert NotificationService().should_send("always", results) is True


def test_error_only_with_all_success():
    results = [
        TaskResult("task1", TaskStatus.SUCCESS, "ok"),
        TaskResult("task2", TaskStatus.SUCCESS, "ok"),
    ]

    assert NotificationService().should_send("error_only", results) is False


def test_error_only_with_failure():
    results = [
        TaskResult("task1", TaskStatus.SUCCESS, "ok"),
        TaskResult("task2", TaskStatus.FAILED, "failed"),
    ]

    assert NotificationService().should_send("error_only", results) is True
