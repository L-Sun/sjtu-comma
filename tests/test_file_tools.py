import json
import os
import stat
from contextlib import asynccontextmanager

import pytest
from jsonschema import validate

from common.app.runtime import Runtime
from common.core.config import Config
from common.core.edit_tools import FileEditor, version
from common.core.types import ModelReply
from lesson_02_computer_use import tools


async def test_general_editor_handles_relative_and_absolute_text_paths(tmp_path):
    editor = FileEditor(tmp_path)
    for relative in ['notes.md', 'nested/settings.json', 'script.py', 'plain-text']:
        path = tmp_path / relative
        path.parent.mkdir(exist_ok=True)
        path.write_bytes('原文\r\n保留\r\n'.encode())
        path.chmod(0o754)
        read = json.loads((await tools.call_tool('read_file', {'path': relative}, editor)).text)
        assert read['content'] == '1: 原文\n2: 保留'
        assert read['next_start_line'] is None
        args = {'path': str(path), 'base_version': read['version'],
                'edits': [{'old_text': '原文', 'new_text': '修改'}]}
        validate(args, next(t.parameters for t in tools.get_tools(editor) if t.name == 'edit'))
        result = await tools.call_tool('edit', args, editor)
        assert not result.is_error
        assert path.read_bytes() == '修改\r\n保留\r\n'.encode()
        assert json.loads(result.text)['version'] == version('修改\r\n保留\r\n')
        if os.name != 'nt':
            assert stat.S_IMODE(path.stat().st_mode) == 0o754
        assert (await tools.call_tool('edit', args, editor)).is_error
    assert (await tools.call_tool('unknown', {}, editor)).is_error


async def test_general_editor_rejects_invalid_batch_and_nontext_files(tmp_path):
    editor = FileEditor(tmp_path)
    path = tmp_path / 'notes.txt'
    path.write_text('one\ntwo\none\n')
    original = path.read_bytes()
    for bad in [
        {'old_text': 'missing', 'new_text': 'x'},
        {'old_text': 'one', 'new_text': 'x'},
        {'old_text': 'two\none', 'new_text': 'x'},
    ]:
        result = await editor.execute('edit', {'path': 'notes.txt',
            'base_version': version(original.decode()),
            'edits': [{'old_text': 'two', 'new_text': 'changed'}, bad]})
        assert result.is_error and path.read_bytes() == original
    for value in [b'\xff', b'a\x00b', b'x' * (2 * 1024 * 1024 + 1)]:
        path.write_bytes(value)
        assert (await editor.execute('read_file', {'path': 'notes.txt'})).is_error
    assert (await editor.execute('read_file', {'path': 'missing'})).is_error
    assert (await editor.execute('read_file', {'path': '.'})).is_error
    path.write_bytes(b'')
    assert json.loads((await editor.execute('read_file', {'path': 'notes.txt'})).text)['total_lines'] == 0


async def test_general_editor_read_and_search_pagination(tmp_path):
    (tmp_path / 'log.txt').write_text(''.join(f'entry {i}\n' for i in range(200)))
    editor = FileEditor(tmp_path)
    first = json.loads((await editor.execute('read_file', {'path': 'log.txt'})).text)
    assert first['next_start_line'] == 121
    second = json.loads((await editor.execute('read_file', {'path': 'log.txt', 'start_line': 121})).text)
    assert second['content'].endswith('200: entry 199') and second['next_start_line'] is None
    first = json.loads((await editor.execute('search_file', {'path': 'log.txt', 'query': 'entry'})).text)
    second = json.loads((await editor.execute('search_file', {'path': 'log.txt', 'query': 'entry',
                                        'after_line': first['next_after_line']})).text)
    assert first['has_more'] and first['matches'][-1]['line'] < second['matches'][0]['line']


async def test_lesson_two_free_chat_edits_files_when_cua_unavailable(tmp_path, monkeypatch):
    @asynccontextmanager
    async def unavailable(command):
        raise RuntimeError('driver unavailable')
        yield

    monkeypatch.setattr('common.app.runtime.connect_driver', unavailable)
    path = tmp_path / 'user-notes.md'
    path.write_text('before\n')
    rounds = []

    async def complete(messages, available, config):
        names = {tool.name for tool in available}
        assert {'read_file', 'edit', 'search_file', 'bash', 'calculate', 'get_current_time'} <= names
        rounds.append(True)
        if len(rounds) == 1:
            name, args = 'read_file', {'path': str(path)}
        elif len(rounds) == 2:
            read = json.loads(json.loads(messages[-1]['content'])['text'])
            name, args = 'edit', {'path': str(path), 'base_version': read['version'],
                                 'edits': [{'old_text': 'before', 'new_text': 'after'}]}
        else:
            assert json.loads(json.loads(messages[-1]['content'])['text'])['saved']
            return ModelReply({'role': 'assistant', 'content': '已修改'})
        return ModelReply({'role': 'assistant', 'content': None, 'tool_calls': [{
            'id': str(len(rounds)), 'type': 'function',
            'function': {'name': name, 'arguments': json.dumps(args)}}]})

    monkeypatch.setattr('common.core.llm.complete', complete)
    runtime = Runtime(lesson=2, root=tmp_path / 'runs')
    await runtime.run('修改文件', Config(lesson=2), lambda event: None)
    assert runtime.last_record.data['status'] == 'completed'
    assert len(rounds) == 3 and path.read_text() == 'after\n'
    assert runtime.edit_path is None
