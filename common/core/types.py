"""课程公共接口。学生可以阅读，无需修改。"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Awaitable

Message = dict[str, Any]  # OpenRouter messages; tool_call_id 必须保留


@dataclass
class ToolSpec:
    name: str
    description: str
    parameters: dict[str, Any]

    def api_dict(self) -> dict:
        return {"type": "function", "function": {
            "name": self.name, "description": self.description,
            "parameters": self.parameters,
        }}


@dataclass
class Image:
    data: str  # base64, not a file path
    mime_type: str = "image/png"


@dataclass
class ToolResult:
    text: str = ""
    images: list[Image] = field(default_factory=list)
    is_error: bool = False


@dataclass
class ModelReply:
    message: Message  # preserve assistant tool_calls and provider reasoning metadata
    usage: dict = field(default_factory=dict)

    @property
    def text(self) -> str:
        return self.message.get("content") or ""

    @property
    def tool_calls(self) -> list[dict]:
        return self.message.get("tool_calls") or []


@dataclass
class Event:
    kind: str  # status, assistant, tool_start, tool_end, usage, error
    data: dict = field(default_factory=dict)


@dataclass
class AgentState:
    messages: list[Message] = field(default_factory=list)


@dataclass
class RunContext:
    config: Any
    tools: list[ToolSpec]
    complete: Callable[..., Awaitable[ModelReply]]
    execute: Callable[[str, dict], Awaitable[ToolResult]]
    emit: Callable[[Event], None]
    system_prompt: str


class ExercisePending(NotImplementedError):
    """The web UI displays this as a learning checkpoint instead of a crash."""
