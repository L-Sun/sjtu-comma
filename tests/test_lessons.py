from pathlib import Path
import pytest

from common.app.runtime import Runtime
from common.core.config import ROOT
from common.core.types import ExercisePending
from lesson_03_computer_use import cua


def test_progressive_modules_are_local_to_each_lesson():
    for lesson, package, modules in [
        (1, 'lesson_01_llm', ['llm']),
        (2, 'lesson_02_agent', ['llm', 'agent']),
        (3, 'lesson_03_computer_use', ['llm', 'agent', 'cua']),
    ]:
        runtime = Runtime(lesson=lesson)
        for module in modules:
            assert runtime.module(module).__name__ == f'{package}.{module}'
        assert (ROOT / package / 'README.md').is_file()
    assert (ROOT / 'lesson_02_agent/llm.py').read_bytes() == (ROOT / 'lesson_03_computer_use/llm.py').read_bytes()
    assert (ROOT / 'common/core/fixtures/course_page.py').read_text().count('\n') == 5000
    assert not (ROOT / 'instructor').exists()
    assert not (ROOT / 'app/tui.py').exists()


async def test_current_computer_lesson_retains_exercise():
    with pytest.raises(ExercisePending, match='TODO 3a'):
        await cua.list_tools(None)
    with pytest.raises(ExercisePending, match='TODO 3b'):
        await cua.call_tool(None, 'list_windows', {})


async def test_capabilities_accumulate_without_a_mode_switch(monkeypatch, tmp_path):
    from contextlib import asynccontextmanager
    from types import SimpleNamespace
    from common.core.config import Config
    from common.core.types import ToolSpec
    from common.core.edit_tools import EditWorkspace
    from tests.test_policy import observation
    calls = []

    @asynccontextmanager
    async def driver(command):
        yield object()

    async def list_tools(session):
        return [ToolSpec('get_window_state', '', {'type': 'object', 'properties': {}})]

    async def call_tool(session, name, args):
        calls.append((name, args))
        return observation()

    monkeypatch.setattr('common.app.runtime.connect_driver', driver)
    editor = EditWorkspace(tmp_path / 'code')
    for lesson in [1, 2, 3]:
        runtime = Runtime(lesson=lesson)
        runtime.module = lambda _: SimpleNamespace(list_tools=list_tools, call_tool=call_tool)
        async with runtime.registry(Config(lesson=lesson), editor) as (tools, execute):
            names = {tool.name for tool in tools}
            if lesson == 1:
                assert not names
            else:
                assert {'calculate', 'bash', 'search_file', 'read_file', 'edit'} <= names
                assert not (await execute('calculate', {'operation': 'add', 'a': 2, 'b': 3})).is_error
            assert ('get_window_state' in names) == (lesson == 3)
            if lesson == 3:
                result = await execute('get_window_state', {'pid': 1, 'window_id': 2})
                assert result.images and 'TREE_SECRET' not in result.text
    assert len(calls) == 1 and calls[0][1]['include_accessibility_tree'] is False


async def test_unfinished_cua_keeps_previous_lesson_tools(monkeypatch):
    from contextlib import asynccontextmanager
    from common.core.config import Config
    from common.app.trace import TraceState
    closed = []

    @asynccontextmanager
    async def driver(command):
        try:
            yield object()
        finally:
            closed.append(True)

    monkeypatch.setattr('common.app.runtime.connect_driver', driver)
    trace = TraceState()
    async with Runtime(lesson=3).registry(Config(), report=trace.feed) as (tools, execute):
        assert closed  # Release the unused driver before running the model.
        assert 'bash' in {tool.name for tool in tools}
        assert not (await execute('calculate', {'operation': 'multiply', 'a': 6, 'b': 7})).is_error
    assert trace.steps[-1].status == 'warning'
    assert 'TODO 3a' in trace.steps[-1].detail
