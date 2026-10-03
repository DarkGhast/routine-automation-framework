import base64
import json

import pytest

pytest.importorskip("jmcomic")
pytest.importorskip("curl_cffi")

from Crypto.Cipher import AES
from curl_cffi.requests.exceptions import Timeout
from jmcomic import JmCryptoTool, JmMagicConstants, JmModuleConfig

from core.exception import TaskTimeoutError
from core.result import TaskStatus
from plugins.jmcomic.client import JMProtocolError, parse_json_object
from plugins.jmcomic.task import JMComicTask
from tests.test_jmcomic_client import build, login_data, RawResponse, SECRET


@pytest.mark.parametrize("text", [
    '\ufeffnoise {"code":200,"data":"a"} tail',
    'garbage {broken {"code":200,"data":{"nested":"}"}} end',
])
def test_dirty_json_preserves_nested_objects(text):
    assert parse_json_object(text)["code"] == 200


@pytest.mark.parametrize("text", ['none', '{} {}', '{broken', '[]'])
def test_ambiguous_or_invalid_json_is_rejected(text):
    with pytest.raises(JMProtocolError):
        parse_json_object(text)


def encrypted_domains(domains):
    raw = json.dumps({"Server": domains}).encode()
    pad = 16 - len(raw) % 16
    key = JmCryptoTool.md5hex(JmMagicConstants.API_DOMAIN_SERVER_SECRET).encode()
    encrypted = AES.new(key, AES.MODE_ECB).encrypt(raw + bytes([pad]) * pad)
    response = RawResponse(None)
    response.text = '\ufeff' + base64.b64encode(encrypted).decode()
    return response


def test_dynamic_domains_are_used_first(monkeypatch):
    monkeypatch.setattr(JmModuleConfig, "API_URL_DOMAIN_SERVER_LIST", ['https://discovery.example.com'])
    cfg, session, client = build([encrypted_domains(['fresh.example.com']), {}])
    cfg.api_domain = None
    with client:
        client.prepare()
        assert client.domain == 'fresh.example.com'
    assert session.calls[0][1] == 'https://discovery.example.com'
    assert session.calls[1][1] == 'https://fresh.example.com/setting'


@pytest.mark.parametrize("response", [Timeout(SECRET), encrypted_domains([None]), encrypted_domains(['https://bad.example.com/path'])])
def test_discovery_failure_falls_back_without_logging_data(monkeypatch, response):
    monkeypatch.setattr(JmModuleConfig, "API_URL_DOMAIN_SERVER_LIST", ['https://discovery.example.com'])
    monkeypatch.setattr(JmModuleConfig, "DOMAIN_API_LIST", ['fallback.example.com'])
    cfg, session, client = build([response, {}])
    cfg.api_domain = None
    with client:
        client.prepare()
        assert client.domain == 'fallback.example.com'


@pytest.mark.parametrize("version,updated", [('99.1.2', True), ('1.0', False), (SECRET, False), (None, False)])
def test_version_negotiation_is_per_session(version, updated):
    original = JmMagicConstants.APP_VERSION
    cfg, session, client = build([{'jm3_version': version}, login_data()])
    with client:
        client.prepare()
        client.login()
    assert session.calls[1][2]['headers']['tokenparam'].split(',')[1] == (version if updated else original)
    assert JmMagicConstants.APP_VERSION == original


def test_login_transient_timeout_retries_once():
    cfg, session, client = build([{}, Timeout(SECRET), login_data(), {'signed': True}])
    cfg.max_retries = 1
    assert JMComicTask('jm', cfg, lambda _: client).execute().status is TaskStatus.SKIPPED
    assert sum(call[1].endswith('/login') for call in session.calls) == 2


def test_timeout_with_server_success_does_not_post_again():
    cfg, session, client = build([{}, login_data(), {'signed': False, 'daily_id': 72}, Timeout(SECRET), {'signed': True}])
    cfg.max_retries = 1
    assert JMComicTask('jm', cfg, lambda _: client).execute().status is TaskStatus.SKIPPED
    assert sum(call[1].endswith('/daily_chk') for call in session.calls) == 1


@pytest.mark.parametrize('second', [
    {'msg': '今天已經簽到過了'},
    RawResponse({'code': 400, 'errorMsg': '今天已經簽到過了'}),
])
def test_timeout_then_duplicate_is_not_failed(second):
    cfg, session, client = build([
        {}, login_data(), {'signed': False, 'daily_id': 72}, Timeout(SECRET),
        {'signed': False, 'daily_id': 72}, second,
    ])
    cfg.max_retries = 1
    assert JMComicTask('jm', cfg, lambda _: client).execute().status is TaskStatus.SKIPPED
    assert sum(call[1].endswith('/daily_chk') for call in session.calls) == 2


def test_retry_exhaustion_is_not_success():
    cfg, session, client = build([
        {}, login_data(), {'signed': False, 'daily_id': 72}, Timeout(SECRET),
        {'signed': False, 'daily_id': 72}, Timeout(SECRET), {'signed': False, 'daily_id': 72},
    ])
    cfg.max_retries = 1
    with pytest.raises(TaskTimeoutError):
        JMComicTask('jm', cfg, lambda _: client).execute()
    assert session.closed
    assert sum(call[1].endswith('/daily_chk') for call in session.calls) == 2


def test_unreadable_verification_never_triggers_another_post():
    cfg, session, client = build([
        {}, login_data(), {'signed': False, 'daily_id': 72}, Timeout(SECRET), {},
    ])
    cfg.max_retries = 1
    with pytest.raises(TaskTimeoutError):
        JMComicTask('jm', cfg, lambda _: client).execute()
    assert sum(call[1].endswith('/daily_chk') for call in session.calls) == 1


def test_retry_rejection_rechecks_delayed_server_success():
    cfg, session, client = build([
        {}, login_data(), {'signed': False, 'daily_id': 72}, Timeout(SECRET),
        {'signed': False, 'daily_id': 72}, RawResponse({'code':400, 'errorMsg':SECRET}),
        {'signed': True},
    ])
    cfg.max_retries = 1
    assert JMComicTask('jm', cfg, lambda _: client).execute().status is TaskStatus.SKIPPED
