"""教师提供的 LLM 客户端：请求配置的 OpenAI 兼容接口。"""
import asyncio
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import math
import random

import httpx
from urllib.parse import urlsplit
from common.core.types import ModelReply

_parameters = {}
MAX_REQUEST_RETRIES = 3
MAX_RETRY_WAIT = 60.0


def retry_after_seconds(value):
    """Accept Retry-After seconds or an HTTP date; ignore malformed headers."""
    if value is None:
        return None
    try:
        seconds = float(value)
    except ValueError:
        try:
            when = parsedate_to_datetime(value)
            seconds = (when - datetime.now(timezone.utc)).total_seconds()
        except (TypeError, ValueError, OverflowError):
            return None
    return max(0.0, seconds) if math.isfinite(seconds) and seconds >= 0 else None


def retryable_status(response):
    if response.status_code in (429, 503):
        return response.status_code
    if response.status_code != 200:
        return None
    # Non-streaming providers can report an error after sending HTTP 200.
    try:
        data = response.json()
    except ValueError:
        return None
    error = data.get("error") if isinstance(data, dict) else None
    if isinstance(error, dict):
        for status in (429, 503):
            if error.get("code") in (status, str(status)):
                return status
    return None


async def request_with_retry(client, method, url, **kwargs):
    """Retry explicit 429/503 responses, never the Agent/tool loop."""
    waited = 0.0
    for attempt in range(MAX_REQUEST_RETRIES + 1):
        response = await client.request(method, url, **kwargs)
        status = retryable_status(response)
        if status is None:
            return response
        delay = retry_after_seconds(response.headers.get("Retry-After"))
        if delay is None:
            delay = 2 ** (attempt + 1) + random.uniform(0, 1)
        if attempt == MAX_REQUEST_RETRIES or waited + delay > MAX_RETRY_WAIT:
            # Never echo provider bodies, which may contain prompts or secrets.
            if status == 503:
                raise RuntimeError(
                    "模型服务暂不可用（HTTP 503），已停止自动重试。"
                    "请稍后再试，或切换服务商或模型。"
                )
            raise RuntimeError(
                "模型接口限流（429），已停止自动重试。请稍后再试；"
                "免费模型请检查每日额度，上游限流可切换服务商或模型。"
            )
        # Cancellation and the enclosing turn timeout interrupt this wait.
        await asyncio.sleep(delay)
        waited += delay


async def model_parameters(client, model, base_url="https://openrouter.ai/api/v1"):
    cache_key = (base_url, model)
    if cache_key not in _parameters:
        response = await request_with_retry(client, "GET", base_url.rstrip("/") + "/models")
        response.raise_for_status()
        _parameters.update({(base_url, m["id"]): set(m["supported_parameters"]) for m in response.json()["data"] if "supported_parameters" in m})
    return _parameters.get(cache_key)


def request_parameters(config, supported):
    # Strict provider routing refuses GPT-5.6 when temperature is supplied.
    # Do not silently drop required tools; adapt only optional generation knobs.
    result = {}
    if supported is None or "temperature" in supported:
        result["temperature"] = 0
    token_key = "max_tokens" if supported is None or "max_tokens" in supported else "max_completion_tokens"
    result[token_key] = config.max_tokens
    return result


async def complete(messages, tools, config):
    base_url = config.base_url.rstrip("/")
    openrouter = urlsplit(base_url).hostname == "openrouter.ai"
    body = {"model": config.model, "messages": messages}
    headers = {"Authorization": f"Bearer {config.api_key}"} if config.api_key else {}
    if openrouter:
        body["provider"] = {"require_parameters": True}
        headers["X-OpenRouter-Title"] = "COMMA Classroom"
    if tools:
        body["tools"] = [tool.api_dict() for tool in tools]
        body["tool_choice"] = "auto"
    async with httpx.AsyncClient(timeout=60) as client:
        options = (request_parameters(config, await model_parameters(client, config.model, base_url))
                   if openrouter else {"max_tokens": config.max_tokens})
        body.update(options)
        response = await request_with_retry(
            client, "POST", base_url + "/chat/completions", json=body, headers=headers)
    if response.status_code != 200:
        # Provider response bodies can echo request content; don't print them.
        raise RuntimeError(f"模型接口 HTTP {response.status_code}。检查模型、额度或 API Key。")
    data = response.json()
    if not data.get("choices"):
        raise RuntimeError("模型接口未返回可用的模型消息。")
    choice = data["choices"][0]
    if choice.get("finish_reason") == "length":
        raise RuntimeError("模型输出达到 token 上限，未执行可能不完整的工具调用。")
    if not choice["message"].get("content") and not choice["message"].get("tool_calls"):
        raise RuntimeError("模型返回了空回复，不能视为任务完成。")
    return ModelReply(choice["message"], {**data.get("usage", {}), "request_parameters": options})
