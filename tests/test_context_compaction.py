import asyncio
from contextlib import asynccontextmanager

import pytest

from common.app.trace import TraceState, replay_trace
from common.core.config import ROOT
from common.core.event_contract import validate_event
from common.core.lesson_io import context_compaction
from common.core.types import ModelReply, ToolResult, ToolSpec
from lesson_01_agent import agent, check
from tests.test_learning_chat import course
from tests.test_scaffold import client_for


async def test_empty_student_compaction_keeps_history_without_model_or_tool_calls():
    messages = [{'role': 'system', 'content': '课程'}, {'role': 'user', 'content': '问题'}]
    original = list(messages)
    events = []
    async def unexpected(*args):
        raise AssertionError('The empty extension must not request a model or tool')
    await agent.compact_history(messages, check.context_for(unexpected, unexpected, events))
    assert messages == original
    assert [event.data['context_compaction'] for event in events] == ['running', 'completed']


@pytest.mark.parametrize('failure, expected', [(ValueError('bad summary'), 'error'), (asyncio.CancelledError(), 'stopped')])
async def test_compaction_failure_and_cancellation_propagate(failure, expected):
    trace, events = TraceState(), []
    def emit(event):
        validate_event(event)
        trace.feed(event)
        events.append(event)
    context = check.context_for()
    context.emit = emit
    @context_compaction
    async def compress(messages, context):
        raise failure
    with pytest.raises(type(failure)):
        await compress([], context)
    assert len(trace.steps) == 1 and trace.steps[0].status == expected
    assert not trace.pending and trace.compaction_step is None
    assert trace.call_count == 0
    assert all(event.data['context_compaction'] != 'completed' for event in events)


async def test_pending_compaction_is_visible_over_http_before_model_request(course, monkeypatch):
    source = (ROOT / 'lesson_02_computer_use/agent.py').read_text()
    source = source.replace('from common.core.lesson_io import lesson_io',
                            'from common.core.lesson_io import context_compaction, lesson_io')
    source = source.replace('    with lesson_io(', '    await compact_history(messages, context)\n    with lesson_io(')
    source += '''\n@context_compaction
async def compact_history(messages, context):
    if any(tool.name == "test_hold" for tool in context.tools):
        await context.execute("test_hold", {})
'''
    (course / 'lesson_01_agent/agent.py').write_text(source)
    entered, release = asyncio.Event(), asyncio.Event()
    model_requests = []
    @asynccontextmanager
    async def registry(self, config, editor=None, report=None, *, teaching=False):
        async def execute(name, arguments):
            entered.set()
            await release.wait()
            return ToolResult('ready')
        yield [ToolSpec('test_hold', 'hold for test', {'type': 'object'})], execute
    async def complete(messages, tools, config):
        model_requests.append(messages)
        return ModelReply({'role': 'assistant', 'content': '完成'})
    monkeypatch.setattr('common.app.runtime.Runtime.registry', registry)
    monkeypatch.setattr('common.core.llm.complete', complete)
    async with client_for(course / 'runs', lesson=1, lesson_root=course, fake_io=False) as (app, client):
        # The deterministic course checker uses its own executor and does not wait on our gate.
        sid = (await client.post('/api/sessions', json={})).json()['id']
        started = await client.post(f'/api/sessions/{sid}/messages', json={'text': '检查进度'})
        assert started.status_code == 202
        try:
            await asyncio.wait_for(entered.wait(), 2)
            pending = (await client.get(f'/api/sessions/{sid}')).json()
            assert pending['busy'] and pending['trace']['current'] == '正在上下文压缩'
            assert pending['trace']['steps'][-1]['title'] == '正在上下文压缩'
            assert pending['trace']['steps'][-1]['status'] == 'running'
            assert not model_requests and pending['trace']['calls'] == 0
        finally:
            release.set()
        await asyncio.wait_for(app.state.service.get(sid).task, 2)
        done = (await client.get(f'/api/sessions/{sid}')).json()
        assert done['status'] == 'completed' and len(model_requests) == 1
        step = next(step for step in done['trace']['steps'] if step['title'] == '上下文压缩调用结束')
        assert step['status'] == 'done' and step['duration'] is not None
        record = (await client.get(f"/api/runs/{done['run_id']}/export")).json()
        restored = replay_trace(record)
        assert any(step.title == '上下文压缩调用结束' and step.status == 'done' for step in restored.steps)


def test_interrupted_trace_does_not_leave_compaction_running():
    from common.core.types import Event
    state = TraceState()
    state.feed(Event('status', {'text': '正在上下文压缩', 'context_compaction': 'running'}))
    state.finish({'status': 'timeout'})
    assert state.steps[0].status == 'stopped'
    assert state.compaction_step is None
