import asyncio
import json
from contextlib import asynccontextmanager

import httpx
import pytest

from common.app.server import create_app
from common.core.config import Config
from common.core.records import redact
from common.core.experiments import grade
from tests.test_learning_chat import course


@asynccontextmanager
async def client_for(tmp_path, backend='demo', lesson=2, lesson_root=None):
    options = {'lesson_root': lesson_root} if lesson_root is not None else {}
    app = create_app(backend, Config(api_key='test-secret', lesson=lesson), root=tmp_path, **options)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url='http://127.0.0.1:8766') as client:
            bootstrap = (await client.get('/api/bootstrap')).json()
            client.headers['X-Comma-Token'] = bootstrap['csrf_token']
            yield app, client


async def create(client, **settings):
    response = await client.post('/api/sessions', json=settings)
    assert response.status_code == 201, response.text
    return response.json()['id']


async def finish(app, client, sid, text='请展示这个流程', **kwargs):
    response = await client.post(f'/api/sessions/{sid}/messages', json={'text': text, **kwargs})
    assert response.status_code == 202, response.text
    await asyncio.wait_for(asyncio.shield(app.state.service.get(sid).task), 10)
    return (await client.get(f'/api/sessions/{sid}')).json()


@pytest.mark.parametrize('lesson', [1, 2])
async def test_demo_full_http_flow(lesson, tmp_path):
    async with client_for(tmp_path, lesson=lesson) as (app, client):
        sid = await create(client)
        result = await finish(app, client, sid)
        assert result['status'] == 'completed' and result['grade']['status'] == 'not_scored'
        assert [m['role'] for m in result['messages']] == ['user', 'assistant']
        record = (await client.get(f"/api/runs/{result['run_id']}/export")).json()
        assert record['lesson'] == lesson
        assert result['trace']['calls'] > 0
        for image in result['images']:
            assert (await client.get(image['url'])).status_code == 200
        result = await finish(app, client, sid, '再来一次')
        assert len(result['messages']) == 4
        fresh = await create(client)
        assert not (await client.get(f'/api/sessions/{fresh}')).json()['messages']


async def test_lesson_checkpoints_and_llm_probe(tmp_path, monkeypatch, course):
    from common.core.types import ModelReply
    async def complete(messages, tools, config):
        assert not tools or {t.name for t in tools} == {'list_files', 'read_course_file', 'check_agent'}
        return ModelReply({'role': 'assistant', 'content': 'LLM ready'})
    monkeypatch.setattr('common.core.llm.complete', complete)
    async with client_for(tmp_path / 'runs', 'exercise', lesson=1, lesson_root=course) as (app, client):
        sid = await create(client)
        result = await finish(app, client, sid, llm_only=True)
        assert result['status'] == 'completed' and result['messages'][-1]['text'] == 'LLM ready'
        result = await finish(app, client, sid)
        assert result['status'] == 'completed' and result['runner'] == 'teaching_chat'
        assert result['learning']['passed'] == 0
        boot = (await client.get('/api/bootstrap')).json()
        assert boot['lesson_capabilities'] == ['chat', 'tools'] and boot['lesson'] == 1
        assert any(t['id'] == 'code-edit' for t in boot['tasks'])
        assert (await client.post('/api/sessions', json={'task_id': 'code-edit'})).status_code == 201
        assert (await client.post('/api/sessions', json={'task_id': 'calculator'})).status_code == 400


async def test_cancel_blocks_concurrent_turn_and_clears_history(tmp_path):
    async with client_for(tmp_path) as (app, client):
        sid = await create(client)
        other = await create(client)
        response = await client.post(f'/api/sessions/{sid}/messages', json={'text': 'run'})
        assert response.json()['busy']
        assert (await client.post(f'/api/sessions/{other}/messages', json={'text': 'second'})).status_code == 409
        cancelled = await client.post(f'/api/sessions/{sid}/stop', json={})
        assert cancelled.json()['status'] == 'cancelled' and not cancelled.json()['busy']
        assert not app.state.service.get(sid).runtime.state.messages
        assert app.state.service.active_id is None
        assert (await finish(app, client, other))['status'] == 'completed'


async def test_cancel_before_coroutine_starts(tmp_path):
    async with client_for(tmp_path) as (app, client):
        sid = await create(client)
        session = app.state.service.get(sid)
        app.state.service.start(session, 'run')
        await app.state.service.stop(session)
        assert session.status == 'cancelled' and not session.busy
        assert app.state.service.active_id is None


async def test_history_reload_resumes_conversation_and_exports(tmp_path):
    async with client_for(tmp_path) as (app, client):
        sid = await create(client)
        run = (await finish(app, client, sid))['run_id']
    async with client_for(tmp_path) as (app, client):
        items = [s for s in (await client.get('/api/sessions')).json()['sessions'] if not s.get('experiment')]
        assert items[0]['id'] == sid and not items[0]['readonly']
        snapshot = (await client.get(f'/api/sessions/{sid}')).json()
        assert len(snapshot['messages']) == 2
        assert len((await finish(app, client, sid, '继续'))['messages']) == 4
        assert (await client.get(f'/api/runs/{run}/files/../.env')).status_code == 404
        assert (await client.get(f'/api/runs/{run}/files/run.json')).status_code == 404
        assert (await client.get(f'/api/runs/{run}/export')).headers['content-disposition'].startswith('attachment;')


async def test_http_validation_localhost_csrf_and_no_secrets(tmp_path):
    async with client_for(tmp_path) as (app, client):
        boot = await client.get('/api/bootstrap')
        assert 'test-secret' not in boot.text and boot.json()['api_configured']
        assert (await client.get('/', headers={'Host': 'evil.example'})).status_code == 400
        assert (await client.get('/api/bootstrap', headers={'Origin': 'https://evil.example'})).status_code == 403
        assert (await client.get('/api/bootstrap', headers={'Sec-Fetch-Site': 'cross-site'})).status_code == 403
        assert (await client.post('/api/sessions', json={}, headers={'X-Comma-Token': ''})).status_code == 403
        assert (await client.post('/api/sessions', json={'mode': 'chat', 'task_id': 'code-edit'})).status_code == 400
        assert (await client.post('/api/sessions', json={'model': 'unknown'})).status_code == 400
        assert (await client.post('/api/sessions', content='{}')).status_code == 415
        sid = await create(client)
        assert (await client.post(f'/api/sessions/{sid}/messages', json={'text':'  '})).status_code == 400
        assert (await client.post(f'/api/sessions/{sid}/messages', json={'text':'x'*70000})).status_code == 413
        result = await finish(app, client, sid, 'test-secret <img src=x onerror=alert(1)>')
        assert 'test-secret' not in str(result)
        assert (await client.get('/static/app.js')).status_code == 200
        assert 'frame-ancestors' in (await client.get('/')).headers['content-security-policy']


def test_grading_and_redaction():
    assert grade('constraints', '8|6|2', [])['status'] == 'pass'
    assert grade('constraints', '8|6|2。', [])['status'] == 'fail'
    assert grade('calculator', '4736', [])['status'] == 'manual'
    assert 'secret' not in str(redact({'authorization': 'secret', 'text': 'secret'}, 'secret'))


async def test_sse_pending_completion_reconnect_over_real_http(tmp_path):
    import socket
    import uvicorn
    app = create_app('demo', Config(), root=tmp_path)
    sock = socket.socket()
    sock.bind(('127.0.0.1', 0))
    server = uvicorn.Server(uvicorn.Config(app, log_level='error', lifespan='on', timeout_graceful_shutdown=1))
    task = asyncio.create_task(server.serve(sockets=[sock]))
    try:
        async with asyncio.timeout(5):
            while not server.started:
                await asyncio.sleep(.01)
        async with httpx.AsyncClient(base_url=f'http://127.0.0.1:{sock.getsockname()[1]}') as client:
            client.headers['X-Comma-Token'] = (await client.get('/api/bootstrap')).json()['csrf_token']
            sid = await create(client)
            await client.post(f'/api/sessions/{sid}/messages', json={'text': 'SSE test'})
            snapshots = []
            async with asyncio.timeout(5):
                async with client.stream('GET', f'/api/sessions/{sid}/events') as response:
                    assert response.headers['content-type'].startswith('text/event-stream')
                    async for line in response.aiter_lines():
                        if line.startswith('data: '):
                            snapshots.append(json.loads(line[6:]))
                            if not snapshots[-1]['busy']:
                                break
            assert any(s['busy'] for s in snapshots)
            assert any(step['status'] == 'running' for s in snapshots for step in s['trace']['steps'])
            assert snapshots[-1]['status'] == 'completed'
            async with client.stream('GET', f'/api/sessions/{sid}/events') as response:
                async for line in response.aiter_lines():
                    if line.startswith('data: '):
                        assert json.loads(line[6:])['run_id'] == snapshots[-1]['run_id']
                        break
    finally:
        server.should_exit = True
        await asyncio.wait_for(task, 5)
        sock.close()


async def test_lesson_history_excludes_later_capabilities(tmp_path):
    async with client_for(tmp_path, lesson=2) as (app, client):
        sid = await create(client)
        await finish(app, client, sid)
    async with client_for(tmp_path, lesson=1) as (app, client):
        assert not [s for s in (await client.get('/api/sessions')).json()['sessions'] if not s.get('experiment')]


async def test_task_selection_never_changes_lesson_capabilities(tmp_path):
    async with client_for(tmp_path, lesson=1) as (app, client):
        for task_id in ['free', 'format', 'code-edit']:
            sid = await create(client, task_id=task_id)
            snapshot = await finish(app, client, sid)
            record = (await client.get(f"/api/runs/{snapshot['run_id']}/export")).json()
            assert record['lesson'] == 1 and record['mode'] == 'tools'
            assert 'mode' not in snapshot['settings']
        assert (await client.post('/api/sessions', json={'mode': 'chat'})).status_code == 400
