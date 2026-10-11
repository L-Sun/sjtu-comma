"""Verify that helper functions alone cannot unlock the student-owned loop."""
import asyncio
import json
from types import FunctionType

import pytest

from common.core.config import Config
from common.core.types import AgentState, ExercisePending, ModelReply, RunContext, ToolResult
from lesson_01_agent import agent as student, check
from lesson_02_computer_use import agent as completed
from common.core.student_loader import load_student_agent
from pathlib import Path
from tests.student_source import unfinished

HELPERS = ['add_user_message', 'remember_assistant_message',
           'parse_tool_arguments', 'execute_tool', 'make_tool_message']


@pytest.fixture(autouse=True)
def reset_test_exercises(monkeypatch):
    path = Path(student.__file__)
    template = load_student_agent(unfinished(path.read_text()), path)
    for name in [*HELPERS, 'run_turn']:
        monkeypatch.setattr(student, name, getattr(template, name))


def fill(monkeypatch, count):
    for name in HELPERS[:count]:
        monkeypatch.setattr(student, name, getattr(completed, name))


async def test_first_two_helpers_still_need_student_loop(monkeypatch):
    fill(monkeypatch, 2)
    with pytest.raises(ExercisePending, match="TODO 1.6"):
        await check.check_chat(student)
    with pytest.raises(ExercisePending, match='TODO 1.3'):
        student.parse_tool_arguments(check.tool_call())


async def test_five_helpers_do_not_unlock_unwritten_loop(monkeypatch):
    fill(monkeypatch, 5)
    progress = await check.inspect_checks(student)
    assert progress['passed'] == 5 and progress['total'] == 6 and not progress['ready']
    assert next(row for row in progress['checks'] if row['id'] == 'loop')['status'] == 'pending'


def fill_loop(monkeypatch):
    # Use the completed control flow with the student's globals, to exercise its helper calls.
    monkeypatch.setattr(student, 'run_turn', FunctionType(completed.run_turn.__code__, student.__dict__))


async def test_helpers_and_student_loop_pass_all_checks(monkeypatch):
    fill(monkeypatch, 5)
    fill_loop(monkeypatch)
    await check.run_checks(student)
    progress = await check.inspect_checks(student)
    assert progress['ready'] and progress['passed'] == progress['total'] == 6


@pytest.mark.parametrize('filled, missing', [(2, '1.3'), (3, '1.4'), (4, '1.5')])
async def test_unfinished_tool_step_stops_instead_of_retrying_model(monkeypatch, filled, missing):
    fill(monkeypatch, filled)
    fill_loop(monkeypatch)
    requests = []
    async def model(messages, tools, config):
        requests.append(True)
        return ModelReply({'role': 'assistant', 'content': None, 'tool_calls': [check.tool_call()]})
    async def tool(name, args):
        return ToolResult('42')
    with pytest.raises(ExercisePending, match='TODO ' + missing):
        await student.run_turn('calculate', AgentState(), check.context_for(model, tool))
    assert len(requests) == 1


async def test_completed_student_loop_returns_failure_and_propagates_stop(monkeypatch):
    fill(monkeypatch, 5)
    fill_loop(monkeypatch)
    requests = []
    async def model(messages, tools, config):
        requests.append(True)
        if len(requests) == 1:
            return ModelReply({'role': 'assistant', 'content': None, 'tool_calls': [check.tool_call()]})
        assert json.loads(messages[-1]['content']) == {'is_error': True, 'text': 'tool unavailable'}
        return ModelReply({'role': 'assistant', 'content': '工具暂不可用'})
    async def fail(name, args):
        raise RuntimeError('tool unavailable')
    context = RunContext(Config(lesson=1), [], model, fail, lambda event: None, 'system')
    await student.run_turn('calculate', AgentState(), context)
    assert len(requests) == 2

    requests.clear()
    async def stop(name, args):
        raise asyncio.CancelledError()
    context.execute = stop
    with pytest.raises(asyncio.CancelledError):
        await student.run_turn('calculate', AgentState(), context)
    assert len(requests) == 1


@pytest.mark.parametrize('before, after', [
    ('if not reply.tool_calls:', 'if reply.text:'),
    ('messages.append(make_tool_message(call["id"], result))', 'pass'),
    ('range(context.config.max_rounds)', 'range(context.config.max_rounds + 1)'),
])
async def test_loop_checks_reject_common_control_flow_mistakes(before, after):
    from pathlib import Path
    from common.core.student_loader import load_student_agent
    path = Path(completed.__file__)
    source = path.read_text()
    assert before in source
    module = load_student_agent(source.replace(before, after), path)
    progress = await check.inspect_checks(module)
    assert not progress['ready'] and progress['passed'] == 5
    assert next(row for row in progress['checks'] if row['id'] == 'loop')['status'] == 'failed'
