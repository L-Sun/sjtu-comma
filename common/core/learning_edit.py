"""Offer the Edit tool only after the student's registration and dispatch pass."""
import asyncio
from pathlib import Path

from common.core.course_editor import CourseEditor, version
from common.core.student_checks import run_student_check
from common.core.student_loader import load_student_agent
from common.core.types import ToolResult


class EditIntegration:
    def __init__(self, root, *, check_timeout=5):
        self.root = Path(root)
        self.path = self.root / 'lesson_01_agent/tools.py'
        self.editor = CourseEditor(self.root)
        self.check_timeout = check_timeout
        self.lock = asyncio.Lock()
        self.version = None
        self.module = None
        self.specs = []
        self.status = self.not_ready('先与 Chat 一起完成 tools.py 中的两个 Edit 接入函数。')

    @staticmethod
    def not_ready(detail):
        return {'ready': False, 'passed': 0, 'total': 2, 'checks': [], 'detail': detail}

    def public(self):
        return {**self.status, 'version': self.version}

    async def refresh(self, *, force=False):
        async with self.lock:
            try:
                if self.path.is_symlink() or self.path.parent.is_symlink() or self.path.stat().st_size > 256 * 1024:
                    raise ValueError('tools.py 需要是小于256KiB的普通作业文件。')
                source = self.path.read_bytes().decode('utf-8')
                current = version(source)
            except (OSError, ValueError, UnicodeError):
                self.version, self.module, self.specs = None, None, []
                self.status = self.not_ready('无法读取 tools.py，请保存文件后检查 Edit 接入。')
                return self.public()
            if not force and current == self.version:
                return self.public()
            result = await run_student_check(self.root, 'lesson_01_agent.check_edit', source,
                                             self.check_timeout, self.not_ready)
            self.module, self.specs = None, []
            if result['ready']:
                try:
                    self.module = load_student_agent(source, self.path)
                    self.specs = self.module.get_tools()
                except Exception as exc:
                    result = self.not_ready(f'加载 Edit 接入失败：{type(exc).__name__}: {exc}')
                    self.module, self.specs = None, []
            self.status, self.version = result, current
            return self.public()

    def tools(self):
        return list(self.specs) if self.status['ready'] else []

    async def execute(self, name, arguments):
        if not self.status['ready'] or self.module is None:
            return ToolResult('Edit 尚未接入；请先完成 tools.py 并检查，下一轮才能使用。', is_error=True)
        return await self.module.call_tool(name, arguments, self.editor)
