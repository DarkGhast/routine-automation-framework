import re
from typing import Annotated, Literal
from urllib.parse import urlsplit

from pydantic import ConfigDict, Field, SecretStr, field_validator

from configuration.model import StrictModel


DOMAIN_PATTERN = r"^(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+[A-Za-z]{2,63}$"
Domain = Annotated[str, Field(pattern=DOMAIN_PATTERN)]


class JMComicAdvancedConfig(StrictModel):
    """插件支持的网络选项，不透传任意上游下载器配置。"""
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)

    domains: list[Domain] = Field(default_factory=list, max_length=32)
    proxies: dict[Literal["http", "https", "all"], SecretStr] | None = None
    headers: dict[str, SecretStr] = Field(default_factory=dict)

    @field_validator("proxies")
    @classmethod
    def valid_proxies(cls, value):
        for secret in (value or {}).values():
            url = secret.get_secret_value()
            try:
                parts = urlsplit(url)
                valid = (parts.scheme in ("http", "https", "socks5", "socks5h")
                         and parts.hostname and parts.port != 0 and not parts.query
                         and not parts.fragment and parts.path in ("", "/")
                         and not any(ch.isspace() for ch in url))
            except ValueError:
                valid = False
            if not valid:
                raise ValueError("代理地址必须是有效的 HTTP(S) 或 SOCKS5 URL")
        return value

    @field_validator("headers")
    @classmethod
    def valid_headers(cls, value):
        for name, secret in value.items():
            if (not re.fullmatch(r"[!#$%&'*+.^_`|~0-9A-Za-z-]+", name)
                    or name.lower() in {"token", "tokenparam", "cookie", "host", "content-length", "referer"}
                    or any(c in secret.get_secret_value() for c in ("\r", "\n", "\0"))):
                raise ValueError("请求头格式非法或覆盖了协议保留字段")
        return value


class JMComicConfig(StrictModel):
    # 框架会将配置校验异常写入日志，禁止异常文本包含原始输入。
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)

    username: SecretStr = Field(min_length=1)
    password: SecretStr = Field(min_length=1)
    timeout: float = Field(default=20, gt=0, le=120, allow_inf_nan=False)
    max_retries: int = Field(default=1, ge=0, le=3, strict=True)
    random_delay_seconds: int = Field(default=-1, ge=-1, le=86400, strict=True)
    jmcomic_config: JMComicAdvancedConfig = Field(default_factory=JMComicAdvancedConfig)
    api_domain: str | None = Field(
        default=None,
        pattern=DOMAIN_PATTERN,
    )

    @field_validator("random_delay_seconds", mode="before")
    @classmethod
    def disabled_delay(cls, value):
        return -1 if value is False else value

    @field_validator("username", "password")
    @classmethod
    def nonblank_secret(cls, value: SecretStr) -> SecretStr:
        if not value.get_secret_value().strip():
            raise ValueError("账号和密码不能为空")
        # 密码首尾空格可能有实际含义，不修改用户输入。
        return value
