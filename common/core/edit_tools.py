"""Teacher-provided search, ranged read and atomic multi-hunk edit tools."""
import difflib
import hashlib
import json
import os
from pathlib import Path
import stat
import tempfile

from common.core.editor_eval import BASELINE, FILENAME, evaluate
from common.core.types import ToolResult, ToolSpec


def version(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


class FileEditor:
    """Edit existing UTF-8 files using paths relative to the working directory or absolute paths."""

    def __init__(self, root: Path):
        self.root = root.resolve()

    def path_schema(self):
        return {'type': 'string', 'minLength': 1,
                'description': f'已有 UTF-8 文本文件；绝对路径或相对于 {self.root} 的路径。不限文件名或扩展名，最大2MiB。'}

    def resolve_path(self, value):
        path = Path(value).expanduser()
        if not path.is_absolute():
            path = self.root / path
        return path.resolve()

    def tools(self):
        path = self.path_schema()
        return [
            ToolSpec('search_file', '按字面文本搜索长文件，返回带行号的上下文和当前版本。最多20处；可用 after_line 翻页。', {
                'type': 'object', 'properties': {'path': path, 'query': {'type': 'string', 'minLength': 1},
                    'after_line': {'type': 'integer', 'minimum': 0}},
                'required': ['path', 'query'], 'additionalProperties': False}),
            ToolSpec('read_file', '读取一段文本（含首尾行），最多160行，默认从 start_line 起120行，到文件末尾自动截断。返回行号和版本；行号前缀不是文件内容。', {
                'type': 'object', 'properties': {'path': path,
                    'start_line': {'type': 'integer', 'minimum': 1}, 'end_line': {'type': 'integer', 'minimum': 1}},
                'required': ['path'], 'additionalProperties': False}),
            ToolSpec('edit', '一次原子提交多个精确替换。base_version 必须是最近读取的版本；每个 old_text 须非空、唯一且互不重叠。用附近上下文区分同名内容，勿带行号。任何一处失败则全部不写入。', {
                'type': 'object', 'properties': {'path': path,
                    'base_version': {'type': 'string', 'pattern': '^[0-9a-f]{64}$'},
                    'edits': {'type': 'array', 'minItems': 1, 'maxItems': 12, 'items': {
                        'type': 'object', 'properties': {
                            'old_text': {'type': 'string', 'minLength': 1, 'maxLength': 8000},
                            'new_text': {'type': 'string', 'maxLength': 8000}},
                        'required': ['old_text', 'new_text'], 'additionalProperties': False}}},
                'required': ['path', 'base_version', 'edits'], 'additionalProperties': False}),
        ]

    async def execute(self, name, arguments):
        if name not in {'read_file', 'search_file', 'edit'}:
            return ToolResult('Unknown tool', is_error=True)
        try:
            path = self.resolve_path(arguments['path'])
            if not path.is_file() or path.stat().st_size > 2 * 1024 * 1024:
                raise ValueError('只能访问不超过2MiB的已有普通文本文件。')
            before = path.read_bytes().decode('utf-8')
            if '\x00' in before:
                raise ValueError('文件包含二进制内容，不能作为文本编辑。')
        except (OSError, ValueError, KeyError, UnicodeError) as exc:
            return ToolResult(str(exc), is_error=True)
        current = version(before)
        lines = before.splitlines()
        if name == 'read_file':
            start = arguments.get('start_line', 1)
            end = arguments.get('end_line', start + 119)
            if not 1 <= start <= end or start > max(1, len(lines)) or end - start >= 160:
                return ToolResult('行范围无效；每次最多读取160行。', is_error=True)
            end = min(end, len(lines))
            return ToolResult(json.dumps({'path': str(path), 'version': current, 'total_lines': len(lines),
                'next_start_line': end + 1 if end < len(lines) else None,
                'content': '\n'.join(f'{i}: {lines[i-1]}' for i in range(start, end + 1))}, ensure_ascii=False))
        if name == 'search_file':
            query = arguments['query']
            matches = [i for i, line in enumerate(lines, 1) if query in line and i > arguments.get('after_line', 0)]
            return ToolResult(json.dumps({'path': str(path), 'version': current, 'total_lines': len(lines),
                'has_more': len(matches) > 20, 'next_after_line': matches[:20][-1] if matches else None,
                'matches': [{'line': i, 'context': '\n'.join(f'{j}: {lines[j-1]}'
                    for j in range(max(1, i-2), min(len(lines), i+2) + 1))} for i in matches[:20]]}, ensure_ascii=False))
        if name != 'edit':
            return ToolResult('Unknown tool', is_error=True)
        if arguments.get('base_version') != current:
            return ToolResult('版本冲突；文件未修改。请重新读取当前文件再提交。', is_error=True)
        edits = arguments.get('edits', [])
        if not 1 <= len(edits) <= 12:
            return ToolResult('每次提交1—12处替换；文件未修改。', is_error=True)
        spans = []
        for index, edit in enumerate(edits, 1):
            old, new = edit['old_text'], edit['new_text']
            start = before.find(old)
            if not old or start < 0 or before.find(old, start + 1) >= 0 or max(len(old), len(new)) > 8000:
                return ToolResult(f'第{index}处替换不唯一、未匹配或过长；整批未写入。请补充上下文并重新提交。', is_error=True)
            spans.append((start, start + len(old), new))
        spans.sort()
        if any(left[1] > right[0] for left, right in zip(spans, spans[1:])):
            return ToolResult('补丁范围重叠；整批未写入。', is_error=True)
        after = before
        for start, end, new in reversed(spans):
            after = after[:start] + new + after[end:]
        if len(after.encode('utf-8')) > 2 * 1024 * 1024:
            return ToolResult('文件不能超过2MiB；文件未修改。', is_error=True)
        diff = ''.join(difflib.unified_diff(before.splitlines(True), after.splitlines(True),
                                          fromfile='before/' + path.name, tofile='after/' + path.name))
        # No await between validation and replace: serialize a whole batch in the
        # Agent loop and never expose a half-written file to readers.
        fd, temporary = tempfile.mkstemp(prefix='.edit-', dir=path.parent)
        try:
            with os.fdopen(fd, 'wb') as file:
                file.write(after.encode('utf-8'))
            os.chmod(temporary, stat.S_IMODE(path.stat().st_mode))
            os.replace(temporary, path)
        finally:
            Path(temporary).unlink(missing_ok=True)
        return ToolResult(json.dumps({'path': str(path), 'saved': True, 'edit_count': len(spans),
            'base_version': current, 'version': version(after), 'diff': diff}, ensure_ascii=False))


class EditWorkspace(FileEditor):
    """The fixed experiment keeps its own copy and restricted filename."""

    def __init__(self, root: Path, *, initial: bytes | None = None):
        super().__init__(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.path = self.root / FILENAME
        self.path.write_bytes(BASELINE.encode('utf-8') if initial is None else initial)

    def path_schema(self):
        return {'type': 'string', 'enum': [FILENAME]}

    def resolve_path(self, value):
        if value != FILENAME or self.path.is_symlink():
            raise ValueError('只能访问本轮 course_page.py 练习副本。')
        return self.path

    async def grade(self):
        return evaluate(self.path.read_bytes().decode('utf-8'))
