"""Validate the same UI event contract in the lesson checker and live runtime."""
from common.core.types import Event, ToolResult


class EventContractError(ValueError):
    pass


def validate_event(event, *, serialized=False):
    if not isinstance(event, Event) or not isinstance(event.data, dict):
        raise EventContractError('context.emit 需要 Event(kind, 字典)。')
    data = event.data
    required = {
        'assistant': ('text',), 'error': ('text',),
        'tool_start': ('id', 'name', 'arguments'), 'tool_end': ('id', 'name', 'result'),
        'usage': (), 'status': (),
    }
    if event.kind not in required:
        raise EventContractError(f'不支持的事件类型：{event.kind}。请对照第一课 README 的事件格式。')
    missing = [key for key in required[event.kind] if key not in data]
    if missing:
        raise EventContractError(f'{event.kind} 事件缺少字段：{", ".join(missing)}；'
                                 f'收到字段：{", ".join(data)}。请对照第一课 README 的事件格式。')
    for key in ('id', 'name', 'text'):
        if key in data and not isinstance(data[key], str):
            raise EventContractError(f'{event.kind}.{key} 必须是字符串。')
    if event.kind == 'tool_start' and not isinstance(data['arguments'], (str, dict)):
        raise EventContractError('tool_start.arguments 必须是原始 JSON 字符串或参数字典。')
    if event.kind == 'tool_end':
        result = data['result']
        if serialized and isinstance(result, dict) and isinstance(result.get('text'), str):
            return
        if not isinstance(result, ToolResult) or not isinstance(result.text, str):
            raise EventContractError('tool_end.result 必须是执行工具后得到的 ToolResult，包含成功或失败结果。')
