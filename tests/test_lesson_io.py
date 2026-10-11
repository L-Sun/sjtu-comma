"""Provided IO keeps images and trace correct without owning the student loop."""
from copy import deepcopy
import json

from common.core.lesson_io import lesson_io
from common.core.types import AgentState, Image, ModelReply, ToolResult
from lesson_01_agent import check
from lesson_02_computer_use import agent


async def test_provided_io_never_advances_or_fills_in_a_loop():
    calls = []
    async def unexpected(*args):
        calls.append(args)
        raise AssertionError('IO must not call anything on its own')
    messages, events = [], []
    context = check.context_for(unexpected, unexpected, events)
    with lesson_io(context, messages, agent.parse_tool_arguments, agent.execute_tool):
        pass
    assert calls == messages == events == []


async def test_batch_images_follow_all_tool_results_and_events_include_errors():
    batch = [check.tool_call('bad JSON'), check.tool_call(), check.tool_call()]
    for i, call in enumerate(batch):
        call['id'] = f'call-{i}'
    snapshots, executed, events = [], [], []
    async def model(messages, tools, config):
        snapshots.append(deepcopy(messages))
        if len(snapshots) == 1:
            return ModelReply({'role': 'assistant', 'content': '开始', 'tool_calls': batch}, {'total_tokens': 7})
        return ModelReply({'role': 'assistant', 'content': '完成'})
    async def tool(name, arguments):
        executed.append(name)
        return ToolResult(f'image {len(executed)}', [Image(f'base64-{len(executed)}')])
    state = AgentState()
    await agent.run_turn('看两个结果', state, check.context_for(model, tool, events))
    assert len(executed) == len(snapshots) == 2
    assert [m['role'] for m in snapshots[1]] == ['system', 'user', 'assistant', 'tool', 'tool', 'tool', 'user', 'user']
    assert json.loads(snapshots[1][3]['content'])['is_error']
    assert [m['tool_call_id'] for m in snapshots[1][3:6]] == ['call-0', 'call-1', 'call-2']
    images = snapshots[1][6:]
    assert 'call-1' in images[0]['content'][0]['text'] and 'call-2' in images[1]['content'][0]['text']
    assert images[1]['content'][1]['image_url']['url'].endswith('base64-2')
    tool_events = [e for e in events if e.kind.startswith('tool_')]
    assert [(e.kind, e.data['id']) for e in tool_events] == [
        (kind, f'call-{i}') for i in range(3) for kind in ['tool_start', 'tool_end']]
    assert tool_events[1].data['result'].is_error
    assert len([e for e in events if e.kind == 'usage']) == 2
    assert [e.data['text'] for e in events if e.kind == 'assistant'] == ['开始', '完成']
    assert not any(e.data.get('limit') for e in events)


async def test_loop_check_reports_all_independent_failures_together():
    class EmptyLoop:
        async def run_turn(self, text, state, context):
            return
    try:
        await check.check_loop(EmptyLoop())
    except AssertionError as exc:
        assert all(title in str(exc) for title in ['工具往返', '批量工具', '轮数上限', '停止'])
    else:
        raise AssertionError('An empty loop must not pass')
