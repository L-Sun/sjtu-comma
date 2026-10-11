"""Single-step teaching, explicit continuation, and durable tool-result checkpoints."""
import asyncio
from copy import deepcopy

import pytest

from common.core.types import ModelReply
from tests.test_learning_chat import course, tool_reply, continue_step
from tests.test_scaffold import client_for, create, finish


async def test_batch_tools_pause_even_on_errors_and_new_input_can_continue(course, monkeypatch):
    requests = []
    async def model(messages, tools, config):
        requests.append(deepcopy(messages))
        if len(requests) == 1:
            reply = tool_reply('list_files', {}, 'read')
            reply.message['tool_calls'] += tool_reply('not_available', {}, 'error').tool_calls
            return reply
        return ModelReply({'role': 'assistant', 'content': '已处理结果和补充要求'})
    monkeypatch.setattr('common.core.llm.complete', model)
    async with client_for(course/'runs', lesson=1, lesson_root=course, fake_io=False) as (app, client):
        sid = await create(client)
        first = await finish(app, client, sid, '列目录')
        assert len(requests) == 1 and first['status'] == 'waiting' and not first['busy']
        assert first['awaiting_continue'] and first['trace']['calls'] == 2 and first['trace']['errors'] == 1
        assert [m['role'] for m in first['messages']] == ['user']  # no invented assistant summary
        saved = deepcopy(app.state.service.get(sid).runtime.state.messages)
        assert [m['tool_call_id'] for m in saved if m['role'] == 'tool'] == ['read', 'error']
        assert all(step['output'] for step in first['trace']['steps'] if step['tool'])
        second = await finish(app, client, sid, '先解释刚才的错误')
        assert len(requests) == 2 and requests[-1][:-1] == saved
        assert requests[-1][-1] == {'role': 'user', 'content': '先解释刚才的错误'}
        assert second['status'] == 'completed' and not second['awaiting_continue']
        assert (await client.post(f'/api/sessions/{sid}/continue', json={'run_id': second['run_id']})).status_code == 409


async def test_waiting_survives_restart_and_continue_has_no_synthetic_user(course, monkeypatch):
    requests = []
    async def model(messages, tools, config):
        requests.append(deepcopy(messages))
        if len(requests) <= 2:
            return tool_reply('list_files', {}, f'call-{len(requests)}')
        return ModelReply({'role': 'assistant', 'content': '完成'})
    monkeypatch.setattr('common.core.llm.complete', model)
    options = {'lesson': 1, 'lesson_root': course, 'fake_io': False}
    async with client_for(course/'runs', **options) as (app, client):
        sid = await create(client)
        waiting = await finish(app, client, sid, '请读课程目录')
        saved = deepcopy(app.state.service.get(sid).runtime.state.messages)
    async with client_for(course/'runs', **options) as (app, client):
        restored = (await client.get(f'/api/sessions/{sid}')).json()
        assert restored['awaiting_continue'] and restored['status'] == 'waiting'
        assert restored['messages'] == waiting['messages']
        assert '等待继续' in restored['trace']['current']
        second = await continue_step(app, client, restored)
        assert requests[1] == saved and len(requests) == 2
        assert second['awaiting_continue'] and second['messages'] == waiting['messages']
        assert second['runs'][-1]['title'] == '继续下一步'
        stale = await client.post(f'/api/sessions/{sid}/continue', json={'run_id': restored['run_id']})
        assert stale.status_code == 409 and len(requests) == 2
        done = await continue_step(app, client, second)
        assert len(requests) == 3 and done['status'] == 'completed' and not done['awaiting_continue']
        assert sum(m['role'] == 'user' for m in requests[-1]) == 1
        record = (await client.get(f"/api/runs/{done['run_id']}/export")).json()
        assert record['continuation'] and not any(e['kind'] == 'user' for e in record['events'])
    async with client_for(course/'runs', **options) as (_, client):
        restored = (await client.get(f'/api/sessions/{sid}')).json()
        assert restored['status'] == 'completed' and not restored['awaiting_continue']
        assert len(restored['runs']) == 3 and len(restored['messages']) == 2


async def test_duplicate_continue_is_blocked_and_stop_clears_waiting(course, monkeypatch):
    calls = []
    started = asyncio.Event()
    async def model(messages, tools, config):
        calls.append(True)
        if len(calls) == 1:
            return tool_reply('list_files', {}, 'first')
        started.set()
        await asyncio.Event().wait()
    monkeypatch.setattr('common.core.llm.complete', model)
    async with client_for(course/'runs', lesson=1, lesson_root=course, fake_io=False) as (app, client):
        sid = await create(client)
        waiting = await finish(app, client, sid, '列目录')
        args = {'run_id': waiting['run_id']}
        assert (await client.post(f'/api/sessions/{sid}/continue', json=args)).status_code == 202
        await asyncio.wait_for(started.wait(), 3)
        assert (await client.post(f'/api/sessions/{sid}/continue', json=args)).status_code == 409
        stopped = (await client.post(f'/api/sessions/{sid}/stop', json={})).json()
        assert len(calls) == 2 and stopped['status'] == 'cancelled' and not stopped['awaiting_continue']
        assert app.state.service.get(sid).runtime.state.messages == []


async def test_llm_probe_does_not_consume_pending_tool_results(course, monkeypatch):
    requests = []
    async def model(messages, tools, config):
        requests.append(deepcopy(messages))
        return tool_reply('list_files', {}, 'first') if len(requests) == 1 else ModelReply({'role': 'assistant', 'content': '完成'})
    monkeypatch.setattr('common.core.llm.complete', model)
    async with client_for(course/'runs', lesson=1, lesson_root=course, fake_io=False) as (app, client):
        sid = await create(client)
        waiting = await finish(app, client, sid, '列目录')
        saved = deepcopy(app.state.service.get(sid).runtime.state.messages)
        probe = await finish(app, client, sid, '测试接口', llm_only=True)
        assert probe['awaiting_continue'] and app.state.service.get(sid).runtime.state.messages == saved
        done = await continue_step(app, client, probe)
        assert requests[-1] == saved and not done['awaiting_continue']


@pytest.mark.parametrize('body', [{}, {'run_id': '../bad'}, {'run_id': '20261011T000000-12345678', 'extra': True}])
async def test_continue_requires_current_step_id(course, body):
    async with client_for(course/'runs', lesson=1, lesson_root=course, fake_io=False) as (_, client):
        sid = await create(client)
        assert (await client.post(f'/api/sessions/{sid}/continue', json=body)).status_code == 400
