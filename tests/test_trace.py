import json


from common.app.trace import TraceState, result_summary
from common.core.types import Event, ToolResult


def start(state, call_id='a', name='search_file', args=None):
    state.feed(Event('tool_start', {'id': call_id, 'name': name,
        'arguments': json.dumps(args or {'path': 'course_page.py', 'query': 'CourseB'})}))


def end(state, call_id='a', name='search_file', result=None):
    state.feed(Event('tool_end', {'id': call_id, 'name': name,
        'result': result or ToolResult('{"matches":[{"line":1700}],"version":"hidden-hash"}')}))


def test_live_step_updates_and_repeats_keep_order():
    state = TraceState()
    state.begin('修改课程 B')
    start(state)
    assert state.steps[-1].status == 'running'
    end(state)
    assert state.steps[-1].status == 'done'
    assert '1700' in state.steps[-1].detail
    assert len(state.steps) == 2  # Update in place, not a second result row.
    start(state, 'b', 'read_file', {'path': 'course_page.py', 'start_line': 1700, 'end_line': 1702})
    end(state, 'b', 'read_file', ToolResult('{"content":"1700: class CourseB:\\n1701: pass","total_lines":5000}'))
    start(state, 'c')
    assert state.steps[-1].repeat_of == 1
    assert state.steps[-1].repeat_count == 2
    assert 'hidden-hash' not in str(state.public())


def test_failed_edit_never_claims_write_and_finish_is_not_success():
    state = TraceState()
    start(state, name='edit', args={'edits': [{'old_text': 'x', 'new_text': 'y'}]})
    end(state, name='edit', result=ToolResult('第1处替换不唯一、未匹配或过长；整批未写入。', is_error=True))
    assert state.error_count == 1
    assert state.steps[-1].status == 'error'
    assert '未写入' in state.steps[-1].detail
    state.finish({'status': 'completed', 'grade': {'status': 'fail', 'passed': 3, 'total': 8}})
    assert '验收未通过' in state.steps[-1].title


def test_out_of_order_results_and_cancel_pending_action():
    state = TraceState()
    start(state, 'a')
    start(state, 'b')
    end(state, 'b')
    assert state.steps[0].status == 'running'
    assert state.steps[1].status == 'done'
    state.finish({'status': 'cancelled'})
    assert state.steps[0].status == 'stopped'
    assert '效果未知' in state.steps[0].detail
    assert not state.pending


def test_unverified_computer_action_is_not_success():
    status, text = result_summary('click', ToolResult('{"effect":"unverifiable"}'))
    assert status == 'warning' and '确认' in text
    status, text = result_summary('get_window_state', {
        'text': '{"element_count":12}', 'image_count': 1})
    assert status == 'done' and '1 张截图' in text and '12 个' in text
    assert result_summary('get_window_state', ToolResult('{"observation_warning":"missing"}'))[0] == 'warning'


def test_public_summary_contains_no_raw_source_or_hash():
    state = TraceState()
    start(state)
    assert state.public()['steps'][-1]['status'] == 'running'
    end(state, result=ToolResult('{"matches":[{"line":1700,"context":"raw-source"}],"version":"hidden-hash"}'))
    result = state.public()
    assert result['calls'] == 1 and result['steps'][-1]['status'] == 'done'
    assert 'raw-source' not in str(result) and 'hidden-hash' not in str(result)
    assert 'started' not in result['steps'][-1]
