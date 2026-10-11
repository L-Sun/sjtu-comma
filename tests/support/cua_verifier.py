from common.core.types import ToolSpec


async def list_tools(session):
    result = await session.list_tools()
    return [ToolSpec(t.name, t.description or "", t.inputSchema) for t in result.tools]


async def call_tool(session, name, arguments):
    return (await session.call_tool(name, arguments)).model_dump(mode="json", exclude_none=True)
