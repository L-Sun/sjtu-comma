"""Validate a scoped rename without executing untrusted edited source."""
import ast
from pathlib import Path

FILENAME = 'course_page.py'
BASELINE = (Path(__file__).parent / 'fixtures' / FILENAME).read_bytes().decode('utf-8')
TARGET_LINES = (1808, 2060, 3100)


def expected_source():
    lines = BASELINE.splitlines(keepends=True)
    for number in TARGET_LINES:
        lines[number - 1] = lines[number - 1].replace('format_title', 'format_course_title')
    return ''.join(lines)


def evaluate(source):
    expected = expected_source()
    checks = []
    try:
        tree = ast.parse(source)
        syntax_ok = True
    except (SyntaxError, ValueError, RecursionError):
        tree, syntax_ok = ast.Module(body=[], type_ignores=[]), False
    checks.append({'name': 'Python 语法有效', 'passed': syntax_ok})
    courses = [n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'CourseB']
    methods = {n.name: n for n in courses[0].body if isinstance(n, ast.FunctionDef)} if len(courses) == 1 else {}
    checks.append({'name': '课程 B 的函数定义已重命名',
                   'passed': 'format_course_title' in methods and 'format_title' not in methods})
    for name in ('render_card', 'render_outline'):
        calls = [n.func.attr for n in ast.walk(methods[name]) if isinstance(n, ast.Call)
                 and isinstance(n.func, ast.Attribute)] if name in methods else []
        checks.append({'name': f'课程 B 的 {name} 调用已同步', 'passed': calls == ['format_course_title']})
    before, after = BASELINE.splitlines(keepends=True), source.splitlines(keepends=True)
    checks.append({'name': '课程 A 逐字节不变', 'passed': before[:1699] == after[:1699]})
    checks.append({'name': '课程 C 逐字节不变', 'passed': before[3599:] == after[3599:]})
    # Equality to the canonical patch also catches whitespace or comment edits
    # on a target line: only the three identifiers may differ from the baseline.
    untouched = source == expected
    checks.append({'name': '除三处标识符外全部内容不变', 'passed': untouched})
    behavior = False
    if untouched:
        # Execute only the teacher-known canonical program after exact equality;
        # arbitrary model edits never reach exec.
        env = {'__name__': 'course_fixture'}
        exec(compile(expected, FILENAME, 'exec'), env)
        behavior = all(getattr(env[f'Course{letter}'](), method)('  Agent  ') == f'课程 {letter} · Agent'
                       for letter in 'ABC' for method in ('render_card', 'render_outline'))
    checks.append({'name': '三门课程的卡片和目录行为保持一致', 'passed': behavior})
    passed = sum(c['passed'] for c in checks)
    return {'status': 'pass' if passed == len(checks) else 'fail', 'passed': passed,
            'total': len(checks), 'cases': checks, 'line_count': len(after),
            'reason': '检查 B 的三处修改、其他内容逐字节不变及页面方法行为'}
