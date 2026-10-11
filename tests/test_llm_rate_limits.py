"""Exercise rate-limit recovery through the real client without paid requests."""
import asyncio
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
import json

import httpx
import pytest

from common.core import llm
from common.core.config import Config
from common.core.types import AgentState, RunContext, ToolResult
from lesson_02_computer_use import agent


def success():
    return httpx.Response(200, json={
        'choices': [{'message': {'role': 'assistant', 'content': 'done'}, 'finish_reason': 'stop'}],
        'usage': {'completion_tokens': 1},
    })


@pytest.fixture
def transport(monkeypatch):
    original = httpx.AsyncClient
    llm._parameters.clear()
    requests, waits = [], []

    async def sleep(delay):
        waits.append(delay)

    monkeypatch.setattr(llm.asyncio, 'sleep', sleep)
    monkeypatch.setattr(llm.random, 'uniform', lambda a, b: 0.5)

    def install(responses):
        def handler(request):
            requests.append(request)
            response = responses.pop(0)
            if isinstance(response, Exception):
                raise response
            return response
        monkeypatch.setattr(httpx, 'AsyncClient', lambda **kwargs: original(
            **kwargs, transport=httpx.MockTransport(handler)))
        return requests, waits

    yield install
    llm._parameters.clear()


CONFIG = Config(base_url='https://compatible.test/v1', api_key='secret-key')
MESSAGES = [{'role': 'user', 'content': 'private prompt'}]


async def test_retry_after_then_backoff_preserves_request_and_usage(transport):
    requests, waits = transport([
        httpx.Response(429, headers={'Retry-After': '3'}),
        httpx.Response(429, headers={'Retry-After': 'invalid'}), success(),
    ])
    reply = await llm.complete(MESSAGES, [], CONFIG)
    assert reply.text == 'done' and reply.usage['completion_tokens'] == 1
    assert waits == [3, 4.5]
    assert len(requests) == 3
    assert len({request.content for request in requests}) == 1
    assert all(request.headers['Authorization'] == 'Bearer secret-key' for request in requests)
    assert MESSAGES == [{'role': 'user', 'content': 'private prompt'}]


async def test_openrouter_catalog_and_body_rate_limit(transport):
    requests, waits = transport([
        httpx.Response(429),
        httpx.Response(200, json={'data': [{'id': CONFIG.model, 'supported_parameters': ['max_tokens']}]}),
        httpx.Response(200, json={'error': {'code': 429, 'message': 'private prompt'}}),
        success(),
    ])
    reply = await llm.complete(MESSAGES, [], Config())
    assert reply.text == 'done' and waits == [2.5, 2.5]
    assert [request.method for request in requests] == ['GET', 'GET', 'POST', 'POST']
    body = json.loads(requests[-1].content)
    assert body['provider']['require_parameters'] and 'temperature' not in body


async def test_retry_exhaustion_is_bounded_and_does_not_echo_response(transport):
    requests, waits = transport([httpx.Response(429, text='secret-key private prompt')] * 4)
    with pytest.raises(RuntimeError, match='限流（429）') as error:
        await llm.complete(MESSAGES, [], CONFIG)
    assert len(requests) == 4 and waits == [2.5, 4.5, 8.5]
    assert 'secret-key' not in str(error.value) and 'private prompt' not in str(error.value)


@pytest.mark.parametrize('delays,expected', [(['86400'], []), (['40', '30'], [40])])
async def test_wait_budget_never_shortens_provider_delay(transport, delays, expected):
    requests, waits = transport([httpx.Response(429, headers={'Retry-After': value}) for value in delays])
    with pytest.raises(RuntimeError, match='429'):
        await llm.complete(MESSAGES, [], CONFIG)
    assert waits == expected and len(requests) == len(delays)


@pytest.mark.parametrize('value', ['broken', '-1', 'NaN', 'inf', '', '1e999'])
def test_invalid_retry_after(value):
    assert llm.retry_after_seconds(value) is None


def test_retry_after_http_date():
    date = format_datetime(datetime.now(timezone.utc) + timedelta(seconds=30), usegmt=True)
    assert 28 <= llm.retry_after_seconds(date) <= 30
    assert llm.retry_after_seconds('0') == 0


@pytest.mark.parametrize('status', [400, 401, 402, 403, 500, 503])
async def test_other_http_errors_are_not_retried(transport, status):
    requests, waits = transport([httpx.Response(status, text='secret-key')])
    with pytest.raises(RuntimeError, match=f'HTTP {status}'):
        await llm.complete(MESSAGES, [], CONFIG)
    assert len(requests) == 1 and not waits


async def test_transport_timeout_is_not_retried(transport):
    requests, waits = transport([httpx.ReadTimeout('timeout')])
    with pytest.raises(httpx.ReadTimeout):
        await llm.complete(MESSAGES, [], CONFIG)
    assert len(requests) == 1 and not waits


async def test_cancel_during_backoff_stops_requests(transport, monkeypatch):
    requests, _ = transport([httpx.Response(429), success()])
    sleeping = asyncio.Event()

    async def sleep(delay):
        sleeping.set()
        await asyncio.Event().wait()

    monkeypatch.setattr(llm.asyncio, 'sleep', sleep)
    task = asyncio.create_task(llm.complete(MESSAGES, [], CONFIG))
    await asyncio.wait_for(sleeping.wait(), timeout=1)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert len(requests) == 1


async def test_retry_does_not_reexecute_completed_tool(transport):
    call = {'id': 'call-1', 'type': 'function', 'function': {'name': 'test', 'arguments': '{}'}}
    requests, waits = transport([
        httpx.Response(200, json={'choices': [{'message': {
            'role': 'assistant', 'content': None, 'tool_calls': [call]}, 'finish_reason': 'tool_calls'}]}),
        httpx.Response(429), success(),
    ])
    executed = []

    async def execute(name, arguments):
        executed.append(name)
        return ToolResult('tool result')

    state = AgentState()
    context = RunContext(CONFIG, [], llm.complete, execute, lambda event: None, 'system')
    await agent.run_turn('hello', state, context)
    assert executed == ['test'] and waits == [2.5]
    assert requests[1].content == requests[2].content
    assert sum(message['role'] == 'tool' for message in state.messages) == 1
    assert state.messages[-1]['content'] == 'done'
