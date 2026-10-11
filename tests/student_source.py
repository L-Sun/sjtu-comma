"""Create unfinished exercises in test copies without resetting the learner's work."""
import ast


def unfinished(source):
    lines = source.splitlines(keepends=True)
    for node in reversed(ast.parse(source).body):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        doc = ast.get_docstring(node) or ''
        if not doc.startswith('TODO '):
            continue
        if node.name == 'run_turn':
            support = next((item for item in node.body if isinstance(item, ast.With)), None)
            if support:
                first = support.body[0].lineno - 1
                lines[first:support.end_lineno] = [f'        raise ExercisePending({doc.splitlines()[0]!r})\n']
                continue
        first = node.body[0].end_lineno
        lines[first:node.end_lineno] = [f'    raise ExercisePending({doc.splitlines()[0]!r})\n']
    return ''.join(lines)
