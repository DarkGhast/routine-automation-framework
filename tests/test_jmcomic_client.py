"""网络替身配合真实 SDK 加解密，验证协议适配但不访问站点。"""

import base64
import json
from datetime import date

import pytest

pytest.importorskip("jmcomic")
pytest.importorskip("curl_cffi")

from Crypto.Cipher import AES
from curl_cffi.requests.exceptions import ConnectionError as CurlConnectionError, Timeout
from jmcomic import JmCryptoTool, JmMagicConstants

from core.exception import TaskTimeoutError
from core.result import TaskStatus
from plugins.jmcomic.client import BusinessRejected, JMComicClient, JMProtocolError, JMTransportError
from plugins.jmcomic.config import JMComicConfig
from plugins.jmcomic.task import JMComicTask


SECRET = "offline-sensitive-marker"


class Cookies:
    def __init__(self):
        self.values = {}

    def clear(self):
        self.values.clear()

    def set(self, name, value, **kwargs):
        self.values[name] = (value, kwargs)


class Response:
    status_code = 200

    def __init__(self, data, ts):
        self.data = data
        self.ts = ts

    def json(self):
        # 使用上游公开协议构造加密响应，避免用恒定成功假对象掩盖解析错误。
        raw = json.dumps(self.data, ensure_ascii=False).encode()
        padding = 16 - len(raw) % 16
        key = JmCryptoTool.md5hex(f"{self.ts}{JmMagicConstants.APP_DATA_SECRET}").encode()
        encoded = AES.new(key, AES.MODE_ECB).encrypt(raw + bytes([padding]) * padding)
        return {"code": 200, "data": base64.b64encode(encoded).decode()}


class FakeSession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.cookies = Cookies()
        self.calls = []
        self.closed = False

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        answer = self.responses.pop(0)
        if isinstance(answer, Exception):
            raise answer
        if hasattr(answer, "status_code"):
            return answer
        return Response(answer, kwargs["headers"]["tokenparam"].split(",")[0])

    def close(self):
        self.closed = True


def build(responses):
    cfg = JMComicConfig(username="offline-user", password=SECRET, api_domain="example.com", timeout=3, max_retries=0)
    session = FakeSession(responses)
    client = JMComicClient(cfg, lambda **_: session, today=lambda: date(2026, 10, 4))
    return cfg, session, client


def login_data():
    return {"uid": "123", "s": SECRET}


@pytest.mark.parametrize("signed,status", [(True, TaskStatus.SKIPPED), (False, TaskStatus.SUCCESS)])
def test_complete_protocol_flow(signed, status):
    cfg, session, client = build([
        {}, login_data(), {"daily_id": 72, "record": [[{"date": "04", "signed": signed}]]},
        {"msg": "Jcoin:40 EXP:40"},
    ])
    result = JMComicTask("jm", cfg, lambda _: client).execute()
    assert result.status is status
    assert session.closed
    assert client.uid is None and client.session is None
    assert len(session.calls) == (3 if signed else 4)
    assert all(call[2]["timeout"] == 3 and call[2]["allow_redirects"] is False for call in session.calls)
    assert session.calls[1][0] == "POST"
    assert session.calls[1][2]["data"] == {"username": "offline-user", "password": SECRET}
    assert session.cookies.values["AVS"][1]["domain"] == "example.com"
    if not signed:
        assert session.calls[-1][2]["data"] == {"user_id": "123", "daily_id": "72"}
    assert SECRET not in result.message


class RawResponse:
    def __init__(self, value, status=200):
        self.value = value
        self.status_code = status

    def json(self):
        if isinstance(self.value, Exception):
            raise self.value
        return self.value


def test_explicit_login_rejection_never_queries_daily():
    cfg, session, client = build([{}, RawResponse({"code": 400, "errorMsg": SECRET})])
    result = JMComicTask("jm", cfg, lambda _: client).execute()
    assert result.status is TaskStatus.FAILED
    assert result.message == "JMComic 登录被服务端拒绝"
    assert len(session.calls) == 2
    assert session.closed


@pytest.mark.parametrize("response,error", [
    (Timeout(SECRET), TaskTimeoutError),
    (CurlConnectionError(SECRET), JMTransportError),
    (RawResponse({}, 503), JMTransportError),
    (RawResponse({}, 302), JMTransportError),
    (RawResponse(ValueError(SECRET)), JMProtocolError),
    (RawResponse([]), JMProtocolError),
    (RawResponse({"code": "200"}), JMProtocolError),
    (RawResponse({"code": 999}), JMProtocolError),
    (RawResponse({"code": 200, "data": []}), JMProtocolError),
    (RawResponse({"code": 200, "data": SECRET}), JMProtocolError),
    ([], JMProtocolError),
    ({"uid": None, "s": SECRET}, JMProtocolError),
    ({"uid": "123"}, JMProtocolError),
])
def test_login_errors_are_sanitized_and_resources_closed(response, error):
    cfg, session, client = build([{}, response])
    with pytest.raises(error) as caught:
        JMComicTask("jm", cfg, lambda _: client).execute()
    import traceback
    assert SECRET not in "".join(traceback.format_exception(caught.value))
    assert session.closed
    assert len(session.calls) == 2


def test_post_timeout_never_retries():
    cfg, session, client = build([{}, login_data(), {"signed": False, "daily_id": 72}, Timeout(SECRET), Timeout(SECRET)])
    with pytest.raises(TaskTimeoutError):
        JMComicTask("jm", cfg, lambda _: client).execute()
    assert len(session.calls) == 5
    assert session.closed


def test_post_race_already_signed():
    cfg, session, client = build([{}, login_data(), {"signed": False, "daily_id": 72}, {"msg": "今天已經簽到過了"}])
    assert JMComicTask("jm", cfg, lambda _: client).execute().status is TaskStatus.SKIPPED


def test_prepare_only_switches_domains_before_login(monkeypatch):
    from jmcomic import JmModuleConfig
    monkeypatch.setattr(JmModuleConfig, "DOMAIN_API_LIST", ["first.example.com", "second.example.com"])
    cfg, session, client = build([CurlConnectionError(SECRET), {}, login_data(), {"signed": True}])
    cfg.api_domain = None
    monkeypatch.setattr(client, "_discover_domains", lambda: [])
    result = JMComicTask("jm", cfg, lambda _: client).execute()
    assert result.status is TaskStatus.SKIPPED
    assert session.calls[0][1] == "https://first.example.com/setting"
    assert all("second.example.com" in call[1] for call in session.calls[1:])


def test_separate_sessions_and_cookies():
    _, session_a, client_a = build([])
    _, session_b, client_b = build([])
    with client_a, client_b:
        client_a.session.cookies.set("AVS", "first")
        assert client_b.session.cookies.values == {}
    assert session_a.closed and session_b.closed


def test_prepare_timeout_closes_session():
    cfg, session, client = build([Timeout(SECRET)])
    with pytest.raises(TaskTimeoutError):
        JMComicTask("jm", cfg, lambda _: client).execute()
    assert session.closed
    assert len(session.calls) == 1


@pytest.mark.parametrize("daily_id", [None, "", 0, True, "not-an-id"])
def test_invalid_daily_id_never_submits(daily_id):
    cfg, session, client = build([{}, login_data(), {"signed": False, "daily_id": daily_id}])
    with pytest.raises(JMProtocolError):
        JMComicTask("jm", cfg, lambda _: client).execute()
    assert session.closed
    assert len(session.calls) == 3


def test_post_rejection_returns_failed_without_retry():
    cfg, session, client = build([
        {}, login_data(), {"signed": False, "daily_id": 72},
        RawResponse({"code": 400, "errorMsg": SECRET}),
    ])
    result = JMComicTask("jm", cfg, lambda _: client).execute()
    assert result.status is TaskStatus.FAILED
    assert result.message == "JMComic 签到被服务端拒绝"
    assert session.closed
    assert len(session.calls) == 4


@pytest.mark.parametrize("code,category,error_type", [
    (5, "COULDNT_RESOLVE_PROXY", JMTransportError),
    (6, "COULDNT_RESOLVE_HOST", JMTransportError),
    (7, "COULDNT_CONNECT", JMTransportError),
    (28, "OPERATION_TIMEDOUT", TaskTimeoutError),
    (35, "SSL_CONNECT_ERROR", JMTransportError),
    (60, "PEER_FAILED_VERIFICATION", JMTransportError),
    (77, "SSL_CACERT_BADFILE", JMTransportError),
])
def test_debug_network_diagnostics_hide_exception_and_proxy_credentials(caplog, monkeypatch, code, category, error_type):
    import logging
    import traceback

    monkeypatch.setenv("HTTPS_PROXY", f"http://proxy-user:{SECRET}@example.com:8080")
    error = Timeout(SECRET, code=code) if code == 28 else CurlConnectionError(SECRET, code=code)
    cfg, session, client = build([error])
    with caplog.at_level(logging.DEBUG, logger="plugins.jmcomic.client"):
        with pytest.raises(error_type) as caught:
            JMComicTask("jm", cfg, lambda _: client).execute()
    assert f"curl_code={code}" in caplog.text
    assert category in caplog.text
    assert "HTTPS_PROXY=True" in caplog.text
    assert "domain=example.com" in caplog.text
    output = caplog.text + "".join(traceback.format_exception(caught.value))
    assert SECRET not in output
    assert "proxy-user" not in output
    assert session.closed


def test_debug_success_hides_credentials_uid_tokens_and_response(caplog, monkeypatch):
    import logging

    monkeypatch.setattr(JmCryptoTool, "token_and_tokenparam", lambda ts, **_: ("private-token-marker", f"{ts},1"))
    cfg, session, client = build([
        {}, {"uid": "987654321", "s": SECRET}, {"signed": True, "private": SECRET},
    ])
    with caplog.at_level(logging.DEBUG, logger="plugins.jmcomic.client"):
        assert JMComicTask("jm", cfg, lambda _: client).execute().status is TaskStatus.SKIPPED
    assert "HTTP=200" in caplog.text
    assert "code=200" in caplog.text
    for secret in (SECRET, "offline-user", "987654321", "private-token-marker"):
        assert secret not in caplog.text


def test_system_proxy_is_forwarded_without_logging_address(monkeypatch, caplog):
    import logging
    from common import ProxyBuilder

    proxies = {"https": f"http://proxy-user:{SECRET}@example.com:8080"}
    monkeypatch.setattr(ProxyBuilder, "system_proxy", lambda: proxies)
    received = {}
    session = FakeSession([])

    def factory(**kwargs):
        received.update(kwargs)
        return session

    cfg = JMComicConfig(username="offline", password=SECRET)
    with caplog.at_level(logging.DEBUG, logger="plugins.jmcomic.client"):
        with JMComicClient(cfg, session_factory=factory):
            pass
    assert received["proxies"] == proxies
    assert SECRET not in caplog.text
    assert "proxy-user" not in caplog.text
    assert session.closed


@pytest.mark.parametrize('proxies', [{}, {'https': 'http://user:password@example.com:8080'}])
def test_explicit_proxy_overrides_system(monkeypatch, proxies):
    from common import ProxyBuilder
    from curl_cffi import CurlOpt
    monkeypatch.setattr(ProxyBuilder, 'system_proxy', lambda: pytest.fail('不应查询系统代理'))
    received = {}
    session = FakeSession([])
    def factory(**kwargs):
        received.update(kwargs)
        return session
    cfg = JMComicConfig(username='fake', password='fake', jmcomic_config={'proxies': proxies})
    with JMComicClient(cfg, session_factory=factory):
        pass
    assert received['proxies'] == proxies
    if not proxies:
        assert received['curl_options'][CurlOpt.PROXY] == b''


def test_nested_domains_and_headers_take_effect(monkeypatch):
    cfg, session, client = build([{}])
    cfg.api_domain = None
    from plugins.jmcomic.config import JMComicAdvancedConfig
    cfg.jmcomic_config = JMComicAdvancedConfig(domains=['custom.example.com'], headers={'user-agent': SECRET})
    monkeypatch.setattr(client, '_discover_domains', lambda: pytest.fail('显式域名不得自动更新'))
    with client:
        client.prepare()
    assert session.calls[0][1] == 'https://custom.example.com/setting'
    headers = session.calls[0][2]['headers']
    assert headers['user-agent'] == SECRET
    assert 'User-Agent' not in headers
