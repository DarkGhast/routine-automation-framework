import io
import json
import ssl
from pathlib import Path
from urllib.error import HTTPError, URLError

import pytest
from pydantic import ValidationError

from configuration.model import ApplicationConfig
from core.exception import TaskTimeoutError
from core.executor import TaskExecutor
from core.result import TaskStatus
from plugins.picacg.audit import AuditLog
from plugins.picacg.client import (
    BASE_URL, BusinessRejected, NoRedirect, PicACGClient, ProtocolError,
    TransportError, signed_headers,
    system_proxies,
)
from plugins.picacg.config import PicACGConfig
from plugins.picacg.task import PicACGTask
from tasks.registry import create_tasks


# 登录/用户为人工样例；签到结构另有真实脱敏响应回归，不读取工作区 config-test。
LOGIN = {"code": 200, "data": {"token": "test-token-only"}}
PROFILE = {"code": 200, "data": {"user": {"_id": "fake-user-id", "email": "fake@example.invalid", "level": 2, "exp": 10, "isPunched": False}}}


class Response(io.BytesIO):
    def __init__(self, body, code=200, url=None):
        super().__init__(body if isinstance(body, bytes) else json.dumps(body).encode())
        self.code, self.url = code, url

    def geturl(self):
        return self.url


class FakeOpener:
    def __init__(self, *items):
        self.items, self.requests = list(items), []
        self.responses = []

    def open(self, request, timeout):
        self.requests.append((request, timeout))
        item = self.items.pop(0)
        if isinstance(item, Exception):
            raise item
        response = item if isinstance(item, Response) else Response(item)
        response.url = response.url or request.full_url
        self.responses.append(response)
        return response


@pytest.fixture
def config(tmp_path):
    return PicACGConfig(username="fake", password=" secret ", max_retries=0, proxy_mode="direct")


def test_signature_fixed_vector():
    headers = signed_headers("POST", "auth/sign-in", timestamp=1700000000, nonce="0123456789abcdef0123456789abcdef")
    # 固定值独立按 RFC 2104 内外填充公式计算，未调用被测签名函数。
    assert headers["signature"] == "76ee79364bce0cbac8a3315df284361ed7ac4279060d9095294e298f8b711fe8"
    assert "authorization" not in headers
    assert signed_headers("GET", "users/profile", "fake-token")["authorization"] == "fake-token"


def test_full_login_only_and_durable_redacted_log(config, tmp_path):
    opener = FakeOpener(LOGIN, PROFILE)
    with AuditLog((tmp_path / "logs")) as audit:
        with PicACGClient(config, audit, opener=opener) as client:
            assert client.login_and_verify("test-account", "test-password")["_id"] == "fake-user-id"
            # 尚未关闭文件时已能读取完整响应日志。
            content = audit.path.read_text(encoding="utf-8")
            assert '"isPunched": false' in content
            for secret in ("test-token-only", "fake-user-id", "fake@example.invalid", "test-account", "test-password"):
                assert secret not in content
        assert client._token is None
    assert [(r.method, r.full_url) for r, _ in opener.requests] == [
        ("POST", BASE_URL + "/auth/sign-in"), ("GET", BASE_URL + "/users/profile")]
    assert all(response.closed for response in opener.responses)
    assert opener.requests[1][0].get_header("Authorization") == "test-token-only"


@pytest.mark.parametrize("body,status,error", [
    ({"code": 200, "data": {}}, 200, ProtocolError),
    ({"code": "200", "data": {}}, 200, ProtocolError),
    ({"code": 200, "data": {"token": "bad\r\ntoken"}}, 200, ProtocolError),
    ({"code": 999}, 200, ProtocolError),
    ({"code": 200, "data": {"token": "fake"}}, 403, ProtocolError),
    (b"<html>secret response</html>", 200, ProtocolError),
    ({"code": 400, "message": "invalid signature"}, 200, BusinessRejected),
    ({"code": 401, "message": "invalid email or password"}, 401, BusinessRejected),
    ({"code": 403}, 403, BusinessRejected),
])
def test_login_rejections_do_not_query(config, body, status, error, tmp_path):
    opener = FakeOpener(Response(body, status))
    with AuditLog((tmp_path / "logs")) as audit, PicACGClient(config, audit, opener=opener) as client:
        with pytest.raises(error):
            client.login_and_verify("x", "y")
        assert client._token is None
    assert len(opener.requests) == 1


@pytest.mark.parametrize("body,kind", [
    ({"code": 401, "message": "token expired"}, "TOKEN_INVALID"),
    ({"code": 401, "message": "unauthorized"}, "AUTH_REJECTED"),
    ({"code": 400, "message": "invalid signature"}, "SIGNATURE_ERROR"),
])
def test_profile_rejection_invalidates_token(config, body, kind, tmp_path):
    with AuditLog((tmp_path / "logs")) as audit, PicACGClient(config, audit, opener=FakeOpener(LOGIN, body)) as client:
        with pytest.raises(BusinessRejected) as exc:
            client.login_and_verify("x", "y")
        assert exc.value.kind == kind
        assert client._token is None


@pytest.mark.parametrize("user", [{}, [], {"_id": ""}, {"_id": 123}])
def test_profile_requires_identity(config, user, tmp_path):
    with AuditLog((tmp_path / "logs")) as audit, PicACGClient(config, audit, opener=FakeOpener(LOGIN, {"code": 200, "data": {"user": user}})) as client:
        with pytest.raises(ProtocolError):
            client.login_and_verify("x", "y")


def test_post_never_retried_and_timeout_classified(config, tmp_path):
    config.max_retries = 2
    opener = FakeOpener(URLError(TimeoutError("secret")))
    with AuditLog((tmp_path / "logs")) as audit, PicACGClient(config, audit, opener=opener) as client:
        with pytest.raises(TaskTimeoutError) as exc:
            client.login("x", "y")
        assert "secret" not in str(exc.value)
    assert len(opener.requests) == 1


def test_get_retries_fresh_signatures_and_records_every_response(config, tmp_path):
    config.max_retries = 2
    opener = FakeOpener(LOGIN, Response(b"busy", 503), URLError(TimeoutError()), PROFILE)
    waits = []
    with AuditLog((tmp_path / "logs")) as audit, PicACGClient(config, audit, opener=opener, sleep=waits.append) as client:
        client.login_and_verify("x", "y")
        content = audit.path.read_text(encoding="utf-8")
        assert '"http_status": 503' in content
        assert '"transport_error"' in content
    assert waits == [1, 2]
    assert len({r.get_header("Nonce") for r, _ in opener.requests}) == 4


def test_tls_failure_not_retried(config, tmp_path):
    config.max_retries = 2
    opener = FakeOpener(LOGIN, URLError(ssl.SSLCertVerificationError("private")))
    with AuditLog((tmp_path / "logs")) as audit, PicACGClient(config, audit, opener=opener) as client:
        with pytest.raises(TransportError, match="TLS_ERROR"):
            client.login_and_verify("x", "y")
    assert len(opener.requests) == 2


def test_http_error_response_is_saved_and_closed(config, tmp_path):
    stream = io.BytesIO(json.dumps({"code": 401, "error": "invalid credentials"}).encode())
    error = HTTPError(BASE_URL + "/auth/sign-in", 401, "Unauthorized", {}, stream)
    with AuditLog((tmp_path / "logs")) as audit, PicACGClient(config, audit, opener=FakeOpener(error)) as client:
        with pytest.raises(BusinessRejected, match="CREDENTIALS_ERROR"):
            client.login("x", "y")
        assert '"http_status": 401' in audit.path.read_text(encoding="utf-8")
    assert stream.closed


def test_redirect_and_unapproved_route_blocked(config, tmp_path):
    assert NoRedirect().redirect_request(None, None, 307, "", {}, "https://elsewhere.invalid") is None
    opener = FakeOpener(Response(LOGIN, 302))
    with AuditLog((tmp_path / "logs")) as audit, PicACGClient(config, audit, opener=opener) as client:
        with pytest.raises(TransportError, match="REDIRECT_BLOCKED"):
            client.login("x", "y")
        for method, path in [("POST", "users/unknown"), ("GET", "https://elsewhere.invalid"), ("GET", "../auth/sign-in")]:
            with pytest.raises(ValueError):
                client._request(method, path)
    assert len(opener.requests) == 1


def test_transport_has_tls_verification_and_no_proxy(config, monkeypatch, tmp_path):
    config.proxy_mode = "direct"
    monkeypatch.setenv("HTTPS_PROXY", "http://untrusted.invalid:8080")
    with AuditLog((tmp_path / "logs")) as audit, PicACGClient(config, audit) as client:
        from urllib.request import HTTPSHandler, ProxyHandler
        https = next(h for h in client.opener.handlers if isinstance(h, HTTPSHandler))
        assert https._context.verify_mode == ssl.CERT_REQUIRED
        assert https._context.check_hostname
        assert not any(isinstance(h, ProxyHandler) and h.proxies for h in client.opener.handlers)


def test_system_proxy_and_direct_override(monkeypatch):
    monkeypatch.setattr("plugins.picacg.client.getproxies", lambda: {"https": "http://127.0.0.1:7890"})
    assert system_proxies("system") == {"https": "http://127.0.0.1:7890"}
    assert system_proxies("direct") == {}
    monkeypatch.setattr("plugins.picacg.client.getproxies", lambda: {"all": "socks5://private:secret@localhost:1080"})
    with pytest.raises(ValueError) as exc:
        system_proxies("system")
    assert "secret" not in str(exc.value)


def test_framework_loads_and_executes(tmp_path):
    tasks = create_tasks(ApplicationConfig.model_validate({"tasks": {
        "pica": {"type": "picacg", "config": {"username": "fake", "password": " password ", "proxy_mode": "direct"}},
        "disabled": {"type": "picacg", "enabled": False, "config": {"invalid": "ignored"}},
    }}))
    assert len(tasks) == 1
    opener = FakeOpener(LOGIN, PROFILE, {"code": 200, "data": {"res": {"status": "ok"}}}, signed_profile())
    tasks[0].client_factory = lambda config, audit: PicACGClient(config, audit, opener=opener)
    result = TaskExecutor().execute(tasks)[0]
    assert result.status is TaskStatus.SUCCESS
    assert json.loads(opener.requests[0][0].data)["password"] == " password "


def test_resolved_credentials(config, monkeypatch):
    # 环境由框架解析一次，执行阶段不悄悄切换到后来变化的账号。
    monkeypatch.setenv("PICA_USERNAME", "different-account")
    monkeypatch.setenv("PICA_PASSWORD", "different-password")
    assert (config.username.get_secret_value(), config.password.get_secret_value()) == ("fake", " secret ")


@pytest.mark.parametrize("values", [{"timeout": 0}, {"timeout": float("nan")}, {"max_retries": 3}, {"max_retries": True}, {"password": "NEVER_PRINT"}, {"check_in": True}])
def test_config_validation(values):
    with pytest.raises(ValidationError) as exc:
        PicACGConfig(**values)
    assert "NEVER_PRINT" not in str(exc.value)


def test_task_business_failure_and_program_error(config, tmp_path):
    opener = FakeOpener({"code": 401, "message": "invalid credentials"})
    task = PicACGTask("pica", config, lambda c, a: PicACGClient(c, a, opener=opener))
    assert task.execute().status is TaskStatus.FAILED
    task.client_factory = lambda c, a: PicACGClient(c, a, opener=FakeOpener(b"malformed"))
    with pytest.raises(ProtocolError):
        task.execute()
    assert not (tmp_path / "logs").exists()


def test_new_login_clears_old_token(config, tmp_path):
    opener = FakeOpener(LOGIN, {"code": 401})
    with AuditLog((tmp_path / "logs")) as audit, PicACGClient(config, audit, opener=opener) as client:
        client.login("first", "password")
        with pytest.raises(BusinessRejected):
            client.login("second", "password")
        assert client._token is None
        assert opener.requests[1][0].get_header("Authorization") is None


def test_normal_task_never_writes_response_files(config, monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    opener = FakeOpener(LOGIN, signed_profile())
    def fail(*args, **kwargs):
        raise AssertionError("normal task must not persist responses")
    monkeypatch.setattr("plugins.picacg.audit.os.fsync", fail)
    result = PicACGTask("pica", config, lambda c, a: PicACGClient(c, a, opener=opener)).execute()
    assert result.status is TaskStatus.SKIPPED
    assert not list(tmp_path.iterdir())


def test_unknown_fields_redacted(config, tmp_path):
    obj = {"code": 400, "message": "password was leaked", "data": {"custom-secret-key": "secret-value", "password": "secret-password", "token": "secret-token"}}
    with AuditLog((tmp_path / "logs")) as audit, PicACGClient(config, audit, opener=FakeOpener(obj)) as client:
        with pytest.raises(BusinessRejected):
            client.login("x", "y")
        content = audit.path.read_text(encoding="utf-8")
        for secret in ("password was leaked", "custom-secret-key", "secret-value", "secret-password", "secret-token"):
            assert secret not in content


def signed_profile(value=True):
    return {"code": 200, "data": {"user": {"_id": "fake-user-id", "isPunched": value}}}


@pytest.mark.parametrize("marker,expected", [("ok", TaskStatus.SUCCESS), ("fail", TaskStatus.SKIPPED)])
def test_checkin_and_duplicate_response(config, marker, expected, tmp_path):
    opener = FakeOpener(LOGIN, PROFILE, {"code": 200, "data": {"res": {"status": marker, "punchInLastDay": "2026-10-04"}}}, signed_profile())
    with AuditLog((tmp_path / "logs")) as audit, PicACGClient(config, audit, opener=opener) as client:
        client.login("x", "y")
        assert client.check_in() is expected
        assert '"punchInLastDay": "2026-10-04"' in audit.path.read_text(encoding="utf-8")
    assert [r.full_url.rsplit("/", 1)[-1] for r, _ in opener.requests] == ["sign-in", "profile", "punch-in", "profile"]


def test_already_signed_skips_post(config, tmp_path):
    opener = FakeOpener(LOGIN, signed_profile())
    with AuditLog((tmp_path / "logs")) as audit, PicACGClient(config, audit, opener=opener) as client:
        client.login("x", "y")
        assert client.check_in() is TaskStatus.SKIPPED
    assert len(opener.requests) == 2


@pytest.mark.parametrize("value", [None, "true", 1, 0, "false"])
def test_unknown_daily_state_never_submits(config, value, tmp_path):
    opener = FakeOpener(LOGIN, signed_profile(value))
    with AuditLog((tmp_path / "logs")) as audit, PicACGClient(config, audit, opener=opener) as client:
        client.login("x", "y")
        with pytest.raises(ProtocolError):
            client.check_in()
    assert len(opener.requests) == 2


@pytest.mark.parametrize("confirmed", [True, False])
@pytest.mark.parametrize("failure_type", ["timeout", "http", "unknown"])
def test_uncertain_submission_queries_without_resubmit(config, confirmed, failure_type, tmp_path):
    failure = {"timeout": lambda: URLError(TimeoutError()), "http": lambda: Response(b"busy", 503),
               "unknown": lambda: {"code": 200, "data": {"res": {"status": "unexpected"}}}}[failure_type]()
    opener = FakeOpener(LOGIN, PROFILE, failure, signed_profile(confirmed))
    with AuditLog((tmp_path / "logs")) as audit, PicACGClient(config, audit, opener=opener) as client:
        client.login("x", "y")
        if confirmed:
            assert client.check_in() is TaskStatus.SUCCESS
        else:
            with pytest.raises((TaskTimeoutError, TransportError, ProtocolError)):
                client.check_in()
    assert sum(r.full_url.endswith("punch-in") for r, _ in opener.requests) == 1


@pytest.mark.parametrize("status,error", [("fail", BusinessRejected), ("ok", ProtocolError)])
def test_checkin_requires_profile_confirmation(config, status, error, tmp_path):
    opener = FakeOpener(LOGIN, PROFILE, {"code": 200, "data": {"res": {"status": status}}}, signed_profile(False))
    with AuditLog((tmp_path / "logs")) as audit, PicACGClient(config, audit, opener=opener) as client:
        client.login("x", "y")
        with pytest.raises(error):
            client.check_in()


def test_explicit_checkin_business_rejection(config, tmp_path):
    opener = FakeOpener(LOGIN, PROFILE, {"code": 403})
    with AuditLog((tmp_path / "logs")) as audit, PicACGClient(config, audit, opener=opener) as client:
        client.login("x", "y")
        with pytest.raises(BusinessRejected):
            client.check_in()
    assert len(opener.requests) == 3


@pytest.mark.parametrize("response,expected", [
    ({"code": 200, "message": "success", "data": {"res": {"status": "ok", "punchInLastDay": "2026-10-03"}}}, TaskStatus.SUCCESS),
    ({"code": 200, "message": "success", "data": {"res": {"status": "fail"}}}, TaskStatus.SKIPPED),
])
def test_real_checkin_response_regression(config, response, expected, tmp_path):
    # 来自 2026-10-04 本地联调日志；日期不同于本地日期不能推翻服务端状态。
    with AuditLog((tmp_path / "logs")) as audit, PicACGClient(config, audit, opener=FakeOpener(LOGIN, response, signed_profile())) as client:
        client.login("x", "y")
        assert client.submit_checkin() is expected


def test_task_already_signed_maps_to_skipped(config):
    opener = FakeOpener(LOGIN, signed_profile())
    result = PicACGTask("pica", config, lambda c, a: PicACGClient(c, a, opener=opener)).execute()
    assert result.status is TaskStatus.SKIPPED
    assert len(opener.requests) == 2


def test_uncertain_submission_and_failed_query_preserves_timeout(config, tmp_path):
    opener = FakeOpener(LOGIN, PROFILE, URLError(TimeoutError()), {"code": 401})
    with AuditLog((tmp_path / "logs")) as audit, PicACGClient(config, audit, opener=opener) as client:
        client.login("x", "y")
        with pytest.raises(TaskTimeoutError):
            client.check_in()
    assert sum(r.full_url.endswith("punch-in") for r, _ in opener.requests) == 1


def test_failed_log_stream_creation_closes_descriptor(config, monkeypatch, tmp_path):
    import os
    opened = []
    actual_open = os.open
    def tracked_open(*args, **kwargs):
        descriptor = actual_open(*args, **kwargs)
        opened.append(descriptor)
        return descriptor
    def fail_stream(*args, **kwargs):
        raise OSError("stream creation failed")
    monkeypatch.setattr("plugins.picacg.audit.os.open", tracked_open)
    monkeypatch.setattr("plugins.picacg.audit.os.fdopen", fail_stream)
    with pytest.raises(OSError, match="日志创建失败"):
        with AuditLog((tmp_path / "logs")):
            pytest.fail("must not reach request stage")
    assert len(opened) == 1
    with pytest.raises(OSError):
        os.fstat(opened[0])


def test_response_log_failure_stops_followup_requests(config, monkeypatch, tmp_path):
    # 响应已收到但落盘失败时，不能继续查询或签到。
    opener = FakeOpener(LOGIN, PROFILE)
    with AuditLog((tmp_path / "logs")) as audit, PicACGClient(config, audit, opener=opener) as client:
        actual_write = audit.write
        def fail_response(event, **fields):
            if event == "response":
                raise OSError("disk full")
            return actual_write(event, **fields)
        monkeypatch.setattr(audit, "write", fail_response)
        with pytest.raises(OSError):
            client.login_and_verify("x", "y")
    assert len(opener.requests) == 1


def test_debug_progress_is_useful_redacted_and_file_free(config, caplog, monkeypatch, tmp_path):
    import logging
    monkeypatch.chdir(tmp_path)
    caplog.set_level(logging.DEBUG, logger="plugins.picacg")
    opener = FakeOpener(LOGIN, PROFILE, {"code": 200, "data": {"res": {"status": "ok"}}}, signed_profile())
    result = PicACGTask("test-instance", config, lambda c, a: PicACGClient(c, a, opener=opener)).execute()
    assert result.status is TaskStatus.SUCCESS
    for marker in ("会话创建", "path=auth/sign-in", "path=users/profile", "path=users/punch-in",
                   "HTTP=200", "业务码=200", "耗时=", "今日未签到", "签到确认", "会话结束"):
        assert marker in caplog.text
    for secret in ("test-token-only", "fake-user-id", "fake@example.invalid", " secret "):
        assert secret not in caplog.text
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize("sample_name", ["success_2026-10-03", "success_2026-10-04", "already_signed"])
def test_saved_real_response_samples(config, tmp_path, sample_name):
    path = Path(__file__).resolve().parents[1] / "plugins/picacg/samples" / (sample_name + ".json")
    sample = json.loads(path.read_text(encoding="utf-8"))
    opener = FakeOpener(LOGIN, sample["response"], signed_profile(sample["verification"]["isPunched_after"]))
    with AuditLog(tmp_path / "logs") as audit, PicACGClient(config, audit, opener=opener) as client:
        client.login("x", "y")
        expected = TaskStatus.SKIPPED if sample_name == "already_signed" else TaskStatus.SUCCESS
        assert client.submit_checkin() is expected
