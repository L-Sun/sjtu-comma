import json
import math
from datetime import datetime
from common.core.types import ToolSpec, ToolResult


def basic_tools() -> list[ToolSpec]:
    return [
        ToolSpec("calculate", "执行一次加、减、乘、除。每次只执行一个运算。", {
            "type": "object", "properties": {
                "operation": {"type": "string", "enum": ["add", "subtract", "multiply", "divide"]},
                "a": {"type": "number"}, "b": {"type": "number"},
            }, "required": ["operation", "a", "b"], "additionalProperties": False,
        }),
        ToolSpec("get_current_time", "读取电脑当前时间与时区。", {
            "type": "object", "properties": {}, "additionalProperties": False,
        }),
    ]


async def execute_basic(name: str, arguments: dict) -> ToolResult:
    if name == "get_current_time":
        return ToolResult(datetime.now().astimezone().isoformat())
    if name != "calculate":
        return ToolResult("Unknown tool", is_error=True)
    a, b = arguments["a"], arguments["b"]
    try:
        answer = {"add": lambda: a + b, "subtract": lambda: a - b,
                  "multiply": lambda: a * b, "divide": lambda: a / b}[arguments["operation"]]()
        if not math.isfinite(answer):
            raise ValueError("Non-finite result")
        return ToolResult(json.dumps({"result": answer}, allow_nan=False))
    except (ZeroDivisionError, ValueError, OverflowError) as exc:
        return ToolResult(str(exc), is_error=True)
