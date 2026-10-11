import json
import pytest
from common.core.edit_tools import EditWorkspace, BASELINE, FILENAME, version
from common.core.editor_eval import evaluate, expected_source, TARGET_LINES


def patches():
    lines = BASELINE.splitlines(keepends=True)
    result = []
    for number in TARGET_LINES:
        old = ''.join(lines[number-3:number])
        result.append({'old_text': old, 'new_text': old.replace('format_title', 'format_course_title')})
    return result


def request(edits=None, base=None):
    return {'path': FILENAME, 'base_version': base or version(BASELINE), 'edits': edits if edits is not None else patches()}


async def test_long_file_search_read_and_atomic_edit(tmp_path):
    editor = EditWorkspace(tmp_path)
    assert len(BASELINE.splitlines()) == 5000
    result = json.loads((await editor.execute('search_file', {'path': FILENAME, 'query': 'def format_title'})).text)
    assert [m['line'] for m in result['matches']] == [108, 1808, 3808]
    assert result['version'] == version(BASELINE)
    result = json.loads((await editor.execute('read_file', {'path': FILENAME, 'start_line': 1807, 'end_line': 1809})).text)
    assert '1808:     def format_title' in result['content']
    assert (await editor.execute('read_file', {'path': FILENAME, 'start_line': 1, 'end_line': 5000})).is_error
    r = await editor.execute('edit', request())
    assert json.loads(r.text)['edit_count'] == 3
    assert editor.path.read_bytes() == expected_source().encode('utf-8')
    assert (await editor.grade())['passed'] == 8


async def test_invalid_batch_never_partially_writes(tmp_path):
    editor = EditWorkspace(tmp_path)
    for bad in [{'old_text': '', 'new_text': 'x'}, {'old_text': 'missing', 'new_text': 'x'},
                {'old_text': 'format_title', 'new_text': 'format_course_title'}]:
        result = await editor.execute('edit', request([patches()[0], bad]))
        assert result.is_error
        assert editor.path.read_bytes() == BASELINE.encode('utf-8')
    assert (await editor.execute('edit', {**request(), 'path': '../secret'})).is_error


async def test_stale_version_and_overlapping_hunks_rejected(tmp_path):
    editor = EditWorkspace(tmp_path)
    assert (await editor.execute('edit', request([patches()[0], patches()[0]]))).is_error
    assert not (await editor.execute('edit', request())).is_error
    after = editor.path.read_bytes()
    assert (await editor.execute('edit', request())).is_error
    assert editor.path.read_bytes() == after


async def test_failed_replace_preserves_original_and_cleans_temp(tmp_path, monkeypatch):
    editor = EditWorkspace(tmp_path)
    def fail(*args):
        raise OSError('simulated write failure')
    monkeypatch.setattr('common.core.edit_tools.os.replace', fail)
    with pytest.raises(OSError):
        await editor.execute('edit', request())
    assert editor.path.read_bytes() == BASELINE.encode('utf-8')
    assert sorted(p.name for p in tmp_path.iterdir()) == [FILENAME]


def test_grader_detects_global_replace_missed_call_and_unrelated_change():
    assert evaluate(expected_source())['passed'] == 8
    assert evaluate(BASELINE)['status'] == 'fail'
    for changed in (BASELINE.replace('format_title', 'format_course_title'),
                    expected_source().replace('课程 A ·', '课程 AA ·'),
                    expected_source().replace('    section_0022', '    changed_0022'),
                    BASELINE.replace(patches()[0]['old_text'], patches()[0]['new_text'])):
        assert evaluate(changed)['status'] == 'fail'


def test_grader_never_executes_unexpected_source():
    malicious = expected_source() + '\nraise RuntimeError("must not execute")\n'
    grade = evaluate(malicious)
    assert grade['status'] == 'fail'
    assert not grade['cases'][-1]['passed']


async def test_search_pagination(tmp_path):
    editor = EditWorkspace(tmp_path)
    first = json.loads((await editor.execute('search_file', {'path': FILENAME, 'query': 'section_'})).text)
    second = json.loads((await editor.execute('search_file', {'path': FILENAME, 'query': 'section_',
        'after_line': first['next_after_line']})).text)
    assert len(first['matches']) == 20 and first['has_more']
    assert first['matches'][-1]['line'] < second['matches'][0]['line']
