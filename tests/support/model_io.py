"""Test-only model/tool substitutes; exercise the production Agent and HTTP stack."""
import asyncio
from contextlib import asynccontextmanager, contextmanager
from unittest.mock import patch

from common.core.types import ModelReply, ToolResult, ToolSpec


async def complete(messages, tools, config):
    await asyncio.sleep(.03)
    if tools and messages[-1]['role'] != 'tool':
        return ModelReply({'role': 'assistant', 'content': None, 'tool_calls': [{
            'id': 'test-call', 'type': 'function',
            'function': {'name': 'test_echo', 'arguments': '{}'}}]})
    return ModelReply({'role': 'assistant', 'content': '测试回复'})


@asynccontextmanager
async def registry(self, config, editor=None, report=None, *, teaching=False):
    async def execute(name, arguments):
        await asyncio.sleep(.08)
        return ToolResult('测试工具结果')
    yield [ToolSpec('test_echo', '测试工具', {'type': 'object', 'properties': {}})], execute


@contextmanager
def fake_runtime_io():
    with patch('common.core.llm.complete', complete), patch('common.app.runtime.Runtime.registry', registry):
        yield
