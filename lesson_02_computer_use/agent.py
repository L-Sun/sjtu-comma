"""第一课的标准实现，供第二课直接使用。

函数接口与第一课一致，四个辅助函数和 run_turn 循环均已补全。
"""
import json

from common.core.lesson_io import lesson_io

from common.core.types import AgentState, Event, ExercisePending, ModelReply, RunContext, ToolResult


# ── 第一课四个函数的标准实现 ──────────────────────────────


def remember_assistant_message(messages: list[dict], reply: ModelReply) -> None:
    """已完成：将模型的完整回复追加到历史中，无需返回值。

    reply.message 已经是一条可以直接加入 messages 的字典。
    不要只保存 reply.text：模型还可能在 message 中给出 tool_calls。
    例：reply.message == {"role": "assistant", "content": "你好！"}
    """
    messages.append(reply.message)


def parse_tool_arguments(call: dict) -> dict:
    """已完成：将工具参数的 JSON 字符串转换为 Python 字典。

    字符串位于 call["function"]["arguments"]，用 json.loads() 转换。
    例：'{"operation":"multiply","a":6,"b":7}' → 一个含三个键的字典。
    如果转换结果不是 dict，raise ValueError("工具参数必须是字典")。
    无效 JSON 的异常直接抛出；下面提供的循环会处理它。不使用 eval()。
    """
    arguments = json.loads(call["function"]["arguments"])
    if not isinstance(arguments, dict):
        raise ValueError("工具参数必须是字典")
    return arguments


async def execute_tool(name: str, arguments: dict, context: RunContext) -> ToolResult:
    """已完成：执行模型选择的工具，返回工具结果。

    使用 await context.execute(name, arguments)。这是实际执行工具的地方。
    name 可能是 calculate、get_current_time、read_file 等，不要硬编码工具名。
    返回原来的 ToolResult，不转成字符串，也不自己计算答案。
    工具报错时交给下面提供的循环处理，本函数不需要 try/except。
    """
    return await context.execute(name, arguments)


def make_tool_message(call_id: str, result: ToolResult) -> dict:
    """已完成：将工具结果包装成发给模型的消息，返回这个字典。

    消息有三个键：role 为 "tool"，tool_call_id 为传入的 call_id，
    content 为 JSON 字符串（使用 json.dumps(..., ensure_ascii=False)）。
    content 里面保存 {"is_error": result.is_error, "text": result.text}。
    成功和失败都要保留。这里不用修改历史，run_turn 会追加返回的消息。
    """
    return {
        "role": "tool",
        "tool_call_id": call_id,
        "content": json.dumps({"is_error": result.is_error, "text": result.text}, ensure_ascii=False),
    }


# ── 已提供的核心循环：第二课只需接入 cua.py ─────────────────────


async def run_turn(user_text: str | None, state: AgentState, context: RunContext) -> None:
    """第一课的核心循环标准实现"""
    # 已提供：复用历史；有新输入时只追加一次，点击继续时不追加。
    messages = state.messages
    if not messages:
        messages.append({"role": "system", "content": context.system_prompt})
    if user_text is not None:
        messages.append({"role": "user", "content": user_text})

    # 已提供：连接四个辅助函数中的解析和执行，处理网页展示与图片。
    with lesson_io(context, messages, parse_tool_arguments, execute_tool) as context:
        for _ in range(context.config.max_rounds):
            reply = await context.complete(messages, context.tools, context.config)
            remember_assistant_message(messages, reply)
            if not reply.tool_calls:
                return
            for call in reply.tool_calls:
                result = await context.run_tool(call)
                messages.append(make_tool_message(call["id"], result))
