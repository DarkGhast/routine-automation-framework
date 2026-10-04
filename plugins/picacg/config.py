from typing import Literal

from pydantic import ConfigDict, Field, SecretStr, field_validator

from configuration.model import StrictModel


class PicACGConfig(StrictModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)

    username: SecretStr = Field(min_length=1)
    password: SecretStr = Field(min_length=1)
    timeout: float = Field(default=15, gt=0, le=120, allow_inf_nan=False)
    max_retries: int = Field(default=2, ge=0, le=2, strict=True)
    proxy_mode: Literal["system", "direct"] = "system"

    @field_validator("username", "password")
    @classmethod
    def nonblank_secret(cls, value):
        if not value.get_secret_value().strip():
            raise ValueError("账号和密码不能为空")
        return value
