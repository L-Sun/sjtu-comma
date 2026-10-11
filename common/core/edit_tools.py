"""Teacher-provided search, ranged read and atomic multi-hunk edit tools."""
import difflib
import hashlib
import json
import os
from pathlib import Path
import tempfile

from common.core.editor_eval import BASELINE, FILENAME, evaluate
from common.core.types import ToolResult, ToolSpec


def version(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


class EditWorkspace:
    def __init__(self, root: Path, *, initial: bytes | None = None):
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.path = self.root / FILENAME
        self.path.write_bytes(BASELINE.encode('utf-8') if initial is None else initial)

    def tools(self):
        path = {'type': 'string', 'enum': [FILENAME]}
        return [
            ToolSpec('search_file', '按字面文本搜索长文件，返回带行号的上下文和当前版本。最多20处；可用 after_line 翻页。', {
                'type': 'object', 'properties': {'path': path, 'query': {'type': 'string', 'minLength': 1},
                    'after_line': {'type': 'integer', 'minimum': 0}},
                'required': ['path', 'query'], 'additionalProperties': False}),
            ToolSpec('read_file', '读取一段代码（含首尾行），最多160行，默认1—120行。返回行号和版本；行号前缀不是文件内容。', {
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
        if arguments.get('path') != FILENAME or self.path.is_symlink():
            return ToolResult('只能访问本轮 course_page.py 练习副本。', is_error=True)
        before = self.path.read_bytes().decode('utf-8')
        current = version(before)
        lines = before.splitlines()
        if name == 'read_file':
            start, end = arguments.get('start_line', 1), arguments.get('end_line', 120)
            if not 1 <= start <= end <= len(lines) or end - start >= 160:
                return ToolResult('行范围无效；每次最多读取160行。', is_error=True)
            return ToolResult(json.dumps({'version': current, 'total_lines': len(lines),
                'content': '\n'.join(f'{i}: {lines[i-1]}' for i in range(start, end + 1))}, ensure_ascii=False))
        if name == 'search_file':
            query = arguments['query']
            matches = [i for i, line in enumerate(lines, 1) if query in line and i > arguments.get('after_line', 0)]
            return ToolResult(json.dumps({'version': current, 'total_lines': len(lines),
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
            return ToolResult('练习文件不能超过2MiB；文件未修改。', is_error=True)
        diff = ''.join(difflib.unified_diff(before.splitlines(True), after.splitlines(True),
                                          fromfile='before/' + FILENAME, tofile='after/' + FILENAME))
        # No await between validation and replace: serialize a whole batch in the
        # Agent loop and never expose a half-written file to readers.
        fd, temporary = tempfile.mkstemp(prefix='.edit-', dir=self.root)
        try:
            with os.fdopen(fd, 'wb') as file:
                file.write(after.encode('utf-8'))
            os.replace(temporary, self.path)
        finally:
            Path(temporary).unlink(missing_ok=True)
        return ToolResult(json.dumps({'saved': True, 'edit_count': len(spans),
            'base_version': current, 'version': version(after), 'diff': diff}, ensure_ascii=False))

    async def grade(self):
        return evaluate(self.path.read_bytes().decode('utf-8'))
