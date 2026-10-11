"""File-writing primitive for the student's first tool-integration exercise."""
import difflib
import hashlib
import json
import os
from pathlib import Path
import tempfile
import uuid

from jsonschema import validate, ValidationError
from common.core.types import ToolResult

EDITABLE_FILES = ['lesson_01_agent/agent.py', 'lesson_01_agent/tools.py']
EDIT_PARAMETERS = {
    'type': 'object', 'properties': {
        'path': {'type': 'string', 'enum': EDITABLE_FILES},
        'base_version': {'type': 'string', 'pattern': '^[0-9a-f]{64}$'},
        'edits': {'type': 'array', 'minItems': 1, 'maxItems': 12, 'items': {
            'type': 'object', 'properties': {
                'old_text': {'type': 'string', 'minLength': 1, 'maxLength': 16000},
                'new_text': {'type': 'string', 'maxLength': 16000}},
            'required': ['old_text', 'new_text'], 'additionalProperties': False}}},
    'required': ['path', 'base_version', 'edits'], 'additionalProperties': False,
}


def version(source):
    return hashlib.sha256(source.encode('utf-8')).hexdigest()


class CourseEditor:
    """Provided IO, backups and conflict checks; students connect its execution to a tool."""
    def __init__(self, root):
        self.root = Path(root).resolve()

    async def execute(self, arguments):
        try:
            validate(arguments, EDIT_PARAMETERS)
            path = self.root / arguments['path']
            if (path.is_symlink() or path.parent.is_symlink()
                    or not path.resolve().is_relative_to(self.root)
                    or not path.is_file() or path.stat().st_size > 256 * 1024):
                raise ValueError('只能编辑第一课中的普通作业文件，每个文件不超过256KiB。')
            before = path.read_bytes().decode('utf-8')
            current = version(before)
            if current != arguments['base_version']:
                raise ValueError('版本冲突，文件未修改。请重新读取文件后再编辑。')
            spans = []
            for number, edit in enumerate(arguments['edits'], 1):
                old = edit['old_text']
                start = before.find(old)
                if start < 0 or before.find(old, start + 1) >= 0:
                    raise ValueError(f'第{number}处原文未匹配或不唯一，整批未写入。请补充上下文，不要包含行号。')
                spans.append((start, start + len(old), edit['new_text']))
            spans.sort()
            if any(left[1] > right[0] for left, right in zip(spans, spans[1:])):
                raise ValueError('替换范围重叠，整批未写入。')
            after = before
            for start, end, replacement in reversed(spans):
                after = after[:start] + replacement + after[end:]
            if len(after.encode('utf-8')) > 256 * 1024:
                raise ValueError('编辑后的文件超过256KiB，文件未修改。')
            try:
                compile(after, str(path), 'exec')
            except SyntaxError as exc:
                raise ValueError(f'编辑后有 Python 语法错误（第{exc.lineno}行：{exc.msg}），文件未修改。') from None
            if after == before:
                return ToolResult(json.dumps({'saved': False, 'version': current, 'detail': '内容没有变化。'}, ensure_ascii=False))
            backup_root = self.root / '.course-edits'
            if backup_root.is_symlink():
                raise ValueError('作业备份目录不可用，文件未修改。')
            backup_root.mkdir(exist_ok=True)
            backup = backup_root / (uuid.uuid4().hex + '.py')
            with backup.open('xb') as file:
                file.write(before.encode('utf-8'))
            fd, temporary = tempfile.mkstemp(prefix='.course-edit-', dir=path.parent)
            try:
                with os.fdopen(fd, 'wb') as file:
                    file.write(after.encode('utf-8'))
                os.chmod(temporary, path.stat().st_mode & 0o777)
                # Check again before replacing, in case an external editor saved meanwhile.
                if path.is_symlink() or path.read_bytes().decode('utf-8') != before:
                    raise ValueError('编辑期间文件发生变化，未覆盖新内容。请重新读取。')
                os.replace(temporary, path)
            finally:
                Path(temporary).unlink(missing_ok=True)
            diff = ''.join(difflib.unified_diff(before.splitlines(True), after.splitlines(True),
                                              fromfile='before/' + arguments['path'], tofile='after/' + arguments['path']))
            return ToolResult(json.dumps({'saved': True, 'path': arguments['path'], 'edit_count': len(spans),
                'base_version': current, 'version': version(after), 'diff': diff,
                'backup': backup.relative_to(self.root).as_posix()}, ensure_ascii=False))
        except ValidationError:
            return ToolResult('编辑参数无效；只能编辑第一课的 agent.py 或 tools.py，请先读取文件并使用返回的版本。', is_error=True)
        except (OSError, ValueError, UnicodeError) as exc:
            return ToolResult(str(exc), is_error=True)
