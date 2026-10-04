import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formatdate, make_msgid, formataddr
from typing import Literal
from pydantic import Field, SecretStr, field_validator, model_validator
from configuration.model import StrictModel
from core.result import TaskResult, TaskStatus
from notification.base import NotificationChannel
from notification.definition import NotificationDefinition


class EmailConfig(StrictModel):
    host: str = Field(min_length=1)
    port: int = Field(default=465, ge=1, le=65535)
    security: Literal["ssl", "starttls"] = "ssl"
    username: str | None = None
    password: SecretStr | None = None
    sender: str
    sender_name: str | None = None
    recipients: list[str] = Field(min_length=1)
    subject: str = "日常自动化任务通知"
    timeout: float = Field(default=20, gt=0, le=120, allow_inf_nan=False)

    @field_validator("host", "sender", "subject", "username", "sender_name")
    @classmethod
    def single_line(cls, value):
        if value is not None and (not value.strip() or "\r" in value or "\n" in value):
            raise ValueError("字段不能为空或包含换行")
        return value

    @staticmethod
    def address(value):
        # 仅接受单个纯邮箱地址，避免收件人列表与邮件头注入。
        if value.count("@") != 1 or any(c.isspace() or c in ",;<>" for c in value):
            raise ValueError("请填写单个纯邮箱地址")
        if not all(value.split("@")):
            raise ValueError("邮箱地址不完整")
        return value

    @field_validator("sender")
    @classmethod
    def sender_address(cls, value):
        return cls.address(value)

    @field_validator("recipients")
    @classmethod
    def recipient_addresses(cls, values):
        return [cls.address(value) for value in values]

    @model_validator(mode="after")
    def credentials_pair(self):
        if (self.username is None) != (self.password is None):
            raise ValueError("username 和 password 必须同时设置或同时省略")
        if self.password is not None and not self.password.get_secret_value():
            raise ValueError("password 不能为空")
        return self


class EmailChannel(NotificationChannel):
    def __init__(self, config: EmailConfig):
        self.config = config

    def send(self, results: list[TaskResult]) -> None:
        config = self.config
        message = EmailMessage()
        message["From"] = formataddr((config.sender_name, config.sender)) if config.sender_name else config.sender
        message["To"] = ", ".join(config.recipients)
        message["Subject"] = config.subject
        message["Date"] = formatdate(localtime=True)
        message["Message-ID"] = make_msgid()
        counts = {s: sum(r.status == s for r in results) for s in TaskStatus}
        lines = ["任务执行通知", " | ".join(f"{s.value}: {counts[s]}" for s in TaskStatus), ""]
        lines.extend(f"{r.task_name}: {r.status.value} - {r.message}" for r in results)
        if not results:
            lines.append("本次没有执行任务")
        message.set_content("\n".join(lines))
        context = ssl.create_default_context()
        if config.security == "ssl":
            connection = smtplib.SMTP_SSL(config.host, config.port, timeout=config.timeout, context=context)
        else:
            connection = smtplib.SMTP(config.host, config.port, timeout=config.timeout)
        with connection as smtp:
            if config.security == "starttls":
                smtp.ehlo()
                smtp.starttls(context=context)
                smtp.ehlo()
            if config.username is not None:
                smtp.login(config.username, config.password.get_secret_value())
            refused = smtp.send_message(message, from_addr=config.sender, to_addrs=config.recipients)
            if refused:
                raise RuntimeError("部分邮件收件人被拒绝")


PLUGIN = NotificationDefinition(EmailChannel, EmailConfig)
