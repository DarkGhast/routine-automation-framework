"""诊断工具：正式任务使用 NullAudit，不创建响应日志文件。"""

import json
import math
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4


# 自由文本只保留已知常量；未知响应仍保留形状，避免新字段泄漏个人资料。
SAFE_TEXT = frozenset({
    "success", "ok", "fail", "unauthorized", "forbidden", "bad request",
    "invalid signature", "signature invalid", "invalid email or password",
    "invalid credentials", "incorrect password", "invalid token", "token expired",
    "jwt expired", "token invalid", "invalid_signature", "invalid_credentials",
    "invalid_token", "token_expired",
})
KNOWN_KEYS = frozenset({
    "code", "message", "error", "detail", "data", "token", "user", "res", "status",
    "_id", "id", "email", "name", "username", "password", "authorization", "cookie",
    "level", "exp", "isPunched", "punchInLastDay", "birthday", "gender", "title",
    "verified", "characters", "created_at", "character", "avatar", "slogan", "role",
})


def response_shape(value, path=(), depth=0):
    """按路径白名单保留业务信息；不依赖黑名单猜测所有敏感字段。"""
    if depth > 12:
        return "<深度超限>"
    if path in {("data", "token"), ("data", "user", "_id"), ("data", "user", "email")}:
        return {"redacted": True, "type": type(value).__name__, "present": bool(value)}
    if isinstance(value, dict):
        return {
            key if key in KNOWN_KEYS else f"<未知字段{i}>": response_shape(item, path + (key,), depth + 1)
            for i, (key, item) in enumerate(list(value.items())[:100])
        }
    if isinstance(value, list):
        return [response_shape(item, path + ("[]",), depth + 1) for item in value[:30]]
    if path == ("code",) and type(value) is int:
        return value
    if path in {("data", "user", "level"), ("data", "user", "exp")} and (
        type(value) is int or (type(value) is float and math.isfinite(value))
    ):
        return value
    if path == ("data", "user", "isPunched") and type(value) is bool:
        return value
    if path in {("data", "res", "punchInLastDay"), ("data", "user", "punchInLastDay")}:
        if isinstance(value, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}(?:T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})?)?", value):
            return value
    if path in {("message",), ("error",), ("detail",), ("data", "res", "status")}:
        if isinstance(value, str) and value.lower() in SAFE_TEXT:
            return value.lower()
    if value is None:
        return None
    return {"redacted": True, "type": type(value).__name__}


class NullAudit:
    """正式运行不保存响应；保留诊断注入点供离线测试使用。"""

    def write(self, event, **fields):
        pass


class AuditLog:
    def __init__(self, directory: Path):
        self.directory = directory
        self.path = directory / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid4().hex + ".log")
        self.stream = None

    def __enter__(self):
        fd = None
        try:
            self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
            fd = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            self.stream = os.fdopen(fd, "w", encoding="utf-8")
            fd = None  # 文件描述符的所有权已交给 stream。
            self.write("start", mode="daily_checkin", version=2)
            return self
        except OSError:
            if self.stream is not None:
                self.stream.close()
            elif fd is not None:
                os.close(fd)
            raise OSError("哔咔响应日志创建失败，已停止执行") from None

    def write(self, event, **fields):
        try:
            self.stream.write(json.dumps({"time": datetime.now(timezone.utc).isoformat(), "event": event, **fields}, ensure_ascii=False, allow_nan=False) + "\n")
            self.stream.flush()
            os.fsync(self.stream.fileno())
        except OSError:
            raise OSError("哔咔响应日志写入失败，已停止执行") from None

    def __exit__(self, *_):
        self.stream.close()
