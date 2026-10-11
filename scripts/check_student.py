"""Focused checkpoint runner; no hidden implementation or automatic paid calls."""
import argparse
import asyncio
import json
import importlib

from common.core.config import load_config
from common.core.types import AgentState, ModelReply, RunContext, ToolResult
from common.core.basic_tools import basic_tools, execute_basic


async def check(stage, lesson=None):
    lesson = lesson or {'llm': 1, 'agent': 2, 'cua': 3}[stage]
    package = {1: 'lesson_01_llm', 2: 'lesson_02_agent', 3: 'lesson_03_computer_use'}[lesson]
    module = importlib.import_module(f'{package}.{stage}')
    if stage == "llm":
        response = await module.complete([{"role": "user", "content": "只回答 READY"}], [], load_config())
        assert response.text.strip() == "READY", "请检查 API 返回消息的解析"
    elif stage == "agent":
        requests, events = [], []
        async def fake_model(messages, tools, config):
            requests.append(json.loads(json.dumps(messages)))
            if len(requests) == 1:
                return ModelReply({"role": "assistant", "content": None, "tool_calls": [{
                    "id": "check-1", "type": "function", "function": {
                        "name": "calculate", "arguments": '{"operation":"multiply","a":6,"b":7}'}}]})
            return ModelReply({"role": "assistant", "content": "42"})
        await module.run_turn("计算 6 × 7", AgentState(), RunContext(
            load_config(), basic_tools(), fake_model, execute_basic, events.append, "check"))
        assert len(requests) == 2, "工具执行后需要再次请求模型"
        result = next(m for m in requests[1] if m.get("role") == "tool")
        assert result["tool_call_id"] == "check-1", "工具结果需关联调用 ID"
        assert "42" in result["content"], "工具结果未写回历史"
        assert any(e.kind == "assistant" and e.data["text"] == "42" for e in events)
    else:
        from common.core.mcp_transport import connect_driver
        async with connect_driver(load_config().driver) as session:
            tools = await module.list_tools(session)
            assert any(t.name == "get_window_state" for t in tools)
            result = await module.call_tool(session, "list_windows", {})
            assert isinstance(result, dict) and "content" in result
            assert not result.get("isError"), "Cua 返回错误，请检查系统权限"
    print(f"PASS · {stage}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("stage", choices=["llm", "agent", "cua"])
    parser.add_argument('--lesson', type=int, choices=[1, 2, 3])
    args = parser.parse_args()
    try:
        asyncio.run(check(args.stage, args.lesson))
    except Exception as exc:
        print(f"未通过 · {type(exc).__name__}: {exc}")
        raise SystemExit(1)
