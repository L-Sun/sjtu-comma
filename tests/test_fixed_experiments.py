import pytest

from common.core.experiments import task_by_id
from common.core.types import ModelReply
from tests.test_scaffold import client_for, create, finish


@pytest.mark.parametrize('lesson, count', [(1, 1), (2, 1)])
async def test_fixed_experiments_are_seeded_and_never_cleared(tmp_path, lesson, count):
    async with client_for(tmp_path, lesson=lesson) as (_, client):
        rows = (await client.get('/api/sessions')).json()['sessions']
        assert len(rows) == count and all(row['experiment'] for row in rows)
        for row in rows:
            value = (await client.get(f"/api/sessions/{row['id']}")).json()
            assert value['initial_prompt'] == task_by_id(row['experiment']).prompt
            assert not value['messages'] and value['title'] == task_by_id(row['experiment']).title
        await create(client)
        result = (await client.post('/api/sessions/clear-history', json={})).json()
        assert result['cleared'] == 1
        assert [s['id'] for s in result['sessions']] == [s['id'] for s in rows]


async def test_experiment_reset_clears_context_and_restores_prompt(tmp_path, monkeypatch):
    requests = []
    async def complete(messages, tools, config):
        requests.append([dict(m) for m in messages])
        return ModelReply({'role': 'assistant', 'content': '未修改文件'})
    monkeypatch.setattr('common.core.llm.complete', complete)
    async with client_for(tmp_path, fake_io=False, lesson=2) as (app, client):
        sid = 'experiment-2-code-edit'
        initial = (await client.get(f'/api/sessions/{sid}')).json()
        assert (await client.post(f'/api/sessions/{sid}/settings', json={'perception': 'tree'})).status_code == 200
        done = await finish(app, client, sid, 'FIRST_ATTEMPT')
        assert done['title'] == initial['title'] and done['grade']['status'] == 'fail'
        assert app.state.service.get(sid).runtime.state.messages
        assert (await client.post(f'/api/sessions/{sid}/settings', json={'perception': 'vision'})).status_code == 409
        cleared = (await client.post('/api/sessions/clear-history', json={})).json()
        assert cleared['cleared'] == 0
        assert (await client.get(f'/api/sessions/{sid}')).json()['messages'] == done['messages']
        reset = (await client.post(f'/api/sessions/{sid}/reset', json={})).json()
        assert reset['id'] == sid and reset['title'] == initial['title']
        assert reset['initial_prompt'] == initial['initial_prompt']
        assert not reset['messages'] and not reset['trace']['steps'] and not reset['images']
        assert reset['run_id'] is None and reset['code_file'] is None and reset['grade'] is None
        assert reset['status'] == 'ready' and not reset['readonly']
        assert reset['settings']['perception'] == 'tree'
        assert not app.state.service.get(sid).runtime.state.messages
        assert (await client.get(f"/api/runs/{done['run_id']}/export")).status_code == 404
        assert list((tmp_path/'.trash').glob(f"*/{done['run_id']}/run.json"))
        again = await finish(app, client, sid, initial['initial_prompt'])
        assert again['status'] == 'completed' and 'FIRST_ATTEMPT' not in str(requests[-1])
        assert [m['role'] for m in requests[-1]] == ['system', 'user']


async def test_saved_experiment_reopens_in_fixed_slot_and_resets_after_restart(tmp_path):
    sid = 'experiment-1-code-edit'
    async with client_for(tmp_path, lesson=1) as (app, client):
        done = await finish(app, client, sid)
        run_id = done['run_id']
    async with client_for(tmp_path, lesson=1) as (app, client):
        rows = (await client.get('/api/sessions')).json()['sessions']
        assert len(rows) == 1 and sum(row['id'] == sid for row in rows) == 1
        value = (await client.get(f'/api/sessions/{sid}')).json()
        assert not value['readonly'] and value['messages'] == done['messages']
        assert (await client.post('/api/sessions/clear-history', json={})).json()['cleared'] == 0
        assert (await client.get(f'/api/runs/{run_id}/export')).status_code == 200
        assert (await client.post(f'/api/sessions/{sid}/reset', json={})).status_code == 200
    async with client_for(tmp_path, lesson=1) as (_, client):
        fresh = (await client.get(f'/api/sessions/{sid}')).json()
        assert not fresh['messages'] and not fresh['readonly']
        assert fresh['initial_prompt'] == task_by_id('code-edit').prompt


async def test_reset_checks_csrf_busy_and_session_type(tmp_path):
    async with client_for(tmp_path, lesson=1) as (app, client):
        sid = 'experiment-1-code-edit'
        assert (await client.post(f'/api/sessions/{sid}/reset', json={}, headers={'X-Comma-Token': ''})).status_code == 403
        normal = await create(client)
        assert (await client.post(f'/api/sessions/{normal}/reset', json={})).status_code == 409
        assert (await client.post(f'/api/sessions/{sid}/settings', json={'task_id': 'free'})).status_code == 400
        await client.post(f'/api/sessions/{sid}/messages', json={'text': 'start'})
        assert (await client.post(f'/api/sessions/{sid}/reset', json={})).status_code == 409
        assert app.state.service.get(sid).busy
        await client.post(f'/api/sessions/{sid}/stop', json={})
        assert (await client.post(f'/api/sessions/{sid}/reset', json={})).status_code == 200


@pytest.mark.parametrize('lesson', [1, 2])
async def test_retired_experiments_are_rejected_and_hidden_after_restart(tmp_path, lesson):
    import json

    retired = ['format', 'constraints', 'quoted', 'tool-order', 'calculator', 'form', 'canvas']
    async with client_for(tmp_path, lesson=lesson) as (app, client):
        boot = (await client.get('/api/bootstrap')).json()
        assert [task['id'] for task in boot['tasks']] == ['free', 'code-edit']
        for task_id in retired:
            assert (await client.post('/api/sessions', json={'task_id': task_id})).status_code == 400
            assert (await client.get(f'/api/sessions/experiment-{lesson}-{task_id}')).status_code == 404
        current = await create(client)
        done = await finish(app, client, current)
        original = json.loads((tmp_path / done['run_id'] / 'run.json').read_text())

    old_paths = []
    for index, task_id in enumerate(retired):
        # Old fixed experiments, resumable chats, and pre-session legacy runs.
        for variant in range(3):
            record = {**original, 'id': f'20261010T000000-{index * 3 + variant:08x}', 'task_id': task_id}
            if variant == 0:
                record['experiment_id'] = f'experiment-{lesson}-{task_id}'
            elif variant == 1:
                record['session_id'] = f'{index:032x}'
            else:
                record.pop('session_id', None)
            path = tmp_path / record['id'] / 'run.json'
            path.parent.mkdir()
            path.write_text(json.dumps(record))
            old_paths.append(path)

    async with client_for(tmp_path, lesson=lesson) as (_, client):
        rows = (await client.get('/api/sessions')).json()['sessions']
        assert {row['id'] for row in rows} == {f'experiment-{lesson}-code-edit', current}
        assert all(path.is_file() for path in old_paths)
