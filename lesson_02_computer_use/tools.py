"""第一课工具声明与执行分发的完整实现：在第二课接入通用文件编辑。"""
from common.core.edit_tools import FileEditor
from common.core.types import ToolResult, ToolSpec


def get_tools(editor: FileEditor) -> list[ToolSpec]:
    """向模型声明搜索、分段读取和精确替换工具及参数。"""
    return editor.tools()


async def call_tool(name: str, arguments: dict, editor: FileEditor) -> ToolResult:
    """将模型选择的文件工具交给编辑器执行，保留原来的结果。"""
    if name in {'search_file', 'read_file', 'edit'}:
        return await editor.execute(name, arguments)
    return ToolResult('未知工具', is_error=True)
