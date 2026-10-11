"""Use the student's actual run_turn with deterministic model replies and real edit tools."""
from copy import deepcopy
import json

import pytest

from common.core.config import ROOT
from common.core.edit_tools import BASELINE, FILENAME, version
from common.core.editor_eval import expected_source
from common.core.types import ModelReply
from tests.test_edit import patches
from tests.test_learning_chat import course, tool_reply
from tests.test_scaffold import client_for, finish


@pytest.mark.parametrize('restart', [False, True])
async def test_student_can_undo_previous_turn_and_reset_explicitly(course, monkeypatch, restart):
    # Install a completed student implementation only in the isolated course copy.
    (course / 'lesson_01_agent/agent.py').write_bytes((ROOT / 'lesson_02_computer_use/agent.py').read_bytes())
    requests = []

    async def complete(messages, tools, config):
        requests.append(deepcopy(messages))
        command = next(m['content'] for m in reversed(messages) if m['role'] == 'user')
        if messages[-1]['role'] == 'tool':
            assert not json.loads(messages[-1]['content'])['is_error']
            return ModelReply({'role': 'assistant', 'content': '已修改' if command == 'rename' else '已撤销'})
        if command == 'fresh':
            assert [m['role'] for m in messages] == ['system', 'user']
            return ModelReply({'role': 'assistant', 'content': '新实验'})
        edits = patches()
        if command == 'undo':
            assert any(m.get('content') == '已修改' for m in messages)
            assert any(m['role'] == 'tool' for m in messages)
            assert any(m.get('tool_calls') for m in messages)
            edits = [{'old_text': item['new_text'], 'new_text': item['old_text']} for item in edits]
        return tool_reply('edit', {'path': FILENAME, 'base_version': version(
            expected_source() if command == 'undo' else BASELINE), 'edits': edits}, command)

    monkeypatch.setattr('common.core.llm.complete', complete)
    sid = 'experiment-1-code-edit'
    runs = course / 'runs'

    async def undo_and_reset(app, client, first):
        undone = await finish(app, client, sid, 'undo')
        assert undone['status'] == 'completed' and undone['runner'] == 'student'
        original = runs / first['run_id']
        after = runs / undone['run_id']
        assert (original / 'code' / FILENAME).read_bytes() == expected_source().encode()
        assert (after / 'code' / FILENAME).read_bytes() == BASELINE.encode()
        record = json.loads((after / 'run.json').read_text())
        assert record['code_parent_run'] == first['run_id']
        assert any(m.get('content') == 'rename' for m in record['model_messages'])
        # Reset while the file is edited, then verify both history and file start fresh.
        renamed = await finish(app, client, sid, 'rename')
        assert renamed['grade']['passed'] == 8
        assert (await client.post(f'/api/sessions/{sid}/reset', json={})).status_code == 200
        assert app.state.service.get(sid).runtime.edit_path is None
        fresh = await finish(app, client, sid, 'fresh')
        assert (runs / fresh['run_id'] / 'code' / FILENAME).read_bytes() == BASELINE.encode()
        assert len(requests[-1]) == 2

    async with client_for(runs, lesson=1, lesson_root=course, fake_io=False) as (app, client):
        first = await finish(app, client, sid, 'rename')
        assert first['grade']['passed'] == 8 and first['runner'] == 'student'
        if not restart:
            await undo_and_reset(app, client, first)
            return
    async with client_for(runs, lesson=1, lesson_root=course, fake_io=False) as (app, client):
        restored = (await client.get(f'/api/sessions/{sid}')).json()
        assert not restored['readonly']
        await undo_and_reset(app, client, first)


async def test_error_after_edit_keeps_file_for_next_turn(course, monkeypatch):
    (course / 'lesson_01_agent/agent.py').write_bytes((ROOT / 'lesson_02_computer_use/agent.py').read_bytes())
    async def complete(messages, tools, config):
        command = next(m['content'] for m in reversed(messages) if m['role'] == 'user')
        if command == 'recover':
            assert any('simulated failure' in str(m.get('content')) for m in messages)
            return tool_reply('read_file', {'path': FILENAME, 'start_line': 1808, 'end_line': 1808}, 'read') if messages[-1]['role'] != 'tool' else ModelReply({'role': 'assistant', 'content': '文件仍保留修改'})
        if messages[-1]['role'] == 'tool':
            raise RuntimeError('simulated failure after editing')
        return tool_reply('edit', {'path': FILENAME, 'base_version': version(BASELINE), 'edits': patches()}, 'edit')
    monkeypatch.setattr('common.core.llm.complete', complete)
    runs = course / 'runs'
    sid = 'experiment-1-code-edit'
    async with client_for(runs, lesson=1, lesson_root=course, fake_io=False) as (app, client):
        failed = await finish(app, client, sid, 'rename')
        assert failed['status'] == 'error'
    async with client_for(runs, lesson=1, lesson_root=course, fake_io=False) as (app, client):
        recovered = await finish(app, client, sid, 'recover')
        assert recovered['status'] == 'completed' and recovered['grade']['passed'] == 8
        assert (runs / recovered['run_id'] / 'code' / FILENAME).read_bytes() == expected_source().encode()


@pytest.mark.parametrize('missing', ['model_messages', 'file'])
async def test_incomplete_saved_experiment_requires_explicit_reset(course, monkeypatch, missing):
    (course / 'lesson_01_agent/agent.py').write_bytes((ROOT / 'lesson_02_computer_use/agent.py').read_bytes())
    async def complete(messages, tools, config):
        return ModelReply({'role': 'assistant', 'content': '完成'})
    monkeypatch.setattr('common.core.llm.complete', complete)
    runs = course / 'runs'
    sid = 'experiment-1-code-edit'
    async with client_for(runs, lesson=1, lesson_root=course, fake_io=False) as (app, client):
        done = await finish(app, client, sid)
    path = runs / done['run_id'] / 'run.json'
    if missing == 'model_messages':
        record = json.loads(path.read_text())
        record.pop('model_messages')
        path.write_text(json.dumps(record))
    else:
        (path.parent / 'code' / FILENAME).unlink()
    async with client_for(runs, lesson=1, lesson_root=course, fake_io=False) as (_, client):
        restored = (await client.get(f'/api/sessions/{sid}')).json()
        assert restored['readonly']
        assert (await client.post(f'/api/sessions/{sid}/messages', json={'text': 'continue'})).status_code == 409
        assert (await client.post(f'/api/sessions/{sid}/reset', json={})).status_code == 200
