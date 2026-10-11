"""TODO 3 — 通过提供的 MCP session 接入 Cua Driver。

list_tools: await session.list_tools() → 用 name/description/inputSchema 构造 ToolSpec。
call_tool: await session.call_tool(name, arguments) → 返回其 model_dump() 字典。
保留 content 的 text/image、structuredContent、isError，不要丢掉图片。
模式筛选与实验隔离由框架执行，学生不需要修改 Web 或 policy。
"""
from common.core.types import ToolSpec, ExercisePending


async def list_tools(session) -> list[ToolSpec]:
    raise ExercisePending("TODO 3a · 在 lesson_03_computer_use/cua.py 获取并转换 MCP 工具列表。")


async def call_tool(session, name: str, arguments: dict) -> dict:
    raise ExercisePending("TODO 3b · 在 lesson_03_computer_use/cua.py 调用 MCP 工具并保留多模态结果。")
