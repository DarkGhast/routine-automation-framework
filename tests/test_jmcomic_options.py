import pytest
from pydantic import ValidationError

from plugins.jmcomic.config import JMComicConfig
from plugins.jmcomic.task import JMComicTask
from tests.test_jmcomic import FakeClient


@pytest.mark.parametrize('limit', [-1, False, 0, 20])
def test_random_delay_runs_once_before_client_creation(monkeypatch, limit):
    cfg = JMComicConfig(username='fake', password='fake', random_delay_seconds=limit)
    events = []
    monkeypatch.setattr('plugins.jmcomic.task.random.uniform', lambda a, b: 7)
    monkeypatch.setattr('plugins.jmcomic.task.time.sleep', lambda seconds: events.append(('sleep', seconds)))
    def factory(config):
        events.append(('client', None))
        return FakeClient(config)
    JMComicTask('jm', cfg, factory).execute()
    assert events == ([('sleep', 7), ('client', None)] if limit == 20 else [('client', None)])


@pytest.mark.parametrize('options', [
    {'random_delay_seconds': True}, {'random_delay_seconds': -2}, {'random_delay_seconds': 1.5},
    {'random_delay_seconds': 86401}, {'max_retries': 4}, {'max_retries': True},
    {'jmcomic_config': {'unknown': 'secret'}},
    {'jmcomic_config': {'domains': ['https://example.com']}},
    {'jmcomic_config': {'proxies': {'http': 'not-a-url'}}},
    {'jmcomic_config': {'headers': {'TOKEN': 'secret'}}},
    {'jmcomic_config': {'headers': {'User-Agent': 'secret\r\nbad'}}},
])
def test_invalid_options_do_not_expose_values(options):
    with pytest.raises(ValidationError) as caught:
        JMComicConfig(username='fake', password='fake', **options)
    assert 'secret' not in str(caught.value)
