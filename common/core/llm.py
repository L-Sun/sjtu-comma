"""教师提供的 LLM 客户端：请求配置的 OpenAI 兼容接口。"""
import httpx
from urllib.parse import urlsplit
from common.core.types import ModelReply

_parameters = {}


async def model_parameters(client, model, base_url="https://openrouter.ai/api/v1"):
    cache_key = (base_url, model)
    if cache_key not in _parameters:
        response = await client.get(base_url.rstrip("/") + "/models")
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
        response = await client.post(base_url + "/chat/completions", json=body, headers=headers)
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
