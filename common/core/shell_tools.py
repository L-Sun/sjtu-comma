"""Teacher-provided local command runner with platform-aware shell selection."""
from __future__ import annotations

import asyncio
import base64
from dataclasses import dataclass
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time

from common.core.types import ToolResult, ToolSpec

OUTPUT_LIMIT = 16 * 1024  # Per stream; keep draining after this limit to avoid pipe deadlock.


@dataclass(frozen=True)
class Shell:
    platform: str
    name: str
    executable: str | None

    def argv(self, command: str) -> list[str]:
        if not self.executable:
            raise FileNotFoundError(f'{self.platform} 上未找到 {self.name}，请先安装该 shell。')
        if self.name == 'PowerShell':
            script = (
                '[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)\n'
                '$OutputEncoding = [Console]::OutputEncoding\n'
                "$ErrorActionPreference = 'Stop'\n"
                + command + '\nif ($null -ne $LASTEXITCODE) { exit $LASTEXITCODE }\n'
            )
            encoded = base64.b64encode(script.encode('utf-16-le')).decode('ascii')
            return [self.executable, '-NoLogo', '-NoProfile', '-NonInteractive', '-EncodedCommand', encoded]
        if self.name == 'zsh':
            return [self.executable, '-f', '-c', command]
        return [self.executable, '--noprofile', '--norc', '-c', command]


def select_shell(platform=None) -> Shell:
    platform = platform or sys.platform
    if platform == 'win32':
        executable = shutil.which('pwsh') or shutil.which('powershell')
        return Shell('Windows', 'PowerShell', executable)
    if platform == 'darwin':
        return Shell('macOS', 'zsh', shutil.which('zsh'))
    return Shell('Linux' if platform.startswith('linux') else platform, 'bash', shutil.which('bash'))


def child_environment():
    # Avoid inheriting API credentials; this is not a filesystem/security sandbox.
    allowed = {'PATH', 'HOME', 'USER', 'LOGNAME', 'USERPROFILE', 'SYSTEMROOT', 'WINDIR',
               'COMSPEC', 'PATHEXT', 'TEMP', 'TMP', 'TMPDIR', 'LOCALAPPDATA', 'APPDATA',
               'LANG', 'LC_ALL', 'LC_CTYPE', 'VIRTUAL_ENV'}
    env = {k: v for k, v in os.environ.items() if k.upper() in allowed}
    env['PYTHONIOENCODING'] = 'utf-8'
    return env


class ShellRunner:
    def __init__(self, cwd: Path, shell: Shell | None = None):
        self.cwd = cwd.resolve()
        self.shell = shell or select_shell()

    def tool(self):
        shell = self.shell
        return ToolSpec('bash', (
            f'在本机执行命令。工具名统一为 bash，但当前平台为 {shell.platform}，实际 shell 为 {shell.name}；'
            f'必须使用 {shell.name} 语法。默认工作目录：{self.cwd}。'
            '每次调用使用新的非交互 shell，cd 和环境变量不会延续到下次；用 cwd 指定目录。'
            '返回 stdout、stderr、exit_code、超时和输出截断标记；非零退出或超时视为失败。'
            '默认超时30秒，最多120秒；每个输出流最多返回16KiB。只能执行用户任务所需命令。'
        ), {
            'type': 'object',
            'properties': {
                'command': {'type': 'string', 'minLength': 1, 'maxLength': 16000,
                            'description': f'要执行的 {shell.name} 命令；不是其他平台的 shell 语法。'},
                'cwd': {'type': 'string', 'minLength': 1,
                        'description': '可选工作目录；相对路径基于本轮默认目录。'},
                'timeout_seconds': {'type': 'integer', 'minimum': 1, 'maximum': 120},
            },
            'required': ['command'], 'additionalProperties': False,
        })

    async def _stop(self, process):
        if sys.platform == 'win32':
            # /T kills the descendant tree as well as the shell; no cmd.exe quoting.
            killer = None
            try:
                killer = await asyncio.create_subprocess_exec(
                    'taskkill', '/PID', str(process.pid), '/T', '/F',
                    stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
                await asyncio.wait_for(killer.wait(), 3)
            except (OSError, TimeoutError):
                if killer is not None and killer.returncode is None:
                    try:
                        killer.kill()
                    except ProcessLookupError:
                        pass
                    await killer.wait()
            if process.returncode is None:
                try:
                    process.kill()
                except ProcessLookupError:
                    pass
        else:
            # The shell can have exited while its children still hold the pipes.
            try:
                os.killpg(process.pid, signal.SIGTERM)
                await asyncio.sleep(.15)
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        try:
            await asyncio.wait_for(process.wait(), 2)
        except TimeoutError:
            # Detached children can retain pipes; never let cleanup hang the UI.
            pass

    async def execute(self, arguments):
        started = time.monotonic()
        directory = Path(arguments.get('cwd', str(self.cwd))).expanduser()
        if not directory.is_absolute():
            directory = self.cwd / directory
        directory = directory.resolve()
        output = {'platform': self.shell.platform, 'shell': self.shell.name, 'cwd': str(directory),
                  'exit_code': None, 'stdout': '', 'stderr': '', 'timed_out': False,
                  'stdout_truncated': False, 'stderr_truncated': False}
        timeout = arguments.get('timeout_seconds', 30)
        command = arguments.get('command', '')
        if (not isinstance(command, str) or not command.strip() or len(command) > 16000
                or type(timeout) is not int or not 1 <= timeout <= 120):
            output['stderr'] = '命令不能为空且最多16000字符；timeout_seconds 必须是1—120的整数。'
            return ToolResult(json.dumps(output, ensure_ascii=False), is_error=True)
        if not directory.is_dir():
            output['stderr'] = '工作目录不存在或不是目录。'
            return ToolResult(json.dumps(output, ensure_ascii=False), is_error=True)
        try:
            process = await asyncio.create_subprocess_exec(
                *self.shell.argv(command), cwd=directory, env=child_environment(),
                stdin=asyncio.subprocess.DEVNULL, stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                **({'creationflags': subprocess.CREATE_NEW_PROCESS_GROUP} if sys.platform == 'win32'
                   else {'start_new_session': True}))
        except OSError as exc:
            output['stderr'] = str(exc)
            return ToolResult(json.dumps(output, ensure_ascii=False), is_error=True)

        buffers = {'stdout': bytearray(), 'stderr': bytearray()}

        async def drain(stream, name):
            while chunk := await stream.read(8192):
                remaining = OUTPUT_LIMIT - len(buffers[name])
                buffers[name].extend(chunk[:remaining])
                if len(chunk) > remaining:
                    output[name + '_truncated'] = True

        readers = [asyncio.create_task(drain(process.stdout, 'stdout')),
                   asyncio.create_task(drain(process.stderr, 'stderr'))]
        try:
            async with asyncio.timeout(timeout):
                await process.wait()
                await asyncio.gather(*readers)
        except TimeoutError:
            output['timed_out'] = True
            await self._stop(process)
        except asyncio.CancelledError:
            await self._stop(process)
            raise
        finally:
            for reader in readers:
                if not reader.done():
                    reader.cancel()
            await asyncio.gather(*readers, return_exceptions=True)
        for name, content in buffers.items():
            output[name] = content.decode('utf-8', errors='replace')
        output['exit_code'] = process.returncode
        output['duration_seconds'] = round(time.monotonic() - started, 3)
        return ToolResult(json.dumps(output, ensure_ascii=False),
                          is_error=output['timed_out'] or process.returncode != 0)
