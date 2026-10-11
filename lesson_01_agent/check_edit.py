"""Offline checks for the first exercise: register and dispatch an Edit tool."""
import argparse
import asyncio
from contextlib import redirect_stdout, redirect_stderr
import json
from pathlib import Path
import sys

from common.core.course_editor import EDIT_PARAMETERS
from common.core.student_loader import load_student_agent
from common.core.types import ExercisePending, ToolResult, ToolSpec
from lesson_01_agent.check import QuietOutput


async def check_definition(module):
    tools = module.get_tools()
    assert isinstance(tools, list) and len(tools) == 1, 'get_tools 返回一个只含 Edit 工具的列表。'
    tool = tools[0]
    assert isinstance(tool, ToolSpec) and tool.name == 'edit_course_file', '用 ToolSpec 声明 edit_course_file，名称必须与分发一致。'
    assert isinstance(tool.description, str) and tool.description.strip(), '用中文说明工具的用途与先读后改的要求。'
    assert tool.parameters == EDIT_PARAMETERS, '把已提供的 EDIT_PARAMETERS 作为工具参数定义。'


async def check_dispatch(module):
    calls = []
    expected = ToolResult('假编辑结果', is_error=True)
    class FakeEditor:
        async def execute(self, arguments):
            calls.append(arguments)
            return expected
    editor = FakeEditor()
    arguments = {'example': '原样传递'}
    result = await module.call_tool('edit_course_file', arguments, editor)
    assert calls == [arguments] and calls[0] is arguments, '等待 editor.execute(arguments)，原样传递参数。'
    assert result is expected, '返回原来的 ToolResult，保留成功或错误标记。'
    unknown = await module.call_tool('unknown_tool', {}, editor)
    assert isinstance(unknown, ToolResult) and unknown.is_error, '未知工具要返回错误 ToolResult。'
    assert len(calls) == 1, '未知工具不能执行编辑。'


async def inspect(module):
    checks = []
    for key, title, check in [('definition', '声明 Edit 工具', check_definition), ('dispatch', '连接编辑执行', check_dispatch)]:
        try:
            await check(module)
            status, detail = 'passed', '通过'
        except ExercisePending as exc:
            status, detail = 'pending', str(exc)
        except Exception as exc:
            status, detail = 'failed', f'{type(exc).__name__}: {exc}'
        checks.append({'id': 'edit-' + key, 'title': title, 'status': status, 'detail': detail[:1200]})
    failed = next((row for row in checks if row['status'] != 'passed'), None)
    return {'ready': failed is None, 'passed': sum(row['status'] == 'passed' for row in checks),
            'total': 2, 'checks': checks, 'detail': failed['detail'] if failed else 'Edit 接入通过，下一轮可直接编辑作业。'}


def main():
    parser = argparse.ArgumentParser(description='检查 Edit 接入：使用假编辑器，不修改文件、不调用模型。')
    parser.add_argument('--json', action='store_true')
    parser.add_argument('--source-stdin', action='store_true', help=argparse.SUPPRESS)
    args = parser.parse_args()
    path = Path(__file__).with_name('tools.py')
    try:
        with redirect_stdout(QuietOutput()), redirect_stderr(QuietOutput()):
            source = sys.stdin.read() if args.source_stdin else path.read_text(encoding='utf-8')
            result = asyncio.run(inspect(load_student_agent(source, path)))
    except Exception as exc:
        result = {'ready': False, 'passed': 0, 'total': 2, 'checks': [], 'detail': f'{type(exc).__name__}: {exc}'[:1200]}
    if args.json:
        print(json.dumps(result, ensure_ascii=False))
    else:
        for check in result['checks']:
            print(f"{check['title']} · {check['detail']}")
        print(result['detail'])
    raise SystemExit(0 if result['ready'] else 1)


if __name__ == '__main__':
    main()
