"""TODO 1 — 实现一次 OpenRouter 请求。这里只做一次模型调用，不执行工具。

POST https://openrouter.ai/api/v1/chat/completions
请求: model, messages, tools（有工具时）, max_tokens；Authorization: Bearer ...
返回 ModelReply(message=choices[0].message, usage=usage)。
保留 tool_calls/id 和返回的 reasoning_details（如有）。
messages 中的 image_url 是图片输入，不能整体转成字符串。
使用异步 HTTP 客户端；不要打印 API Key；错误需抛出供 Web 显示。
不同模型支持的生成参数可能不同；例如不支持 temperature 的模型不能强行传入该参数。
"""
from common.core.types import Message, ModelReply, ToolSpec, ExercisePending
from common.core.config import Config


async def complete(messages: list[Message], tools: list[ToolSpec], config: Config) -> ModelReply:
    raise ExercisePending("TODO 1 · 在 lesson_01_llm/llm.py 实现 OpenRouter API 调用。")
