"""Create unfinished exercises in test copies without resetting the learner's work."""
import ast


def unfinished(source):
    lines = source.splitlines(keepends=True)
    needs_pending_import = False
    for node in reversed(ast.parse(source).body):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        doc = ast.get_docstring(node) or ''
        if not doc.startswith('TODO '):
            # Learners may replace tools.py with an implementation without docstrings.
            # Keep test copies unfinished independently of their current exercise work.
            label = {'get_tools': 'TODO Edit.1：声明编辑工具。',
                     'call_tool': 'TODO Edit.2：连接工具执行。'}.get(node.name)
            if label:
                first = node.body[0].lineno - 1
                lines[first:node.end_lineno] = [f'    raise ExercisePending({label!r})\n']
                needs_pending_import = True
            continue
        if node.name == 'run_turn':
            support = next((item for item in node.body if isinstance(item, ast.With)), None)
            if support:
                first = support.body[0].lineno - 1
                lines[first:support.end_lineno] = [f'        raise ExercisePending({doc.splitlines()[0]!r})\n']
                continue
        first = node.body[0].end_lineno
        lines[first:node.end_lineno] = [f'    raise ExercisePending({doc.splitlines()[0]!r})\n']
    if needs_pending_import:
        lines.append('\nfrom common.core.types import ExercisePending\n')
    return ''.join(lines)
