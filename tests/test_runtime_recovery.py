"""Runtime failures are diagnosed without losing history or retrying side effects."""
from contextlib import asynccontextmanager
from copy import deepcopy
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from common.app.runtime import Runtime
from common.core.config import Config
from common.core.records import Record
from common.core.runtime_diagnostics import PREFIX
from common.core.student_loader import load_student_agent
from common.core.types import Event, ModelReply, ToolResult
from lesson_01_agent import check
from lesson_02_computer_use import agent as reference
from tests.test_learning_chat import course, tool_reply
from tests.test_scaffold import client_for, create, finish


@pytest.mark.parametrize('old,new,missing', [
    ('"id": call["id"], "name": name,\n                                               "arguments":',
     '"call_id": call["id"], "tool_name": name,\n                                               "tool_args":', 'id, name, arguments'),
    ('"name": name, "result": result', '"name": name', 'result'),
])
async def test_lesson_checker_rejects_events_that_used_to_crash_ui(old, new, missing):
    path = Path(reference.__file__)
    source = path.read_text()
    assert old in source
    module = load_student_agent(source.replace(old, new), path)
    result = await check.inspect_checks(module)
    loop = next(row for row in result['checks'] if row['id'] == 'loop')
    assert not result['ready'] and result['passed'] == 4
    assert loop['status'] == 'failed' and 'EventContractError' in loop['detail'] and missing in loop['detail']


@pytest.mark.parametrize('after_execution', [False, True])
async def test_runtime_error_rolls_back_incomplete_pairs_and_restores_diagnostics(course, monkeypatch, after_execution):
    snapshots = []
    async def model(messages, tools, config):
        snapshots.append(deepcopy(messages))
        if len(snapshots) == 1:
            return tool_reply('calculate', {'operation': 'multiply', 'a': 6, 'b': 7}, 'call-1')
        assert any(PREFIX in str(m.get('content')) and 'EventContractError' in str(m.get('content')) for m in messages)
        return ModelReply({'role': 'assistant', 'content': '事件格式错误，已看到错误信息'})
    monkeypatch.setattr('common.core.llm.complete', model)
    async def broken(text, state, ctx):
        state.messages.append({'role': 'user', 'content': text})
        reply = await ctx.complete(state.messages, ctx.tools, ctx.config)
        state.messages.append(reply.message)
        if after_execution:
            ctx.emit(Event('tool_start', {'id': 'call-1', 'name': 'calculate', 'arguments': '{}'}))
            await ctx.execute('calculate', {'operation': 'multiply', 'a': 6, 'b': 7})
            ctx.emit(Event('tool_end', {'id': 'call-1', 'name': 'calculate'}))
        else:
            ctx.emit(Event('tool_start', {'call_id': 'call-1', 'tool_name': 'calculate', 'tool_args': '{}'}))
    rt = Runtime(root=course/'runs', lesson=1)
    rt.conversation = {'session_id': 'a'*32, 'session_title': '恢复错误上下文', 'session_created_at': '2026-10-11T00:00:00+00:00'}
    rt.state.messages = [{'role': 'system', 'content': 'system'}, {'role': 'user', 'content': '记住旧历史'},
                         {'role': 'assistant', 'content': '记住了'}]
    before = deepcopy(rt.state.messages)
    rt.module = lambda name: SimpleNamespace(run_turn=broken, complete=model)
    await rt.run('计算一次', Config(lesson=1, api_key='test-secret'), lambda event: None)
    record = rt.last_record.data
    assert record['status'] == 'error' and record['context_recovered'] and len(snapshots) == 1
    assert rt.state.messages[1:3] == before[1:3]
    assert rt.state.messages[3] == {'role': 'user', 'content': '计算一次'}
    assert not any(m.get('tool_calls') or m.get('role') == 'tool' for m in rt.state.messages)
    diagnostic = record['error_context']
    assert len(diagnostic['tool_outcomes']) == int(after_execution)
    if after_execution:
        assert json.loads(diagnostic['tool_outcomes'][0]['text'])['result'] == 42
    async with client_for(course/'runs', fake_io=False, lesson=1, lesson_root=course) as (app, client):
        session = app.state.service.get('a'*32)
        assert session.runtime.state.messages == rt.state.messages
        result = await finish(app, client, session.id, '刚才为什么失败？')
        assert result['status'] == 'completed' and len(snapshots) == 2
        assert sum(PREFIX in str(m.get('content')) for m in snapshots[-1]) == 1
        assert '记住旧历史' in str(snapshots[-1])


async def test_executor_exception_is_returned_as_tool_error_without_crashing():
    from tempfile import TemporaryDirectory
    requests = []
    async def model(messages, tools, config):
        requests.append(deepcopy(messages))
        if len(requests) == 1:
            return tool_reply('calculate', {'operation': 'multiply', 'a': 6, 'b': 7}, 'call-1')
        data = json.loads(messages[-1]['content'])
        assert data['is_error'] and data['text'] == 'RuntimeError: 工具暂不可用'
        return ModelReply({'role': 'assistant', 'content': '收到工具错误'})
    @asynccontextmanager
    async def registry(*args, **kwargs):
        from common.core.basic_tools import basic_tools
        async def execute(*args):
            raise RuntimeError('工具暂不可用')
        yield basic_tools(), execute
    with TemporaryDirectory() as root:
        rt = Runtime(root=Path(root), lesson=1)
        rt.registry = registry
        rt.module = lambda name: SimpleNamespace(run_turn=reference.run_turn, complete=model)
        await rt.run('计算', Config(lesson=1), lambda event: None)
        assert rt.last_record.data['status'] == 'completed' and len(requests) == 2


async def test_old_malformed_event_does_not_break_session_restore_and_next_model_sees_failure(course, monkeypatch):
    config = Config(lesson=1)
    failed = Record(config, 'free', root=course/'runs')
    failed.data.update({'lesson': 1, 'session_id': 'b'*32, 'session_title': '旧会话', 'status': 'error', 'model_messages': []})
    failed.add('user', {'text': '读取文件列表'})
    failed.add('tool_start', {'call_id': 'legacy-call', 'tool_name': 'list_files', 'tool_args': '{}'})
    failed.add('error', {'text': "'name'"})
    failed.save()
    latest = Record(config, 'free', root=course/'runs')
    latest.data.update({'lesson': 1, 'session_id': 'b'*32, 'status': 'completed', 'model_messages': [
        {'role': 'system', 'content': 'system'}, {'role': 'user', 'content': '失败了？'},
        {'role': 'assistant', 'content': '请提供错误信息'}]})
    latest.add('user', {'text': '失败了？'})
    latest.add('assistant', {'text': '请提供错误信息'})
    latest.save()
    async def model(messages, tools, config):
        assert any(PREFIX in str(m.get('content')) and 'tool_name' in str(m.get('content')) for m in messages)
        return ModelReply({'role': 'assistant', 'content': '现在能看到之前的事件格式错误'})
    monkeypatch.setattr('common.core.llm.complete', model)
    async with client_for(course/'runs', fake_io=False, lesson=1, lesson_root=course) as (app, client):
        result = await finish(app, client, 'b'*32, '现在可以诊断了吗？')
        assert result['status'] == 'completed' and '能看到' in result['messages'][-1]['text']
