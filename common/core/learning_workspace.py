"""Read-only course files and isolated, versioned checks of the student's Agent."""
from __future__ import annotations
import asyncio
import hashlib
import json
from pathlib import Path
import subprocess
import sys

from common.core.config import ROOT
from common.core.shell_tools import child_environment, ShellRunner
from common.core.student_loader import load_student_agent
from common.core.types import ToolResult, ToolSpec

SOURCE_FOLDERS = ('lesson_01_agent', 'common', 'docs/student')
SOURCE_FILES = ('README.md', 'pyproject.toml', '.env.example')
TEXT_SUFFIXES = {'.py', '.md', '.toml', '.html', '.js', '.css', '.svg', '.txt', '.json'}


class LearningWorkspace:
    def __init__(self, root=ROOT, *, check_timeout=5):
        self.root = Path(root).resolve()
        self.agent_path = self.root / 'lesson_01_agent/agent.py'
        self.check_timeout = check_timeout
        self.lock = asyncio.Lock()
        self.source = None
        self.version = None
        self.status = self._not_ready('正在检查已保存的 agent.py。')

    def _not_ready(self, detail):
        return {'ready': False, 'passed': 0, 'total': 7, 'checks': [], 'detail': detail}

    def public(self):
        return {**self.status, 'version': self.version,
                'runner': 'student' if self.status['ready'] else 'teaching_chat'}

    def _allowed(self, relative, *, directory=False):
        text = relative.as_posix()
        if text in SOURCE_FILES:
            return True
        if any(part.startswith('.') or part == '__pycache__' for part in relative.parts):
            return False
        if directory and text == '.':
            return True
        for folder in SOURCE_FOLDERS:
            if text == folder or text.startswith(folder + '/'):
                return directory or relative.suffix in TEXT_SUFFIXES
            if directory and folder.startswith(text + '/'):
                return True
        return False

    def _path(self, value, *, directory=False):
        relative = Path(value)
        if relative.is_absolute() or '..' in relative.parts:
            raise ValueError('请使用课程目录内的相对路径，不包含 ..。')
        path = self.root / relative
        if (not self._allowed(relative, directory=directory)
                or not path.resolve().is_relative_to(self.root)
                or any(p.is_symlink() for p in [path, *path.parents] if p != self.root and self.root in p.parents)):
            raise ValueError('只能访问公开的课程源文件、第一课作业和讲义。')
        return path

    def tools(self):
        return [
            ToolSpec('list_files', '列出课程目录中的文件与子目录。先用它确认路径，再读取文件。可浏览 lesson_01_agent、common、docs/student 及根目录讲义，不包含密钥、运行记录或第二课答案。', {
                'type': 'object', 'properties': {
                    'path': {'type': 'string', 'description': '相对目录，默认 .；例如 lesson_01_agent'},
                    'offset': {'type': 'integer', 'minimum': 0},
                }, 'additionalProperties': False,
            }),
            ToolSpec('read_course_file', '读取最新保存的课程源文件或讲义，返回带行号文本。每次最多160行，可分段继续读取。修改建议前先读文件；此工具不会写文件。', {
                'type': 'object', 'properties': {
                    'path': {'type': 'string', 'description': '例如 lesson_01_agent/agent.py 或 lesson_01_agent/README.md'},
                    'start_line': {'type': 'integer', 'minimum': 1},
                    'end_line': {'type': 'integer', 'minimum': 1},
                }, 'required': ['path'], 'additionalProperties': False,
            }),
            ToolSpec('check_agent', '检查最新保存的第一课 agent.py：六个辅助函数、学生自己实现的 run_turn、两轮聊天、批量工具调用、错误处理与轮数上限。用假模型和假工具，不消耗模型额度。返回逐项结果和代码版本；依据实际结果解释待修复问题。通过后下一个回合使用学生自己的 Agent。', {
                'type': 'object', 'properties': {}, 'additionalProperties': False,
            }),
        ]

    async def execute(self, name, arguments):
        try:
            if name == 'check_agent':
                result = await self.refresh(force=True)
            elif name == 'list_files':
                path = self._path(arguments.get('path', '.'), directory=True)
                if not path.is_dir():
                    raise ValueError('目录不存在。')
                entries = []
                for child in path.iterdir():
                    relative = child.relative_to(self.root)
                    if child.is_symlink() or not self._allowed(relative, directory=child.is_dir()):
                        continue
                    entries.append({'path': relative.as_posix(), 'type': 'directory' if child.is_dir() else 'file'})
                entries.sort(key=lambda item: (item['type'] != 'directory', item['path']))
                offset = arguments.get('offset', 0)
                if type(offset) is not int or offset < 0:
                    raise ValueError('offset 必须是非负整数。')
                result = {'path': path.relative_to(self.root).as_posix(), 'entries': entries[offset:offset+80],
                          'total': len(entries), 'next_offset': offset+80 if len(entries) > offset+80 else None}
            elif name == 'read_course_file':
                path = self._path(arguments['path'])
                if not path.is_file() or path.stat().st_size > 1024 * 1024:
                    raise ValueError('文件不存在，或超过1MiB读取限制。')
                start = arguments.get('start_line', 1)
                end = arguments.get('end_line', start+159)
                if type(start) is not int or type(end) is not int or start < 1 or end < start or end-start >= 160:
                    raise ValueError('请提供有效行号，每次最多读取160行。')
                lines = path.read_text(encoding='utf-8').splitlines()
                selected = lines[start-1:end]
                result = {'path': path.relative_to(self.root).as_posix(), 'total_lines': len(lines),
                          'start_line': start, 'end_line': min(end, len(lines)),
                          'content': '\n'.join(f'{i}: {line}' for i, line in enumerate(selected, start))}
            else:
                return ToolResult('课程工具不存在。', is_error=True)
            return ToolResult(json.dumps(result, ensure_ascii=False))
        except (OSError, ValueError, KeyError, UnicodeError) as exc:
            return ToolResult(str(exc), is_error=True)

    async def refresh(self, *, force=False):
        async with self.lock:
            try:
                if self.agent_path.is_symlink() or self.agent_path.stat().st_size > 256 * 1024:
                    raise ValueError('agent.py 需要是小于256KiB的普通文件。')
                source = self.agent_path.read_text(encoding='utf-8')
                version = hashlib.sha256(source.encode('utf-8')).hexdigest()
            except (OSError, ValueError, UnicodeError):
                self.version, self.source = None, None
                self.status = self._not_ready('无法读取 lesson_01_agent/agent.py，请保存文件后重试。')
                return self.public()
            if not force and version == self.version:
                return self.public()
            self.status = await self._check(source)
            self.source, self.version = source, version
            return self.public()

    async def _check(self, source):
        options = {'start_new_session': True} if sys.platform != 'win32' else {
            'creationflags': subprocess.CREATE_NEW_PROCESS_GROUP}
        try:
            process = await asyncio.create_subprocess_exec(
            sys.executable, '-m', 'lesson_01_agent.check', '--json', '--source-stdin',
            cwd=self.root, env=child_environment(), stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE, **options)
        except OSError:
            return self._not_ready("无法启动检查进程，请运行离线检查查看详情。")
        async def read_limited(stream):
            data = bytearray()
            while chunk := await stream.read(8192):
                if len(data) < 64 * 1024:
                    data.extend(chunk[:64 * 1024-len(data)])
            return bytes(data)
        async def communicate():
            async def send_source():
                try:
                    process.stdin.write(source.encode('utf-8'))
                    await process.stdin.drain()
                except (BrokenPipeError, ConnectionResetError):
                    pass
                finally:
                    process.stdin.close()
            _, stdout, _ = await asyncio.gather(send_source(), read_limited(process.stdout), read_limited(process.stderr))
            await process.wait()
            return stdout
        try:
            output = await asyncio.wait_for(communicate(), self.check_timeout)
            result = json.loads(output)
            if not isinstance(result, dict) or not isinstance(result.get('checks'), list):
                raise ValueError()
            result['ready'] = result.get('ready') is True and process.returncode == 0
            return result
        except asyncio.CancelledError:
            await ShellRunner(self.root)._stop(process)
            raise
        except TimeoutError:
            await ShellRunner(self.root)._stop(process)
            return self._not_ready('检查超时，请检查是否有无限循环或未结束的等待。教学 Chat 仍可使用。')
        except (ValueError, OSError):
            await ShellRunner(self.root)._stop(process)
            return self._not_ready('检查未能完成，请检查 agent.py 的导入或运行错误，或运行离线检查查看详情。')

    def student_agent(self):
        if not self.status['ready'] or self.source is None:
            raise ValueError('学生 Agent 尚未通过检查。')
        return load_student_agent(self.source, self.agent_path)
