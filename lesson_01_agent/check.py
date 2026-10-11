"""第一课的离线检查器：不需要 API Key，不联网，不执行本机命令。

在项目根目录运行：uv run python -m lesson_01_agent.check 1
省略数字会检查全部步骤。这个文件已提供，学生无需修改。
"""
import argparse
import asyncio
from copy import deepcopy
import json

from common.core.config import Config
from common.core.types import AgentState, ExercisePending, ModelReply, RunContext, ToolResult
from pathlib import Path
import sys

from common.core.student_loader import load_student_agent


def context_for(complete=None, execute=None, events=None):
    return RunContext(Config(lesson=1, max_rounds=4), [], complete, execute,
                      events.append if events is not None else lambda event: None,
                      "你是课堂助手")


async def check_reply(module):
    messages = [{"role": "user", "content": "算一下"}]
    reply = ModelReply({"role": "assistant", "content": None, "tool_calls": [tool_call()],
                        "reasoning_details": [{"type": "example", "data": "保留这个字段"}]})
    module.remember_assistant_message(messages, reply)
    assert len(messages) == 2 and messages[-1] == reply.message, "保存完整 reply.message，不能只存文本或遗漏 tool_calls 等字段。"


def tool_call(arguments='{"operation":"multiply","a":6,"b":7}'):
    return {"id": "call-1", "type": "function", "function": {"name": "calculate", "arguments": arguments}}


async def check_arguments(module):
    arguments = module.parse_tool_arguments(tool_call())
    assert arguments == {"operation": "multiply", "a": 6, "b": 7}, "使用 json.loads 将 arguments 字符串变成字典，不是 json.dumps。"
    for invalid in ["not JSON", "[1, 2]", "null"]:
        try:
            module.parse_tool_arguments(tool_call(invalid))
        except ValueError:
            continue
        raise AssertionError("无效 JSON 或非字典参数应抛出 ValueError，不能静默返回空字典。")


async def check_execution(module):
    calls = []
    expected = ToolResult("示例工具结果", is_error=True)
    async def fake_tool(name, arguments):
        calls.append((name, arguments))
        return expected
    arguments = {"example": 123}
    result = await module.execute_tool("some_tool", arguments, context_for(execute=fake_tool))
    assert calls == [("some_tool", arguments)], "把传入的工具名和参数交给 context.execute，不要只支持 calculate。"
    assert result is expected, "返回原来的 ToolResult，保留 text、is_error 和 images。"


async def check_tool_message(module):
    for failed in [False, True]:
        result = ToolResult("结果或错误：示例", is_error=failed)
        message = module.make_tool_message("call-123", result)
        assert isinstance(message, dict), "make_tool_message 应返回字典。"
        assert message.get("role") == "tool" and message.get("tool_call_id") == "call-123", "role 为 tool；tool_call_id 必须原样对应传入的 ID。"
        assert isinstance(message.get("content"), str), "content 必须是 json.dumps 得到的字符串。"
        assert json.loads(message["content"]) == {"is_error": failed, "text": result.text}, "content 中应保留工具文本和成功/失败标记。"


async def check_chat(module):
    snapshots, events = [], []
    async def fake_model(messages, tools, config):
        assert messages is state.messages and tools is context.tools and config is context.config, "在循环中将原来的 messages、context.tools、context.config 传给 context.complete。"
        snapshots.append(deepcopy(messages))
        return ModelReply({"role": "assistant", "content": "你好！"})
    state = AgentState()
    context = context_for(complete=fake_model, events=events)
    await module.run_turn("第一句话", state, context)
    await module.run_turn("第二句话", state, context)
    assert len(snapshots) == 2, "无工具调用时应结束当前回合，不再请求模型。"
    assert [m["role"] for m in snapshots[-1]] == ["system", "user", "assistant", "user"], "第二轮要保留第一轮问答，且 system 只出现一次。"
    assert snapshots[0] == [
        {"role": "system", "content": context.system_prompt},
        {"role": "user", "content": "第一句话"},
    ], "第一次请求应包含 system 和当前用户输入。"
    assert snapshots[-1][1]["content"] == "第一句话", "第一轮输入丢失了。"
    assert snapshots[-1][-1] == {"role": "user", "content": "第二句话"}, "每轮应追加当前用户输入。"
    assert len([e for e in events if e.kind == "assistant"]) == 2, "每个回合的回复都应显示在界面。"


async def check_tool_roundtrip(module):
    snapshots, calls, events = [], [], []
    async def fake_model(messages, tools, config):
        snapshots.append(deepcopy(messages))
        if len(snapshots) == 1:
            return ModelReply({"role": "assistant", "content": "我来计算", "tool_calls": [tool_call()]})
        return ModelReply({"role": "assistant", "content": "42"})
    async def fake_tool(name, arguments):
        calls.append((name, arguments))
        return ToolResult("42")
    state = AgentState()
    await module.run_turn("计算 6 × 7", state, context_for(fake_model, fake_tool, events))
    assert len(snapshots) == 2, "工具执行完之后，要带着工具结果再问一次模型。"
    assert calls == [("calculate", {"operation": "multiply", "a": 6, "b": 7})], "工具名、解析后的参数或实际执行次数不正确。"
    assert [m["role"] for m in snapshots[1]] == ["system", "user", "assistant", "tool"], "模型的调用请求在前，对应 tool 结果在后，然后才再次请求模型。"
    tool_message = snapshots[1][-1]
    assert tool_message["tool_call_id"] == "call-1" and json.loads(tool_message["content"])["text"] == "42", "工具结果没有正确交回模型。"
    assert state.messages[-1] == {"role": "assistant", "content": "42"}, "最终回复也需要保存在历史中。"
    assert any(e.kind == "assistant" and e.data["text"] == "42" for e in events), "最终回复没有显示给用户。"
    assert [e.kind for e in events if e.kind.startswith('tool_')] == ['tool_start', 'tool_end'], "执行工具前后都要发送事件，网页才能显示真实调用。"
    assert len([e for e in events if e.kind == 'usage']) == 2, "每次模型回复都要发送 usage 事件。"


async def check_tool_batch_and_errors(module):
    requests, calls, events = [], [], []
    batch = [tool_call('bad JSON'), tool_call(), tool_call()]
    for index, call in enumerate(batch):
        call['id'] = f'batch-{index}'
    async def model(messages, tools, config):
        requests.append(deepcopy(messages))
        if len(requests) == 1:
            return ModelReply({'role': 'assistant', 'content': None, 'tool_calls': batch})
        return ModelReply({'role': 'assistant', 'content': '已处理工具结果'})
    async def tool(name, args):
        calls.append(name)
        if len(calls) == 1:
            raise RuntimeError('练习工具暂不可用')
        return ToolResult('42')
    await module.run_turn('批量练习', AgentState(), context_for(model, tool, events))
    assert len(requests) == 2 and len(calls) == 2, '逐个处理所有工具调用；无效参数不要执行，单个错误不能跳过其余调用。'
    results = [m for m in requests[1] if m['role'] == 'tool']
    assert [m['tool_call_id'] for m in results] == ['batch-0', 'batch-1', 'batch-2'], '每个工具调用都必须写回对应结果，然后才再次请求模型。'
    assert [json.loads(m['content'])['is_error'] for m in results] == [True, True, False], '参数错误和工具异常都要作为错误结果交回模型。'
    assert len([e for e in events if e.kind == 'tool_end']) == 3, '成功和失败的工具都应有 tool_end 事件。'


async def check_loop_limit(module):
    requests, events = [], []
    async def model(messages, tools, config):
        requests.append(True)
        assert len(requests) <= config.max_rounds, '达到 max_rounds 后必须结束，不能继续请求模型。'
        return ModelReply({'role': 'assistant', 'content': None, 'tool_calls': [tool_call()]})
    async def tool(name, args):
        return ToolResult('42')
    context = context_for(model, tool, events)
    context.config.max_rounds = 2
    await module.run_turn('持续调用工具', AgentState(), context)
    assert len(requests) == 2, '有工具请求时继续循环，直到回答或轮数上限。'
    assert any(e.kind == 'status' and e.data.get('limit') for e in events), '达到上限时发送 status 事件，并设置 limit=True。'


async def check_loop_stop(module):
    for error in (ExercisePending('练习尚未完成'), asyncio.CancelledError()):
        async def model(messages, tools, config):
            return ModelReply({'role': 'assistant', 'content': None, 'tool_calls': [tool_call()]})
        async def tool(name, args):
            raise error
        try:
            await module.run_turn('停止练习', AgentState(), context_for(model, tool))
        except type(error):
            continue
        raise AssertionError('不能把 ExercisePending 或 CancelledError 转成普通工具结果；必须重新抛出。')


async def check_loop(module):
    """Step 5 is the student's control flow, including its stopping conditions."""
    await check_tool_roundtrip(module)
    await check_tool_batch_and_errors(module)
    await check_loop_limit(module)
    await check_loop_stop(module)


CHECKS = {
    "1": ("保存模型回复", check_reply),
    "2": ("解析工具参数", check_arguments),
    "3": ("执行工具", check_execution),
    "4": ("包装工具结果", check_tool_message),
    "chat": ("无工具退出与多轮历史（run_turn 分支检查）", check_chat),
    "loop": ("第 5 步 · run_turn（循环、批量工具、错误、上限、停止）", check_loop),
}


async def run_checks(module, step="all"):
    step = "loop" if step == "5" else step
    for number in (CHECKS if step == "all" else [step]):
        title, check = CHECKS[number]
        print(f"检查 {number} · {title}")
        await check(module)
        print("  通过")


async def inspect_checks(module):
    """Structured results for the teaching Chat; every check uses fake dependencies."""
    results = []
    for number, (title, check) in CHECKS.items():
        try:
            await check(module)
            status, detail = 'passed', '通过'
        except ExercisePending as exc:
            status, detail = 'pending', str(exc)
        except Exception as exc:
            status, detail = 'failed', f'{type(exc).__name__}: {exc}'
        results.append({'id': number, 'title': title, 'status': status, 'detail': detail[:1200]})
    failed = next((row for row in results if row['status'] != 'passed'), None)
    loop_ready = all(row['status'] == 'passed' for row in results if row['id'] in {'chat', 'loop'})
    return {'ready': failed is None,
            'passed': sum(row['status'] == 'passed' for row in results if row['id'].isdigit()) + int(loop_ready),
            'total': 5, 'checks': results,
            'detail': failed['detail'] if failed else '四个辅助函数与自己实现的 Agent loop 全部通过。'}


class QuietOutput:
    # Student print() calls should not corrupt JSON or grow an unbounded buffer.
    def write(self, value):
        return len(value)
    def flush(self):
        pass


def main():
    parser = argparse.ArgumentParser(description="第一课离线检查：不联网、不调用真实模型或电脑。")
    parser.add_argument("step", nargs="?", default="all", choices=[*CHECKS, "5", "all"],
                        help="1—4 检查辅助函数；5 或 loop 检查自己写的循环；chat 检查聊天；默认全部")
    parser.add_argument('--json', action='store_true', help='输出逐项检查结果，供工作台读取')
    parser.add_argument('--source-stdin', action='store_true', help=argparse.SUPPRESS)
    args = parser.parse_args()
    path = Path(__file__).with_name('agent.py')
    if args.json:
        from contextlib import redirect_stdout, redirect_stderr
        try:
            with redirect_stdout(QuietOutput()), redirect_stderr(QuietOutput()):
                source = sys.stdin.read() if args.source_stdin else path.read_text(encoding='utf-8')
                module = load_student_agent(source, path)
                result = asyncio.run(inspect_checks(module))
        except Exception as exc:
            result = {'ready': False, 'passed': 0, 'total': 5, 'checks': [],
                      'detail': f'{type(exc).__name__}: {exc}'[:1200]}
        print(json.dumps(result, ensure_ascii=False))
        raise SystemExit(0 if result['ready'] else 1)
    try:
        module = load_student_agent(path.read_text(encoding='utf-8'), path)
        asyncio.run(run_checks(module, args.step))
    except ExercisePending as exc:
        print(f"待完成：{exc}\n请填写对应函数，保存文件后重新运行同一命令。")
        raise SystemExit(1)
    except Exception as exc:
        print(f"检查未通过 · {type(exc).__name__}: {exc}\n请对照 README 的对应步骤检查 agent.py。")
        raise SystemExit(1)
    print("所选检查全部通过。下一步见 README。")


if __name__ == "__main__":
    main()
