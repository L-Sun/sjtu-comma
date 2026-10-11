"""Live, deterministic summaries of observed actions; never invented model reasoning."""
from __future__ import annotations

from dataclasses import dataclass, asdict
import json
import time

from common.core.records import redact
from common.core.types import Event, ToolResult


def short(value, limit=100):
    text = ' '.join(str(redact(value)).split())
    return text if len(text) <= limit else text[:limit - 1] + '…'


def object_value(value):
    if isinstance(value, dict):
        return value
    try:
        parsed = json.loads(value)
        return parsed if isinstance(parsed, dict) else {}
    except (ValueError, TypeError):
        return {}


def action_title(name, args):
    path = short(args.get('path', '文件'), 40)
    if name == 'search_file':
        suffix = f" · 第 {args['after_line']} 行之后" if args.get('after_line') else ''
        return f"搜索「{short(args.get('query', ''), 50)}」", path + suffix
    if name == 'list_files':
        return '列出课程文件', short(args.get('path', '.'), 40)
    if name == 'check_agent':
        return '检查自己的 Agent', '辅助函数 · 自己的 Agent loop'
    if name in {'read_file', 'read_course_file'}:
        return f"读取第 {args.get('start_line', 1)}–{args.get('end_line', 120)} 行", path
    if name in {'edit', 'edit_course_file'}:
        return f"修改 {len(args.get('edits', []))} 处代码", path + ' · 整批校验后写入'
    if name == 'bash':
        return '执行命令 · ' + short(args.get('command', ''), 90), ''
    if name == 'calculate':
        operator = {'add': '+', 'subtract': '−', 'multiply': '×', 'divide': '÷'}.get(args.get('operation'), '?')
        return f"计算 {args.get('a', '?')} {operator} {args.get('b', '?')}", ''
    if name == 'get_current_time':
        return '读取当前时间', ''
    if name == 'list_windows':
        return '查找应用窗口', ''
    if name == 'get_window_state':
        return '观察窗口', '获取当前界面'
    if name == 'click':
        target = f"位置 ({args['x']}, {args['y']})" if 'x' in args and 'y' in args else '已观察到的控件'
        return '点击' + target, ''
    if name == 'type_text':
        return f"输入「{short(args.get('text', ''), 45)}」", ''
    if name == 'press_key':
        return f"按键 {short(args.get('key', ''), 40)}", ''
    if name == 'hotkey':
        return '按快捷键 ' + short('+'.join(args.get('keys', [])), 40), ''
    if name == 'scroll':
        direction = {'up': '上', 'down': '下', 'left': '左', 'right': '右'}.get(args.get('direction'), '')
        return '向' + direction + '滚动', ''
    return '调用 ' + short(name, 40), ''


def result_summary(name, result):
    if isinstance(result, ToolResult):
        text, error, image_count = result.text, result.is_error, len(result.images)
    else:
        text = result.get('text', '')
        error = result.get('is_error', False)
        image_count = result.get('image_count', len(result.get('images', [])))
    data = object_value(text)
    if name == 'bash' and data:
        shell = data.get('shell', 'shell')
        if data.get('timed_out'):
            status, summary = 'error', f'{shell} · 命令超时，已请求停止进程'
        elif error:
            code = data.get("exit_code")
            outcome = f"退出码 {code}" if code is not None else "未启动"
            status, summary = 'error', f"{shell} · 执行失败 · {outcome}"
        else:
            status, summary = 'done', f"{shell} · 退出码 {data.get('exit_code', 0)}"
        preview = data.get('stderr') if error else data.get('stdout') or data.get('stderr')
        if preview:
            summary += ' · ' + short(preview, 100)
        if data.get('stdout_truncated') or data.get('stderr_truncated'):
            summary += ' · 输出已截断'
        return status, summary
    if error:
        if name == 'edit' and '不唯一、未匹配' in text:
            return 'error', '未匹配到唯一原文；整批未写入，需检查上下文和文本格式'
        if data:
            return 'error', short(data.get('hint') or data.get('error') or '工具返回错误，请检查参数')
        return 'error', short(text or '工具执行失败', 150)
    if name == 'list_files' and 'entries' in data:
        return 'done', f"{data.get('path', '.')} · 返回 {len(data['entries'])}/{data.get('total', '?')} 项"
    if name == 'read_course_file' and 'content' in data:
        return 'done', f"{data.get('path', '')} · 已读取 {len(data['content'].splitlines())} 行"
    if name == 'check_agent' and 'ready' in data:
        outcome = '全部通过，下轮使用我的 Agent' if data['ready'] else short(data.get('detail', '请继续完成作业'), 95)
        edit = data.get('edit')
        prefix = f"Edit {'已接入' if edit['ready'] else str(edit.get('passed', 0)) + '/2'} · Loop " if edit else ''
        return 'done', f"{prefix}{data.get('passed', 0)}/{data.get('total', 7)} 步通过 · {outcome}"
    if name == 'search_file' and 'matches' in data:
        lines = [str(m['line']) for m in data['matches'] if 'line' in m]
        if not lines:
            return 'done', '未找到匹配内容'
        more = ' · 还有结果，可继续翻页' if data.get('has_more') else ''
        return 'done', f"找到 {len(lines)} 处 · 第 {', '.join(lines[:8])}{'…' if len(lines) > 8 else ''} 行" + more
    if name == 'read_file' and 'content' in data:
        return 'done', f"已读取 {len(data['content'].splitlines())} 行 · 全文 {data.get('total_lines', '?')} 行"
    if name in {'edit', 'edit_course_file'} and data.get('saved'):
        return 'done', f"已写入 {data.get('edit_count', '?')} 处修改"
    if name == 'calculate' and 'result' in data:
        return 'done', '结果：' + short(data['result'])
    if name == 'list_windows' and 'windows' in data:
        windows = data['windows']
        names = list(dict.fromkeys(w.get('app_name') or w.get('title') or '未命名窗口' for w in windows))
        return 'done', f"找到 {len(windows)} 个窗口" + (' · ' + short('、'.join(names), 80) if names else '')
    if name == 'get_window_state':
        parts = []
        if image_count:
            parts.append(f'{image_count} 张截图')
        if 'element_count' in data or 'elements' in data:
            parts.append(f"{data.get('element_count', len(data.get('elements', [])))} 个可访问控件")
        if data.get('observation_warning') or data.get('degraded_reason'):
            return 'warning', '观察不完整 · ' + ('、'.join(parts) or '请检查返回内容')
        return 'done', '收到' + '、'.join(parts) if parts else '观察返回；未提供截图或控件数量'
    if name in {'click', 'type_text', 'press_key', 'hotkey', 'scroll'}:
        if data.get('effect') == 'confirmed':
            return 'done', '驱动确认动作生效 · 仍需观察任务结果'
        return 'warning', '动作已返回 · 需要再次观察确认效果'
    if data:
        return 'done', '工具已返回结果'
    return 'done', short(text or '工具已返回结果')


@dataclass
class Step:
    title: str
    detail: str = ''
    status: str = 'running'
    number: int = 0
    repeat_of: int | None = None
    repeat_count: int = 1
    started: float = 0
    duration: float | None = None

    tool: str = ''

    def public(self):
        data = asdict(self)
        data.pop('started')
        if data['duration'] is not None:
            data['duration'] = round(data['duration'], 3)
        return data


class TraceState:
    def __init__(self):
        self.steps: list[Step] = []
        self.pending = {}
        self.seen = {}
        self.call_count = self.error_count = self.tokens = self.turn_count = 0
        self.current = '就绪'

    def begin(self, prompt):
        self.turn_count += 1
        self.current = '等待模型响应'
        self.steps.append(Step(f'第 {self.turn_count} 轮 · {short(prompt, 100)}', status='note'))

    def feed(self, event):
        data = event.data
        if event.kind == 'tool_start':
            args = object_value(data.get('arguments', {}))
            name = data['name']
            title, detail = action_title(name, args)
            self.call_count += 1
            signature = name + json.dumps(args, sort_keys=True, ensure_ascii=False)
            first, count = self.seen.get(signature, (self.call_count, 0))
            self.seen[signature] = (first, count + 1)
            step = Step(title, detail if not count else '', number=self.call_count,
                        repeat_of=first if count else None, repeat_count=count + 1, started=time.monotonic(), tool=name)
            self.pending[data['id']] = (len(self.steps), name)
            self.steps.append(step)
            self.current = title
        elif event.kind == 'tool_end':
            found = self.pending.pop(data['id'], None)
            if found is None:
                return
            index, name = found
            step = self.steps[index]
            step.status, step.detail = result_summary(name, data['result'])
            step.duration = time.monotonic() - step.started
            if step.status == 'error':
                self.error_count += 1
            self.current = '等待模型继续' if not self.pending else '等待其余工具返回'
        elif event.kind == 'usage':
            value = data.get('total_tokens')
            if isinstance(value, (int, float)):
                self.tokens += int(value)
        elif event.kind == 'status':
            self.current = short(data.get('text', ''), 120)
            if data.get('capability_unavailable'):
                self.steps.append(Step('电脑能力未接通', self.current, status='warning'))
        elif event.kind == 'assistant':
            self.current = '已收到模型回复'
        elif event.kind == 'error':
            self.current = '本轮执行出错'
            self.steps.append(Step('执行出错', short(data.get('text', ''), 180), status='error'))

    def finish(self, record):
        status = record.get('status', 'error')
        for index, _ in self.pending.values():
            self.steps[index].status = 'stopped'
            self.steps[index].detail = '未收到工具结果；实际执行效果未知'
        self.pending.clear()
        labels = {'completed': '本轮结束', 'cancelled': '已停止', 'timeout': '本轮超时',
                  'limit': '达到轮次上限', 'error': '本轮出错'}
        title = labels.get(status, '本轮结束')
        grade = record.get('grade', {})
        if grade.get('status') == 'fail':
            title += ' · 验收未通过'
        elif grade.get('status') == 'pass':
            title += ' · 验收通过'
        elif grade.get('status') == 'manual':
            title += ' · 结果需人工确认'
        detail = f"{record.get('elapsed_seconds', 0):.1f}s · {record.get('tool_calls', 0)} 次工具调用"
        if 'passed' in grade and 'total' in grade:
            detail += f" · 验收 {grade['passed']}/{grade['total']}"
        state = 'warning' if grade.get('status') == 'fail' or status != 'completed' else 'note'
        self.steps.append(Step(title, detail, status=state))
        self.current = title

    @property
    def summary(self):
        tokens = f'{self.tokens / 1000:.1f}k' if self.tokens >= 1000 else str(self.tokens)
        return f'{self.current}\n{self.call_count} 次调用 · {self.error_count} 次错误 · {tokens} tokens'


    def public(self):
        return {'current': self.current, 'calls': self.call_count, 'errors': self.error_count,
                'tokens': self.tokens, 'steps': [step.public() for step in self.steps]}


def replay_trace(record):
    state = TraceState()
    for event in record.get('events', []):
        if event['kind'] == 'user':
            state.begin(event['data']['text'])
        else:
            state.feed(Event(event['kind'], event['data']))
    state.finish(record)
    for step in state.steps:
        step.duration = None  # Old records have no per-event timestamps.
    return state
