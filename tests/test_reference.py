import asyncio
import base64
import json
from types import SimpleNamespace
import pytest

agent = pytest.importorskip("lesson_02_computer_use.agent")
from common.app.runtime import Runtime
from common.core.config import Config
from common.core.types import AgentState, Event, Image, ModelReply, RunContext, ToolResult
from common.core.basic_tools import basic_tools, execute_basic


def call(id, name, args):
    return {"id": id, "type": "function", "function": {"name": name, "arguments": args}}


async def test_agent_multi_call_errors_images_and_history():
    snapshots, events = [], []
    async def complete(messages, tools, config):
        snapshots.append(json.loads(json.dumps(messages)))
        if len(snapshots) == 1:
            return ModelReply({"role": "assistant", "content": None, "tool_calls": [
                call("bad", "calculate", "INVALID"), call("pic", "observe", "{}")],
                "reasoning_details": [{"type": "test", "data": "preserve"}]})
        return ModelReply({"role": "assistant", "content": "done"})
    async def execute(name, args):
        return ToolResult("observed", [Image(base64.b64encode(b"png").decode())])
    state = AgentState()
    context = RunContext(Config(), [], complete, execute, events.append, "system")
    await agent.run_turn("first", state, context)
    second = snapshots[1]
    assert [m["role"] for m in second] == ["system", "user", "assistant", "tool", "tool", "user"]
    assert second[2]["reasoning_details"]
    assert json.loads(second[3]["content"])["is_error"]
    assert second[3]["tool_call_id"] == "bad"
    assert second[4]["tool_call_id"] == "pic"
    assert second[5]["content"][1]["type"] == "image_url"
    await agent.run_turn("second", state, context)
    assert any(m.get("content") == "first" for m in snapshots[-1])


async def test_max_rounds():
    async def complete(*args):
        return ModelReply({"role": "assistant", "tool_calls": [call("c", "get_current_time", "{}")]})
    events = []
    context = RunContext(Config(max_rounds=2), basic_tools(), complete, execute_basic, events.append, "system")
    await agent.run_turn("time", AgentState(), context)
    assert len([e for e in events if e.kind == "tool_start"]) == 2
    assert events[-1].data["limit"]


async def test_runtime_timeout_no_broken_history(tmp_path):
    async def slow(*args):
        await asyncio.sleep(10)
    rt = Runtime(lesson=1, root=tmp_path)
    rt.module = lambda name: SimpleNamespace(run_turn=agent.run_turn, complete=slow)
    await rt.run("hello", Config(turn_timeout=.03), lambda e: None)
    assert rt.last_record.data["status"] == "timeout"
    assert rt.state.messages == []


async def test_dispatch_rejects_unknown_and_bad_args(tmp_path):
    seen = []
    async def malicious_turn(text, state, ctx):
        seen.append(await ctx.execute("shell", {"command": "ls"}))
        seen.append(await ctx.execute("calculate", {"operation": "divide", "a": 1, "b": 0}))
        seen.append(await ctx.execute("calculate", {"operation": "add", "a": "wrong", "b": 0}))
    rt = Runtime(lesson=1, root=tmp_path)
    rt.module = lambda name: SimpleNamespace(run_turn=malicious_turn, complete=None)
    await rt.run("hello", Config(lesson=1), lambda e: None)
    assert all(r.is_error for r in seen)


def test_calculator_verifier_reads_result_not_expression():
    from scripts.live_verify import calculator_display
    assert calculator_display('- AXStaticText = "‎128‎×‎37"\n- AXStaticText = "‎4,736"') == "4736"
    assert calculator_display('- AXStaticText = "0"') == "0"
    assert calculator_display('no display') is None


def test_model_optional_parameters_follow_catalog():
    from common.core.llm import request_parameters
    config = Config()
    assert request_parameters(config, {'tools', 'max_tokens', 'temperature'}) == {'temperature': 0, 'max_tokens': 2048}
    assert request_parameters(config, {'tools', 'max_tokens'}) == {'max_tokens': 2048}
    assert request_parameters(config, {'tools', 'max_completion_tokens'}) == {'max_completion_tokens': 2048}
