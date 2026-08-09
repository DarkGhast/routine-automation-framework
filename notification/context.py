from dataclasses import dataclass


@dataclass
class NotificationContext:
    title: str
    results: list
