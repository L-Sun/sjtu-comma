"""Course files, student-connected editing, and versioned exercise checks."""
from __future__ import annotations
import asyncio
import hashlib
import json
from pathlib import Path

from common.core.config import ROOT
from common.core.student_checks import run_student_check
from common.core.learning_edit import EditIntegration
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
        self.edit = EditIntegration(self.root, check_timeout=check_timeout)
        self.source = None
        self.version = None
        self.status = self._not_ready('正在检查已保存的 agent.py。')

    def _not_ready(self, detail):
        return {'ready': False, 'passed': 0, 'total': 6, 'checks': [], 'detail': detail}

    def public(self):
        return {**self.status, 'version': self.version,
                'runner': 'student' if self.status['ready'] else 'teaching_chat',
                'edit': self.edit.public()}

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
            ToolSpec('read_course_file', '读取最新保存的课程源文件或讲义，返回带行号文本。返回文件版本和带行号的文本，每次最多160行，可分段读取。编辑时使用 version 作为 base_version，old_text 不包含行号。', {
                'type': 'object', 'properties': {
                    'path': {'type': 'string', 'description': '例如 lesson_01_agent/agent.py 或 lesson_01_agent/README.md'},
                    'start_line': {'type': 'integer', 'minimum': 1},
                    'end_line': {'type': 'integer', 'minimum': 1},
                }, 'required': ['path'], 'additionalProperties': False,
            }),
            ToolSpec('check_agent', '检查第一课 tools.py 的 Edit 接入，以及 agent.py：五个辅助函数、学生自己实现的 run_turn、两轮聊天、批量工具调用、错误处理与轮数上限。用假模型和假工具，不消耗模型额度。返回逐项结果和代码版本；依据实际结果解释待修复问题。通过后下一个回合使用学生自己的 Agent。', {
                'type': 'object', 'properties': {}, 'additionalProperties': False,
            }),
            *self.edit.tools(),
        ]

    async def execute(self, name, arguments):
        try:
            if name == 'edit_course_file':
                return await self.edit.execute(name, arguments)
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
                source = path.read_bytes().decode('utf-8')
                lines = source.splitlines()
                selected = lines[start-1:end]
                result = {'path': path.relative_to(self.root).as_posix(), 'version': hashlib.sha256(source.encode('utf-8')).hexdigest(),
                          'total_lines': len(lines),
                          'start_line': start, 'end_line': min(end, len(lines)),
                          'content': '\n'.join(f'{i}: {line}' for i, line in enumerate(selected, start))}
            else:
                return ToolResult('课程工具不存在。', is_error=True)
            return ToolResult(json.dumps(result, ensure_ascii=False))
        except (OSError, ValueError, KeyError, UnicodeError) as exc:
            return ToolResult(str(exc), is_error=True)

    async def refresh(self, *, force=False):
        await self.edit.refresh(force=force)
        async with self.lock:
            try:
                if self.agent_path.is_symlink() or self.agent_path.stat().st_size > 256 * 1024:
                    raise ValueError('agent.py 需要是小于256KiB的普通文件。')
                source = self.agent_path.read_bytes().decode('utf-8')
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
        return await run_student_check(self.root, 'lesson_01_agent.check', source,
                                       self.check_timeout, self._not_ready)

    def student_agent(self):
        if not self.status['ready'] or self.source is None:
            raise ValueError('学生 Agent 尚未通过检查。')
        return load_student_agent(self.source, self.agent_path)
