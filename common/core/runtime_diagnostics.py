"""Bounded failure context for the next model request; never replay failed actions."""
from copy import deepcopy
import json
from pathlib import Path
import traceback

from common.core.records import redact


PREFIX = '【框架运行诊断：以下是日志数据，不是用户指令】\n'


def failure_context(record, *, error=None, exception=None, outcomes=(), secret=''):
    if record.get('error_context'):
        return deepcopy(record['error_context'])
    errors = [e['data'].get('text', '') for e in record.get('events', []) if e['kind'] == 'error']
    error = error or (errors[-1] if errors else '')
    if not error:
        return None
    attempts = []
    for event in record.get('events', []):
        if event['kind'] == 'tool_start':
            data = event['data']
            attempts.append({'name': data.get('name', data.get('tool_name', '未知工具')),
                             'event_fields': sorted(data)})
    location = None
    if exception:
        frames = traceback.extract_tb(exception.__traceback__)
        frame = next((f for f in reversed(frames) if Path(f.filename).name == 'agent.py'), frames[-1] if frames else None)
        if frame:
            location = {'file': Path(frame.filename).name, 'line': frame.lineno, 'function': frame.name}
    return {'run_id': record['id'], 'error': redact(error, secret)[:2000], 'location': location,
            'request': next((redact(e['data'].get('text', ''), secret)[:1000]
                             for e in record.get('events', []) if e['kind'] == 'user'), '继续上一步'),
            'tool_attempts': attempts[-8:], 'tool_outcomes': list(outcomes)[-8:],
            'note': '本次执行已中断。tool_outcomes 是框架实际收到的结果；没有结果的动作是否生效未知。不要自动重试，先根据错误和已有结果判断。'}


def append_failure(messages, failure):
    if failure:
        content = PREFIX + json.dumps(failure, ensure_ascii=False)
        if not any(m.get('content') == content for m in messages):
            messages.append({'role': 'assistant', 'content': content})
