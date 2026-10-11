"""Focused checkpoint runner; no hidden implementation or automatic paid calls."""
import argparse
import asyncio
import importlib

from common.core.config import load_config


async def check(stage, lesson=None):
    lesson = lesson or {'llm': 1, 'agent': 1, 'cua': 2}[stage]
    package = {1: 'lesson_01_agent', 2: 'lesson_02_computer_use'}[lesson]
    module = importlib.import_module('common.core.llm' if stage == 'llm' else f'{package}.{stage}')
    if stage == "llm":
        response = await module.complete([{"role": "user", "content": "只回答 READY"}], [], load_config())
        assert response.text.strip() == "READY", "请检查 API 返回消息的解析"
    elif stage == "agent":
        from lesson_01_agent.check import run_checks
        await run_checks(module)
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
    parser.add_argument('--lesson', type=int, choices=[1, 2])
    args = parser.parse_args()
    try:
        asyncio.run(check(args.stage, args.lesson))
    except Exception as exc:
        print(f"未通过 · {type(exc).__name__}: {exc}")
        raise SystemExit(1)
