"""第一课：和教学 Chat 一起完成 4 个辅助函数，以及第 5 步 Agent loop。

从 README.md 开始，先与 Chat 完成 tools.py 的 Edit 接入，再用它一起修改这里。
四个辅助函数作为一个阶段完成，再写核心循环。编辑后自动检查；网页和图片处理已提供。
"""
import json

from common.core.lesson_io import context_compaction, lesson_io

from common.core.types import AgentState, ExercisePending, ModelReply, RunContext, ToolResult


# ── 学生填写区：阶段二一起完成四个函数；阶段三实现 run_turn ──────────────────────────────


def remember_assistant_message(messages: list[dict], reply: ModelReply) -> None:
    """TODO 1.1：将模型的完整回复追加到历史中，无需返回值。

    reply.message 已经是一条可以直接加入 messages 的字典。
    不要只保存 reply.text：模型还可能在 message 中给出 tool_calls。
    例：reply.message == {"role": "assistant", "content": "你好！"}
    """
    raise ExercisePending("TODO 1.1 · 完成 remember_assistant_message：保存完整回复。")


def parse_tool_arguments(call: dict) -> dict:
    """TODO 1.2：将工具参数的 JSON 字符串转换为 Python 字典。

    字符串位于 call["function"]["arguments"]，用 json.loads() 转换。
    例：'{"operation":"multiply","a":6,"b":7}' → 一个含三个键的字典。
    如果转换结果不是 dict，raise ValueError("工具参数必须是字典")。
    无效 JSON 的异常直接抛出；已提供的 context.run_tool 会处理它。不使用 eval()。
    """
    raise ExercisePending("TODO 1.2 · 完成 parse_tool_arguments：读取工具参数。")


async def execute_tool(name: str, arguments: dict, context: RunContext) -> ToolResult:
    """TODO 1.3：执行模型选择的工具，返回工具结果。

    使用 await context.execute(name, arguments)。这是实际执行工具的地方。
    name 可能是 calculate、get_current_time、read_file 等，不要硬编码工具名。
    返回原来的 ToolResult，不转成字符串，也不自己计算答案。
    错误转换由已提供的 context.run_tool 处理，本函数不需要 try/except。
    """
    raise ExercisePending("TODO 1.3 · 完成 execute_tool：等待并返回工具结果。")


def make_tool_message(call_id: str, result: ToolResult) -> dict:
    """TODO 1.4：将工具结果包装成发给模型的消息，返回这个字典。

    消息有三个键：role 为 "tool"，tool_call_id 为传入的 call_id，
    content 为 JSON 字符串（使用 json.dumps(..., ensure_ascii=False)）。
    content 里面保存 {"is_error": result.is_error, "text": result.text}。
    成功和失败都要保留。这里不用修改历史，run_turn 会追加返回的消息。
    """
    raise ExercisePending("TODO 1.4 · 完成 make_tool_message：把结果交回模型。")


# ── 可选扩展：上下文压缩 ──────────────────────────────────────


@context_compaction
async def compact_history(messages: list[dict], context: RunContext) -> None:
    """扩展练习：按需压缩 messages，在原列表上修改；默认留空，不发起模型请求。

    保留 system、当前任务和完整的工具调用/结果配对。
    自己决定何时需要压缩；不需要时直接返回。不要每次都循环请求摘要。
    调用时的网页进度由 @context_compaction 提供，不需要编写 Event 或 emit。
    """
    pass


# ── 阶段三：自己实现核心 Agent loop ─────────────────────────────


async def run_turn(user_text: str | None, state: AgentState, context: RunContext) -> None:
    """TODO 1.5：自己实现“请求模型 → 执行工具 → 回传结果 → 再请求模型”。

    前四个辅助函数一起完成后，再实现这个循环。保留下面已提供的准备代码。
    在 with 块中替换 TODO，循环体由你和 Chat 编写：
    1. 用 for 最多循环 context.config.max_rounds 次。
    2. reply = await context.complete(messages, context.tools, context.config)
       再调用 remember_assistant_message(messages, reply) 保存完整回复。
    3. 如果 reply.tool_calls 为空，return 结束；有文字不代表没有工具调用。
    4. 遍历 reply.tool_calls 中的每个 call：
       result = await context.run_tool(call)
       把 make_tool_message(call["id"], result) 返回的字典追加到 messages。
    5. 所有结果放回历史后，开始下一次模型请求。

    context.run_tool 已接好你写的 parse_tool_arguments 和 execute_tool，
    会将普通错误变成 ToolResult；停止信号和未完成提示会自动向外传递。
    lesson_io 提供网页事件、用量、图片和到达上限的提示；不需要编写 emit、
    Event、try/except 或图片处理。它不会替你请求模型、遍历工具或写回工具结果。
    """
    # 已提供：复用历史；有新输入时只追加一次，点击继续时不追加。
    messages = state.messages
    if not messages:
        messages.append({"role": "system", "content": context.system_prompt})
    if user_text is not None:
        messages.append({"role": "user", "content": user_text})

    # 已提供：调用可选压缩函数；空实现不修改历史、不请求模型。
    await compact_history(messages, context)

    # 已提供：连接四个辅助函数中的解析和执行，处理网页展示与图片。
    with lesson_io(context, messages, parse_tool_arguments, execute_tool) as context:
        raise ExercisePending('TODO 1.5：自己实现“请求模型 → 执行工具 → 回传结果 → 再请求模型”。')
