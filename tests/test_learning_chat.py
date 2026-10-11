"""Exercise the actual tutor-to-student handoff with saved source and fake model IO."""
import asyncio
import json
from pathlib import Path
import shutil

import httpx
import pytest

from common.app.server import create_app
from common.core.config import ROOT, Config
from common.core.learning_workspace import LearningWorkspace
from common.core.types import ModelReply
from tests.student_source import unfinished


@pytest.fixture
def course(tmp_path):
    for folder in ('common', 'lesson_01_agent'):
        shutil.copytree(ROOT / folder, tmp_path / folder, ignore=shutil.ignore_patterns('__pycache__'))
    for name in ('agent.py', 'tools.py'):
        path = tmp_path / 'lesson_01_agent' / name
        path.write_text(unfinished(path.read_text()))
    (tmp_path / 'README.md').write_text('课程说明')
    (tmp_path / '.env').write_text('SECRET=never-read')
    return tmp_path


async def test_list_read_and_boundaries(course):
    workspace = LearningWorkspace(course)
    listing = json.loads((await workspace.execute('list_files', {})).text)
    paths = [item['path'] for item in listing['entries']]
    assert 'lesson_01_agent' in paths and '.env' not in paths
    read = await workspace.execute('read_course_file', {'path': 'lesson_01_agent/agent.py', 'start_line': 1, 'end_line': 20})
    assert not read.is_error and '1:' in json.loads(read.text)['content']
    (course / 'common/link.py').symlink_to(course / '.env')
    for path in ['.env', '../README.md', str(course / 'README.md'), 'common/link.py', 'lesson_02_computer_use/agent.py']:
        assert (await workspace.execute('read_course_file', {'path': path})).is_error
    for i in range(85):
        (course / 'common' / f'fixture_{i}.txt').write_text('example')
    page = json.loads((await workspace.execute('list_files', {'path': 'common'})).text)
    assert len(page['entries']) == 80 and page['next_offset'] == 80
    more = json.loads((await workspace.execute('list_files', {'path': 'common', 'offset': 80})).text)
    assert more['entries'] and not set(x['path'] for x in page['entries']) & set(x['path'] for x in more['entries'])


async def test_checks_cache_errors_and_timeout(course, monkeypatch):
    workspace = LearningWorkspace(course)
    first = await workspace.refresh()
    assert first['passed'] == 0 and len(first['checks']) == 7 and not first['ready']
    original = workspace._check
    async def unexpected(source):
        raise AssertionError('Unchanged source must reuse checks')
    monkeypatch.setattr(workspace, '_check', unexpected)
    assert await workspace.refresh() == first
    monkeypatch.setattr(workspace, '_check', original)
    workspace.agent_path.write_text('def broken(')
    error = await workspace.refresh()
    assert 'SyntaxError' in error['detail'] and error['version'] != first['version']
    workspace.check_timeout = .3
    workspace.agent_path.write_text('while True: pass')
    timed = await asyncio.wait_for(workspace.refresh(), 3)
    assert '超时' in timed['detail'] and timed['runner'] == 'teaching_chat'


def tool_reply(name, args, call_id):
    return ModelReply({'role': 'assistant', 'content': None, 'tool_calls': [
        {'id': call_id, 'type': 'function', 'function': {'name': name, 'arguments': json.dumps(args)}}]})


async def test_tutor_reads_then_real_student_loop_checks_itself(course, monkeypatch):
    replies = iter([
        tool_reply('list_files', {'path': 'lesson_01_agent'}, 'list'),
        tool_reply('read_course_file', {'path': 'lesson_01_agent/agent.py'}, 'read'),
        ModelReply({'role': 'assistant', 'content': '把这个函数粘贴回 agent.py。'}),
        tool_reply('check_agent', {}, 'self-check'),
        ModelReply({'role': 'assistant', 'content': '自己的循环检查通过。'}),
        ModelReply({'role': 'assistant', 'content': '我们来修复语法错误。'}),
    ])
    requests = []
    async def complete(messages, tools, config):
        requests.append((list(messages), {t.name for t in tools}))
        return next(replies)
    monkeypatch.setattr('common.core.llm.complete', complete)
    app = create_app('exercise', Config(lesson=1, api_key='test-secret'), root=course/'runs', lesson_root=course)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url='http://127.0.0.1') as client:
            boot = (await client.get('/api/bootstrap')).json()
            client.headers['X-Comma-Token'] = boot['csrf_token']
            assert not boot['learning']['ready']
            sid = (await client.post('/api/sessions', json={})).json()['id']
            async def turn(text):
                assert (await client.post(f'/api/sessions/{sid}/messages', json={'text': text})).status_code == 202
                await asyncio.wait_for(app.state.service.get(sid).task, 10)
                return (await client.get(f'/api/sessions/{sid}')).json()
            first = await turn('请列文件、读代码')
            assert first['status'] == 'completed' and first['runner'] == 'teaching_chat'
            assert requests[0][1] == {'list_files', 'read_course_file', 'check_agent'}
            assert first['trace']['calls'] == 2
            # Five filled helpers must still leave the actual run_turn as student work.
            import ast
            completed_source = (ROOT/'lesson_02_computer_use/agent.py').read_text()
            original_source = (course/'lesson_01_agent/agent.py').read_text()
            helpers = [node for node in ast.parse(completed_source).body
                       if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                       and node.name not in {'run_turn', 'image_messages'}]
            helper_code = '\n\n'.join(ast.get_source_segment(completed_source, node) for node in helpers)
            (course/'lesson_01_agent/agent.py').write_text(original_source + '\n' + helper_code)
            partial = (await client.post('/api/learning/check', json={})).json()
            assert partial['passed'] == 5 and partial['total'] == 6
            assert not partial['ready'] and partial['runner'] == 'teaching_chat'
            assert 'TODO 1.6' in partial['detail']
            source = completed_source
            source += '\n_original_run = run_turn\nasync def run_turn(text, state, context):\n    context.emit(Event("status", {"text": "STUDENT_SOURCE_EXECUTED"}))\n    await _original_run(text, state, context)\n'
            (course/'lesson_01_agent/agent.py').write_text(source)
            check = (await client.post('/api/learning/check', json={})).json()
            assert check['ready'] and check['passed'] == 6
            second = await turn('请检查你自己')
            assert second['status'] == 'completed' and second['runner'] == 'student'
            assert second['source_version'] == check['version'] != first['source_version']
            record = (await client.get(f"/api/runs/{second['run_id']}/export")).json()
            assert any(e['data'].get('text') == 'STUDENT_SOURCE_EXECUTED' for e in record['events'])
            check_result = next(e['data']['result']['text'] for e in record['events'] if e['kind'] == 'tool_end')
            assert json.loads(check_result)['ready']
            assert len([m for m in requests[3][0] if m['role'] == 'user']) == 2
            (course/'lesson_01_agent/agent.py').write_text('def broken(')
            third = await turn('帮我修复')
            assert third['runner'] == 'teaching_chat' and third['status'] == 'completed'
            assert 'SyntaxError' in third['learning']['detail']
