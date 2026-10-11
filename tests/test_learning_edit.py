"""Student Edit wiring, actual file edits, and the tutor-to-student transition."""
import ast
import asyncio
import json

import httpx
import pytest

from common.app.server import create_app
from common.core.config import ROOT, Config
from common.core.course_editor import CourseEditor, version
from common.core.learning_workspace import LearningWorkspace
from common.core.types import ModelReply
from tests.test_learning_chat import course, tool_reply


# Test-only student solution; never copied into the actual course workspace.
CONNECTED = '''from common.core.course_editor import EDIT_PARAMETERS
from common.core.types import ToolSpec, ToolResult
calls = []
def get_tools():
    return [ToolSpec('edit_course_file', '先读取文件，再编辑第一课作业。', EDIT_PARAMETERS)]
async def call_tool(name, arguments, editor):
    calls.append(name)
    if name == 'edit_course_file':
        return await editor.execute(arguments)
    return ToolResult('未知工具', is_error=True)
'''
TARGET = 'lesson_01_agent/agent.py'


def edit_args(source, old, new):
    return {'path': TARGET, 'base_version': version(source),
            'edits': [{'old_text': old, 'new_text': new}]}


async def test_editor_preserves_bytes_and_creates_recoverable_backup(course):
    path = course / TARGET
    before = 'value = 1\r\nother = 2\r\n'
    path.write_bytes(before.encode())
    path.chmod(0o640)
    result = await CourseEditor(course).execute(edit_args(before, 'value = 1', 'value = 42'))
    data = json.loads(result.text)
    assert not result.is_error and data['saved']
    after = before.replace('value = 1', 'value = 42')
    assert path.read_bytes() == after.encode()
    assert (course / data['backup']).read_bytes() == before.encode()
    assert path.stat().st_mode & 0o777 == 0o640
    assert data['version'] == version(after) and '-value = 1' in data['diff']
    assert not list(path.parent.glob('.course-edit-*'))
    stale = await CourseEditor(course).execute(edit_args(before, 'other = 2', 'other = 3'))
    assert stale.is_error and '版本冲突' in stale.text
    assert path.read_bytes() == after.encode()


@pytest.mark.parametrize('kind', ['outside', 'missing', 'ambiguous', 'overlap', 'syntax', 'symlink', 'parent_link', 'backup_link'])
async def test_rejected_edits_leave_all_original_bytes(course, kind):
    path = course / TARGET
    before = 'value = 1\nother = 1\n'
    path.write_text(before)
    args = edit_args(before, 'value = 1', 'value = 42')
    if kind == 'outside':
        args['path'] = '.env'
    elif kind == 'missing':
        args['edits'].append({'old_text': 'missing', 'new_text': 'new'})
    elif kind == 'ambiguous':
        args['edits'][0]['old_text'] = '1'
    elif kind == 'overlap':
        args['edits'].append({'old_text': 'value', 'new_text': 'new'})
    elif kind == 'syntax':
        args['edits'][0]['new_text'] = 'def broken('
    elif kind == 'symlink':
        path.unlink()
        path.symlink_to(course / '.env')
    elif kind == 'parent_link':
        path.parent.rename(course / 'real_lesson')
        path.parent.symlink_to(course / 'real_lesson', target_is_directory=True)
    elif kind == 'backup_link':
        (course / '.course-edits').symlink_to(course / 'common', target_is_directory=True)
    original = path.read_bytes()
    result = await CourseEditor(course).execute(args)
    assert result.is_error
    assert path.read_bytes() == original
    assert (course / '.env').read_text() == 'SECRET=never-read'


async def test_only_valid_student_wiring_exposes_edit_and_runs_student_dispatch(course):
    workspace = LearningWorkspace(course)
    initial = await workspace.refresh()
    assert initial['edit']['passed'] == 0 and initial['edit']['total'] == 2
    assert 'edit_course_file' not in {tool.name for tool in workspace.tools()}
    assert (await workspace.execute('edit_course_file', {})).is_error
    path = course / 'lesson_01_agent/tools.py'
    path.write_text(CONNECTED)
    connected = await workspace.refresh()
    assert connected['edit']['ready'] and connected['passed'] == 0
    assert 'edit_course_file' in {tool.name for tool in workspace.tools()}
    module = workspace.edit.module
    await workspace.refresh()
    assert workspace.edit.module is module
    read = json.loads((await workspace.execute('read_course_file', {'path': TARGET})).text)
    source = (course / TARGET).read_text()
    args = edit_args(source, 'import json', 'import json  # edited through student dispatch')
    assert args['base_version'] == read['version']
    result = await workspace.execute('edit_course_file', args)
    assert not result.is_error and module.calls == ['edit_course_file']
    assert '# edited through student dispatch' in (course / TARGET).read_text()
    path.write_text('def broken(')
    broken = await workspace.refresh()
    assert not broken['edit']['ready'] and 'SyntaxError' in broken['edit']['detail']
    assert 'edit_course_file' not in {tool.name for tool in workspace.tools()}


@pytest.mark.parametrize('old,new', [
    ("ToolSpec('edit_course_file'", "ToolSpec('wrong_name'"),
    ('return await editor.execute(arguments)', "return ToolResult('pretend success')"),
    ("return ToolResult('未知工具', is_error=True)", 'return await editor.execute(arguments)'),
])
async def test_incorrect_registration_or_dispatch_cannot_enable_edit(course, old, new):
    (course / 'lesson_01_agent/tools.py').write_text(CONNECTED.replace(old, new))
    workspace = LearningWorkspace(course)
    status = await workspace.refresh()
    assert not status['edit']['ready'] and status['edit']['passed'] == 1
    assert 'edit_course_file' not in {tool.name for tool in workspace.tools()}


async def test_chat_uses_connected_edit_to_complete_loop_then_student_takes_over(course, monkeypatch):
    original = (course / TARGET).read_text()
    solution = (ROOT / 'lesson_02_computer_use/agent.py').read_text()
    solution += '\n_original = run_turn\nasync def run_turn(text, state, context):\n    context.emit(Event("status", {"text": "EDIT_BUILT_THIS_LOOP"}))\n    await _original(text, state, context)\n'
    helper = next(node for node in ast.parse(solution).body if isinstance(node, ast.FunctionDef) and node.name == 'add_user_message')
    first_helper = ast.get_source_segment(solution, helper)
    partial = original + '\n' + first_helper + '\n'
    requests = []
    step = 0
    async def complete(messages, tools, config):
        nonlocal step
        step += 1
        requests.append({t.name for t in tools})
        if step == 1:
            return ModelReply({'role': 'assistant', 'content': '先一起接入 tools.py。'})
        if step in (2, 6):
            return tool_reply('read_course_file', {'path': TARGET}, f'read-{step}')
        if step in (3, 7):
            data = json.loads(json.loads(messages[-1]['content'])['text'])
            before, after = (original, partial) if step == 3 else (partial, solution)
            args = edit_args(before, before, after)
            args['base_version'] = data['version']
            return tool_reply('edit_course_file', args, f'edit-{step}')
        if step in (4, 8, 10):
            return tool_reply('check_agent', {}, f'check-{step}')
        assert step in (5, 9, 11)
        return ModelReply({'role': 'assistant', 'content': '已按实际检查结果完成本步。'})
    monkeypatch.setattr('common.core.llm.complete', complete)
    app = create_app('exercise', Config(lesson=1, api_key='fake'), root=course / 'runs', lesson_root=course)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url='http://127.0.0.1') as client:
            boot = (await client.get('/api/bootstrap')).json()
            client.headers['X-Comma-Token'] = boot['csrf_token']
            sid = (await client.post('/api/sessions', json={})).json()['id']
            async def turn(text):
                assert (await client.post(f'/api/sessions/{sid}/messages', json={'text': text})).status_code == 202
                await asyncio.wait_for(app.state.service.get(sid).task, 15)
                session = (await client.get(f'/api/sessions/{sid}')).json()
                assert session['status'] == 'completed'
                record = (await client.get(f"/api/runs/{session['run_id']}/export")).json()
                return session, record
            initial, _ = await turn('先一起接入 Edit')
            assert initial['runner'] == 'teaching_chat' and 'edit_course_file' not in requests[0]
            # The student's sole manual bootstrap step happens in this temporary course.
            (course / 'lesson_01_agent/tools.py').write_text(CONNECTED)
            first, first_record = await turn('使用我们接好的 Edit，完成第一个辅助函数')
            assert first['runner'] == 'teaching_chat' and 'edit_course_file' in requests[1]
            assert (course / TARGET).read_text() == partial
            first_results = [json.loads(e['data']['result']['text']) for e in first_record['events'] if e['kind'] == 'tool_end']
            assert first_results[1]['saved'] and first_results[1]['diff']
            assert first_results[2]['passed'] == 1 and first_results[2]['edit']['ready']
            last, _ = await turn('按讨论结果完成其余函数与 Loop')
            assert last['runner'] == 'teaching_chat'  # no switch halfway through a turn
            assert (course / TARGET).read_text() == solution
            ready = (await client.post('/api/learning/check', json={})).json()
            assert ready['ready'] and ready['passed'] == 7 and ready['edit']['ready']
            student, record = await turn('由刚写好的 Loop 检查自己')
            assert student['runner'] == 'student' and student['source_version'] == ready['version']
            assert 'edit_course_file' in requests[9]
            assert any(e['data'].get('text') == 'EDIT_BUILT_THIS_LOOP' for e in record['events'])
            assert len(list((course / '.course-edits').glob('*.py'))) == 2
