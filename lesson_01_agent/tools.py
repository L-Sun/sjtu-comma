"""第一课先做这一步：和教学 Chat 一起接入 Edit，再用它一起完成 Agent loop。

底层文件读写已提供；你负责把“模型能看见的工具定义”和“实际执行入口”接起来。
初始教学 Chat 只能列文件、读文件和检查。完成这里的两个函数，保存并检查，
下一轮就会出现 edit_course_file，可直接修改本课的 tools.py 和 agent.py。
"""
from common.core.course_editor import EDIT_PARAMETERS
from common.core.types import ExercisePending, ToolResult, ToolSpec


def get_tools() -> list[ToolSpec]:
    """TODO Edit.1：让模型知道有一个编辑工具。

    返回只包含一个 ToolSpec 的列表。
    ToolSpec 的三个参数依次是：
    - 工具名称："edit_course_file"（需要与下面的执行分发一致）。
    - 中文说明：编辑第一课作业；先读文件，再按当前版本精确替换。
    - 参数定义：EDIT_PARAMETERS（已提供，描述 path、base_version、edits）。
    这个函数只声明工具，不读写文件。
    """
    return [
        ToolSpec(
            name="edit_course_file",
            description="编辑第一课作业；先读文件，再按当前版本精确替换。",
            parameters=EDIT_PARAMETERS,
        )
    ]


async def call_tool(name: str, arguments: dict, editor) -> ToolResult:
    """TODO Edit.2：模型选中工具后，把请求交给实际执行程序。

    当 name 等于 "edit_course_file" 时：
    用 await editor.execute(arguments)，并返回原来的 ToolResult。
    其他名称：返回 ToolResult("未知工具", is_error=True)，不能执行编辑。

    editor 的版本检查、精确替换、备份与写入均已提供，不需要自己操作磁盘。
    你要理解：上一个函数只给模型看说明，这个函数才连接真正的执行。
    """
    if name == "edit_course_file":
        return await editor.execute(arguments)
    else:
        return ToolResult(f"未知工具: {name}", is_error=True)