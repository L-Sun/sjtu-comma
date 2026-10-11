"""TODO 2 — 实现同一个聊天 / 工具调用循环。

state.messages 保存模型历史；context.system_prompt 放到首条 system 消息。
把用户输入加入历史，然后 await context.complete(messages, tools, config)。
没有 tool_calls：发出 assistant 事件并结束。
有 tool_calls：顺序解析参数、执行 context.execute、写回对应 tool_call_id。
每个请求中的所有 tool_calls 都需收到结果，再请求模型。
ToolResult.images 需作为后续 user 图片消息传回，注明来自哪个工具调用。
错误也是工具结果；达到 max_rounds 停止；不要吞掉 asyncio.CancelledError。

事件例：context.emit(Event("assistant", {"text": "你好"}))。
完整事件契约见 docs/student/CONTRACT.md。第一步可先实现无工具的聊天分支。
"""
from common.core.types import AgentState, RunContext, ExercisePending


async def run_turn(user_text: str, state: AgentState, context: RunContext) -> None:
    raise ExercisePending("TODO 2 · 在 lesson_02_agent/agent.py 实现聊天和工具调用循环。")
