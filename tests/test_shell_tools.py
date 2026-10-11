import asyncio
import base64
import json
from pathlib import Path
import shlex
import sys
from types import SimpleNamespace

import pytest

from common.app.runtime import Runtime
from common.app.trace import result_summary
from common.core.config import Config
from common.core.shell_tools import OUTPUT_LIMIT, Shell, ShellRunner, child_environment, select_shell
from common.core.types import ModelReply
from lesson_02_computer_use import agent


def python_command(source):
    if sys.platform == 'win32':
        quote = lambda s: "'" + s.replace("'", "''") + "'"
        return '& ' + quote(sys.executable) + ' -c ' + quote(source)
    return shlex.quote(sys.executable) + ' -c ' + shlex.quote(source)


@pytest.mark.parametrize('platform,name', [('darwin', 'zsh'), ('linux', 'bash'), ('win32', 'PowerShell')])
def test_platform_shell_and_argv(monkeypatch, platform, name):
    monkeypatch.setattr('common.core.shell_tools.shutil.which', lambda name: '/test/' + name)
    shell = select_shell(platform)
    assert shell.name == name
    command = 'echo "中文"'
    argv = shell.argv(command)
    if name == 'PowerShell':
        assert shell.executable == '/test/pwsh'
        assert '-NonInteractive' in argv and '-NoProfile' in argv
        script = base64.b64decode(argv[-1]).decode('utf-16-le')
        assert command in script and 'UTF8Encoding' in script and 'exit $LASTEXITCODE' in script
    else:
        assert argv[-2:] == ['-c', command]
        assert ('-f' in argv) if name == 'zsh' else ('--norc' in argv)
    spec = ShellRunner(Path.cwd(), shell).tool()
    assert name in spec.description and spec.name == 'bash'


def test_powershell_fallback_and_missing(monkeypatch):
    monkeypatch.setattr('common.core.shell_tools.shutil.which', lambda name: 'powershell.exe' if name == 'powershell' else None)
    assert select_shell('win32').executable == 'powershell.exe'
    with pytest.raises(FileNotFoundError):
        Shell('Linux', 'bash', None).argv('pwd')


def test_child_env_excludes_api_keys(monkeypatch):
    monkeypatch.setenv('OPENROUTER_API_KEY', 'must-not-inherit')
    monkeypatch.setenv('OTHER_API_SECRET', 'also-secret')
    env = child_environment()
    assert 'OPENROUTER_API_KEY' not in env and 'OTHER_API_SECRET' not in env
    assert 'PATH' in env and env['PYTHONIOENCODING'] == 'utf-8'


async def test_native_shell_utf8_streams_exit_and_cwd(tmp_path):
    folder = tmp_path / 'space 中文'
    folder.mkdir()
    runner = ShellRunner(tmp_path)
    result = await runner.execute({'command': python_command(
        "import os,sys; print('你好'); print(os.getcwd()); print('failure detail',file=sys.stderr); sys.exit(7)"),
        'cwd': folder.name})
    data = json.loads(result.text)
    assert result.is_error and data['exit_code'] == 7
    assert '你好' in data['stdout'] and str(folder) in data['stdout']
    assert 'failure detail' in data['stderr'] and data['cwd'] == str(folder)
    assert not data['timed_out']
    assert result_summary('bash', result)[0] == 'error'


async def test_output_cap_drains_both_streams(tmp_path):
    result = await ShellRunner(tmp_path).execute({'command': python_command(
        "import sys; sys.stdout.write('a'*200000); sys.stderr.write('b'*200000)")})
    data = json.loads(result.text)
    assert not result.is_error and data['exit_code'] == 0
    assert len(data['stdout']) == OUTPUT_LIMIT and len(data['stderr']) == OUTPUT_LIMIT
    assert data['stdout_truncated'] and data['stderr_truncated']
    assert '截断' in result_summary('bash', result)[1]


async def test_missing_cwd_and_executable_return_errors(tmp_path):
    result = await ShellRunner(tmp_path).execute({'command': 'echo test', 'cwd': 'missing'})
    assert result.is_error and '目录' in json.loads(result.text)['stderr']
    result = await ShellRunner(tmp_path, Shell('test', 'bash', None)).execute({'command': 'echo test'})
    assert result.is_error and '未找到' in json.loads(result.text)['stderr']


@pytest.mark.skipif(sys.platform == 'win32', reason='POSIX process-group cleanup; Windows needs native taskkill verification')
@pytest.mark.parametrize('cancel', [False, True])
async def test_timeout_and_cancel_stop_descendants(tmp_path, cancel):
    marker = tmp_path / 'child-survived'
    ready = tmp_path / 'started'
    child = f"import time,pathlib; time.sleep(2); pathlib.Path({str(marker)!r}).touch()"
    source = (f"import subprocess,sys,time,pathlib; subprocess.Popen([sys.executable,'-c',{child!r}]); "
              f"pathlib.Path({str(ready)!r}).touch(); time.sleep(30)")
    task = asyncio.create_task(ShellRunner(tmp_path).execute({'command': python_command(source), 'timeout_seconds': 1}))
    if cancel:
        async with asyncio.timeout(3):
            while not ready.exists():
                await asyncio.sleep(.01)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    else:
        result = await task
        data = json.loads(result.text)
        assert result.is_error and data['timed_out']
        assert result_summary('bash', result)[0] == 'error'
    await asyncio.sleep(2.1)
    assert not marker.exists()


async def test_real_shell_through_reference_agent_and_runtime(tmp_path, monkeypatch):
    monkeypatch.setattr('common.app.runtime.ROOT', tmp_path)
    runtime = Runtime(lesson=1, root=tmp_path / 'runs')
    requests = 0

    async def complete(messages, tools, config):
        nonlocal requests
        requests += 1
        assert any(t.name == 'bash' and select_shell().name in t.description for t in tools)
        if requests == 1:
            return ModelReply({'role': 'assistant', 'content': None, 'tool_calls': [
                {'id': 'shell-check', 'type': 'function', 'function': {'name': 'bash',
                 'arguments': json.dumps({'command': python_command("print('shell-loop-ok')")})}}]})
        response = json.loads(messages[-1]['content'])
        assert not response['is_error']
        assert json.loads(response['text'])['stdout'].strip() == 'shell-loop-ok'
        return ModelReply({'role': 'assistant', 'content': '命令执行成功'})

    runtime.module = lambda name: agent if name == 'agent' else SimpleNamespace(complete=complete)
    events = []
    await runtime.run('执行命令验证', Config(lesson=1), events.append)
    assert runtime.last_record.data['status'] == 'completed'
    assert runtime.last_record.data['tool_calls'] == 1
    assert [e.kind for e in events if e.kind.startswith('tool_')] == ['tool_start', 'tool_end']
    async with Runtime(lesson=1).registry(Config(lesson=1)) as (tools, _):
        assert 'bash' in {tool.name for tool in tools}


async def test_edit_exercise_shell_defaults_to_copy(tmp_path):
    from common.core.edit_tools import EditWorkspace
    editor = EditWorkspace(tmp_path / 'code')
    runtime = Runtime(lesson=1)
    async with runtime.registry(Config(lesson=1), editor) as (tools, execute):
        assert {'bash', 'search_file', 'read_file', 'edit'} <= {t.name for t in tools}
        result = await execute('bash', {'command': python_command('import os; print(os.getcwd())')})
        assert json.loads(result.text)['stdout'].strip() == str(editor.root)


async def test_shell_result_redacts_api_key_before_model(monkeypatch):
    from common.core.types import ToolResult
    async def fake_execute(self, arguments):
        return ToolResult('known-private-key')
    monkeypatch.setattr(ShellRunner, 'execute', fake_execute)
    async with Runtime(lesson=1).registry(Config(lesson=1, api_key='known-private-key')) as (_, execute):
        result = await execute('bash', {'command': 'example'})
        assert result.text == '[REDACTED]'
