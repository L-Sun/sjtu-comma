from pathlib import Path

from common.core.types import ModelReply
from tests.test_scaffold import client_for, create, finish


async def test_clear_history_keeps_current_context_and_survives_restart(tmp_path, monkeypatch):
    requests = []
    async def complete(messages, tools, config):
        requests.append([dict(message) for message in messages])
        return ModelReply({'role': 'assistant', 'content': '收到'})
    monkeypatch.setattr('common.core.llm.complete', complete)
    async with client_for(tmp_path, fake_io=False, lesson=1) as (app, client):
        old = await create(client)
        first = await finish(app, client, old, '旧对话第一轮')
        second = await finish(app, client, old, '旧对话第二轮')
        current = await create(client, task_id='format')
        kept = await finish(app, client, current, '保留当前暗号 KEEP_CONTEXT')
        response = await client.post('/api/sessions/clear-history', json={'keep_id': current})
        assert response.status_code == 200 and response.json()['cleared'] == 1
        assert [s['id'] for s in response.json()['sessions'] if not s.get('experiment')] == [current]
        after = (await client.get(f'/api/sessions/{current}')).json()
        for field in ['messages', 'trace', 'settings', 'run_id', 'status']:
            assert after[field] == kept[field]
        assert (await client.get(f'/api/sessions/{old}')).status_code == 404
        for run in [first['run_id'], second['run_id']]:
            assert (await client.get(f'/api/runs/{run}/export')).status_code == 404
            assert len(list((tmp_path/'.trash').glob(f'*/{run}/run.json'))) == 1
        assert (await client.get(f"/api/runs/{kept['run_id']}/export")).status_code == 200
        await finish(app, client, current, '继续当前话题')
        assert 'KEEP_CONTEXT' in str(requests[-1])
    async with client_for(tmp_path, fake_io=False, lesson=1) as (_, client):
        rows = (await client.get('/api/sessions')).json()['sessions']
        assert all(row['id'] not in {'run-'+first['run_id'], 'run-'+second['run_id']} for row in rows)
        assert any(row['id'] == current for row in rows)


async def test_clear_saved_history_keeps_running_task_and_checks_requests(tmp_path):
    async with client_for(tmp_path) as (app, client):
        sid = await create(client)
        saved = await finish(app, client, sid)
    async with client_for(tmp_path) as (app, client):
        history = sid
        old_session = app.state.service.get(history)
        current = await create(client)
        await client.post(f'/api/sessions/{current}/messages', json={'text': '正在执行'})
        assert (await client.post('/api/sessions/clear-history', json={}, headers={'X-Comma-Token': ''})).status_code == 403
        assert (await client.post('/api/sessions/clear-history', json={'keep_id': 'stale'})).status_code == 409
        assert (await client.post('/api/sessions/clear-history', json={'keep_id': 1})).status_code == 400
        protected = await client.post('/api/sessions/clear-history', json={'keep_id': history})
        assert protected.status_code == 200 and protected.json()['cleared'] == 0
        assert (await client.get(f'/api/sessions/{history}')).json()['messages']
        response = await client.post('/api/sessions/clear-history', json={})
        assert response.status_code == 200 and response.json()['cleared'] == 1
        assert app.state.service.active_id == current and app.state.service.get(current).busy
        assert app.state.service.snapshot(old_session)['removed']
        assert not old_session.messages
        await app.state.service.get(current).task
        assert app.state.service.get(current).status == 'completed'
        assert (await client.post('/api/sessions/clear-history', json={})).json()['cleared'] == 1
        assert not [s for s in (await client.get('/api/sessions')).json()['sessions'] if not s.get('experiment')]
        assert (await client.post('/api/sessions/clear-history', json={})).json()['cleared'] == 0


async def test_clear_history_failure_rolls_back_entire_batch(tmp_path, monkeypatch):
    async with client_for(tmp_path) as (app, client):
        first = await finish(app, client, await create(client))
        second = await finish(app, client, await create(client), '第二段对话')
        run_ids = sorted([first['run_id'], second['run_id']])
        rename = Path.rename
        def fail_second(source, target):
            if source == tmp_path/run_ids[1]:
                raise PermissionError('test locked file')
            return rename(source, target)
        monkeypatch.setattr(Path, 'rename', fail_second)
        response = await client.post('/api/sessions/clear-history', json={})
        assert response.status_code == 500
        assert len([s for s in (await client.get('/api/sessions')).json()['sessions'] if not s.get('experiment')]) == 2
        for run in run_ids:
            assert (tmp_path/run/'run.json').is_file()
