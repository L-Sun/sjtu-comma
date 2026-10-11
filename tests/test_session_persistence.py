"""Conversation identity and model context survive service restarts."""
from copy import deepcopy
import json

import pytest

from common.core.config import Config
from common.core.records import Record, saved_messages
from common.core.types import ModelReply
from tests.test_learning_chat import tool_reply
from tests.test_scaffold import client_for, create, finish


async def test_multiturn_tool_context_and_identity_survive_two_restarts(tmp_path, monkeypatch):
    requests = []
    async def complete(messages, tools, config):
        requests.append(deepcopy(messages))
        if len(requests) == 1:
            return tool_reply('list_files', {}, 'saved-call')
        return ModelReply({'role': 'assistant', 'content': '记住了',
                           'reasoning_details': [{'type': 'example', 'data': 'provider metadata'}]})
    monkeypatch.setattr('common.core.llm.complete', complete)
    async with client_for(tmp_path, 'exercise', lesson=1) as (app, client):
        sid = await create(client)
        first = await finish(app, client, sid, '记住暗号 COMMA_PERSIST')
        second = await finish(app, client, sid, '同一段对话的下一轮')
        expected = deepcopy(app.state.service.get(sid).runtime.state.messages)
        run_ids = [first['run_id'], second['run_id']]
    async with client_for(tmp_path, 'exercise', lesson=1) as (app, client):
        rows = [s for s in (await client.get('/api/sessions')).json()['sessions'] if not s.get('experiment')]
        assert len(rows) == 1 and rows[0]['id'] == sid and not rows[0]['readonly']
        restored = (await client.get(f'/api/sessions/{sid}')).json()
        assert restored['title'] == first['title'] and restored['created_at'] == first['created_at']
        assert restored['messages'] == second['messages']
        assert restored['trace']['calls'] == second['trace']['calls'] == 1
        assert len(restored['trace']['steps']) == len(second['trace']['steps'])
        assert [r['id'] for r in restored['runs']] == run_ids
        assert app.state.service.get(sid).runtime.state.messages == expected
        third = await finish(app, client, sid, '重启后继续，暗号是什么？')
        assert requests[-1][:-1] == expected
        assert any(m.get('tool_call_id') == 'saved-call' for m in requests[-1])
        assert any(m.get('reasoning_details') for m in requests[-1])
        assert len(third['messages']) == 6
        for run in run_ids:
            assert (await client.get(f'/api/runs/{run}/export')).status_code == 200
        # Same opening text must still create a separate conversation.
        other = await create(client)
        await finish(app, client, other, '记住暗号 COMMA_PERSIST')
    async with client_for(tmp_path, 'exercise', lesson=1) as (_, client):
        rows = [s for s in (await client.get('/api/sessions')).json()['sessions'] if not s.get('experiment')]
        assert {s['id'] for s in rows} == {sid, other}
        assert len((await client.get(f'/api/sessions/{sid}')).json()['runs']) == 3
        assert (await client.post('/api/sessions/clear-history', json={'keep_id': other})).json()['cleared'] == 1
    async with client_for(tmp_path, 'exercise', lesson=1) as (_, client):
        rows = [s for s in (await client.get('/api/sessions')).json()['sessions'] if not s.get('experiment')]
        assert [s['id'] for s in rows] == [other]


@pytest.mark.parametrize('status', ['running', 'cancelled', 'timeout', 'error'])
async def test_interrupted_context_is_not_sent_back_to_model(tmp_path, monkeypatch, status):
    calls = []
    async def complete(messages, tools, config):
        calls.append(deepcopy(messages))
        return ModelReply({'role': 'assistant', 'content': '完成'})
    monkeypatch.setattr('common.core.llm.complete', complete)
    async with client_for(tmp_path, 'exercise', lesson=1) as (app, client):
        sid = await create(client)
        snapshot = await finish(app, client, sid, '旧请求')
    path = tmp_path / snapshot['run_id'] / 'run.json'
    record = json.loads(path.read_text())
    record['status'] = status
    record['model_messages'] = [{'role': 'assistant', 'content': None, 'tool_calls': [
        {'id': 'unmatched', 'type': 'function', 'function': {'name': 'list_files', 'arguments': '{}'}}]}]
    path.write_text(json.dumps(record))
    async with client_for(tmp_path, 'exercise', lesson=1) as (app, client):
        restored = (await client.get(f'/api/sessions/{sid}')).json()
        assert not restored['busy'] and not restored['readonly'] and restored['messages']
        assert restored['status'] == ('cancelled' if status == 'running' else status)
        await finish(app, client, sid, '继续新请求')
        assert [m['role'] for m in calls[-1]] == ['system', 'user']
        assert calls[-1][-1]['content'] == '继续新请求'


async def test_legacy_runs_stay_distinct_readonly_and_clearable(tmp_path):
    ids = []
    for text in ['旧轮次一', '旧轮次二']:
        record = Record(Config(lesson=1), 'exercise', 'free', root=tmp_path)
        record.add('user', {'text': text})
        record.add('assistant', {'text': '旧回复'})
        record.data['status'] = 'completed'
        record.save()
        ids.append('run-' + record.id)
    async with client_for(tmp_path, lesson=1) as (_, client):
        rows = [s for s in (await client.get('/api/sessions')).json()['sessions'] if not s.get('experiment')]
        assert {s['id'] for s in rows} == set(ids)
        assert all(s['legacy'] and s['readonly'] for s in rows)
        for sid in ids:
            assert len((await client.get(f'/api/sessions/{sid}')).json()['messages']) == 2
            assert (await client.post(f'/api/sessions/{sid}/messages', json={'text': '继续'})).status_code == 409
        result = (await client.post('/api/sessions/clear-history', json={'keep_id': ids[0]})).json()
        assert result['cleared'] == 1
    async with client_for(tmp_path, lesson=1) as (_, client):
        assert [s['id'] for s in (await client.get('/api/sessions')).json()['sessions'] if s.get('legacy')] == [ids[0]]


def test_saved_context_redacts_secrets_and_replaces_images_without_mutation():
    messages = [{'role': 'assistant', 'content': 'test-secret'},
                {'role': 'user', 'content': [{'type': 'text', 'text': '观察结果'},
                 {'type': 'image_url', 'image_url': {'url': 'data:image/png;base64,YWJj'}}]}]
    before = deepcopy(messages)
    saved = saved_messages(messages, 'test-secret')
    assert messages == before
    assert saved[0]['content'] == '[REDACTED]'
    assert all(p['type'] == 'text' for p in saved[1]['content'])
    assert 'data:image' not in json.dumps(saved)


def test_record_save_failure_preserves_previous_checkpoint(tmp_path, monkeypatch):
    record = Record(Config(), 'exercise', 'free', root=tmp_path)
    path = record.save()
    before = path.read_bytes()
    def fail(*args):
        raise OSError('模拟磁盘保存失败')
    monkeypatch.setattr('common.core.records.os.replace', fail)
    record.data['status'] = 'completed'
    with pytest.raises(OSError):
        record.save()
    assert path.read_bytes() == before
    assert not list(record.path.glob('.run-*'))
